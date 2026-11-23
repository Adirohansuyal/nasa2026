
import os
from pathlib import Path

# Application root
APP_ROOT = Path(__file__).resolve().parent

# Google Drive research project
PROJECT_ROOT = Path(
    os.getenv(
        "EARTHPULSE_PROJECT_ROOT",
        str(
            Path.home()
            / "Library/CloudStorage"
            / "GoogleDrive-adityasuyal@birlainstitute.co.in"
            / "My Drive/EARTHPULSE_X"
        )
    )
)

# Research directories
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MONTHLY_DATA_DIR = (
    PROCESSED_DIR / "harmonized" / "monthly"
)

METADATA_DIR = DATA_DIR / "metadata"
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
REPORTS_DIR = PROJECT_ROOT / "reports"
BOUNDARIES_DIR = DATA_DIR / "raw" / "boundaries"

# Application settings
APP_NAME = "EARTHPULSE-X"
APP_VERSION = "1.0.0"
STUDY_REGION = "Uttarakhand, India"
ANALYSIS_START = "2015-04-01"
ANALYSIS_END = "2025-09-30"

# Important result files
REGIONAL_TIMESERIES = (
    METADATA_DIR / "earthpulse_x_regional_monthly_timeseries.csv"
)

INTERACTION_RESULTS = (
    RESULTS_DIR / "earthpulse_x_integrated_interaction_analysis.csv"
)

DISTRICT_RESULTS = (
    RESULTS_DIR / "earthpulse_x_aug2025_gpm_district_intelligence.csv"
)

# Pre-computed trend results (autocorrelation-adjusted)
TREND_RESULTS = (
    METADATA_DIR / "earthpulse_x_autocorrelation_adjusted_trends.csv"
)

TREND_RESULTS_JSON = (
    METADATA_DIR / "earthpulse_x_autocorrelation_adjusted_trends.json"
)

# Monthly seasonal anomalies (all variables, 126 months)
SEASONAL_ANOMALIES = (
    METADATA_DIR / "earthpulse_x_monthly_seasonal_anomalies.csv"
)

# Spatial multi-variable anomaly events (pixel-level, 50K records)
SPATIAL_ANOMALY_EVENTS = (
    RESULTS_DIR / "earthpulse_x_spatial_isolation_forest_events.csv"
)

# Pixel-scale robust anomaly events and precomputed connected-component clusters.
PIXEL_ANOMALY_EVENTS = (
    METADATA_DIR / "earthpulse_x_pixel_anomaly_events.csv"
)
SPATIAL_CLUSTER_RESULTS = (
    METADATA_DIR / "earthpulse_x_spatial_anomaly_clusters.csv"
)
SPATIAL_CLUSTER_MONTHLY_SUMMARY = (
    METADATA_DIR / "earthpulse_x_spatial_cluster_monthly_summary.csv"
)

# Verify project directory
if not PROJECT_ROOT.exists():
    raise FileNotFoundError(
        f"EARTHPULSE_X research directory not found: {PROJECT_ROOT}"
    )
