"""Build compact, CDN-ready annual label frames for the Land Cover timeline.

Run from the repository root with research/.venv/bin/python. The generated
grayscale PNGs contain Dynamic World class IDs (0–8) and 255 for no-data; the
browser applies the selected class colors and transition colors.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.mask import mask
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "research" / "data" / "dynamic_world_maps"
OUTPUT_DIR = ROOT / "assets" / "landcover_frames"
YEARS = list(range(2015, 2026))


def slug(value: str) -> str:
    return "-".join(value.lower().split())


def main() -> None:
    collection = json.loads((SOURCE_DIR / "districts.geojson").read_text())
    features = collection["features"]
    districts = [("Uttarakhand", mapping(unary_union([shape(f["geometry"]) for f in features])))]
    districts.extend(
        (feature["properties"]["GAUL2_NAME"], feature["geometry"])
        for feature in features
    )

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    for district, geometry in districts:
        district_dir = OUTPUT_DIR / slug(district)
        district_dir.mkdir()
        frames = {}
        projected_geometry = None

        for year in YEARS:
            raster_path = SOURCE_DIR / f"dynamic_world_label_{year}.tif"
            with rasterio.open(raster_path) as source:
                if projected_geometry is None:
                    projected_geometry = transform_geom("EPSG:4326", source.crs, geometry)
                cropped, transform = mask(
                    source, [projected_geometry], crop=True, filled=True, nodata=255
                )
                labels = np.where(cropped[0] < 9, cropped[0], 255).astype(np.uint8)
                png_path = district_dir / f"{year}.png"
                Image.fromarray(labels).save(png_path, format="PNG", optimize=True)
                west, south, east, north = transform_bounds(
                    source.crs,
                    "EPSG:4326",
                    *rasterio.transform.array_bounds(labels.shape[0], labels.shape[1], transform),
                )
                frames[str(year)] = {
                    "file": f"{year}.png",
                    "bounds": [[south, west], [north, east]],
                }

        manifest = {"district": district, "years": YEARS, "frames": frames}
        (district_dir / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
        print(f"{district}: {sum(p.stat().st_size for p in district_dir.iterdir()) / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
