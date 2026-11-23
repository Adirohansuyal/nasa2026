
import pandas as pd
import xarray as xr
import geopandas as gpd
import streamlit as st

from pathlib import Path

from config import (
    MONTHLY_DATA_DIR,
    REGIONAL_TIMESERIES,
    INTERACTION_RESULTS,
    DISTRICT_RESULTS,
    TREND_RESULTS,
    SEASONAL_ANOMALIES,
    SPATIAL_ANOMALY_EVENTS,
    PIXEL_ANOMALY_EVENTS,
    SPATIAL_CLUSTER_RESULTS,
    SPATIAL_CLUSTER_MONTHLY_SUMMARY,
    BOUNDARIES_DIR,
)


# -----------------------------------------
# 1. Regional monthly time-series
# -----------------------------------------

@st.cache_data
def load_regional_timeseries():
    if not REGIONAL_TIMESERIES.exists():
        raise FileNotFoundError(
            f"Regional time-series not found: {REGIONAL_TIMESERIES}"
        )

    df = pd.read_csv(REGIONAL_TIMESERIES)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df


# -----------------------------------------
# 2. Interaction analysis results
# -----------------------------------------

@st.cache_data
def load_interaction_results():
    if not INTERACTION_RESULTS.exists():
        raise FileNotFoundError(
            f"Interaction results not found: {INTERACTION_RESULTS}"
        )

    return pd.read_csv(INTERACTION_RESULTS)


# -----------------------------------------
# 3. District intelligence results
# -----------------------------------------

@st.cache_data
def load_district_results():
    if not DISTRICT_RESULTS.exists():
        raise FileNotFoundError(
            f"District results not found: {DISTRICT_RESULTS}"
        )

    return pd.read_csv(DISTRICT_RESULTS)


# -----------------------------------------
# 4. Discover monthly NetCDF files
# -----------------------------------------

@st.cache_data
def get_monthly_files():
    if not MONTHLY_DATA_DIR.exists():
        raise FileNotFoundError(
            f"Monthly data directory not found: {MONTHLY_DATA_DIR}"
        )

    files = sorted(MONTHLY_DATA_DIR.glob("earthpulse_x_*.nc"))

    if not files:
        raise FileNotFoundError(
            "No monthly NetCDF files found."
        )

    return [str(file) for file in files]


# -----------------------------------------
# 5. Load individual NetCDF file
# -----------------------------------------

@st.cache_resource
def load_monthly_dataset(file_path):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(path)

    return xr.open_dataset(path)


# -----------------------------------------
# 6. Uttarakhand district boundaries
# -----------------------------------------

@st.cache_data
def load_district_boundaries():
    boundary_file = (
        BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"
    )

    if not boundary_file.exists():
        raise FileNotFoundError(
            f"District boundary file not found: {boundary_file}"
        )

    return gpd.read_file(boundary_file, engine="pyogrio")


# -----------------------------------------
# 8. Pre-computed autocorrelation-adjusted trend results
# -----------------------------------------

@st.cache_data
def load_trend_results():
    if not TREND_RESULTS.exists():
        raise FileNotFoundError(
            f"Trend results not found: {TREND_RESULTS}"
        )
    return pd.read_csv(TREND_RESULTS)


# -----------------------------------------
# 9. Monthly seasonal anomalies (all variables)
# -----------------------------------------

@st.cache_data
def load_seasonal_anomalies():
    if not SEASONAL_ANOMALIES.exists():
        raise FileNotFoundError(
            f"Seasonal anomalies not found: {SEASONAL_ANOMALIES}"
        )
    df = pd.read_csv(SEASONAL_ANOMALIES)
    df["date"] = pd.to_datetime(df["month"])
    return df


# -----------------------------------------
# 10. Spatial pixel-level anomaly events
# -----------------------------------------

@st.cache_data
def load_spatial_anomaly_events():
    if not SPATIAL_ANOMALY_EVENTS.exists():
        raise FileNotFoundError(
            f"Spatial anomaly events not found: {SPATIAL_ANOMALY_EVENTS}"
        )
    df = pd.read_csv(SPATIAL_ANOMALY_EVENTS)
    df["date"] = pd.to_datetime(df["month"])
    return df


@st.cache_data
def load_pixel_anomaly_events():
    """Load thresholded pixel anomalies used by the spatial cluster analysis."""
    if not PIXEL_ANOMALY_EVENTS.exists():
        raise FileNotFoundError(f"Pixel anomaly events not found: {PIXEL_ANOMALY_EVENTS}")
    df = pd.read_csv(PIXEL_ANOMALY_EVENTS)
    df["date"] = pd.to_datetime(df["month"], errors="coerce")
    return df


@st.cache_data
def load_spatial_cluster_results():
    """Load the validated per-month, per-signal connected-component summary."""
    if not SPATIAL_CLUSTER_RESULTS.exists():
        raise FileNotFoundError(f"Spatial cluster summary not found: {SPATIAL_CLUSTER_RESULTS}")
    return pd.read_csv(SPATIAL_CLUSTER_RESULTS)


@st.cache_data
def load_spatial_cluster_monthly_summary():
    """Load monthly counts of spatial anomaly clusters and clustered pixels."""
    if not SPATIAL_CLUSTER_MONTHLY_SUMMARY.exists():
        raise FileNotFoundError(
            f"Monthly spatial cluster summary not found: {SPATIAL_CLUSTER_MONTHLY_SUMMARY}"
        )
    return pd.read_csv(SPATIAL_CLUSTER_MONTHLY_SUMMARY)

def get_data_status():

    boundary_file = (
        BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"
    )

    return {
        "monthly_files": len(get_monthly_files()),
        "regional_timeseries": REGIONAL_TIMESERIES.exists(),
        "interaction_results": INTERACTION_RESULTS.exists(),
        "district_results": DISTRICT_RESULTS.exists(),
        "district_boundaries": boundary_file.exists(),
    }
