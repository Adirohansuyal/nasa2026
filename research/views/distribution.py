from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parents[1]
WORLD_COVER_PATH = APP_DIR / "outputs" / "uttarakhand_worldcover_2021_districtwise.csv"
ANNUAL_PATH = APP_DIR / "outputs" / "uttarakhand_dynamic_world_annual_district_classes_2015_2025.csv"
CLASS_LABELS = {
    "tree_cover": "Tree cover",
    "trees": "Tree cover",
    "shrubland": "Shrubland",
    "shrub_and_scrub": "Shrubland",
    "grassland": "Grassland",
    "grass": "Grassland",
    "cropland": "Cropland",
    "crops": "Cropland",
    "built_up": "Built-up",
    "built": "Built-up",
    "bare_sparse_vegetation": "Bare / sparse vegetation",
    "bare": "Bare / sparse vegetation",
    "snow_ice": "Snow / ice",
    "snow_and_ice": "Snow / ice",
    "permanent_water": "Permanent water",
    "water": "Water",
    "herbaceous_wetland": "Herbaceous wetland",
    "flooded_vegetation": "Flooded vegetation",
    "mangroves": "Mangroves",
    "moss_lichen": "Moss / lichen",
}
CLASS_COLORS = {
    "Water": "#4C78A8",
    "Tree cover": "#167D63",
    "Grassland": "#78A641",
    "Flooded vegetation": "#7A65A8",
    "Cropland": "#C58A2B",
    "Shrubland": "#B06A3B",
    "Built-up": "#C9574D",
    "Bare / sparse vegetation": "#918F83",
    "Snow / ice": "#76AFC4",
    "Herbaceous wetland": "#439B8B",
    "Mangroves": "#287A70",
    "Moss / lichen": "#A1A84A",
    "Permanent water": "#4C78A8",
}


@st.cache_data
def load_csv(path: str, modified: float) -> pd.DataFrame:
    del modified
    return pd.read_csv(path)


annual_exists = ANNUAL_PATH.exists()
if annual_exists:
    annual_all = load_csv(str(ANNUAL_PATH), ANNUAL_PATH.stat().st_mtime)
    annual = annual_all[annual_all["district"] != "Uttarakhand"].copy()
    annual["class_label"] = annual["cover_class"].map(CLASS_LABELS).fillna(annual["cover_class"])
    available_years = sorted(annual["year"].dropna().astype(int).unique().tolist())
else:
    annual = pd.DataFrame()
    annual_all = pd.DataFrame()
    available_years = []

if WORLD_COVER_PATH.exists():
    worldcover = load_csv(str(WORLD_COVER_PATH), WORLD_COVER_PATH.stat().st_mtime)
    worldcover["class_label"] = worldcover["cover_class"].map(CLASS_LABELS).fillna(worldcover["cover_class"])
else:
    worldcover = pd.DataFrame()

with st.sidebar:
    st.header("Explore the data")
    sources = []
    if annual_exists:
        sources.append("Annual Dynamic World")
    if not worldcover.empty:
        sources.append("ESA WorldCover · 2021")
    if not sources:
        st.error("Land-cover CSVs nahi mile. Research README ke run steps follow karein.")
        st.stop()
    source_choice = st.selectbox(
        "Dataset",
        sources,
        help="Dynamic World provides the annual series; WorldCover is the separate 2021 baseline.",
    )
    is_annual = source_choice == "Annual Dynamic World"
    if is_annual:
        selected_year = st.select_slider(
            "Year",
            options=available_years,
            value=available_years[-1],
            help="2015 is partial; 2016–2025 are complete calendar years.",
        )
        view = annual[annual["year"].astype(int) == selected_year].copy()
        districts = sorted(view["district"].unique().tolist())
        district_choice = st.selectbox("District composition", ["Uttarakhand (statewide)", *districts])
    else:
        view = worldcover.copy()
        districts = sorted(view["district"].unique().tolist())
        selected_year = 2021
        district_choice = st.selectbox("District composition", ["Uttarakhand (statewide)", *districts])
    class_options = sorted(view["class_label"].dropna().unique().tolist())
    focus_class = st.selectbox(
        "Compare this class across districts",
        class_options,
        index=class_options.index("Tree cover") if "Tree cover" in class_options else 0,
    )
    metric = st.segmented_control(
        "Measure",
        ["Area (ha)", "Valid mapped area (%)"],
        default="Area (ha)",
        key="distribution_measure",
        width="stretch",
    )

