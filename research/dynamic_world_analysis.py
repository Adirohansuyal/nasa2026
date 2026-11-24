"""Fetch annual Dynamic World class areas for Uttarakhand and estimate trends.

Dynamic World starts on 2015-06-27, so 2015 is partial. Trend statistics use
the ten complete calendar years 2016-2025. Annual hard-label modes are sampled
on a 500 m grid; area estimates therefore represent district-level distribution,
not a 10 m pixel count.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import ee
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, theilslopes

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
ANNUAL_CSV = OUTPUT_DIR / "uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv"
TREND_CSV = OUTPUT_DIR / "uttarakhand_dynamic_world_class_trends_2016_2025.csv"
HIGHLIGHT_CSV = OUTPUT_DIR / "uttarakhand_dynamic_world_trend_highlights_2016_2025.csv"

PROJECT = "gen-lang-client-0039569301"
START_YEAR = 2015
END_YEAR = 2025
ANALYSIS_SCALE_M = 500
COLLECTION_ID = "GOOGLE/DYNAMICWORLD/V1"
DISTRICT_COLLECTION_ID = "FAO/GAUL/2025/level2"
CLASS_NAMES = {
    "water": "Water",
    "trees": "Tree cover",
    "grass": "Grassland",
    "flooded_vegetation": "Flooded vegetation",
    "crops": "Cropland",
    "shrub_and_scrub": "Shrubland",
    "built": "Built-up",
    "bare": "Bare / sparse vegetation",
    "snow_and_ice": "Snow / ice",
}
PROBABILITY_BANDS = list(CLASS_NAMES)


def initialize_earth_engine() -> None:
    """Use the user's existing local Earth Engine credentials."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Your project has exceeded its noncommercial compute quota.*")
        ee.Initialize(project=PROJECT)


def get_districts() -> ee.FeatureCollection:
    return (
        ee.FeatureCollection(DISTRICT_COLLECTION_ID)
        .filter(ee.Filter.eq("GAUL0_NAME", "India"))
        .filter(ee.Filter.eq("GAUL1_NAME", "Uttarakhand"))
    )


def annual_district_rows(year: int, districts: ee.FeatureCollection) -> list[dict]:
    """Calculate all district class areas with one aggregation per year."""
    start = ee.Date.fromYMD(year, 1, 1)
    end = ee.Date.fromYMD(year + 1, 1, 1)
    scenes = (
        ee.ImageCollection(COLLECTION_ID)
        .filterBounds(districts.geometry())
        .filterDate(start, end)
    )
    scene_count = int(scenes.size().getInfo())
    if scene_count == 0:
        raise RuntimeError(f"Dynamic World has no scenes for {year}.")

    source_projection = ee.Image(scenes.first()).select("label").projection()
    annual_label = scenes.select("label").mode().setDefaultProjection(source_projection).unmask(255)
    fraction_images = [
        annual_label.eq(code).rename(f"fraction_{name}").toFloat()
        for code, name in enumerate(PROBABILITY_BANDS)
    ]
    valid_fraction = annual_label.neq(255).rename("valid_fraction").toFloat()
    fractions = ee.Image.cat(fraction_images + [valid_fraction])
    districts_with_area = districts.map(
        lambda feature: feature.set("district_area_ha", feature.geometry().area(100).divide(10000))
    )
    reduced = fractions.reduceRegions(
        collection=districts_with_area,
        reducer=ee.Reducer.mean(),
        crs=source_projection,
        scale=ANALYSIS_SCALE_M,
        tileScale=8,
        maxPixelsPerRegion=100000000,
    )
    features = reduced.getInfo()["features"]
    rows: list[dict] = []
    for feature in features:
        properties = feature["properties"]
        district = properties["GAUL2_NAME"]
        district_ha = float(properties.get("district_area_ha") or 0)
        valid_fraction_value = float(properties.get("valid_fraction") or 0)
        valid_ha = district_ha * valid_fraction_value
        coverage_pct = 100 * valid_ha / district_ha if district_ha else 0
        for name, label in CLASS_NAMES.items():
            area_fraction = float(properties.get(f"fraction_{name}") or 0)
            area_ha = district_ha * area_fraction
            rows.append(
                {
                    "district": district,
                    "year": year,
                    "class_code": PROBABILITY_BANDS.index(name),
                    "cover_class": name,
                    "class_label": label,
                    "area_ha": area_ha,
                    "pct_of_district": 100 * area_ha / district_ha if district_ha else 0,
                    "pct_of_valid_area": 100 * area_ha / valid_ha if valid_ha else 0,
                    "district_area_ha": district_ha,
                    "valid_mapped_area_ha": valid_ha,
                    "data_coverage_pct": coverage_pct,
                    "scene_count": scene_count,
                    "analysis_scale_m": ANALYSIS_SCALE_M,
                    "area_method": "annual mode of scene labels; class fractions estimated from 500 m grid samples",
                    "source": "Google Dynamic World V1",
                    "year_status": "partial (from 2015-06-27)" if year == 2015 else "complete calendar year",
                }
            )
    return rows


