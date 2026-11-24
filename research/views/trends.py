from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
ANNUAL_PATH = OUTPUTS / "uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv"
TREND_PATH = OUTPUTS / "uttarakhand_dynamic_world_class_trends_2016_2025.csv"
HIGHLIGHT_PATH = OUTPUTS / "uttarakhand_dynamic_world_trend_highlights_2016_2025.csv"
EE_PROJECT = "gen-lang-client-0039569301"
DYNAMIC_WORLD_ID = "GOOGLE/DYNAMICWORLD/V1"
GAUL_DISTRICTS_ID = "FAO/GAUL/2025/level2"
MAP_CLASSES = [
    ("Water", 0, "#4C78A8"),
    ("Tree cover", 1, "#167D63"),
    ("Grassland", 2, "#78A641"),
    ("Flooded vegetation", 3, "#7A65A8"),
    ("Cropland", 4, "#C58A2B"),
    ("Shrubland", 5, "#B06A3B"),
    ("Built-up", 6, "#E45756"),
    ("Bare / sparse vegetation", 7, "#918F83"),
    ("Snow / ice", 8, "#76AFC4"),
]

st.badge("DYNAMIC WORLD · 2015–2025", icon=":material/trending_up:", color="green")
st.title("How land cover is changing")
st.caption("Track tree cover, grassland, shrubland, and other classes by district and across Uttarakhand.")

if not all(path.exists() for path in (ANNUAL_PATH, TREND_PATH, HIGHLIGHT_PATH)):
    st.warning("Annual Dynamic World land-cover outputs are not ready yet.", title="Annual data is not ready")
    st.code("research/.venv/bin/python research/dynamic_world_analysis.py", language="bash")
    st.info(
        "Earth Engine export har district ke liye 9 class-area estimates banata hai. 2015 mein source sirf 27 June se hai; "
        "trend test 10 complete years, 2016–2025, use karta hai."
    )
    st.stop()


@st.cache_data
def load_csv(path: str, modified: float) -> pd.DataFrame:
    del modified
    return pd.read_csv(path)


annual = load_csv(str(ANNUAL_PATH), ANNUAL_PATH.stat().st_mtime)
trends = load_csv(str(TREND_PATH), TREND_PATH.stat().st_mtime)
highlights = load_csv(str(HIGHLIGHT_PATH), HIGHLIGHT_PATH.stat().st_mtime)

districts = sorted(trends["district"].unique().tolist())
with st.sidebar:
    st.header("Trend controls")
    district = st.selectbox("District", districts, index=districts.index("Nainital") if "Nainital" in districts else 0)
    class_labels = sorted(trends["class_label"].unique().tolist())
    cover_class = st.selectbox(
        "Land-cover class",
        class_labels,
        index=class_labels.index("Tree cover") if "Tree cover" in class_labels else 0,
    )
    metric = st.radio("Trend measure", ["Area (ha)", "District area share (percentage points)"])

selected = trends[trends["district"] == district].copy().sort_values("sen_slope_ha_per_year")
selected_highlights = highlights[highlights["district"] == district].copy()
up = selected_highlights[selected_highlights["highlight"] == "largest increase"].iloc[0]
down = selected_highlights[selected_highlights["highlight"] == "largest decrease"].iloc[0]
class_result = selected[selected["class_label"] == cover_class].iloc[0]
state_trends = trends[trends["district"] == "Uttarakhand"].copy()
state_class = state_trends[state_trends["class_label"] == cover_class].iloc[0]

area_slope = "sen_slope_ha_per_year"
share_slope = "sen_slope_share_percentage_points_per_year"
value_column = area_slope if metric == "Area (ha)" else share_slope
unit = "ha/year" if metric == "Area (ha)" else "percentage points/year"


