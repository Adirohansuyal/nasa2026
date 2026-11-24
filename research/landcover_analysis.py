"""District-wise ESA WorldCover 2021 area summary for Uttarakhand."""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio.features
from odc.stac import load
from pystac_client import Client

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
GADM_FILE = DATA_DIR / "gadm41_IND_2.json"
GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_2.json.zip"
STATE_NAME = "Uttarakhand"
YEAR = 2021
UTM = "EPSG:32644"
OUT_CSV = OUTPUT_DIR / "uttarakhand_worldcover_2021_districtwise.csv"

CLASSES = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse_vegetation",
    70: "snow_ice",
    80: "permanent_water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_lichen",
}


def ensure_gadm_file() -> None:
    """Fetch GADM boundaries on first run; raw boundary data is not bundled."""
    if GADM_FILE.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading GADM level-2 India boundaries...")
    with urllib.request.urlopen(GADM_URL, timeout=90) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    member = next(name for name in archive.namelist() if name.endswith("gadm41_IND_2.json"))
    GADM_FILE.write_bytes(archive.read(member))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_gadm_file()

    gdf = gpd.read_file(GADM_FILE)
    state = gdf.loc[gdf["NAME_1"].str.casefold() == STATE_NAME.casefold()].to_crs(4326)
    if state.empty:
        raise RuntimeError(f"No GADM districts found for {STATE_NAME}; check NAME_1 spelling.")

    # GADM may split one administrative unit into multiple polygon features.
    state = state[["NAME_2", "geometry"]].dissolve(by="NAME_2", as_index=False)

    districts = []
    for _, row in state.iterrows():
        source_name = str(row["NAME_2"])
        # GADM's spelling is retained for provenance; normalize common display spelling.
        display_name = {
            "hardwar": "Haridwar",
            "garhwal": "Pauri Garhwal",
            "tehrigarhwal": "Tehri Garhwal",
            "udhamsinghnagar": "Udham Singh Nagar",
        }.get(source_name.casefold().replace(" ", ""), source_name)
        districts.append((display_name, source_name, row.geometry))

    print(f"Districts found ({len(districts)}):", ", ".join(sorted(x[0] for x in districts)))
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace,
    )
    rows: list[dict] = []

    for district, source_name, geom_wgs in districts:
        print(f"Processing {district}...")
        items = list(
            catalog.search(
                collections=["esa-worldcover"],
                intersects=geom_wgs.__geo_interface__,
                datetime=f"{YEAR}-01-01T00:00:00Z/{YEAR}-12-31T23:59:59Z",
            ).items()
        )
        if not items:
            raise RuntimeError(f"No ESA WorldCover tiles returned for {district} in {YEAR}.")

        ds = load(
            items,
            bands=["map"],
            crs=UTM,
            resolution=10,
            geopolygon=geom_wgs,
            chunks={"x": 2048, "y": 2048},
            groupby="solar_day",
        )
        if "time" in ds.dims:
            raster = ds["map"].isel(time=0).compute()
        else:
            raster = ds["map"].compute()
        values = np.asarray(raster.values)
        if values.ndim != 2:
            raise RuntimeError(f"Unexpected raster dimensions for {district}: {values.shape}")

        geom_utm = gpd.GeoSeries([geom_wgs], crs=4326).to_crs(UTM).iloc[0]
        transform = raster.odc.transform
        inside = rasterio.features.rasterize(
            [(geom_utm, 1)],
            out_shape=values.shape,
            transform=transform,
            fill=0,
            dtype="uint8",
        ).astype(bool)
        district_pixels = int(inside.sum())
        observed = values[inside]
        valid = observed != 0
        valid_values = observed[valid]
        valid_pixels = int(valid.sum())
        pixel_area_m2 = abs(transform.a * transform.e - transform.b * transform.d)
        area_ha_per_pixel = pixel_area_m2 / 10_000
        counts = dict(zip(*np.unique(valid_values, return_counts=True)))

        for code, class_name in CLASSES.items():
            pixel_count = int(counts.get(code, 0))
            area_ha = pixel_count * area_ha_per_pixel
            rows.append(
                {
                    "district": district,
                    "gadm_district_name": source_name,
                    "year": YEAR,
                    "class_code": code,
                    "cover_class": class_name,
                    "pixel_count": pixel_count,
                    "area_ha": area_ha,
                    "area_sqkm": area_ha / 100,
                    "pct_of_district": 100 * pixel_count / district_pixels if district_pixels else 0,
                    "pct_of_valid_area": 100 * pixel_count / valid_pixels if valid_pixels else 0,
                    "district_pixels": district_pixels,
                    "valid_pixels": valid_pixels,
                    "data_coverage_pct": 100 * valid_pixels / district_pixels if district_pixels else 0,
                    "source": "ESA WorldCover v200 (2021), 10 m",
                }
            )
        print(f"  valid mapped coverage: {100 * valid_pixels / district_pixels:.1f}%")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, float_format="%.4f")
    wide = df.pivot(index="district", columns="cover_class", values="area_ha").round(1)
    wide.to_csv(OUT_CSV.with_name("uttarakhand_worldcover_2021_wide.csv"))
    print("\nArea (ha) by district and class:")
    print(wide.to_string())
    print(f"\nSaved: {OUT_CSV}")
    print(f"Saved: {OUT_CSV.with_name('uttarakhand_worldcover_2021_wide.csv')}")


if __name__ == "__main__":
    main()
