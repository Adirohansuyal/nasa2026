
import re
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from groq import Groq

from core.data_loader import (
    load_regional_timeseries,
    get_monthly_files,
    load_monthly_dataset,
)
from core.physics_engine import generate_physics_report

from components.theme import inject_theme, page_header, section_header, info_banner, ai_card, footer
from components.sidebar import render_sidebar
from components.maps import satellite_layer, validity_grid
from components.charts import coverage_chart, _apply_layout, COLORS

# -----------------------------------------
# GROQ CLIENT
# -----------------------------------------

_GROQ_CLIENT = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# -----------------------------------------
# PAGE CONFIG
# -----------------------------------------

st.set_page_config(
    page_title="Physics & Uncertainty | EARTHPULSE-X",
    page_icon="⚛️",
    layout="wide",
)

inject_theme()
render_sidebar()


# -----------------------------------------
# LOAD DATA
# -----------------------------------------

@st.cache_data
def load_data():
    df = load_regional_timeseries().copy()
    df["date"] = pd.to_datetime(df["month"], format="%Y-%m")
    return df


try:
    df = load_data()
    monthly_files = get_monthly_files()

except Exception as error:
    st.error(f"Unable to load data: {error}")
    st.stop()


# -----------------------------------------
# SHARED HELPERS
# -----------------------------------------

def md_to_html(text):
    from components.theme import md_to_html as _md
    return _md(text)


def render_ai_explanation(explanation):
    ai_card(explanation)


def call_groq(prompt, max_tokens=600):
    """Call Groq and return the text response."""
    response = _GROQ_CLIENT.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


# -----------------------------------------
# HEADER
# -----------------------------------------

page_header("PHYSICS & UNCERTAINTY", "Physics-Aware Intelligence & Data Quality Assessment", "⚛️")
st.caption("Uttarakhand | 2015–2025 | MODIS · SMAP · GPM sensors")

info_banner(
    "🛰️ This page combines **data quality assessment** (observation coverage, strict vs relaxed "
    "quality, sensor consistency) with **physics-aware intelligence** (physical plausibility bounds, "
    "seasonal consistency checks, contradictory signal detection, uncertainty propagation, and "
    "sensitivity analysis). Together these answer: How reliable is the satellite data, and does it "
    "tell a physically consistent story?",
    kind="info",
)

st.divider()


# =========================================
# SECTION 1 — OBSERVATION COVERAGE
# =========================================

section_header("1. How Much Did the Satellites Actually See?", "🛰️")

st.markdown(
    "Each satellite measures something different: "
    "**Ground Temperature (LST)** is how hot the land surface is, "
    "**Vegetation Greenness (NDVI)** tracks how lush the forest and fields look, "
    "**Soil Moisture (SMAP AM/PM)** measures water content of the soil morning and evening, "
    "and **Rainfall (GPM)** records how much rain fell. "
    "The chart shows what percentage of Uttarakhand's grid had a valid, "
    "usable reading each month over the study period."
)

st.caption(
    "💡 **Reading tip:** 100% means every grid square had a clean reading "
    "that month. A dip usually means monsoon clouds or sensor gaps blocked the view."
)

coverage_columns = {
    "LST (Ground Temperature)": "lst_strict_coverage_pct",
    "NDVI (Vegetation Greenness)": "ndvi_strict_coverage_pct",
    "SMAP AM (Morning Soil Moisture)": "smap_am_strict_coverage_pct",
    "SMAP PM (Evening Soil Moisture)": "smap_pm_strict_coverage_pct",
    "GPM (Rainfall)": "gpm_monthly_precipitation_coverage_pct",
}

coverage_fig = coverage_chart(
    df, "date",
    {k.replace(" (Ground Temperature)", "").replace(" (Vegetation Greenness)", "")
     .replace(" (Morning Soil Moisture)", "").replace(" (Evening Soil Moisture)", "")
     .replace(" (Rainfall)", ""): v for k, v in coverage_columns.items()},
    height=420,
)
st.plotly_chart(coverage_fig, use_container_width=True)


# Latest metrics
latest = df.iloc[-1]

section_header("Most Recent Month — Snapshot", "📸", "How much of Uttarakhand had a valid reading")