if is_annual:
    view["area_sqkm"] = view["area_ha"] / 100
    view["pixel_count"] = pd.NA
    if district_choice == "Uttarakhand (statewide)":
        chosen = annual_all[
            (annual_all["district"] == "Uttarakhand") & (annual_all["year"].astype(int) == selected_year)
        ].copy()
        reference_area = float(chosen["district_area_ha"].iloc[0]) if not chosen.empty else 0
        valid_area = float(chosen["valid_mapped_area_ha"].iloc[0]) if not chosen.empty else 0
        coverage_pct = float(chosen["data_coverage_pct"].iloc[0]) if not chosen.empty else 0
        focus = view[view["class_label"] == focus_class].copy()
    else:
        chosen = view[view["district"] == district_choice].copy()
        reference_area = float(chosen["district_area_ha"].iloc[0]) if not chosen.empty else 0
        valid_area = float(chosen["valid_mapped_area_ha"].iloc[0]) if not chosen.empty else 0
        coverage_pct = float(chosen["data_coverage_pct"].iloc[0]) if not chosen.empty else 0
        focus = view[view["class_label"] == focus_class].copy()
    if district_choice == "Uttarakhand (statewide)":
        focus = focus[focus["district"] != "Uttarakhand"]
    chart_data = chosen.copy()
    if district_choice == "Uttarakhand (statewide)":
        chart_data = annual_all[
            (annual_all["district"] == "Uttarakhand") & (annual_all["year"].astype(int) == selected_year)
        ].copy()
        chart_data["class_label"] = chart_data["cover_class"].map(CLASS_LABELS).fillna(chart_data["cover_class"])
else:
    view["area_sqkm"] = view["area_sqkm"].astype(float)
    if district_choice == "Uttarakhand (statewide)":
        chart_data = view.groupby(["cover_class", "class_label"], as_index=False).agg(
            area_ha=("area_ha", "sum"), area_sqkm=("area_sqkm", "sum"),
            pixel_count=("pixel_count", "sum"), pct_of_valid_area=("pct_of_valid_area", "mean"),
        )
        reference_area = float(chart_data["area_ha"].sum())
        valid_total = float(view.groupby("district")["valid_pixels"].first().sum())
        chart_data["pct_of_reference_area"] = 100 * chart_data["area_ha"] / reference_area
        chart_data["pct_of_district"] = chart_data["pct_of_reference_area"]
        chart_data["pct_of_valid_area"] = 100 * chart_data["pixel_count"] / valid_total if valid_total else 0
        valid_area = valid_total
        coverage_pct = float(view.groupby("district")["data_coverage_pct"].first().mean())
        focus = view[view["class_label"] == focus_class].copy()
    else:
        chart_data = view[view["district"] == district_choice].copy()
        reference_area = float(chart_data["area_ha"].sum())
        valid_area = float(chart_data["valid_pixels"].iloc[0]) if not chart_data.empty else 0
        coverage_pct = float(chart_data["data_coverage_pct"].iloc[0]) if not chart_data.empty else 0
        focus = view[view["class_label"] == focus_class].copy()
    focus = focus.drop_duplicates("district")

distribution_column = "area_ha" if metric == "Area (ha)" else "pct_of_valid_area"
distribution_percent = "pct_of_district" if is_annual else "pct_of_district"
focus["label"] = focus.apply(
    lambda row: f"{row['area_ha']:,.0f} ha · {row[distribution_percent]:.1f}%", axis=1
)
chart_data["label"] = chart_data.apply(
    lambda row: f"{row['area_ha']:,.0f} ha · {row.get('pct_of_district', 0):.1f}%", axis=1
)

st.badge("UTTARAKHAND · LAND-COVER ATLAS", icon=":material/landscape:", color="green")
st.title("Land cover, district by district")
st.caption("Compare class area, district share, and annual satellite mapping coverage across all 13 districts.")

with st.container(horizontal=True):
    st.metric("Districts", "13", border=True)
    st.metric("Land-cover classes", f"{len(class_options)}", border=True)
    st.metric("Reference area", f"{reference_area / 100:,.0f} km²", border=True)
    st.metric("Mapped coverage", f"{coverage_pct:.1f}%", border=True)

