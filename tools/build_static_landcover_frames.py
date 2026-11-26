"""Build pre-colored, CDN-ready WebP frames for every district and class.

Run from the repository root with research/.venv/bin/python. The browser only
preloads and displays these images; it does not decode or recolor raster data.
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
CLASS_COLORS = [
    "#005A9C", "#006B3C", "#A6BF00", "#8C4FA3", "#D88700",
    "#88532D", "#C13728", "#777777", "#A4CFE3",
]
PALETTE = [
    tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
    for color in CLASS_COLORS
] + [(236, 0, 140), (0, 214, 107), (0, 207, 255)]


def slug(value: str) -> str:
    return "-".join(value.lower().split())


def rgba_for_frame(current: np.ndarray, previous: np.ndarray | None, class_index: int) -> np.ndarray:
    display = np.where(current < 9, current, 255).astype(np.uint8)
    if previous is None:
        display[current == class_index] = 9
    else:
        valid = (current < 9) & (previous < 9)
        selected_now = current == class_index
        selected_before = previous == class_index
        display[valid & selected_now & selected_before] = 9
        display[valid & selected_now & ~selected_before] = 10
        display[valid & ~selected_now & selected_before] = 11

    rgba = np.zeros((*display.shape, 4), dtype=np.uint8)
    for code, color in enumerate(PALETTE):
        selected = display == code
        rgba[selected, :3] = color
        rgba[selected, 3] = 255
    return rgba


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
        labels_by_year = []
        bounds_by_year = {}
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
                labels_by_year.append(labels)
                west, south, east, north = transform_bounds(
                    source.crs,
                    "EPSG:4326",
                    *rasterio.transform.array_bounds(labels.shape[0], labels.shape[1], transform),
                )
                bounds_by_year[str(year)] = [[south, west], [north, east]]

        classes = {}
        for class_index in range(9):
            class_dir = district_dir / str(class_index)
            class_dir.mkdir()
            class_frames = {}
            for index, year in enumerate(YEARS):
                current = labels_by_year[index]
                previous = labels_by_year[index - 1] if index else None
                rgba = rgba_for_frame(current, previous, class_index)
                image = Image.fromarray(rgba)
                image.thumbnail((1200, 1200), Image.Resampling.NEAREST)
                file_name = f"{class_index}/{year}.webp"
                image.save(
                    district_dir / file_name,
                    format="WEBP",
                    lossless=True,
                    quality=100,
                    method=4,
                )
                class_frames[str(year)] = {
                    "file": file_name,
                    "bounds": bounds_by_year[str(year)],
                }
            classes[str(class_index)] = class_frames
            print(f"{district}: class {class_index + 1}/9 ready", flush=True)

        manifest = {"district": district, "years": YEARS, "classes": classes}
        (district_dir / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
        size_mib = sum(path.stat().st_size for path in district_dir.rglob("*") if path.is_file()) / 1024 / 1024
        print(f"{district}: {size_mib:.1f} MiB total", flush=True)


if __name__ == "__main__":
    main()