friendly_labels = {
    "LST (Ground Temperature)": "🌡️ Ground Temp",
    "NDVI (Vegetation Greenness)": "🌿 Vegetation",
    "SMAP AM (Morning Soil Moisture)": "💧 Soil (Morning)",
    "SMAP PM (Evening Soil Moisture)": "💧 Soil (Evening)",
    "GPM (Rainfall)": "🌧️ Rainfall",
}

cols = st.columns(5)
for col, (name, column) in zip(cols, coverage_columns.items()):
    with col:
        st.metric(friendly_labels[name], f"{latest[column]:.1f}%")


# --- AI BUTTON: Section 1 ---
st.markdown("")

@st.cache_data(show_spinner=False)
def ai_coverage(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user is looking at a line chart showing satellite observation coverage (%) over time for Uttarakhand, India, across 5 sensors: ground temperature, vegetation greenness, morning soil moisture, evening soil moisture, and rainfall.

Data:
{summary}

Give a direct, factual explanation. No storytelling. No intro sentences like "Great question" or "Let me explain". Just tell them:
- Which sensor covered the most area on average and which covered the least
- Whether coverage dropped during certain seasons (e.g. monsoon = clouds = less optical coverage)
- What low coverage actually means for that sensor's data
- One line on whether the data is reliable enough to trust

Use short bullet points. Numbers where possible. Plain English, no jargon."""
    return call_groq(prompt)

if st.button("🤖 Explain this coverage chart in simple terms", key="ai_sec1"):
    lines = [f"Coverage data over {len(df)} months:"]
    for name, col in coverage_columns.items():
        lines.append(
            f"- {name}: avg {df[col].mean():.1f}%, "
            f"min {df[col].min():.1f}%, max {df[col].max():.1f}%"
        )
    with st.spinner("AI scientist is reading the data..."):
        try:
            render_ai_explanation(ai_coverage("\n".join(lines)))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


st.divider()


# =========================================
# SECTION 2 — STRICT VS RELAXED QUALITY
# =========================================

st.markdown("## 🔍 2. Strict vs. Relaxed Quality — What's the Difference?")

st.markdown(
    "When scientists process satellite data, they apply quality filters — "
    "like a photo editor rejecting blurry shots. "
    "**Strict** quality keeps only the cleanest, most reliable readings. "
    "**Relaxed** quality keeps more data but accepts slightly fuzzier conditions. "
    "The bars below show the average percentage of Uttarakhand covered under each standard."
)

st.caption(
    "💡 If the teal and orange bars are nearly the same height, "
    "the data is very clean. A big gap means a lot of borderline readings exist "
    "that strict mode throws out."
)

quality_pairs = {
    "LST": ("lst_strict_coverage_pct", "lst_relaxed_coverage_pct"),
    "NDVI": ("ndvi_strict_coverage_pct", "ndvi_relaxed_coverage_pct"),
    "SMAP AM": ("smap_am_strict_coverage_pct", "smap_am_relaxed_coverage_pct"),
    "SMAP PM": ("smap_pm_strict_coverage_pct", "smap_pm_relaxed_coverage_pct"),
}

quality_rows = []
for variable, (strict_col, relaxed_col) in quality_pairs.items():
    quality_rows.append({
        "Variable": variable,
        "Strict (High Confidence) %": df[strict_col].mean(),
        "Relaxed (Broader Acceptance) %": df[relaxed_col].mean(),
    })

quality_df = pd.DataFrame(quality_rows)

quality_fig = go.Figure()
quality_fig.add_trace(go.Bar(
    x=quality_df["Variable"],
    y=quality_df["Strict (High Confidence) %"],
    name="Strict (High Confidence)",
    marker_color="#35C9D0",
))
quality_fig.add_trace(go.Bar(
    x=quality_df["Variable"],
    y=quality_df["Relaxed (Broader Acceptance) %"],
    name="Relaxed (Broader Acceptance)",
    marker_color="#E9A34B",
))
quality_fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    barmode="group",
    height=400,
    yaxis_title="Mean coverage over all months (%)",
)

st.plotly_chart(quality_fig, use_container_width=True)


# --- AI BUTTON: Section 2 ---
@st.cache_data(show_spinner=False)
def ai_quality(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user is looking at a grouped bar chart comparing "strict" vs "relaxed" quality satellite data for 4 sensors over Uttarakhand, India.

Strict = only cleanest readings kept. Relaxed = more readings kept but some are borderline quality.

Data:
{summary}

Give a direct, factual explanation. No intro, no storytelling. Just:
- For each sensor: is the gap between strict and relaxed large or small, and what does that mean
- Which sensor loses the most data under strict filtering and why that matters
- Whether strict-quality data is good enough to use confidently
- One-line verdict on data quality overall

Short bullets. Numbers. Plain English."""
    return call_groq(prompt)

if st.button("🤖 Explain this quality chart in simple terms", key="ai_sec2"):
    lines = ["Strict vs relaxed quality comparison (mean coverage %):"]
    for _, row in quality_df.iterrows():
        gap = row["Relaxed (Broader Acceptance) %"] - row["Strict (High Confidence) %"]
        lines.append(
            f"- {row['Variable']}: strict {row['Strict (High Confidence) %']:.1f}%, "
            f"relaxed {row['Relaxed (Broader Acceptance) %']:.1f}% "
            f"(gap: {gap:.1f}%)"
        )
    with st.spinner("AI scientist is analysing the quality data..."):
        try:
            render_ai_explanation(ai_quality("\n".join(lines)))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


st.divider()


# =========================================
# SECTION 3 — SPATIAL VALIDITY MASK
# =========================================

st.markdown("## 🗺️ 3. Which Grid Squares Had Valid Data?")

st.markdown(
    "This map zooms into a single month and a single sensor. "
    "Each square is one grid cell across Uttarakhand. "
    "**Teal = valid reading** for that location and month. "
    "**Red = no usable reading** — blocked by clouds, bad geometry, or sensor gaps. "
    "You can change the month and sensor below to explore different combinations."
)

st.caption(
    "💡 Patchy red areas often follow mountain ridges or cloud-prone valleys. "
    "A mostly-teal map means the satellite had a great view that month."
)

col_file, col_mask = st.columns(2)

with col_file:
    selected_file = st.selectbox(
        "📅 SELECT MONTH",
        monthly_files,
        index=len(monthly_files) - 1,
        format_func=lambda x: (
            x.split("_")[-2] + " – " + x.split("_")[-1].replace(".nc", "")
        ),
    )

try:
    ds = load_monthly_dataset(selected_file)
except Exception as error:
    st.error(f"Dataset loading failed: {error}")
    st.stop()

mask_variables = [
    "lst_strict_valid",
    "ndvi_strict_valid",
    "smap_am_strict_valid",
    "smap_pm_strict_valid",
    "gpm_monthly_precipitation_valid",
]
available_masks = [v for v in mask_variables if v in ds.data_vars]

mask_labels = {
    "lst_strict_valid": "🌡️ Ground Temperature (LST)",
    "ndvi_strict_valid": "🌿 Vegetation Greenness (NDVI)",
    "smap_am_strict_valid": "💧 Morning Soil Moisture (SMAP AM)",
    "smap_pm_strict_valid": "💧 Evening Soil Moisture (SMAP PM)",
    "gpm_monthly_precipitation_valid": "🌧️ Rainfall (GPM)",
}

with col_mask:
    selected_mask = st.selectbox(
        "📡 SELECT SENSOR",
        available_masks,
        format_func=lambda x: mask_labels[x],
    )

mask = ds[selected_mask].load()
mask_values = mask.values
total_pixels = int(mask_values.size)
valid_pixels = int(np.count_nonzero(mask_values == 1))
invalid_pixels = total_pixels - valid_pixels
coverage = valid_pixels / total_pixels * 100 if total_pixels else 0

m1, m2, m3 = st.columns(3)
m1.metric("🗂️ Total Grid Squares", total_pixels)
m2.metric("✅ Had a Valid Reading", valid_pixels)
m3.metric("📊 Coverage This Month", f"{coverage:.1f}%")

mask_df = mask.to_dataframe(name="validity").reset_index()

mask_fig = px.scatter(
    mask_df,
    x="x",
    y="y",
    color=mask_df["validity"].astype(str),
    color_discrete_map={"1": "#35C9D0", "0": "#EF6461"},
    title="Grid-Level Observation Coverage Map",
    labels={
        "color": "Reading Available?",
        "x": "West ← → East",
        "y": "South ← → North",
    },
)
mask_fig.update_traces(marker=dict(size=9, symbol="square"))
mask_fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=500,
)

