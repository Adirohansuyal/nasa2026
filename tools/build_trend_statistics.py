"""Export Streamlit's precomputed regional trend report for the static website."""

import csv
import json
import os
from pathlib import Path

app_root = Path(__file__).resolve().parents[1]
project_root = Path(os.environ.get(
    "EARTHPULSE_PROJECT_ROOT",
    Path.home() / "Library/CloudStorage/GoogleDrive-adityasuyal@birlainstitute.co.in/My Drive/EARTHPULSE_X",
))
source = project_root / "data/metadata/earthpulse_x_autocorrelation_adjusted_trends.csv"
if not source.exists():
    raise SystemExit(f"Trend results not found: {source}")

fields = (
    "modified_mk_trend", "modified_mk_tau", "modified_mk_p_value",
    "fdr_adjusted_p_value_modified", "fdr_significant", "trend_slope_per_year",
    "lag1_autocorrelation", "valid_months",
)
with source.open(newline="", encoding="utf-8") as stream:
    rows = csv.DictReader(stream)
    result = {}
    for row in rows:
        item = {}
        for field in fields:
            value = row[field]
            if field == "modified_mk_trend":
                item[field] = value
            elif field == "fdr_significant":
                item[field] = value.strip().lower() == "true"
            elif field == "valid_months":
                item[field] = int(value)
            else:
                item[field] = float(value)
        result[row["variable"].lower()] = item

target = app_root / "assets/trend_regional_stats.js"
target.write_text(
    "window.EP_TREND_REGIONAL_STATS="
    + json.dumps(result, separators=(",", ":"), allow_nan=False)
    + ";\n",
    encoding="utf-8",
)
print(f"Wrote {target}")