def add_relative_rate(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach annual Sen-slope as a percent of each class's typical area."""
    baseline = (
        annual[annual["year"].between(2016, 2025)]
        .groupby(["district", "class_label"], as_index=False)["area_ha"]
        .median()
        .rename(columns={"area_ha": "baseline_area_ha"})
    )
    result = frame.merge(baseline, on=["district", "class_label"], how="left")
    result["relative_rate_pct_per_year"] = (
        result[area_slope] / result["baseline_area_ha"].replace(0, np.nan) * 100
    )
    result["rate_label"] = result["relative_rate_pct_per_year"].map(
        lambda rate: f"{rate:+.2f}%/yr" if pd.notna(rate) else "n/a"
    )
    return result


def add_rate_end_labels(chart: alt.Chart, frame: pd.DataFrame, x_field: str) -> alt.LayerChart:
    """Put a signed relative annual rate beside each positive/negative bar end."""
    positive = frame[frame[x_field] >= 0]
    negative = frame[frame[x_field] < 0]
    layers = [chart]
    if not positive.empty:
        layers.append(
            alt.Chart(positive).mark_text(align="left", dx=7, color="#e7f2ed", fontSize=12)
            .encode(x=alt.X(f"{x_field}:Q"), y=alt.Y("class_label:N", sort="-x"), text="rate_label:N")
        )
    if not negative.empty:
        layers.append(
            alt.Chart(negative).mark_text(align="right", dx=-7, color="#e7f2ed", fontSize=12)
            .encode(x=alt.X(f"{x_field}:Q"), y=alt.Y("class_label:N", sort="-x"), text="rate_label:N")
        )
    return alt.layer(*layers)


@st.cache_data(ttl=1800, show_spinner=False)
def get_dynamic_world_map(district_name: str, year: int, class_index: int, class_color: str):
    """Return a temporary Earth Engine tile URL and its district outline."""
    import ee

    ee.Initialize(project=EE_PROJECT)
    district = (
        ee.FeatureCollection(GAUL_DISTRICTS_ID)
        .filter(ee.Filter.eq("GAUL0_NAME", "India"))
        .filter(ee.Filter.eq("GAUL1_NAME", "Uttarakhand"))
    )
    if district_name != "Uttarakhand":
        district = district.filter(ee.Filter.eq("GAUL2_NAME", district_name))
    if district.size().getInfo() == 0:
        raise ValueError(f"Earth Engine mein {district_name} district nahi mila.")

    region = district.geometry()
    scenes = (
        ee.ImageCollection(DYNAMIC_WORLD_ID)
        .filterBounds(region)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    )
    if scenes.size().getInfo() == 0:
        raise ValueError(f"Dynamic World mein {year} ke liye koi scenes nahi mile.")
    source_projection = ee.Image(scenes.first()).select("label").projection()
    annual_label = scenes.select("label").mode().setDefaultProjection(source_projection).clip(region)
    class_mask = annual_label.eq(class_index).selfMask()
    map_id = class_mask.getMapId({"min": 1, "max": 1, "palette": [class_color]})
    geometry = region.simplify(500).getInfo()
    outline = {"type": "Feature", "geometry": geometry, "properties": {"district": district_name}}
    center = region.centroid(1000).coordinates().getInfo()
    return map_id["tile_fetcher"].url_format, outline, center

with st.container(horizontal=True):
    st.metric("District", district, border=True)
    st.metric("Class", cover_class, border=True)
    st.metric("District trend", f"{class_result[value_column]:+,.1f} {unit}", border=True)
    st.metric("Uttarakhand trend", f"{state_class[value_column]:+,.1f} {unit}", border=True)

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.subheader("Fastest estimated increase")
        st.metric(str(up["class_label"]), f"{up[area_slope]:+,.1f} ha/year")
        st.caption(f"FDR q = {up['fdr_q_value']:.3f} · {up['trend_evidence']}")
with right:
    with st.container(border=True):
        st.subheader("Fastest estimated decrease")
        st.metric(str(down["class_label"]), f"{down[area_slope]:+,.1f} ha/year")
        st.caption(f"FDR q = {down['fdr_q_value']:.3f} · {down['trend_evidence']}")

state_up = state_trends.loc[state_trends[area_slope].idxmax()]
state_down = state_trends.loc[state_trends[area_slope].idxmin()]
st.markdown(
    f"**Uttarakhand overall:** largest estimated increase is **{state_up['class_label']}** "
    f"({state_up[area_slope]:+,.1f} ha/year); largest decrease is **{state_down['class_label']}** "
    f"({state_down[area_slope]:+,.1f} ha/year)."
)

with st.container(border=True):
    st.subheader(f"{cover_class} map timeline · {district}")
    map_year = st.select_slider(
        "Map year",
        options=list(range(2015, 2026)),
        value=2025,
        key="dynamic_world_map_year",
        help="2015 is partial because Dynamic World starts on 27 June; each other layer is the year's most frequent class label.",
    )
    class_index = next(index for label, index, _ in MAP_CLASSES if label == cover_class)
    class_color = next(color for label, _, color in MAP_CLASSES if label == cover_class)
    try:
        with st.spinner(f"Loading {map_year} Dynamic World map…"):
            tile_url, district_outline, map_center = get_dynamic_world_map(
                district, map_year, class_index, class_color
            )
        map_layers = [
            pdk.Layer(
                "TileLayer",
                data=tile_url,
                min_zoom=5,
                max_zoom=15,
                tile_size=256,
                opacity=0.88,
            ),
            pdk.Layer(
                "GeoJsonLayer",
                data=district_outline,
                stroked=True,
                filled=False,
                get_line_color=[235, 242, 237, 230],
                get_line_width=2,
                line_width_min_pixels=2,
                pickable=False,
            ),
        ]
        st.pydeck_chart(
            pdk.Deck(
                layers=map_layers,
                initial_view_state=pdk.ViewState(
                    latitude=map_center[1],
                    longitude=map_center[0],
                    zoom=7 if district == "Uttarakhand" else 8,
                    pitch=0,
                ),
                map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                tooltip={"text": "Dynamic World · " + cover_class + " · " + str(map_year)},
            ),
            height=560,
            width="stretch",
        )
        st.caption(
            f"Red/colored pixels mark {cover_class.lower()} in the {map_year} annual mode. "
            "Drag the year slider to compare maps. Classification is from Dynamic World V1; 2015 is partial."
        )
    except Exception as exc:
        st.warning(
            "Map load nahi hua. Earth Engine credentials/network check karein; map layer ke liye local GEE access zaroori hai. "
            f"Details: {exc}"
        )

years = annual[(annual["district"] == district) & (annual["class_label"] == cover_class)].copy()
years = years.sort_values("year")
with st.container(border=True):
    st.subheader(f"{cover_class} · annual area · {district}")
    st.caption("2015 is shown as a partial observation; dashed trend estimate is based on complete years 2016–2025.")
    line = alt.Chart(years).encode(
        x=alt.X("year:Q", title="Year", axis=alt.Axis(format="d", tickMinStep=1)),
        y=alt.Y("area_ha:Q", title="Estimated area (ha)"),
        tooltip=[
            alt.Tooltip("year:Q", title="Year", format="d"),
            alt.Tooltip("area_ha:Q", title="Estimated area (ha)", format=",.1f"),
            alt.Tooltip("pct_of_district:Q", title="District area (%)", format=".2f"),
            alt.Tooltip("data_coverage_pct:Q", title="Data coverage (%)", format=".1f"),
            alt.Tooltip("scene_count:Q", title="Scenes", format="d"),
        ],
    )
    observations = line.mark_line(point=True, color="#218c74", strokeWidth=3)
    fit_years = years[years["year"].between(2016, 2025)]
    if len(fit_years) and pd.notna(class_result[area_slope]):
        intercept = float((fit_years["area_ha"] - class_result[area_slope] * fit_years["year"]).median())
        fitted = pd.DataFrame({"year": [2016, 2025], "fitted_area": [intercept + class_result[area_slope] * y for y in [2016, 2025]]})
        trend_line = alt.Chart(fitted).mark_line(color="#e17b47", strokeDash=[7, 4], strokeWidth=2).encode(
            x=alt.X("year:Q", axis=alt.Axis(format="d", tickMinStep=1)),
            y=alt.Y("fitted_area:Q", title="Estimated area (ha)"),
        )
        st.altair_chart((observations + trend_line).properties(height=360), width="stretch", alt=f"Annual {cover_class} area trend for {district}")
    else:
        st.altair_chart(observations.properties(height=360), width="stretch", alt=f"Annual {cover_class} area for {district}")

with st.container(border=True):
    st.subheader(f"All class trends · {district}")
    st.caption("Bar-end labels show the relative rate per year, using each class's median 2016–2025 area as its baseline. FDR q < 0.05 marks a statistically supported monotonic trend after multiple-test correction.")
    plot = add_relative_rate(selected)
    plot["direction"] = plot[area_slope].apply(lambda value: "Increase" if value > 0 else "Decrease" if value < 0 else "Flat")
    plot_span = max(float(plot[value_column].max() - plot[value_column].min()), 1.0)
    plot_domain = [min(0.0, float(plot[value_column].min())) - plot_span * 0.12,
                   max(0.0, float(plot[value_column].max())) + plot_span * 0.12]
    slope_chart = alt.Chart(plot).mark_bar().encode(
        y=alt.Y("class_label:N", title="Land-cover class", sort="-x"),
        x=alt.X(f"{value_column}:Q", title=f"Sen slope ({unit})", scale=alt.Scale(domain=plot_domain)),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Increase", "Decrease", "Flat"], range=["#29a879", "#df6b64", "#8994a6"]), legend=None),
        tooltip=["class_label:N", alt.Tooltip(f"{area_slope}:Q", title="Sen slope (ha/year)", format="+,.2f"), alt.Tooltip("relative_rate_pct_per_year:Q", title="Relative rate (%/year)", format="+.2f"), alt.Tooltip(f"{share_slope}:Q", title="Share slope (pp/year)", format="+,.3f"), alt.Tooltip("fdr_q_value:Q", title="FDR q", format=".4f"), "trend_evidence:N"],
    )
    slope_chart = add_rate_end_labels(slope_chart, plot, value_column)
    st.altair_chart(slope_chart.properties(height=340), width="stretch", alt=f"Sen slope and relative annual rate for all land-cover classes in {district}")
    st.dataframe(
        selected[["class_label", area_slope, share_slope, "relative_change_pct_2016_2025", "mann_kendall_p_value", "fdr_q_value", "trend_evidence", "mean_data_coverage_pct"]]
        .rename(columns={"class_label": "Class", area_slope: "Sen slope (ha/year)", share_slope: "Share slope (pp/year)", "relative_change_pct_2016_2025": "Relative fitted change (%)", "mann_kendall_p_value": "Mann–Kendall p", "fdr_q_value": "FDR q", "trend_evidence": "Trend evidence", "mean_data_coverage_pct": "Mean coverage (%)"})
        .sort_values("Sen slope (ha/year)", ascending=False),
        hide_index=True, alt=f"Trend statistics for all land-cover classes in {district}",
    )

with st.container(border=True):
    st.subheader("Statewide trend by land-cover class")
    state_plot = add_relative_rate(state_trends).sort_values(area_slope, ascending=False)
    state_plot["direction"] = state_plot[area_slope].apply(lambda value: "Increase" if value > 0 else "Decrease" if value < 0 else "Flat")
    state_span = max(float(state_plot[value_column].max() - state_plot[value_column].min()), 1.0)
    state_domain = [min(0.0, float(state_plot[value_column].min())) - state_span * 0.12,
                    max(0.0, float(state_plot[value_column].max())) + state_span * 0.12]
    state_chart = alt.Chart(state_plot).mark_bar().encode(
        y=alt.Y("class_label:N", title="Land-cover class", sort="-x"),
        x=alt.X(f"{value_column}:Q", title=f"Sen slope ({unit})", scale=alt.Scale(domain=state_domain)),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Increase", "Decrease", "Flat"], range=["#29a879", "#df6b64", "#8994a6"]), legend=None),
        tooltip=["class_label:N", alt.Tooltip(f"{area_slope}:Q", title="Sen slope (ha/year)", format="+,.2f"), alt.Tooltip("relative_rate_pct_per_year:Q", title="Relative rate (%/year)", format="+.2f"), alt.Tooltip(f"{share_slope}:Q", title="Share slope (pp/year)", format="+,.3f"), alt.Tooltip("fdr_q_value:Q", title="FDR q", format=".4f"), "trend_evidence:N"],
    )
    state_chart = add_rate_end_labels(state_chart, state_plot, value_column)
    st.altair_chart(state_chart.properties(height=340), width="stretch", alt="Statewide Sen slope and relative annual rate for each land-cover class")
    st.dataframe(
        state_trends[["class_label", area_slope, share_slope, "relative_change_pct_2016_2025", "fdr_q_value", "trend_evidence"]]
        .rename(columns={"class_label": "Class", area_slope: "Sen slope (ha/year)", share_slope: "Share slope (pp/year)", "relative_change_pct_2016_2025": "Relative fitted change (%)", "fdr_q_value": "FDR q", "trend_evidence": "Trend evidence"})
        .sort_values("Sen slope (ha/year)", ascending=False),
        hide_index=True, alt="Statewide trend statistics for every land-cover class",
    )

download_col1, download_col2 = st.columns(2)
with download_col1:
    st.download_button(
        "Download annual district class data",
        data=annual.to_csv(index=False).encode("utf-8"),
        file_name="uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv",
        mime="text/csv",
        width="stretch",
    )
with download_col2:
    st.download_button(
        "Download district and statewide trends",
        data=trends.to_csv(index=False).encode("utf-8"),
        file_name="uttarakhand_dynamic_world_class_trends_2016_2025.csv",
        mime="text/csv",
        width="stretch",
    )
st.info(
    "**Data and limits:** Dynamic World V1 has 9 land-cover classes. Annual class area comes from the modal hard label in each year, "
    "with class fractions estimated from 500 m grid samples and scaled to district area. It is not ESA WorldCover's 10 m hard-label area "
    "and may differ from the 2021 snapshot. Annual modes can still vary with cloud/season coverage. "
    "2015 is partial; Sen slope and Mann–Kendall use 2016–2025. FDR q-values correct across all class × district/state tests; a non-significant "
    "result means evidence is inconclusive, not proof that land cover did not change."
)