st.plotly_chart(mask_fig, use_container_width=True)


# --- AI BUTTON: Section 3 ---
@st.cache_data(show_spinner=False)
def ai_mask(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user is looking at a grid map of Uttarakhand where teal squares = satellite had a valid reading, red squares = no usable data that month.

Map summary:
{summary}

Give a direct, factual explanation. No intro sentences. Just:
- How much of Uttarakhand had data vs no data this month (use the % numbers)
- Whether this coverage is good, average, or poor
- The most likely reason for missing squares (clouds, terrain, sensor gaps — be specific to the sensor selected)
- Whether this month's data can be trusted for analysis

Short bullets. Factual. No jargon."""
    return call_groq(prompt)

if st.button("🤖 Explain this coverage map in simple terms", key="ai_sec3"):
    month_label = (
        selected_file.split("_")[-2]
        + "-"
        + selected_file.split("_")[-1].replace(".nc", "")
    )
    summary = (
        f"Month: {month_label}\n"
        f"Sensor: {mask_labels.get(selected_mask, selected_mask)}\n"
        f"Total grid squares: {total_pixels}\n"
        f"Squares with valid data: {valid_pixels} ({coverage:.1f}%)\n"
        f"Squares with no data: {invalid_pixels} ({100 - coverage:.1f}%)"
    )
    with st.spinner("AI scientist is reading the map..."):
        try:
            render_ai_explanation(ai_mask(summary))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


st.divider()


# =========================================
# SECTION 4 — SENSOR CONSISTENCY
# =========================================

st.markdown("## 🌗 4. Morning vs. Evening Soil Moisture — Do They Agree?")

st.markdown(
    "The SMAP satellite passes over Uttarakhand **twice a day** — "
    "once around **6 am** and once around **6 pm**. "
    "Both passes measure soil moisture independently, like two different people "
    "checking the same weather forecast at different hours. "
    "If the two lines track each other closely over the years, it means the "
    "readings are stable and trustworthy. "
    "If they drift apart, it could mean the soil genuinely changes through the "
    "day, or that one pass had more difficult measurement conditions."
)

st.caption(
    "💡 The two lines should move together like dance partners. "
    "Large, persistent gaps are worth noting when you use this data."
)

sensor_df = df[["date", "smap_am_strict_mean", "smap_pm_strict_mean"]].copy()

sensor_fig = go.Figure()
sensor_fig.add_trace(go.Scatter(
    x=sensor_df["date"],
    y=sensor_df["smap_am_strict_mean"],
    mode="lines",
    name="🌅 Morning (AM)",
    line=dict(color="#35C9D0", width=2),
))
sensor_fig.add_trace(go.Scatter(
    x=sensor_df["date"],
    y=sensor_df["smap_pm_strict_mean"],
    mode="lines",
    name="🌆 Evening (PM)",
    line=dict(color="#E9A34B", width=2),
))
sensor_fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=420,
    hovermode="x unified",
    xaxis_title="Year",
    yaxis_title="Regional Soil Moisture (m³/m³)",
)

st.plotly_chart(sensor_fig, use_container_width=True)

sensor_df["AM_PM_difference"] = (
    sensor_df["smap_am_strict_mean"] - sensor_df["smap_pm_strict_mean"]
)
mean_diff = sensor_df["AM_PM_difference"].abs().mean()
max_diff = sensor_df["AM_PM_difference"].abs().max()
corr = sensor_df["smap_am_strict_mean"].corr(sensor_df["smap_pm_strict_mean"])

st.markdown("### How Close Are the Two Readings?")

d1, d2, d3 = st.columns(3)
d1.metric(
    "Average Morning–Evening Gap",
    f"{mean_diff:.4f} m³/m³",
    help="Closer to 0 means they almost always agree.",
)
d2.metric(
    "Largest Single-Month Gap",
    f"{max_diff:.4f} m³/m³",
)
d3.metric(
    "How Well They Track Each Other",
    f"{corr:.3f}",
    help="1.0 = perfect agreement. Above 0.95 = excellent.",
)

st.caption(
    "These differences reflect real measurement-time variation, "
    "not a sensor error estimate."
)


# --- AI BUTTON: Section 4 ---
@st.cache_data(show_spinner=False)
def ai_sensor(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user is looking at a line chart comparing morning (AM) vs evening (PM) soil moisture readings from the SMAP satellite over Uttarakhand, India (2015–2025).

Data summary:
{summary}

Give a direct, factual explanation. No intro, no storytelling. Just:
- Do the morning and evening readings agree? State the gap and correlation number plainly
- Is the agreement good, moderate, or poor — and what does that mean for data reliability
- If there are seasonal patterns in the gap (monsoon months vs dry months), say so directly
- One-line verdict: is this soil moisture data trustworthy?

Short bullets. Use the actual numbers. Plain English, no jargon."""
    return call_groq(prompt)

if st.button("🤖 Explain this morning vs evening comparison in simple terms", key="ai_sec4"):
    am_mean = sensor_df["smap_am_strict_mean"].mean()
    pm_mean = sensor_df["smap_pm_strict_mean"].mean()
    summary = (
        f"Study period: {len(sensor_df)} months\n"
        f"Average morning soil moisture: {am_mean:.4f} m³/m³\n"
        f"Average evening soil moisture: {pm_mean:.4f} m³/m³\n"
        f"Average absolute morning–evening gap: {mean_diff:.4f} m³/m³\n"
        f"Largest single-month gap: {max_diff:.4f} m³/m³\n"
        f"Correlation between morning and evening: {corr:.3f} "
        f"({'excellent' if corr > 0.95 else 'good' if corr > 0.85 else 'moderate'})"
    )
    with st.spinner("AI scientist is comparing the readings..."):
        try:
            render_ai_explanation(ai_sensor(summary))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


st.divider()


# =========================================
# SECTION 5 — DATA QUALITY SUMMARY TABLE
# =========================================

st.markdown("## 📋 5. Full Data Quality Summary")

st.markdown(
    "A single table that brings all the coverage statistics together — "
    "one row per sensor, showing how good the data was on average, "
    "in the worst month, and in the best month across the entire 2015–2025 period."
)

st.caption(
    "💡 High minimum values mean the satellite rarely had a really bad month. "
    "A low minimum means at least one month had very patchy data."
)

summary_rows = []
for name, column in coverage_columns.items():
    values = df[column].dropna()
    summary_rows.append({
        "Sensor": name,
        "Average Coverage (%)": round(values.mean(), 1),
        "Worst Month (%)": round(values.min(), 1),
        "Best Month (%)": round(values.max(), 1),
        "Months with Missing Records": int(df[column].isna().sum()),
    })

summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)


