"""Download compact annual Dynamic World label rasters for offline map rendering.

Run once with the project's authenticated Earth Engine account. Raster maps are
written under data/dynamic_world_maps/ and are not committed to git.
"""

from __future__ import annotations

import json
import math
from contextlib import ExitStack
import warnings
from pathlib import Path

import ee
import requests
import rasterio
from rasterio.merge import merge

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "dynamic_world_maps"
PROJECT = "gen-lang-client-0039569301"
YEARS = range(2015, 2026)
SCALE_METERS = 100
CRS = "EPSG:32644"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Your project has exceeded its noncommercial compute quota.*")
        ee.Initialize(project=PROJECT)
    ee.data.setDeadline(600000)

    districts = (
        ee.FeatureCollection("FAO/GAUL/2025/level2")
        .filter(ee.Filter.eq("GAUL0_NAME", "India"))
        .filter(ee.Filter.eq("GAUL1_NAME", "Uttarakhand"))
    )
    feature_data = districts.getInfo()["features"]
    if len(feature_data) != 13:
        raise RuntimeError(f"Expected 13 Uttarakhand districts, found {len(feature_data)}")
    (OUT / "districts.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feature_data}))

    region = districts.geometry()
    ring = region.bounds(maxError=100, proj=ee.Projection(CRS)).coordinates().getInfo()[0]
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    min_x = math.floor(min(xs) / SCALE_METERS) * SCALE_METERS
    max_x = math.ceil(max(xs) / SCALE_METERS) * SCALE_METERS
    min_y = math.floor(min(ys) / SCALE_METERS) * SCALE_METERS
    max_y = math.ceil(max(ys) / SCALE_METERS) * SCALE_METERS
    for year in YEARS:
        target = OUT / f"dynamic_world_label_{year}.tif"
        if target.exists() and target.stat().st_size:
            with rasterio.open(target) as existing:
                if existing.tags().get("offline_map_version") == "2":
                    print(f"{year}: already downloaded", flush=True)
                    continue
            print(f"{year}: replacing earlier raster with an explicit no-data value", flush=True)
        start = ee.Date.fromYMD(year, 1, 1)
        end = ee.Date.fromYMD(year + 1, 1, 1)
        scenes = (
            ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
            .filterBounds(region)
            .filterDate(start, end)
        )
        if scenes.size().getInfo() == 0:
            raise RuntimeError(f"No Dynamic World scenes for {year}")
        source_projection = ee.Image(scenes.first()).select("label").projection()
        annual = (
            scenes.select("label")
            .mode()
            .setDefaultProjection(source_projection)
            .unmask(255)
            .toByte()
            .clip(region)
        )
        tile_divisions = 4 if year == 2017 or year >= 2021 else 2
        tile_paths = []

        def download_tile(tile_bounds: tuple[float, float, float, float], tile_path: Path, depth: int = 0) -> list[Path]:
            if tile_path.exists():
                return [tile_path]
            left, bottom, right, top = tile_bounds
            tile = ee.Geometry.Rectangle([left, bottom, right, top], proj=CRS, geodesic=False)
            url = annual.getDownloadURL({
                "name": tile_path.stem[1:],
                "scale": SCALE_METERS,
                "crs": CRS,
                "region": tile,
                "format": "GEO_TIFF",
            })
            response = requests.get(url, timeout=(30, 600))
            if not response.ok:
                if response.status_code == 503 and "memory capacity exceeded" in response.text.lower() and depth < 3:
                    mid_x = math.floor((left + right) / 2 / SCALE_METERS) * SCALE_METERS
                    mid_y = math.floor((bottom + top) / 2 / SCALE_METERS) * SCALE_METERS
                    if mid_x <= left or mid_x >= right or mid_y <= bottom or mid_y >= top:
                        raise RuntimeError(f"Could not subdivide memory-limited tile {tile_path.name}")
                    child_bounds = [
                        (left, bottom, mid_x, mid_y), (mid_x, bottom, right, mid_y),
                        (left, mid_y, mid_x, top), (mid_x, mid_y, right, top),
                    ]
                    children = []
                    for child_index, bounds in enumerate(child_bounds):
                        child_path = tile_path.with_name(f"{tile_path.stem}_s{depth + 1}_{child_index}.tif")
                        children.extend(download_tile(bounds, child_path, depth + 1))
                    return children
                raise RuntimeError(f"Earth Engine export failed for {year} tile {tile_path.name}: {response.text[:2000]}")
            if not response.content.startswith((b"II*\x00", b"MM\x00*", b"PK\x03\x04")):
                raise RuntimeError(f"Earth Engine returned an unexpected file for tile {tile_path.name}")
            tile_path.write_bytes(response.content)
            return [tile_path]

        for row in range(tile_divisions):
            for column in range(tile_divisions):
                tile_path = OUT / f".tile_{year}_d{tile_divisions}_{row}_{column}.tif"
                left = min_x + math.floor((max_x - min_x) * column / tile_divisions / SCALE_METERS) * SCALE_METERS
                right = min_x + math.ceil((max_x - min_x) * (column + 1) / tile_divisions / SCALE_METERS) * SCALE_METERS
                bottom = min_y + math.floor((max_y - min_y) * row / tile_divisions / SCALE_METERS) * SCALE_METERS
                top = min_y + math.ceil((max_y - min_y) * (row + 1) / tile_divisions / SCALE_METERS) * SCALE_METERS
                tile_paths.extend(download_tile((left, bottom, right, top), tile_path))
        normalized_paths = []
        for tile_path in tile_paths:
            with rasterio.open(tile_path) as downloaded:
                    should_normalize = downloaded.nodata != 255
                    if should_normalize:
                        tile_profile = downloaded.profile.copy()
                        tile_pixels = downloaded.read()
            if should_normalize:
                tile_profile.update(nodata=255)
                normalized_path = tile_path.with_suffix(".normalized.tif")
                with rasterio.open(normalized_path, "w", **tile_profile) as normalized:
                    normalized.write(tile_pixels)
                normalized_path.replace(tile_path)
            normalized_paths.append(tile_path)
        tile_paths = normalized_paths
        with rasterio.open(tile_paths[0]) as first:
            profile = first.profile.copy()
        with ExitStack() as stack:
            sources = [stack.enter_context(rasterio.open(tile_path)) for tile_path in tile_paths]
            mosaic, transform = merge(
                sources,
                bounds=(min_x, min_y, max_x, max_y),
                res=SCALE_METERS,
                nodata=255,
            )
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, nodata=255, compress="lzw")
        with rasterio.open(target, "w", **profile) as output:
            output.write(mosaic)
            output.update_tags(offline_map_version="2", year=year, scale_meters=SCALE_METERS)
        for tile_path in OUT.glob(f".tile_{year}_*.tif"):
            tile_path.unlink(missing_ok=True)
        print(f"{year}: saved {target.stat().st_size / 1024 / 1024:.1f} MiB", flush=True)


if __name__ == "__main__":
    main()
