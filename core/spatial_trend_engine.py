"""District-scale trend analysis from the harmonized monthly Earth data."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from scipy import stats
from shapely.geometry import Point

from core.trend_engine import apply_fdr_correction, modified_mann_kendall


VARIABLES = {
    "LST": {"strict": "lst_strict", "relaxed": "lst_relaxed", "unit": "K"},
    "NDVI": {"strict": "ndvi_strict", "relaxed": "ndvi_relaxed", "unit": "index"},
    "SMAP_AM": {"strict": "smap_am_strict", "relaxed": "smap_am_relaxed", "unit": "m³/m³"},
    "SMAP_PM": {"strict": "smap_pm_strict", "relaxed": "smap_pm_relaxed", "unit": "m³/m³"},
    "GPM": {"strict": "gpm_monthly_precipitation", "relaxed": "gpm_monthly_precipitation", "unit": "mm/month"},
}


def build_district_monthly_series(monthly_files: list[str], boundary_file: str) -> pd.DataFrame:
    """Area-average each valid monthly grid inside every district polygon."""
    if not monthly_files:
        raise FileNotFoundError("No harmonized monthly grids were found.")

    boundaries = gpd.read_file(boundary_file).to_crs("EPSG:6933")
    with xr.open_dataset(monthly_files[0], engine="netcdf4") as first:
        xx, yy = np.meshgrid(first["x"].values, first["y"].values)
        grid_shape = xx.shape

    points = gpd.GeoDataFrame(
        {"cell": np.arange(xx.size)},
        geometry=[Point(x, y) for x, y in zip(xx.ravel(), yy.ravel())],
        crs="EPSG:6933",
    )
    joined = gpd.sjoin(
        points,
        boundaries[["district_name", "geometry"]],
        how="left",
        predicate="within",
    ).drop_duplicates("cell")
    cell_district = joined.set_index("cell")["district_name"].reindex(range(xx.size))
    districts = sorted(boundaries["district_name"].dropna().unique())
    district_masks = {
        district: (cell_district.to_numpy() == district).reshape(grid_shape)
        for district in districts
    }

    records = []
    for file_path in sorted(monthly_files):
        with xr.open_dataset(file_path, engine="netcdf4") as dataset:
            month = pd.to_datetime(dataset.attrs.get("month", Path(file_path).stem[-7:].replace("_", "-")))
            for variable, config in VARIABLES.items():
                data_name = config["strict"]
                if data_name not in dataset:
                    continue
                values = np.asarray(dataset[data_name].values, dtype=float)
                valid_name = f"{data_name}_valid"
                valid = np.asarray(dataset[valid_name].values) == 1 if valid_name in dataset else np.isfinite(values)
                valid &= np.isfinite(values)

                for district, district_mask in district_masks.items():
                    district_cells = int(district_mask.sum())
                    cell_values = values[district_mask & valid]
                    records.append({
                        "month": month,
                        "district_name": district,
                        "variable": variable,
                        "value": float(cell_values.mean()) if cell_values.size else np.nan,
                        "valid_cells": int(cell_values.size),
                        "district_cells": district_cells,
                        "coverage_pct": 100.0 * cell_values.size / district_cells if district_cells else np.nan,
                    })

    result = pd.DataFrame(records)
    if result.empty:
        raise ValueError("The monthly grids did not contain any district-level values.")
    return result.sort_values(["district_name", "variable", "month"]).reset_index(drop=True)


def calculate_district_trends(monthly_series: pd.DataFrame) -> pd.DataFrame:
    """Estimate seasonally adjusted district trends and FDR-correct 65 tests."""
    results = []
    for (district, variable), group in monthly_series.groupby(["district_name", "variable"]):
        work = group[["month", "value", "coverage_pct"]].dropna(subset=["value"]).sort_values("month").copy()
        n = len(work)
        row = {
            "district_name": district,
            "variable": variable,
            "valid_months": n,
            "mean_coverage_pct": float(work["coverage_pct"].mean()) if n else np.nan,
            "trend_per_year": np.nan,
            "slope_ci_low_per_year": np.nan,
            "slope_ci_high_per_year": np.nan,
            "tau": np.nan,
            "p_value": 1.0,
            "q_value": 1.0,
            "lag1_autocorrelation": np.nan,
            "significant": False,
            "direction": "insufficient data",
        }
        if n >= 48:
            month_number = work["month"].dt.month
            seasonal_mean = work.groupby(month_number)["value"].transform("mean")
            anomalies = work["value"].to_numpy(dtype=float) - seasonal_mean.to_numpy(dtype=float)
            x = (work["month"].dt.year.to_numpy() * 12 + work["month"].dt.month.to_numpy()).astype(float)
            mk = modified_mann_kendall(pd.Series(anomalies))
            sen = stats.theilslopes(anomalies, x, alpha=0.95)
            row.update({
                "trend_per_year": float(sen.slope * 12),
                "slope_ci_low_per_year": float(sen.low_slope * 12),
                "slope_ci_high_per_year": float(sen.high_slope * 12),
                "tau": float(mk["tau"]),
                "p_value": float(mk["p_value"]),
                "lag1_autocorrelation": float(mk["lag1_autocorrelation"]),
            })
        results.append(row)

    report = pd.DataFrame(results)
    report["q_value"] = apply_fdr_correction(report["p_value"].tolist())
    enough_data = report["valid_months"] >= 48
    report["significant"] = enough_data & (report["q_value"] < 0.05)
    report["direction"] = np.select(
        [report["significant"] & (report["tau"] > 0), report["significant"] & (report["tau"] < 0)],
        ["increasing", "decreasing"],
        default=np.where(enough_data, "no significant trend", "insufficient data"),
    )
    return report.sort_values(["variable", "trend_per_year"], ascending=[True, False]).reset_index(drop=True)