# --- AI BUTTON: Section 5 ---
@st.cache_data(show_spinner=False)
def ai_summary_table(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user is looking at a data quality summary table for NASA satellite sensors over Uttarakhand (2015–2025). Each row shows average, worst, and best monthly coverage % for one sensor.

Table:
{summary}

Give a direct, factual explanation. No intro sentences. Just:
- Which sensor had the highest average coverage (most reliable)
- Which had the lowest worst-month coverage (most patchy)
- Whether any sensor had missing records and what that means
- One-line verdict: overall, is this dataset good quality for environmental analysis?

Bullets. Numbers. No jargon. No storytelling."""
    return call_groq(prompt)

if st.button("🤖 Explain this summary table in simple terms", key="ai_sec5"):
    lines = ["Data quality summary (2015–2025):"]
    for _, row in summary_df.iterrows():
        lines.append(
            f"- {row['Sensor']}: avg {row['Average Coverage (%)']:.1f}%, "
            f"worst month {row['Worst Month (%)']:.1f}%, "
            f"best month {row['Best Month (%)']:.1f}%, "
            f"missing records: {row['Months with Missing Records']}"
        )
    with st.spinner("AI scientist is reviewing the summary..."):
        try:
            render_ai_explanation(ai_summary_table("\n".join(lines)))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


st.divider()


# =========================================
# PHYSICS-AWARE INTELLIGENCE
# =========================================

st.markdown("# ⚛️ Physics-Aware Intelligence")
st.markdown(
    "Beyond data coverage — are the environmental signals **physically plausible**? "
    "These checks test whether observed values fall within physical bounds, whether "
    "seasonal cycles match expected monsoon patterns, whether sensors agree, and whether "
    "variables contradict each other physically."
)

# Run physics engine
@st.cache_data(show_spinner=False)
def run_physics_checks(_df_hash: int) -> dict:
    return generate_physics_report(df)

physics_report = run_physics_checks(len(df))

# --- Section A: Physical Plausibility ---
section_header("Physical Plausibility Bounds", "📐", "Are observed values within physically reasonable ranges?")

st.markdown(
    "Each satellite variable has a **physical range** — temperatures can't exceed "
    "the boiling point, NDVI can't go above 1.0, soil moisture can't exceed saturation. "
    "The table below checks how many observations fall within these bounds."
)

plausibility = physics_report.get("plausibility", {})
if plausibility:
    plaus_rows = []
    for var_key, res in plausibility.items():
        flag_icon = "✅" if res["flag"] == "pass" else "⚠️" if res["flag"] == "warning" else "❌"
        plaus_rows.append({
            "Variable": res["label"],
            "": flag_icon,
            "In Bounds": f"{res['percentage_in_bounds']:.1f}%",
            "Out of Bounds": res["n_out_of_bounds"],
            "Min Observed": f"{res['min_observed']:.2f} {res['unit']}",
            "Max Observed": f"{res['max_observed']:.2f} {res['unit']}",
            "Physical Range": f"[{res['bound_min']:.1f}, {res['bound_max']:.1f}] {res['unit']}",
        })
    st.dataframe(pd.DataFrame(plaus_rows), use_container_width=True, hide_index=True)
else:
    st.info("No physical plausibility data available.")

st.divider()

# --- Section B: Seasonal Consistency ---
section_header("Seasonal Cycle Consistency", "🌍", "Do seasonal peaks and troughs match expected monsoon patterns?")

st.markdown(
    "Uttarakhand has a strong monsoon climate. Temperature should peak in **May** "
    "(before monsoon cooling), precipitation in **July** (monsoon peak), NDVI in "
    "**September** (post-monsoon green), and soil moisture in **August** (monsoon-wet). "
    "If actual peaks appear in wrong months, it suggests data quality issues or "
    "unexpected environmental shifts."
)

seasonal = physics_report.get("seasonal", {})
if seasonal:
    season_rows = []
    for var_key, res in seasonal.items():
        peak_ok = "✅" if res["peak_match"] else "❌"
        trough_ok = "✅" if res["trough_match"] else "❌"
        season_rows.append({
            "Variable": res["label"],
            "Expected Peak": res["expected_peak_month"],
            "Actual Peak": f"{res['actual_peak_month']} {peak_ok}",
            "Expected Trough": res["expected_trough_month"],
            "Actual Trough": f"{res['actual_trough_month']} {trough_ok}",
            "Overall": "✅ Consistent" if res["seasonal_consistent"] else "⚠️ Unexpected",
            "Amplitude": f"{res['mean_amplitude']:.4f}",
        })
    st.dataframe(pd.DataFrame(season_rows), use_container_width=True, hide_index=True)
else:
    st.info("No seasonal consistency data available.")

st.divider()

# --- Section C: Contradictory Signals ---
section_header("Contradictory Environmental Signals", "⚠️", "Months where variables physically contradict each other")

st.markdown(
    "Sometimes environmental variables tell **contradictory stories**: e.g. high rainfall "
    "but unusually low soil moisture, or high temperature with high vegetation (when heat "
    "should stress plants). These contradictions may reveal data quality issues, extreme "
    "events, or complex physical processes like rapid runoff on steep Himalayan terrain."
)

contradictory = physics_report.get("contradictory", {})
if contradictory:
    c1, c2 = st.columns(2)
    c1.metric("Contradictory Months", contradictory["n_contradictions"])
    c2.metric("Total Observed Months", len(df))

    if contradictory["n_contradictions"] > 0:
        contra_df = pd.DataFrame(contradictory["contradictions"])
        display_contra = contra_df[["month", "type", "description"]].rename(columns={
            "month": "Month",
            "type": "Signal Type",
            "description": "Pattern",
        })
        st.dataframe(display_contra, use_container_width=True, hide_index=True)

        with st.expander("Physical Explanations"):
            for c in contradictory["contradictions"][:3]:
                st.markdown(f"- **{c['month']}** ({c['type']}): {c['physical_explanation']}")
    else:
        st.success("No physically contradictory signals detected — variables are internally consistent.")
else:
    st.info("No contradictory signal data available.")

st.divider()

# --- Section D: Uncertainty Propagation ---
section_header("Uncertainty Propagation from Coverage Gaps", "📏", "How much do coverage gaps inflate our uncertainty?")

st.markdown(
    "When satellites miss part of Uttarakhand, our regional mean estimate becomes less "
    "certain. This section quantifies **how much wider** our confidence intervals get "
    "compared to full-coverage observations. A standard error inflation of 1.0 means "
    "no penalty; 1.4 means our uncertainty is 40% larger."
)

uncertainty = physics_report.get("uncertainty", {})
if uncertainty:
    unc_rows = []
    for name, res in uncertainty.items():
        unc_rows.append({
            "Sensor": name,
            "Mean Coverage": f"{res['mean_coverage_pct']:.1f}%",
            "Worst Month": f"{res['min_coverage_pct']:.1f}%",
            "SE Inflation": f"{res['se_inflation_factor']:.2f}×",
            "CI Width Ratio": f"{res['ci_width_ratio']:.2f}×",
            "Adjusted 95% CI (±)": f"±{res['coverage_adjusted_ci_half_width']:.4f}",
        })
    st.dataframe(pd.DataFrame(unc_rows), use_container_width=True, hide_index=True)

    for name, res in uncertainty.items():
        st.caption(f"**{name}:** {res['interpretation']}")
else:
    st.info("No uncertainty propagation data available.")

st.divider()

# --- Section E: Sensitivity Analysis ---
section_header("Sensitivity to Quality Threshold", "🔬", "Do conclusions change if we relax quality filters?")

st.markdown(
    "If the regional mean barely changes between strict and relaxed quality, our trend "
    "conclusions are **robust** to quality threshold choice. A large difference means "
    "results depend heavily on which quality filter we use."
)

sensitivity = physics_report.get("sensitivity", {})
if sensitivity:
    sens_rows = []
    for name, res in sensitivity.items():
        status = "✅ Robust" if res["robust_to_threshold"] else "⚠️ Sensitive"
        sens_rows.append({
            "Variable": name,
            "Robust?": status,
            "Strict Mean": f"{res['strict_mean']:.4f}",
            "Relaxed Mean": f"{res['relaxed_mean']:.4f}",
            "Difference": f"{res['mean_difference']:.4f}",
            "% of Std": f"{res['relative_difference_pct']:.1f}%",
            "Correlation": f"{res['correlation_strict_relaxed']:.3f}" if res.get("correlation_strict_relaxed") else "N/A",
        })
    st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)

    for name, res in sensitivity.items():
        st.caption(f"**{name}:** {res['interpretation']}")
else:
    st.info("No sensitivity analysis data available.")

st.divider()

# --- AI for Physics Report ---
if st.button("🤖 Explain the physics-aware intelligence findings", key="ai_physics", use_container_width=True):
    prompt = f"""You are an AI analyst for EARTHPULSE-X. A physics-aware intelligence engine ran checks on satellite observations over Uttarakhand, India (2015–2025).

Results:
{physics_report.get('text_summary', 'No data')}

Give direct, factual bullet points:
- Whether the data passes physical plausibility bounds (use the % numbers)
- Whether seasonal patterns match expected monsoon-driven cycles for Uttarakhand
- Whether any contradictory environmental signals were detected and what they mean
- How much observation gaps inflate uncertainty (use the SE inflation factors)
- Whether trend conclusions are robust to quality threshold choice
- VERDICT: one paragraph on the overall physical consistency and reliability

No storytelling. Numbers. Plain English. Be specific about what the physics checks reveal."""
    with st.spinner("AI scientist is reading physics checks..."):
        try:
            response = call_groq(prompt, max_tokens=700)
            render_ai_explanation(response)
        except Exception as e:
            st.error(f"AI unavailable: {e}")

st.divider()


# =========================================
# FULL PAGE AI SUMMARY
# =========================================

st.markdown("## 🤖 UNDERSTAND THE WHOLE PAGE AT ONCE")

st.caption(
    "Want the big picture? Click below for a plain-English summary of "
    "everything this page is telling you — all five sections in one go."
)


@st.cache_data(show_spinner=False)
def ai_full_page(summary: str) -> str:
    prompt = f"""You are an AI analyst. A user has just viewed a full data quality page for NASA satellite observations over Uttarakhand, India (2015–2025). The page covered: observation coverage over time, strict vs relaxed quality, a spatial validity map, morning vs evening soil moisture consistency, and a summary table.

Full data:
{summary}

Give a direct, factual summary. No intro, no storytelling. Cover:
- Overall coverage quality across all sensors (high/medium/low, with numbers)
- Which sensor is most and least reliable
- Whether morning and evening soil moisture agreed (use the correlation number)
- Whether missing data patches are a concern for downstream analysis
- Final verdict: can the analyses built on this data be trusted?

Use short bullets. Actual numbers. Plain English. Be direct."""
    return call_groq(prompt, max_tokens=600)


if st.button(
    "✨ GIVE ME THE BIG PICTURE — EXPLAIN THE WHOLE PAGE",
    use_container_width=True,
    key="ai_full_page",
):
    # Build a combined summary
    cov_lines = [f"Coverage over {len(df)} months:"]
    for name, col in coverage_columns.items():
        cov_lines.append(
            f"- {name}: avg {df[col].mean():.1f}%, "
            f"min {df[col].min():.1f}%"
        )

    q_lines = ["Strict vs relaxed quality:"]
    for _, row in quality_df.iterrows():
        q_lines.append(
            f"- {row['Variable']}: strict {row['Strict (High Confidence) %']:.1f}%, "
            f"relaxed {row['Relaxed (Broader Acceptance) %']:.1f}%"
        )

    sensor_summary = (
        f"Morning vs evening soil moisture: "
        f"avg gap {mean_diff:.4f}, correlation {corr:.3f}"
    )

    full = "\n".join(cov_lines + [""] + q_lines + ["", sensor_summary])

    with st.spinner("AI scientist is reading everything..."):
        try:
            render_ai_explanation(ai_full_page(full))
        except Exception as e:
            st.error(f"AI unavailable: {e}")


# -----------------------------------------
# SCIENTIFIC LIMITATIONS
# -----------------------------------------

with st.expander("📖 Full Scientific Methodology & Limitations"):
    st.markdown("""
    **Observation Coverage**

    Calculated using valid pixel coverage percentages
    supplied by the harmonized research pipeline.

    **Strict and Relaxed Quality**

    Strict quality uses more restrictive validity criteria.
    Relaxed quality accepts a broader set of observations.

    **Spatial Validity Masks**

    Binary validity masks indicate whether a grid cell
    has an accepted observation for a particular variable.

    **SMAP AM–PM Comparison**

    Compares regional morning and evening soil moisture
    summaries. It does not independently establish
    sensor accuracy.

    **Physics-Aware Intelligence (new)**

    1. **Physical plausibility bounds**: Each variable is checked
       against published physical ranges. Values outside bounds
       may indicate retrieval errors or extreme events.

    2. **Seasonal consistency**: Climatological peaks and troughs
       are compared to expected monsoon-driven patterns for
       Uttarakhand. Mismatches may indicate data quality issues.

    3. **Contradictory signal detection**: Months where variables
       show physically contradictory combinations (e.g. high
       rainfall + low soil moisture) are flagged for review.

    4. **Uncertainty propagation**: Observation coverage gaps
       inflate standard errors. The SE inflation factor quantifies
       how much wider confidence intervals become compared to
       full-coverage observations.

    5. **Sensitivity analysis**: Compares regional means under
       strict vs relaxed quality thresholds. Small differences
       mean trend conclusions are robust to quality choice.

    **Important limitations**

    - Coverage is not measurement uncertainty.
    - A valid pixel is not necessarily an error-free pixel.
    - AM–PM differences can reflect real temporal variation,
      retrieval conditions and sampling differences.
    - Physical bounds are approximate ranges, not exact limits.
    - Seasonal expectations are based on climatology, not
      physical models — shifts may indicate real change.
    - Contradictory signals are flagged for investigation, not
      automatically classified as errors.
    - Uncertainty propagation assumes random spatial sampling,
      which may not hold for systematic coverage gaps.
    - No independent physical validation is claimed here.
    - No uncertainty interval is inferred without an
      explicit uncertainty model or source data.
    """)


st.caption("EARTHPULSE-X | Physics & Uncertainty Intelligence")
