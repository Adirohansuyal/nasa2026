"""Export Streamlit's multi-hazard anomaly outputs for the standalone HTML UI."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import DISTRICT_RESULTS, SEASONAL_ANOMALIES, SPATIAL_ANOMALY_EVENTS, BOUNDARIES_DIR
from core.early_warning_engine import (
    HAZARD_CATALOGUE,
    VAR_META,
    chamoli_2021_validation,
    compute_district_risk_from_spatial,
    compute_monthly_alerts,
    district_hazard_breakdown,
    hazard_frequency_summary,
)

OUTPUT = ROOT / "assets" / "anomaly_data.js"


def clean(value):
    if isinstance(value, pd.Series):
        return clean(value.to_dict())
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def records(frame):
    return clean(frame.replace({np.nan: None}).to_dict("records"))


def main():
    anomaly = pd.read_csv(SEASONAL_ANOMALIES)
    anomaly["month"] = pd.to_datetime(anomaly["month"])
    spatial = pd.read_csv(SPATIAL_ANOMALY_EVENTS)
    boundary_path = BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"
    boundaries = gpd.read_file(boundary_path, engine="pyogrio")

    monthly = compute_monthly_alerts(anomaly)
    frequency = hazard_frequency_summary(monthly)
    district_hazards = district_hazard_breakdown(monthly, spatial, boundaries_gdf=boundaries)
    overall = compute_district_risk_from_spatial(spatial, boundaries_gdf=boundaries, threshold=3.0)

    geo = boundaries.to_crs("EPSG:4326").copy()
    geo["geometry"] = geo.geometry.simplify(0.004, preserve_topology=True)
    geometry = json.loads(geo[["district_name", "geometry"]].to_json())

    alert_fields = ["month", "year", "month_number", "active_alerts", "max_alert_level",
                    "primary_hazard", "alert_message", "LST_z", "LST_alert", "NDVI_z",
                    "NDVI_alert", "SMAP_AM_z", "SMAP_AM_alert", "SMAP_PM_z", "SMAP_PM_alert",
                    "GPM_z", "GPM_alert", "hazards"]
    monthly_rows = records(monthly[alert_fields])
    hazard_rows = {key: records(frame) for key, frame in district_hazards.items()}
    frequency_lookup = {str(row.hazard_type): int(row.months_triggered) for row in frequency.itertuples()}
    catalog = {}
    for key, meta in HAZARD_CATALOGUE.items():
        catalog[key] = {**meta, "variableMeta": VAR_META,
                        "monthsTriggered": frequency_lookup.get(key, 0)}

    legacy = []
    if DISTRICT_RESULTS.exists():
        district_frame = pd.read_csv(DISTRICT_RESULTS)
        legacy = records(district_frame)

    data = clean({
        "source": "EARTHPULSE-X Streamlit anomaly engine · NASA satellite record Apr 2015–Sep 2025",
        "recordStart": monthly["month"].min(),
        "recordEnd": monthly["month"].max(),
        "spatialEventCount": int(len(spatial)),
        "districtCount": int(boundaries["district_name"].nunique()),
        "hazards": catalog,
        "frequency": records(frequency),
        "monthlyAlerts": monthly_rows,
        "districtHazards": hazard_rows,
        "districtGeo": geometry,
        "overallRisk": records(overall),
        "legacyGpmAug2025": legacy,
        "chamoliValidation": clean(chamoli_2021_validation(monthly, spatial)),
    })
    OUTPUT.write_text("window.ANOMALY_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    print(f"Hazard groups: {len(hazard_rows)} · months: {len(monthly_rows)} · districts: {data['districtCount']} · pixel events: {len(spatial):,}")


if __name__ == "__main__":
    main()