if is_annual:
    if selected_year == 2015:
        st.warning("2015 is a partial year: Dynamic World observations begin on 27 June.", icon=":material/info:")
else:
    st.caption("Baseline snapshot · ESA WorldCover v200 · 2021 · 10 m")

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.subheader(f"{focus_class} across districts")
        st.caption("Har bar ke upar hectares aur poore district area ka share diya hai.")
        if not focus.empty:
            chart = alt.Chart(focus).encode(
                x=alt.X("district:N", title="District", sort="-y", axis=alt.Axis(labelAngle=-35, labelLimit=110, labelOverlap=False)),
                y=alt.Y(f"{distribution_column}:Q", title=metric),
                tooltip=["district:N", alt.Tooltip("area_ha:Q", format=",.1f"), alt.Tooltip("pct_of_district:Q", format=".2f")],
            )
            st.altair_chart(
                (chart.mark_bar(color="#218c74", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                 + chart.mark_text(dy=-8, fontSize=9, color="#52665C").encode(text="label:N"))
                .properties(height=400),
                width="stretch", alt=f"{focus_class} distribution across Uttarakhand districts",
            )

with right:
    with st.container(border=True):
        title_location = district_choice
        st.subheader(f"Class composition · {title_location}")
        st.caption("Labels show hectares and each class's share of total district area.")
        if metric == "Valid mapped area (%)":
            y_value = "pct_of_valid_area"
        else:
            y_value = "area_ha"
        chart = alt.Chart(chart_data).encode(
            x=alt.X("class_label:N", title="Land-cover class", sort="-y", axis=alt.Axis(labelAngle=-40, labelLimit=130, labelOverlap=False)),
            y=alt.Y(f"{y_value}:Q", title=metric),
            color=alt.Color(
                "class_label:N",
                scale=alt.Scale(domain=list(CLASS_COLORS), range=list(CLASS_COLORS.values())),
                legend=None,
            ),
            tooltip=["class_label:N", alt.Tooltip("area_ha:Q", title="Area (ha)", format=",.1f"), alt.Tooltip("pct_of_district:Q", title="District area (%)", format=".2f")],
        )
        st.altair_chart(
            (chart.mark_bar(color="#218c74", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
             + chart.mark_text(dy=-8, fontSize=9, color="#52665C").encode(text="label:N"))
            .properties(height=400),
            width="stretch", alt=f"Land-cover class areas and district shares for {title_location}",
        )

st.subheader("District × class data")
table = chart_data.copy()
table["class_label"] = table["class_label"].map(lambda value: value)
columns = [c for c in ["district", "year", "class_label", "area_ha", "area_sqkm", "pct_of_valid_area", "pct_of_district", "data_coverage_pct"] if c in table]
st.dataframe(
    table[columns].rename(columns={"district": "District", "year": "Year", "class_label": "Land-cover class", "area_ha": "Area (ha)", "area_sqkm": "Area (km²)", "pct_of_valid_area": "Valid mapped area (%)", "pct_of_district": "District area (%)", "data_coverage_pct": "Mapped coverage (%)"}),
    hide_index=True, alt="Land-cover class distribution and area shares",
)

if is_annual:
    with st.expander("How to interpret annual Dynamic World areas"):
        st.write(
            "Class areas are estimated from the annual modal Dynamic World label using 500 m grid samples. "
            "They are district-level estimates, not exact 10 m pixel counts. "
            "Trend inference uses complete years 2016–2025. The 2015 partial year appears in charts but is excluded from those tests."
        )
    st.download_button(
        "Download selected year CSV", data=view.to_csv(index=False).encode("utf-8"),
        file_name=f"uttarakhand_dynamic_world_{selected_year}_district_classes.csv", mime="text/csv",
    )
else:
    st.info("The 2021 WorldCover map is a one-year baseline. Open **District trends** to explore the annual 2015–2025 land-cover class estimates.")
    st.download_button(
        "Download 2021 district-wise CSV", data=view.to_csv(index=False).encode("utf-8"),
        file_name="uttarakhand_worldcover_2021_districtwise.csv", mime="text/csv",
    )