def add_statewide_rows(annual: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hectares first, then calculate statewide percentages."""
    state = annual.groupby(["year", "class_code", "cover_class", "class_label"], as_index=False).agg(
        area_ha=("area_ha", "sum"),
        district_area_ha=("district_area_ha", "sum"),
        valid_mapped_area_ha=("valid_mapped_area_ha", "sum"),
        scene_count=("scene_count", "max"),
        analysis_scale_m=("analysis_scale_m", "first"),
        area_method=("area_method", "first"),
        source=("source", "first"),
        year_status=("year_status", "first"),
    )
    state["district"] = "Uttarakhand"
    state["pct_of_district"] = 100 * state["area_ha"] / state["district_area_ha"]
    state["pct_of_valid_area"] = 100 * state["area_ha"] / state["valid_mapped_area_ha"]
    state["data_coverage_pct"] = 100 * state["valid_mapped_area_ha"] / state["district_area_ha"]
    return pd.concat([annual, state[annual.columns]], ignore_index=True)


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    values = p_values.to_numpy(dtype=float)
    result = np.full(values.shape, np.nan)
    valid = np.isfinite(values)
    p = values[valid]
    if not len(p):
        return pd.Series(result, index=p_values.index)
    order = np.argsort(p)
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1].clip(0, 1)
    restored = np.empty_like(adjusted)
    restored[order] = adjusted
    result[valid] = restored
    return pd.Series(result, index=p_values.index)


def build_trends(annual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    complete_years = list(range(2016, 2026))
    complete = annual[annual["year"].isin(complete_years)]
    for (district, class_code, cover_class, class_label), group in complete.groupby(
        ["district", "class_code", "cover_class", "class_label"], sort=True
    ):
        group = group.sort_values("year")
        years = group["year"].to_numpy(dtype=float)
        areas = group["area_ha"].to_numpy(dtype=float)
        shares = group["pct_of_district"].to_numpy(dtype=float)
        if len(group) >= 2:
            slope_ha, intercept, low, high = theilslopes(areas, years)
            slope_share, _, _, _ = theilslopes(shares, years)
            tau, p_value = kendalltau(years, areas, method="auto")
            fitted_change_pct = 100 * slope_ha * (years[-1] - years[0]) / max(float(np.median(areas)), 1)
        else:
            slope_ha = slope_share = tau = p_value = low = high = fitted_change_pct = np.nan
        rows.append(
            {
                "district": district,
                "class_code": class_code,
                "cover_class": cover_class,
                "class_label": class_label,
                "sen_slope_ha_per_year": slope_ha,
                "sen_slope_share_percentage_points_per_year": slope_share,
                "sen_slope_ci_low_ha_per_year": low,
                "sen_slope_ci_high_ha_per_year": high,
                "kendall_tau": tau,
                "mann_kendall_p_value": p_value,
                "relative_change_pct_2016_2025": fitted_change_pct,
                "first_year": 2016,
                "last_year": 2025,
                "observations": len(group),
                "mean_data_coverage_pct": group["data_coverage_pct"].mean(),
            }
        )
    trends = pd.DataFrame(rows)
    # Correct the 9 classes × 13 districts plus statewide tests as one family.
    trends["fdr_q_value"] = benjamini_hochberg(trends["mann_kendall_p_value"])
    trends["direction"] = np.select(
        [trends["sen_slope_ha_per_year"] > 0, trends["sen_slope_ha_per_year"] < 0],
        ["Increasing", "Decreasing"],
        default="Stable",
    )
    trends["trend_evidence"] = np.where(
        trends["fdr_q_value"] < 0.05,
        "statistically supported monotonic trend (FDR q < 0.05)",
        "direction estimated; no statistically clear monotonic trend (FDR q ≥ 0.05)",
    )

    highlights = []
    for district, group in trends.groupby("district", sort=True):
        inc = group.loc[group["sen_slope_ha_per_year"].idxmax()]
        dec = group.loc[group["sen_slope_ha_per_year"].idxmin()]
        highlights.extend(
            [
                {"district": district, "highlight": "largest increase", **inc.to_dict()},
                {"district": district, "highlight": "largest decrease", **dec.to_dict()},
            ]
        )
    return trends, pd.DataFrame(highlights)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    initialize_earth_engine()
    districts = get_districts()
    district_count = int(districts.size().getInfo())
    if district_count != 13:
        raise RuntimeError(f"Expected 13 Uttarakhand districts; found {district_count}.")
    district_names = sorted(districts.aggregate_array("GAUL2_NAME").getInfo())
    print("Districts:", ", ".join(district_names))

    annual_rows: list[dict] = []
    for year in range(START_YEAR, END_YEAR + 1):
        print(f"Fetching annual Dynamic World land-cover mode for {year} ...", flush=True)
        year_rows = annual_district_rows(year, districts)
        annual_rows.extend(year_rows)
        interim = pd.DataFrame(annual_rows)
        interim.to_csv(ANNUAL_CSV, index=False)
        print(f"  saved {len(year_rows)} district-class rows", flush=True)

    annual_district = pd.DataFrame(annual_rows)
    annual_all = add_statewide_rows(annual_district)
    annual_all.to_csv(ANNUAL_CSV, index=False)
    trends, highlights = build_trends(annual_all)
    trends.to_csv(TREND_CSV, index=False)
    highlights.to_csv(HIGHLIGHT_CSV, index=False)
    print(f"Saved annual data: {ANNUAL_CSV}")
    print(f"Saved trends: {TREND_CSV}")
    print(f"Saved highlights: {HIGHLIGHT_CSV}")
    print("Largest statewide changes (Sen slope, ha/year):")
    state = trends[trends["district"] == "Uttarakhand"].sort_values("sen_slope_ha_per_year")
    print(state[["class_label", "sen_slope_ha_per_year", "direction", "fdr_q_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
