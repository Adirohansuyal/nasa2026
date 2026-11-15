"""Export the current research data and six-month model outputs for index.html."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from config import REGIONAL_TIMESERIES, MONTHLY_DATA_DIR, BOUNDARIES_DIR, SPATIAL_ANOMALY_EVENTS
from core.forecast_engine import run_all_forecasts, select_model_config, SeasonalARModel
from core.lagged_dynamics import prepare_anomaly_matrix, fit_ridge_var, granger_screen
from core.spatial_trend_engine import build_district_monthly_series
from core.early_warning_engine import compute_district_risk_from_spatial
import geopandas as gpd
from pyproj import Transformer

OUT = ROOT / "assets" / "predictive_data.js"
CONFIG = {
    "LST": {"col": "lst_strict_mean", "label": "Land Surface Temperature", "unit": "K", "emoji": "🌡️"},
    "NDVI": {"col": "ndvi_strict_mean", "label": "Vegetation Greenness", "unit": "index", "emoji": "🌿"},
    "SMAP_AM": {"col": "smap_am_strict_mean", "label": "Morning Soil Moisture", "unit": "m³/m³", "emoji": "💧"},
    "SMAP_PM": {"col": "smap_pm_strict_mean", "label": "Evening Soil Moisture", "unit": "m³/m³", "emoji": "💧"},
    "GPM": {"col": "gpm_monthly_precipitation_mean", "label": "Precipitation", "unit": "mm/mo", "emoji": "🌧️"},
}


def clean(value):
    if isinstance(value, pd.Series):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if k != "model"}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.ndarray,)):
        return clean(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def main():
    frame = pd.read_csv(REGIONAL_TIMESERIES)
    frame["date"] = pd.to_datetime(frame["month"], format="%Y-%m")
    print("Fitting regional satellite forecasts for horizons 1–6 months…", flush=True)
    forecast_runs = {}
    forecasts = {}
    for horizon in range(1, 7):
        print(f"  Horizon {horizon}/6…", flush=True)
        forecasts = run_all_forecasts(frame, "date", CONFIG, h=horizon, run_cv=True)
        forecast_runs[str(horizon)] = {}
        for key, result in forecasts.items():
            forecast_runs[str(horizon)][key] = {"error": result["error"]} if "error" in result else {
                "forecastDates": clean(result["forecast_dates"]), "point": clean(result["point"]),
                "lower80": clean(result["lower_80"]), "upper80": clean(result["upper_80"]),
                "lower95": clean(result["lower_95"]), "upper95": clean(result["upper_95"]),
                "cv": clean(result.get("cv_metrics", {})), "modelConfig": clean(result.get("model_config", {})),
            }
    regional = {}
    for key, result in forecasts.items():
        if "error" in result:
            regional[key] = {"error": result["error"]}
            continue
        regional[key] = {
            "label": CONFIG[key]["label"], "unit": CONFIG[key]["unit"], "emoji": CONFIG[key]["emoji"],
            "dates": clean(result["historical_dates"]), "values": clean(result["historical_values"]),
            "fitted": clean(result["in_sample_fitted"]), "forecastDates": clean(result["forecast_dates"]),
            "point": clean(result["point"]), "lower80": clean(result["lower_80"]), "upper80": clean(result["upper_80"]),
            "lower95": clean(result["lower_95"]), "upper95": clean(result["upper_95"]),
            "cv": clean(result.get("cv_metrics", {})), "modelConfig": clean(result.get("model_config", {})),
        }
        regional[key]["runs"] = {h: forecast_runs[h][key] for h in forecast_runs if key in forecast_runs[h]}
    columns = {key: meta["col"] for key, meta in CONFIG.items() if key in regional and "error" not in regional[key]}
    anomaly, scales, seasonal_means = prepare_anomaly_matrix(frame, "date", columns)
    dynamics = {"keys": list(anomaly.columns), "scales": clean(scales), "seasonalMeans": clean(seasonal_means), "models": {}}
    z = anomaly.to_numpy(dtype=float)
    dynamics["zHistory"] = clean(z)
    for lags in (1, 2, 3):
        print(f"Fitting {lags}-month lag links…", flush=True)
        model = fit_ridge_var(z, lags=lags, alpha=1.0)
        links = granger_screen(z, list(anomaly.columns), lags=lags)
        dynamics["models"][str(lags)] = {
            "coefficients": clean(model["coefficients"]),
            "links": clean(links[["source", "target", "f_stat", "p_value", "q_value"]].to_dict("records")),
        }
    print("Building district outlooks and compact anomaly-pixel bundle…", flush=True)
    boundary_path = BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"
    boundaries = gpd.read_file(boundary_path).to_crs("EPSG:4326")
    simplified = boundaries.copy()
    simplified["geometry"] = simplified.geometry.simplify(0.006, preserve_topology=True)
    geo = json.loads(simplified[["district_name", "geometry"]].to_json())
    spatial = pd.read_csv(SPATIAL_ANOMALY_EVENTS)
    historic = compute_district_risk_from_spatial(spatial, month_filter=None, boundaries_gdf=boundaries, threshold=3.0)
    if not historic.empty:
        historic["exposureRank"] = historic["risk_score"].rank(method="average", pct=True) * 100
    hist_lookup = {str(row.district_name): float(row.exposureRank) for row in historic.itertuples()} if not historic.empty else {}
    district_monthly = build_district_monthly_series(
        sorted(str(path) for path in MONTHLY_DATA_DIR.glob("earthpulse_x_*.nc")), str(boundary_path)
    )
    district_fc = {}
    for (district, variable), group in district_monthly.groupby(["district_name", "variable"]):
        if variable not in {"LST", "NDVI", "SMAP_AM", "GPM"}:
            continue
        series = group.dropna(subset=["value"]).sort_values("month").reset_index(drop=True)
        if len(series) < 60:
            continue
        values = series["value"].to_numpy(dtype=float)
        dates = pd.to_datetime(series["month"])
        months = dates.dt.month.to_numpy(dtype=int)
        config = select_model_config(values, months, h=6, min_train=60, n_splits=4)
        model = SeasonalARModel(**config, n_bootstrap=0).fit(values, months)
        point = model._single_forecast_path(6)
        seasonal_mean = series.assign(month_number=months).groupby("month_number")["value"].mean()
        seasonal_std = series.assign(month_number=months).groupby("month_number")["value"].std(ddof=1)
        last_date = dates.iloc[-1]
        district_fc.setdefault(district, {})[variable] = []
        for step, value in enumerate(point):
            forecast_date = last_date + pd.DateOffset(months=step + 1)
            mean = float(seasonal_mean.get(forecast_date.month, np.nan))
            std = float(seasonal_std.get(forecast_date.month, np.nan))
            district_fc[district][variable].append({
                "date": clean(forecast_date), "value": float(value),
                "anomalyZ": float((value - mean) / std) if np.isfinite(std) and std > 1e-12 else 0.0,
                "validMonths": int(len(series)), "coverage": float(series["coverage_pct"].mean()),
            })
    transformer = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
    event_columns = ["month", "row", "column", "x_epsg6933", "y_epsg6933", "LST_robust_z", "NDVI_robust_z", "SMAP_AM_robust_z", "SMAP_PM_robust_z", "GPM_robust_z"]
    events = spatial[event_columns].copy()
    events["lon"], events["lat"] = transformer.transform(events["x_epsg6933"].to_numpy(), events["y_epsg6933"].to_numpy())
    for col in events.select_dtypes(include=[np.number]).columns:
        events[col] = events[col].round(1 if col in ("x_epsg6933", "y_epsg6933") else 3)
    district_data = {
        "geo": geo,
        "exposureRank": hist_lookup,
        "forecasts": district_fc,
        "events": clean(events.to_dict("records")),
        "gridDegrees": clean(float(np.median(np.diff(np.sort(events["lon"].unique()))))),
    }
    bundle = {
        "source": "NASA satellite monthly regional record · Apr 2015–Sep 2025",
        "lastObserved": clean(frame["date"].max()),
        "months": clean(frame["date"]), "regional": regional, "forecastRuns": forecast_runs, "dynamics": dynamics, "districts": district_data,
    }
    OUT.write_text("window.PREDICTIVE_DATA=" + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
