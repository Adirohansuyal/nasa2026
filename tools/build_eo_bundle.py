"""Build the standalone HTML app's Earth Observation data bundle.

Reads the same monthly NetCDF files and district GeoJSON used by Streamlit.
Set EARTHPULSE_PROJECT_ROOT when the research data are stored elsewhere.
"""

import json
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyproj
import xarray as xr
from shapely import contains_xy


app_root = Path(__file__).resolve().parents[1]
project_root = Path(os.environ.get(
    "EARTHPULSE_PROJECT_ROOT",
    Path.home() / "Library/CloudStorage/GoogleDrive-adityasuyal@birlainstitute.co.in/My Drive/EARTHPULSE_X",
))
monthly_dir = project_root / "data/processed/harmonized/monthly"
boundary_path = project_root / "data/raw/boundaries/uttarakhand_13_districts.geojson"
transformer = pyproj.Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
var_names = {
    "lst": ("lst", "Land Surface Temperature", "K"),
    "ndvi": ("ndvi", "Vegetation Index (NDVI)", ""),
    "smap_am": ("smap_am", "Morning Soil Moisture", "m³/m³"),
    "smap_pm": ("smap_pm", "Evening Soil Moisture", "m³/m³"),
    "gpm": ("gpm_monthly_precipitation", "Precipitation", "mm"),
}

files = sorted(monthly_dir.glob("earthpulse_x_*.nc"))
if not files or not boundary_path.exists():
    raise SystemExit(f"Missing monthly NetCDF data or district boundaries under {project_root}")

with xr.open_dataset(files[0]) as ds:
    x = ds.x.values
    y = ds.y.values
    xx, yy = np.meshgrid(x, y)
    lon, lat = transformer.transform(xx, yy)

boundaries = gpd.read_file(boundary_path)
if boundaries.crs and str(boundaries.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
    boundaries = boundaries.to_crs("EPSG:4326")
study_area = boundaries.geometry.union_all()
inside = contains_xy(study_area, lon, lat)

bundle = {
    "months": [],
    "lon": lon[0].round(6).tolist(),
    "lat": lat[:, 0].round(6).tolist(),
    "inside": inside.astype(int).ravel().tolist(),
    "shape": list(inside.shape),
    "districts": json.loads(boundaries.to_json()),
    "outline": json.loads(gpd.GeoSeries([study_area], crs="EPSG:4326").to_json())["features"][0]["geometry"],
    "variables": {key: {"label": label, "unit": unit, "strict": [], "relaxed": [], "gpm": []}
                  for key, (_, label, unit) in var_names.items()},
}

for path in files:
    month = path.stem.removeprefix("earthpulse_x_").replace("_", "-")
    bundle["months"].append(month)
    with xr.open_dataset(path) as ds:
        for key, (source, _, _) in var_names.items():
            qualities = ("gpm",) if key == "gpm" else ("strict", "relaxed")
            for quality in qualities:
                name = source if quality == "gpm" else f"{source}_{quality}"
                valid_name = f"{name}_valid"
                values = ds[name].values.astype(float)
                valid = ds[valid_name].values == 1 if valid_name in ds else np.isfinite(values)
                valid &= inside & np.isfinite(values)
                payload = [float(value) if keep else None
                           for value, keep in zip(values.round(4).ravel(), valid.ravel())]
                bundle["variables"][key][quality].append(payload)

out = app_root / "assets/eo_observation_data.js"
out.write_text("window.EO_REAL_DATA=" + json.dumps(bundle, separators=(",", ":"), allow_nan=False) + ";\n")
print(f"Wrote {out} ({out.stat().st_size / 1024 / 1024:.2f} MiB)")
