"""Earth System Trend Detective — challenge-first trend analysis."""

import json
import base64
from io import BytesIO

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

from components.sidebar import render_sidebar
from components.theme import footer, inject_theme, page_header, section_header
from config import BOUNDARIES_DIR
from core.data_loader import (
    get_monthly_files,
    load_regional_timeseries,
    load_seasonal_anomalies,
    load_trend_results,
)
from core.spatial_trend_engine import (
    VARIABLES,
    build_district_monthly_series,
    calculate_district_trends,
)
from core.openrouter_client import explain_image


st.set_page_config(
    page_title="Earth System Trend Detective | EARTHPULSE-X",
    page_icon="📈",
    layout="wide",
)
inject_theme()
render_sidebar()


VAR_CONFIG = {
    "LST": {
        "column": "lst_strict_mean", "label": "Land surface temperature",
        "unit": "K", "emoji": "🌡️", "color": "#EF6461",
    },
    "NDVI": {
        "column": "ndvi_strict_mean", "label": "Vegetation greenness",
        "unit": "index", "emoji": "🌿", "color": "#31C48D",
    },
    "SMAP_AM": {
        "column": "smap_am_strict_mean", "label": "Morning soil moisture",
        "unit": "m³/m³", "emoji": "💧", "color": "#6C8EE6",
    },
    "SMAP_PM": {
        "column": "smap_pm_strict_mean", "label": "Evening soil moisture",
        "unit": "m³/m³", "emoji": "💧", "color": "#A78BFA",
    },
    "GPM": {
        "column": "gpm_monthly_precipitation_mean", "label": "Precipitation",
        "unit": "mm/month", "emoji": "🌧️", "color": "#35C9D0",
    },
}


@st.cache_data(show_spinner=False)
def load_trend_data():
    regional = load_regional_timeseries().copy()
    regional["date"] = pd.to_datetime(regional["month"], format="%Y-%m")
    regional = regional.sort_values("date").reset_index(drop=True)
    regional_trends = load_trend_results()
    anomalies = load_seasonal_anomalies()
    district_monthly = build_district_monthly_series(
        get_monthly_files(),
        str(BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"),
    )
    district_report = calculate_district_trends(district_monthly)
    boundaries = gpd.read_file(BOUNDARIES_DIR / "uttarakhand_13_districts.geojson").to_crs("EPSG:4326")
    return regional, regional_trends, anomalies, district_monthly, district_report, boundaries


try:
    with st.spinner("Calculating district trends from NASA monthly grids…"):
        regional, regional_trends, anomalies, district_monthly, district_report, boundaries = load_trend_data()
except Exception as error:
    st.error(f"Trend data could not be loaded: {error}")
    st.stop()


def _trend_description(row: pd.Series, meta: dict) -> str:
    if not bool(row["fdr_significant"]):
        return "The data does not show a reliable long-term direction for this period. This does not mean the signal never changed; the evidence did not meet the significance threshold."
    direction = "increasing" if row["modified_mk_trend"] == "increasing" else "decreasing"
    per_decade = float(row["trend_slope_per_year"]) * 10
    plain_name = {
        "LST": "land-surface temperature measured by satellite",
        "NDVI": "satellite-derived vegetation greenness index",
        "SMAP_AM": "morning soil moisture",
        "SMAP_PM": "evening soil moisture",
        "GPM": "monthly precipitation",
    }[meta["key"]]
    return (
        f"The long-term signal for {plain_name} is {direction} by approximately "
        f"{abs(per_decade):.3g} {meta['unit']} per decade. This is a satellite-observed pattern; "
        "the trend alone does not identify its cause."
    )


def _district_description(row: pd.Series, meta: dict, district: str) -> str:
    """Translate a district result into a short, cautious plain-language read."""
    if row["direction"] == "insufficient data":
        return (
            f"There are not enough valid monthly observations to estimate a reliable long-term "
            f"trend for {district} ({int(row['valid_months'])} months). Grey indicates limited data; "
            "it is not evidence that no change occurred."
        )
    if row["direction"] == "no significant trend":
        return (
            f"Readings in {district} varied, but after accounting for seasonality and multiple "
            "statistical tests, the data does not establish a reliable long-term direction. "
            "This does not prove that no change occurred."
        )

    rate = float(row["trend_per_year"]) * 10
    direction = "increasing" if row["direction"] == "increasing" else "decreasing"
    meaning = {
        "LST": "zameen ki satah ka satellite-measured temperature",
        "NDVI": "satellite-derived vegetation greenness index",
        "SMAP_AM": "morning soil moisture",
        "SMAP_PM": "evening soil moisture",
        "GPM": "monthly precipitation",
    }[meta["key"]]
    return (
        f"In {district}, the long-term signal for {meaning} is {direction} by approximately "
        f"{abs(rate):.3g} {meta['unit']} per decade. This is a district average from satellite-grid "
        "data. The map shows direction; the adjusted q-value summarizes evidence after multiple-test "
        "correction. The trend alone does not identify a cause."
    )


@st.cache_data(ttl=21600, show_spinner=False)
def _generate_heatmap_explanation(
    image_data_uri: str,
    regional_context: str,
    district_context: str,
    monthly_values: str,
    correlation_context: str,
) -> str:
    """Explain the actual heatmap image using its plotted values and project results."""
    prompt = f"""You are the Earth science explainer for EARTHPULSE-X. Visually inspect the attached heatmap image and explain what it shows in clear, concise English for a general audience. The structured monthly values below are the exact data used to draw the image; use them to verify dates and identify the largest anomalies.

PROJECT CONTEXT
- Study area: Uttarakhand, India; April 2015 through September 2025; 126 monthly records.
- Signals: MODIS land-surface temperature (LST) and vegetation greenness (NDVI), SMAP morning/evening soil moisture, and GPM precipitation.
- Each column is one environmental signal, and each row is a month. Red means that signal was higher than usual; blue means lower than usual. Each column uses its own relative scale, so colors compare months within a signal, not physical amounts between signals.
- This is an anomaly heatmap, not a trend test, hazard alert, or event record. It cannot by itself identify a cause or prove that two signals caused one another.

REGIONAL TREND RESULTS (statistical tests are separate from this heatmap)
{regional_context}

DISTRICT TREND CONTEXT
{district_context}

MONTHLY VALUES USED TO DRAW THE HEATMAP (relative to each signal's usual pattern; columns are variables)
{monthly_values}

PROJECT COMPARISON OF HOW SIGNALS MOVE TOGETHER
{correlation_context}

Write 3–5 short bullets in everyday English for a non-technical reader. Explain red/blue as higher/lower than usual for that signal, and distinguish a brief unusual month from a long-term change. Describe related signals as “moving together” only when the supplied comparison supports it; say this does not prove one caused the other. Briefly connect to the regional and district findings, define any technical word you keep, and end with a plain-language takeaway. Mention only supplied dates and values. Do not invent causes, news, events, or measurements. No tables or formulas."""
    return explain_image(prompt, image_data_uri, max_tokens=700)


def _heatmap_image_data_uri(matrix: pd.DataFrame) -> str:
    """Render the plotted monthly anomaly matrix as a PNG for the vision model."""
    colors = ["#4385C5", "#111C2D", "#EF6461"]
    cmap = mcolors.LinearSegmentedColormap.from_list("earthpulse_anomaly", colors)
    max_abs = float(np.nanmax(np.abs(matrix.to_numpy(dtype=float))))
    max_abs = max(max_abs, 1.0)

    fig = Figure(figsize=(13, 7.2), facecolor="#0B1420", dpi=140)
    axis = fig.subplots()
    axis.set_facecolor("#0F1A2E")
    image = axis.imshow(
        matrix.to_numpy(dtype=float),
        aspect="auto",
        interpolation="nearest",
        cmap=cmap,
        vmin=-max_abs,
        vmax=max_abs,
        origin="upper",
    )
    axis.set_xticks(range(len(matrix.columns)))
    axis.set_xticklabels(matrix.columns, rotation=0, ha="center", color="#E5EDF8", fontsize=9)
    dates = pd.to_datetime(matrix.index)
    year_ticks = [index for index, date in enumerate(dates) if date.month == 1 and date.year % 2 == 0]
    axis.set_yticks(year_ticks)
    axis.set_yticklabels([str(dates[index].year) for index in year_ticks], color="#AAB8CC", fontsize=9)
    axis.tick_params(axis="both", length=0, pad=8)
    axis.set_xlabel("Environmental signal", color="#AAB8CC", labelpad=10)
    axis.set_ylabel("Month", color="#AAB8CC", labelpad=10)
    for spine in axis.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_label("Relative anomaly (standard deviations)", color="#E5EDF8", labelpad=10)
    colorbar.ax.tick_params(colors="#AAB8CC", length=0)
    fig.tight_layout(pad=1.2)

    image_buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(image_buffer)
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _trend_image_data_uri(
    series: pd.DataFrame,
    meta: dict,
    significant: bool,
    slope_per_year: float,
) -> tuple[str, str, float, float]:
    """Render the regional time-series graph and return its data URI and plotted values."""
    work = series[["date", meta["column"]]].dropna().sort_values("date").copy()
    dates = pd.to_datetime(work["date"])
    values = work[meta["column"]].to_numpy(dtype=float)
    month_index = dates.dt.year.to_numpy() * 12 + dates.dt.month.to_numpy()
    x = (month_index - month_index[0]).astype(float)
    x_centered = x - np.median(x)
    anchor = float(np.median(values))
    rolling = work[meta["column"]].rolling(12, center=True, min_periods=6).mean()
    sen = stats.theilslopes(values, x, alpha=0.95)
    slope_a = anchor + sen.low_slope * x_centered
    slope_b = anchor + sen.high_slope * x_centered
    low_line = np.minimum(slope_a, slope_b)
    high_line = np.maximum(slope_a, slope_b)
    fitted_line = anchor + (slope_per_year / 12) * x_centered

    fig = Figure(figsize=(13, 5.6), facecolor="#0B1420", dpi=140)
    axis = fig.subplots()
    axis.set_facecolor("#0F1A2E")
    axis.plot(dates, values, color="#A0B5CD", alpha=0.48, linewidth=0.9, label="Monthly observation")
    axis.plot(dates, rolling, color=meta["color"], linewidth=2.2, label="12-month average")
    if significant:
        axis.fill_between(dates, low_line, high_line, color="#F4B860", alpha=0.16, label="95% Sen-slope range")
        axis.plot(dates, fitted_line, color="#F4B860", linewidth=2, linestyle="--", label="Long-term Sen trend")

    axis.set_ylabel(f"{meta['label']} ({meta['unit']})", color="#D8E2F0", labelpad=10)
    axis.set_xlabel("Year", color="#AAB8CC", labelpad=8)
    axis.xaxis.set_major_locator(mdates.YearLocator(2))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axis.tick_params(axis="both", colors="#AAB8CC", length=0, pad=8)
    axis.grid(axis="y", color="#263752", alpha=0.75, linewidth=0.8)
    axis.grid(axis="x", visible=False)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.legend(
        loc="upper center", bbox_to_anchor=(0.5, 1.15), ncol=4,
        frameon=False, fontsize=9, labelcolor="#D8E2F0",
    )
    fig.tight_layout(pad=1.5)

    image_buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(image_buffer)
    encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
    plotted = pd.DataFrame({
        "monthly_observation": values,
        "12_month_average": rolling.to_numpy(dtype=float),
        "reported_trend_line": fitted_line if significant else np.nan,
    }, index=dates.dt.strftime("%Y-%m"))
    return (
        f"data:image/png;base64,{encoded}",
        plotted.to_csv(index_label="month", float_format="%.3f"),
        float(sen.low_slope * 120),
        float(sen.high_slope * 120),
    )


def _district_anomaly_image_data_uri(
    district: str,
    variable_label: str,
    unit: str,
    months: pd.Series,
    anomaly_values: pd.Series,
) -> str:
    """Render the district's same-calendar-month anomaly bars for vision input."""
    dates = pd.to_datetime(months)
    values = anomaly_values.to_numpy(dtype=float)
    colors = ["#31C48D" if value >= 0 else "#EF6461" for value in values]
    fig = Figure(figsize=(9, 4.4), facecolor="#0B1420", dpi=130)
    axis = fig.subplots()
    axis.set_facecolor("#0F1A2E")
    axis.bar(dates, values, width=24, color=colors, alpha=0.95)
    axis.axhline(0, color="#C5D0DF", linewidth=0.8)
    axis.set_title(f"{district}: {variable_label} vs usual same-month level", color="#E5EDF8", loc="left", pad=14)
    axis.set_ylabel(f"Difference ({unit})", color="#D8E2F0")
    axis.xaxis.set_major_locator(mdates.YearLocator(2))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axis.tick_params(axis="both", colors="#AAB8CC", length=0, pad=7)
    axis.grid(axis="y", color="#263752", alpha=0.7, linewidth=0.8)
    axis.grid(axis="x", visible=False)
    for spine in axis.spines.values():
        spine.set_visible(False)
    fig.tight_layout(pad=1.2)
    buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(buffer)
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _district_cycle_image_data_uri(
    district: str,
    variable_label: str,
    unit: str,
    means: pd.Series,
    standard_deviations: pd.Series,
) -> str:
    """Render the district's typical month-by-month cycle for vision input."""
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    values = means.reindex(range(1, 13)).to_numpy(dtype=float)
    errors = standard_deviations.reindex(range(1, 13)).fillna(0).to_numpy(dtype=float)
    fig = Figure(figsize=(9, 4.4), facecolor="#0B1420", dpi=130)
    axis = fig.subplots()
    axis.set_facecolor("#0F1A2E")
    axis.bar(np.arange(12), values, color="#31C48D", yerr=errors, capsize=3, ecolor="#E5EDF8")
    axis.set_xticks(np.arange(12), month_names)
    axis.set_title(f"{district}: typical seasonal cycle for {variable_label}", color="#E5EDF8", loc="left", pad=14)
    axis.set_ylabel(f"Monthly mean ({unit})", color="#D8E2F0")
    axis.tick_params(axis="both", colors="#AAB8CC", length=0, pad=7)
    axis.grid(axis="y", color="#263752", alpha=0.7, linewidth=0.8)
    axis.grid(axis="x", visible=False)
    for spine in axis.spines.values():
        spine.set_visible(False)
    fig.tight_layout(pad=1.2)
    buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(buffer)
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


@st.cache_data(ttl=21600, show_spinner=False)
def _generate_district_chart_explanation(image_data_uri: str, context: str, chart_type: str) -> str:
    if chart_type == "monthly_anomaly":
        chart_reading = (
            "The bars are departures from the average for that same calendar month across the observed period, "
            "not from one flat annual average. Green is above that month’s baseline; red is below."
        )
        purpose = (
            "Name the months that were higher or lower than usual and compare them with the supplied rainfall, "
            "soil-moisture, or temperature readings. A same-month difference is already compared with that "
            "month's usual value, so do not explain it away as simply monsoon or winter."
        )
    else:
        chart_reading = (
            "Each bar is the usual average for that calendar month across the observed years; whiskers show "
            "how much readings varied from year to year. This is the usual yearly pattern, not a long-term trend."
        )
        purpose = (
            "Identify the seasonal high and low months, describe the rise and fall through the year, and relate "
            "the timing to the supplied Uttarakhand monsoon background only when it fits the data. For example, "
            "rainy-season moisture can be a possible context for greener vegetation, but never call it the proven cause."
        )

    prompt = f"""You are EARTHPULSE-X's district chart explainer. Visually inspect the attached chart and connect its pattern to familiar seasonal conditions in plain English.

CHART TYPE: {chart_type}
HOW TO READ THIS GRAPH: {chart_reading}

PROJECT AND SCIENTIFIC CONTEXT
- Study period: April 2015–September 2025. Data are satellite/model grid averages for this district, not ground-station measurements.
- Official seasonal background: India Meteorological Department identifies June–September as Uttarakhand's principal rainy season, contributing about 80% of annual rainfall. NASA Earth Observatory notes that the Asian monsoon controls plant growth in India.
- These are broad regional context, not proof of what caused this district's readings. Call explanations “possible seasonal context” or “a plausible link,” and say when the project data do not establish a reason.
- Seasonal anomaly bars already subtract the usual value for that same calendar month. A normal monsoon/winter cycle alone cannot explain an unusual same-month anomaly; look for the supplied co-occurring project signals.

EXACT DATA USED IN THE PLOT AND RELATED PROJECT SIGNALS
{context}

{purpose}

Return exactly these sections:
### What this chart shows
### Seasonal connection
### What we can conclude

Write 1–2 clear bullets under each heading, using everyday English for a non-technical reader. Explain jargon in familiar words or leave it out: say “higher/lower than usual for that month” instead of “anomaly,” and “usual monthly average” instead of “climatology.” Mention actual months and values. Give possible seasonal connections as context, never as proven causes. Do not invent weather, news, events, or measurements. Use English only; avoid formulas and statistical test names."""
    return explain_image(prompt, image_data_uri, max_tokens=500)


def _render_district_chart_briefing(text: str) -> None:
    headings = {
        "what this chart shows": "📊  WHAT THE BARS SHOW",
        "seasonal connection": "🌦️  SEASONAL CONTEXT",
        "what we can conclude": "🧭  WHAT WE CAN SAY",
    }
    sections = {}
    current = None
    for line in text.splitlines():
        heading = line.strip().lstrip("#").strip().strip("*").lower()
        matched = next((key for key in headings if heading == key), None)
        if matched:
            current = matched
            sections[current] = []
        elif current:
            sections[current].append(line.strip())
    if len(sections) < 2:
        st.markdown(text)
        return
    for key, label in headings.items():
        body = "\n".join(sections.get(key, [])).strip()
        if body:
            st.caption(label)
            st.markdown(body)


@st.cache_data(ttl=21600, show_spinner=False)
def _generate_trend_explanation(image_data_uri: str, context: str) -> str:
    prompt = f"""You are the EARTHPULSE-X Earth science explainer. Visually inspect the attached monthly trend chart and explain it to a general audience in clear, concise English.

PROJECT CONTEXT
- Study area: Uttarakhand, India; monthly satellite and model data from April 2015 to September 2025.
- The plot shows the monthly observation, its centered 12-month average, and—only when statistically significant—the reported robust Sen trend with a 95% slope range.
- The 12-month average smooths seasonal variation. The Sen line shows the long-term direction. Its evidence strength comes from an autocorrelation-adjusted Modified Mann–Kendall test with false-discovery-rate correction across five regional variables.
- Satellite trends show patterns, not causes. They are not ground measurements, forecasts, or proof of a specific historical event.

SELECTED VARIABLE, STATISTICAL RESULT, AND EXACT VALUES USED TO DRAW THE CHART
{context}

Write a detailed but scannable briefing in exactly these five sections, using everyday English for a non-technical reader:
### Main takeaway
### How to read the graph
### Trend evidence
### Notable months
### Interpretation and limits

Include a clear one- or two-sentence takeaway. In each other section, write 2–3 concise bullets. Explain each line and shaded area; distinguish monthly ups and downs from the long-term direction; say how much the signal changed per decade; explain that a lower q-value means stronger evidence and q<0.05 is the project's cutoff; name the highest and lowest months; explain whether district patterns support the regional result. Say “not enough evidence to confirm a trend” instead of “no change” when appropriate. Define technical terms simply or leave them out. Aim for approximately 180 words overall. Use only supplied facts and do not invent causes or events."""
    return explain_image(prompt, image_data_uri, max_tokens=700)


def _trend_explanation_fallback(
    values: pd.Series,
    variable_label: str,
    unit: str,
    significant: bool,
    slope_per_year: float,
    q_value: float,
    district_context: str,
    ci_low_decade: float,
    ci_high_decade: float,
) -> str:
    clean = values.dropna()
    high_month, high_value = clean.idxmax(), clean.max()
    low_month, low_value = clean.idxmin(), clean.min()
    direction = "increasing" if slope_per_year > 0 else "decreasing"
    main = (
        f"The regional {variable_label.lower()} signal is {direction} by approximately "
        f"{abs(slope_per_year * 10):.3g} {unit} per decade."
        if significant else
        f"The monthly {variable_label.lower()} readings vary, but the project did not find a reliable long-term trend."
    )
    evidence = (
        f"The evidence score is {q_value:.3g}; scores below 0.05 pass the project's reliability check. "
        f"This result uses {len(clean)} monthly observations."
        if significant else
        f"There are {len(clean)} monthly observations, but the evidence score ({q_value:.3g}) is above "
        "the 0.05 reliability cutoff."
    )
    slope_range = (
        f"The plotted 95% slope range is {min(ci_low_decade, ci_high_decade):+.3g} to "
        f"{max(ci_low_decade, ci_high_decade):+.3g} {unit} per decade."
        if significant else "No trend line or slope range is shown because the trend did not pass the significance threshold."
    )
    return (
        f"### Main takeaway\n{main}\n\n"
        "### How to read the graph\n"
        "- The thin grey line shows each month's reading; the colored line averages 12 months to make the bigger pattern easier to see.\n"
        "- The dashed yellow line shows the long-term direction; the shaded area shows the likely range around that estimate.\n\n"
        "### Trend evidence\n"
        f"- {evidence}\n"
        f"- {district_context}\n"
        f"- {slope_range}\n\n"
        "### Notable months\n"
        f"- Highest monthly reading: {high_value:.2f} {unit} in {high_month:%b %Y}.\n"
        f"- Lowest monthly reading: {low_value:.2f} {unit} in {low_month:%b %Y}; these readings alone do not explain why.\n\n"
        "### Interpretation and limits\n"
        "- Satellite data shows a surface pattern; it does not identify the cause or replace ground measurements.\n"
        "- This historical trend is not a forecast and cannot confirm a specific past event."
    )


def _render_trend_briefing(text: str) -> None:
    """Render the model's detailed response as a takeaway and scannable evidence cards."""
    headings = {
        "main takeaway": "Main takeaway",
        "how to read the graph": "How to read the graph",
        "trend evidence": "Trend evidence",
        "notable months": "Notable months",
        "interpretation and limits": "Interpretation and limits",
    }
    sections = {}
    current = None
    for line in text.splitlines():
        heading = line.strip().lstrip("#").strip().strip("*").lower()
        matched = next((key for key in headings if heading == key), None)
        if matched:
            current = matched
            sections[current] = []
        elif current:
            sections[current].append(line.strip())

    if len(sections) < 4:
        st.markdown(text)
        return

    takeaway = "\n".join(sections.get("main takeaway", [])).strip()
    if takeaway:
        with st.container(border=True):
            st.caption("✦  MAIN TAKEAWAY")
            st.markdown(takeaway)

    cards = [
        ("how to read the graph", "📊  HOW TO READ THE GRAPH"),
        ("trend evidence", "📈  TREND EVIDENCE"),
        ("notable months", "🗓️  NOTABLE MONTHS"),
        ("interpretation and limits", "🧭  INTERPRETATION & LIMITS"),
    ]
    for start in (0, 2):
        columns = st.columns(2)
        for column, (key, label) in zip(columns, cards[start:start + 2]):
            body = "\n".join(sections.get(key, [])).strip()
            with column:
                with st.container(border=True):
                    st.caption(label)
                    st.markdown(body or "No additional detail was returned.")


def _heatmap_fallback(matrix: pd.DataFrame, correlations: pd.DataFrame) -> str:
    """Create a useful, deterministic reading if the AI service is unavailable."""
    labels = {
        "LST": "land-surface temperature",
        "NDVI": "vegetation greenness",
        "SMAP_AM": "morning soil moisture",
        "SMAP_PM": "evening soil moisture",
        "GPM": "precipitation",
    }
    bullets = [
        "Each row is a month and each column is an environmental signal. Red indicates an above-usual seasonal anomaly; blue indicates a below-usual anomaly. Colors are standardized within each variable, so they do not compare physical magnitudes across columns.",
    ]
    extremes = []
    for key in matrix.columns:
        series = matrix[key].dropna()
        if series.empty:
            continue
        high_month, high_value = series.idxmax(), series.max()
        low_month, low_value = series.idxmin(), series.min()
        extremes.append((abs(float(high_value)), f"The most unusually high {labels.get(key, key)} reading was in {high_month} (relative color-scale position {high_value:+.2f})."))
        extremes.append((abs(float(low_value)), f"The most unusually low {labels.get(key, key)} reading was in {low_month} (relative color-scale position {low_value:+.2f})."))
    for _, statement in sorted(extremes, reverse=True)[:2]:
        bullets.append(statement)

    pairs = []
    for left_idx, left in enumerate(correlations.columns):
        for right in correlations.columns[left_idx + 1:]:
            value = correlations.loc[left, right]
            if pd.notna(value):
                pairs.append((abs(float(value)), left, right, float(value)))
    if pairs:
        _, left, right, value = max(pairs)
        bullets.append(
            f"{labels.get(left, left)} and {labels.get(right, right)} showed the closest tendency to move together "
            "in the project comparison; that does not mean one caused the other."
        )
    bullets.append("These month-to-month anomalies are short-term departures from usual seasonal levels; use the trend results above to assess long-term change. The pattern alone does not identify a cause.")
    return "\n\n".join(f"- {bullet}" for bullet in bullets)


def _district_map(report: pd.DataFrame, geojson: dict, variable: str) -> go.Figure:
    selected = report[report["variable"] == variable].copy()
    selected["slope_label"] = selected["trend_per_year"].map(
        lambda value: f"{value:+.4g}" if pd.notna(value) else "not available"
    )
    selected["direction_label"] = selected["direction"].replace({
        "increasing": "Increasing", "decreasing": "Decreasing",
        "no significant trend": "No significant trend",
        "insufficient data": "Insufficient data",
    })
    selected["coverage_label"] = selected["mean_coverage_pct"].map(
        lambda value: f"{value:.0f}%" if pd.notna(value) else "not available"
    )
    sig = selected[selected["significant"] & selected["trend_per_year"].notna()]
    nonsig = selected[~selected.index.isin(sig.index)]
    finite_slopes = sig["trend_per_year"].abs()
    bound = float(finite_slopes.max()) if not finite_slopes.empty else 1.0
    bound = max(bound, 1e-8)

    fig = go.Figure()
    if not nonsig.empty:
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=nonsig["district_name"],
            z=np.zeros(len(nonsig)),
            featureidkey="properties.district_name",
            colorscale=[[0, "#344256"], [1, "#344256"]],
            zmin=-1,
            zmax=1,
            showscale=False,
            marker_line_color="#90A2B9",
            marker_line_width=0.8,
            customdata=nonsig[["direction_label", "slope_label", "q_value", "valid_months", "coverage_label"]].to_numpy(),
            hovertemplate=(
                "<b>%{location}</b><br>Trend: %{customdata[0]}<br>"
                f"Estimated change: %{{customdata[1]}} {VARIABLES[variable]['unit']}/year<br>"
                "Adjusted q-value: %{customdata[2]:.3g}<br>"
                "Months used: %{customdata[3]}<br>Mean valid area: %{customdata[4]}<extra></extra>"
            ),
            name="No reliable trend",
        ))
    if not sig.empty:
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            locations=sig["district_name"],
            z=sig["trend_per_year"],
            featureidkey="properties.district_name",
            colorscale=[[0, "#4385C5"], [0.5, "#E8EDF5"], [1, "#EF6461"]],
            zmin=-bound,
            zmax=bound,
            zmid=0,
            colorbar={"title": f"Change / year<br>({VARIABLES[variable]['unit']})", "thickness": 14},
            marker_line_color="#E7EEF7",
            marker_line_width=1,
            customdata=sig[["direction_label", "slope_label", "q_value", "valid_months", "coverage_label"]].to_numpy(),
            hovertemplate=(
                "<b>%{location}</b><br>Trend: %{customdata[0]}<br>"
                f"Estimated change: %{{customdata[1]}} {VARIABLES[variable]['unit']}/year<br>"
                "Adjusted q-value: %{customdata[2]:.3g}<br>"
                "Months used: %{customdata[3]}<br>Mean valid area: %{customdata[4]}<extra></extra>"
            ),
            name="Reliable trend",
        ))
    fig.update_geos(
        fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)",
        showcountries=False, showcoastlines=False,
    )
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", height=520,
        margin={"l": 0, "r": 0, "t": 8, "b": 8},
        legend={"orientation": "h", "y": 0.02, "x": 0.02},
    )
    return fig


def _trend_chart(
    series: pd.DataFrame,
    meta: dict,
    significant: bool,
    reported_slope_per_year: float,
) -> go.Figure:
    work = series[["date", meta["column"]]].dropna().sort_values("date").copy()
    values = work[meta["column"]].to_numpy(dtype=float)
    month_index = work["date"].dt.year.to_numpy() * 12 + work["date"].dt.month.to_numpy()
    x = (month_index - month_index[0]).astype(float)
    sen = stats.theilslopes(values, x, alpha=0.95)
    x_centered = x - np.median(x)
    y_anchor = float(np.median(values))
    smooth = work[meta["column"]].rolling(12, center=True, min_periods=6).mean()
    visible_values = [values, smooth.dropna().to_numpy(dtype=float)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=work["date"], y=values, mode="lines", name="Monthly observation",
        line={"color": "rgba(160,181,205,0.55)", "width": 1},
        hovertemplate="%{x|%b %Y}<br>%{y:.3f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=work["date"], y=smooth, mode="lines", name="12-month average",
        line={"color": meta["color"], "width": 2.4},
        hovertemplate="%{x|%b %Y}<br>12-month average: %{y:.3f}<extra></extra>",
    ))
    if significant:
        slope_a = y_anchor + sen.high_slope * x_centered
        slope_b = y_anchor + sen.low_slope * x_centered
        high_line = np.maximum(slope_a, slope_b)
        low_line = np.minimum(slope_a, slope_b)
        center_line = y_anchor + (reported_slope_per_year / 12) * x_centered
        visible_values.extend([high_line, low_line, center_line])
        fig.add_trace(go.Scatter(
            x=work["date"], y=high_line,
            mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=work["date"], y=low_line,
            mode="lines", line={"width": 0}, fill="tonexty",
            fillcolor="rgba(244,184,96,0.14)", name="95% Sen-slope range",
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=work["date"], y=center_line,
            mode="lines", name="Long-term direction (Sen)",
            line={"color": "#F4B860", "width": 2.2, "dash": "dash"},
            hovertemplate="Trend estimate: %{y:.3f}<extra></extra>",
        ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.55)", height=500,
        margin={"l": 12, "r": 12, "t": 18, "b": 12},
        hovermode="x unified", yaxis_title=f"{meta['label']} ({meta['unit']})",
        legend={"orientation": "h", "y": 1.08, "x": 0},
    )
    fig.update_xaxes(gridcolor="#1E2D4A", title="")
    y_min = min(float(np.nanmin(column)) for column in visible_values)
    y_max = max(float(np.nanmax(column)) for column in visible_values)
    y_padding = max((y_max - y_min) * 0.08, 0.1)
    fig.update_yaxes(gridcolor="#1E2D4A", range=[y_min - y_padding, y_max + y_padding])
    return fig


# ── Challenge-first header and all-region answer ───────────────────────────
page_header(
    "EARTH SYSTEM TREND DETECTIVE",
    "NASA Space Apps 2026 · Uttarakhand · April 2015 – September 2025",
    "🌍",
)
st.markdown(
    "Track five NASA-observed environmental signals, see where they are changing, "
    "measure the pace, and check whether the evidence is strong enough to call it a trend."
)

regional_sig = regional_trends[regional_trends["fdr_significant"].astype(bool)]
increasing = regional_sig[regional_sig["modified_mk_trend"] == "increasing"]
decreasing = regional_sig[regional_sig["modified_mk_trend"] == "decreasing"]
if not increasing.empty or not decreasing.empty:
    summary_bits = []
    for _, row in increasing.iterrows():
        meta = VAR_CONFIG.get(row["variable"])
        if meta:
            summary_bits.append(f"{meta['label']} is increasing")
    for _, row in decreasing.iterrows():
        meta = VAR_CONFIG.get(row["variable"])
        if meta:
            summary_bits.append(f"{meta['label']} is decreasing")
    st.success("**Regional signal:** " + " · ".join(summary_bits) + ". No reliable trend was established for the other variables during this period.")
else:
    st.info("No statistically reliable regional trend was found for any variable during this period.")

section_header("What is changing?", "🔎", "Trend direction and pace across the whole study region")
overview_rows = []
for _, row in regional_trends.iterrows():
    key = row["variable"]
    meta = VAR_CONFIG.get(key)
    if not meta:
        continue
    significant = bool(row["fdr_significant"])
    direction = str(row["modified_mk_trend"])
    verdict = {"increasing": "Increasing", "decreasing": "Decreasing"}.get(direction, "No reliable trend") if significant else "No reliable trend"
    overview_rows.append({
        "Variable": meta["label"],
        "Direction": verdict,
        "Change / decade": f"{float(row['trend_slope_per_year']) * 10:+.4g} {meta['unit']}",
        "Evidence strength (adjusted q)": f"{float(row['fdr_adjusted_p_value_modified']):.3g}",
        "Months analysed": int(row["valid_months"]),
        "_key": key,
    })

trend_cards = st.columns(len(overview_rows))
for column, row in zip(trend_cards, overview_rows):
    raw = regional_trends[regional_trends["variable"] == row["_key"]].iloc[0]
    meta = VAR_CONFIG[row["_key"]]
    color = meta["color"] if bool(raw["fdr_significant"]) else "#6B7B91"
    with column:
        with st.container(border=True):
            st.markdown(f"**{meta['label']}**")
            st.markdown(f"**{row['Direction']}**")
            st.caption("Estimated change per decade")
            st.markdown(f"**{row['Change / decade']}**")
            st.caption(
                f"Adjusted q-value: {row['Evidence strength (adjusted q)']}\n\n"
                f"{row['Months analysed']} monthly observations"
            )
            st.markdown(
                f'<div style="height:3px;background:{color};border-radius:4px"></div>',
                unsafe_allow_html=True,
            )

st.caption(
    "‘No reliable trend’ means the data did not pass the significance threshold; it does not prove "
    "that the variable never changed. Lower adjusted q-values indicate stronger statistical evidence; "
    "the significance threshold is q < 0.05. Rates are Sen’s slope multiplied by 10 years."
)


# ── Focused regional time series ───────────────────────────────────────────
section_header("Explore one signal", "📈", "Monthly observations, smoothed seasonality, and the robust long-term line")
selected_variable = st.selectbox(
    "Choose an environmental signal",
    list(VAR_CONFIG),
    format_func=lambda key: f"{VAR_CONFIG[key]['emoji']} {VAR_CONFIG[key]['label']}",
    key="trend_variable",
)
meta = {**VAR_CONFIG[selected_variable], "key": selected_variable}
trend_row = regional_trends[regional_trends["variable"] == selected_variable].iloc[0]
trend_is_significant = bool(trend_row["fdr_significant"])
series = regional[["date", meta["column"]]].dropna().sort_values("date")
annual_values = series.set_index("date")[meta["column"]].resample("YS").mean().dropna()

kpi_a, kpi_b, kpi_c, kpi_d = st.columns(4)
direction_text = str(trend_row["modified_mk_trend"]).title() if trend_is_significant else "No reliable trend"
change_decade = float(trend_row["trend_slope_per_year"]) * 10
kpi_a.metric("Direction", direction_text)
kpi_b.metric("Estimated pace / decade", f"{change_decade:+.3g} {meta['unit']}")
kpi_c.metric("Evidence strength", f"q = {float(trend_row['fdr_adjusted_p_value_modified']):.3g}", help="False-discovery-rate adjusted p-value across the five regional variables.")
kpi_d.metric("Data coverage", f"{len(series)} / 126 months")

st.info(_trend_description(trend_row, meta))
st.plotly_chart(
    _trend_chart(
        regional,
        meta,
        trend_is_significant,
        float(trend_row["trend_slope_per_year"]),
    ),
    width="stretch",
    alt=f"Monthly {meta['label']} measurements with a 12-month average and robust trend line",
)
st.caption("The 12-month average makes the long-term direction easier to see through seasonal ups and downs. Dashed line = robust Sen trend; shaded band = 95% slope range. The trend line appears only when the adjusted trend is significant.")

trend_slope = float(trend_row["trend_slope_per_year"])
trend_image, plotted_values, ci_low_decade, ci_high_decade = _trend_image_data_uri(
    series,
    meta,
    trend_is_significant,
    trend_slope,
)
confidence_context = (
    f"95% Sen-slope range shown in the chart: {min(ci_low_decade, ci_high_decade):+.4g} to "
    f"{max(ci_low_decade, ci_high_decade):+.4g} {meta['unit']} per decade."
    if trend_is_significant else
    "No Sen trend line or slope range is shown because the adjusted trend was not statistically significant."
)
district_signal = district_report[
    (district_report["variable"] == selected_variable)
    & district_report["significant"]
].copy()
if district_signal.empty:
    district_context = "No district passed the adjusted significance threshold for this variable."
else:
    district_signal["absolute_rate"] = district_signal["trend_per_year"].abs()
    district_examples = ", ".join(
        f"{row.district_name} ({row.direction}, {row.trend_per_year * 10:+.3g} {meta['unit']} per decade)"
        for row in district_signal.nlargest(3, "absolute_rate").itertuples()
    )
    district_context = (
        f"{len(district_signal)} of 13 districts show a reliable adjusted trend. "
        f"Largest-rate examples: {district_examples}."
    )

trend_context = (
    f"Selected signal: {meta['label']} ({selected_variable}), measured in {meta['unit']}.\n"
    f"Study region: Uttarakhand, India; April 2015–September 2025.\n"
    f"Regional result: {trend_row['modified_mk_trend'] if trend_is_significant else 'no reliable trend'}; "
    f"reported Sen slope {trend_slope:+.5g} {meta['unit']}/year "
    f"({trend_slope * 10:+.4g} {meta['unit']}/decade); adjusted q="
    f"{float(trend_row['fdr_adjusted_p_value_modified']):.4g}; "
    f"{int(trend_row['valid_months'])} monthly observations.\n"
    f"{confidence_context}\n"
    f"District context: {district_context}\n\n"
    "Exact plotted monthly values (month, observation, 12-month average, reported trend line):\n"
    f"{plotted_values}"
)
section_header(
    "AI graph briefing",
    "🤖",
    "A plain-English explanation based on the graph, monthly readings, and project findings",
)
with st.container(key="ai-regional-trend-response"):
    st.caption("AI EXPLANATION · BASED ON THE CHART AND PROJECT DATA")
    try:
        with st.spinner("Reading the trend lines and monthly pattern…"):
            trend_explanation = _generate_trend_explanation(trend_image, trend_context)
        _render_trend_briefing(trend_explanation)
    except Exception:
        fallback = _trend_explanation_fallback(
            series.set_index("date")[meta["column"]],
            meta["label"],
            meta["unit"],
            trend_is_significant,
            trend_slope,
            float(trend_row["fdr_adjusted_p_value_modified"]),
            district_context,
            ci_low_decade,
            ci_high_decade,
        )
        _render_trend_briefing(fallback)
        st.caption("OpenRouter is temporarily unavailable. This briefing is computed from the plotted data.")

annual_fig = go.Figure(go.Bar(
    x=annual_values.index.year,
    y=annual_values.values,
    marker={"color": meta["color"], "opacity": 0.82},
    hovertemplate="Year %{x}<br>Annual mean: %{y:.3f}<extra></extra>",
))
annual_fig.update_layout(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,26,46,0.55)", height=300,
    margin={"l": 12, "r": 12, "t": 18, "b": 12},
    yaxis_title=f"Annual mean ({meta['unit']})", xaxis_title="Year",
)
annual_fig.update_xaxes(gridcolor="#1E2D4A")
annual_fig.update_yaxes(gridcolor="#1E2D4A")
st.plotly_chart(annual_fig, width="stretch", alt=f"Annual mean {meta['label']} from 2015 to 2025")
st.caption("2015 begins in April and 2025 ends in September, so those two annual bars cover partial years.")


# ── Where: actual district-level spatial trends ────────────────────────────
section_header("Where is it changing?", "🗺️", "District averages from the 126 harmonized NASA monthly grids")
map_report = district_report[district_report["variable"] == selected_variable].copy()
geojson = json.loads(boundaries.to_json())
st.plotly_chart(
    _district_map(map_report, geojson, selected_variable),
    width="stretch",
    alt=f"Uttarakhand district map showing statistically reliable {meta['label']} trends",
)
st.caption(
    "Red = reliably increasing · Blue = reliably decreasing · Grey = no trend passed the "
    "multiple-testing threshold or there was too little valid data. Hover a district for its estimated rate, evidence strength, "
    "months used, and average valid-pixel coverage. District tests use seasonally adjusted values "
    "and FDR correction across all 65 district-variable tests."
)

district_options = sorted(map_report["district_name"].unique())
selected_district = st.selectbox("Open a district trend", district_options, key="trend_district")
drow = map_report[map_report["district_name"] == selected_district].iloc[0]
dseries = district_monthly[
    (district_monthly["district_name"] == selected_district)
    & (district_monthly["variable"] == selected_variable)
].sort_values("month").copy()
dseries["month_number"] = dseries["month"].dt.month
dseries["seasonal_baseline"] = dseries.groupby("month_number")["value"].transform("mean")
dseries["anomaly"] = dseries["value"] - dseries["seasonal_baseline"]

d1, d2, d3, d4 = st.columns(4)
d1.metric("District trend", str(drow["direction"]).replace("no significant trend", "No reliable trend").title())
d2.metric("Estimated change / decade", f"{float(drow['trend_per_year']) * 10:+.3g} {meta['unit']}" if pd.notna(drow["trend_per_year"]) else "Insufficient data")
d3.metric("Evidence strength", f"q = {float(drow['q_value']):.3g}" if pd.notna(drow["q_value"]) else "—")
d4.metric("Average valid area", f"{float(drow['mean_coverage_pct']):.0f}%" if pd.notna(drow["mean_coverage_pct"]) else "—")
st.info(_district_description(drow, meta, selected_district))

col_anom, col_season = st.columns(2)
with col_anom:
    anomaly_fig = go.Figure(go.Bar(
        x=dseries["month"], y=dseries["anomaly"],
        marker_color=["#31C48D" if value >= 0 else "#EF6461" for value in dseries["anomaly"]],
        hovertemplate="%{x|%b %Y}<br>Difference from this month's usual value: %{y:.3f}<extra></extra>",
    ))
    anomaly_fig.add_hline(y=0, line_color="#AAB8CC", line_width=1)
    anomaly_fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.55)", height=320,
        margin={"l": 12, "r": 12, "t": 26, "b": 12},
        title="District readings vs its usual same-month level",
        yaxis_title=f"Difference ({meta['unit']})", xaxis_title="",
    )
    anomaly_fig.update_xaxes(gridcolor="#1E2D4A")
    anomaly_fig.update_yaxes(gridcolor="#1E2D4A")
    st.plotly_chart(anomaly_fig, width="stretch", alt=f"Monthly anomalies for {selected_district}")
    monthly_anomaly_image = _district_anomaly_image_data_uri(
        selected_district,
        meta["label"],
        meta["unit"],
        dseries["month"],
        dseries["anomaly"],
    )
    district_wide = district_monthly[
        district_monthly["district_name"] == selected_district
    ].pivot(index="month", columns="variable", values="value").sort_index()
    district_monthly_baseline = district_wide.groupby(district_wide.index.month).transform("mean")
    district_departures = district_wide - district_monthly_baseline
    related_context = []
    if selected_variable in district_departures:
        related = district_departures.corr(method="spearman")[selected_variable].drop(selected_variable, errors="ignore").dropna()
        for other, coefficient in related.reindex(related.abs().sort_values(ascending=False).index).head(2).items():
            paired_months = district_departures[[selected_variable, other]].dropna().shape[0]
            related_context.append(
                f"{other}: Spearman correlation {coefficient:+.2f} over {paired_months} paired months "
                "(exploratory co-movement only; not a causal or significance test)."
            )
    anomaly_context = (
        f"District: {selected_district}, Uttarakhand. Signal: {meta['label']} ({selected_variable}), in {meta['unit']}.\n"
        "This chart subtracts each calendar month's own long-period average, so it shows unusual departures "
        "within that month rather than the normal seasonal cycle.\n"
        f"District trend result: {drow['direction']}; estimated change "
        f"{float(drow['trend_per_year']) * 10:+.4g} {meta['unit']} per decade; adjusted q="
        f"{float(drow['q_value']):.3g} across district tests; {int(drow['valid_months'])} valid months.\n"
        f"Other district signals: {' '.join(related_context) if related_context else 'No sufficiently paired signals available.'}\n\n"
        "Exact plotted values (month, anomaly from same-month baseline):\n"
        f"{dseries[['month', 'anomaly']].to_csv(index=False, float_format='%.4f')}"
    )
    with st.container(border=True, key="ai-district-anomaly-response"):
        st.caption("AI EXPLAINS THE MONTHLY DEPARTURES")
        try:
            with st.spinner("Explaining the unusual months…"):
                anomaly_explanation = _generate_district_chart_explanation(
                    monthly_anomaly_image,
                    anomaly_context,
                    "monthly_anomaly",
                )
            _render_district_chart_briefing(anomaly_explanation)
        except Exception:
            max_anomaly = dseries.loc[dseries["anomaly"].idxmax()]
            min_anomaly = dseries.loc[dseries["anomaly"].idxmin()]
            st.markdown(
                f"- Highest above-usual reading: **{max_anomaly['month']:%b %Y}** "
        f"({max_anomaly['anomaly']:+.3g} {meta['unit']} from what is usual for that month).\n"
                f"- Lowest below-usual reading: **{min_anomaly['month']:%b %Y}** "
        f"({min_anomaly['anomaly']:+.3g} {meta['unit']} from what is usual for that month).\n"
                "- These readings were above or below what is usual for those months; the chart alone cannot identify why."
            )
            st.caption("OpenRouter is unavailable; key readings are summarized directly from the plotted data.")
    st.caption(
        "Seasonal background: [IMD Uttarakhand monsoon report](https://mausam.imd.gov.in/imd_latest/monsoon_report_2025_2.pdf) · "
        "[NASA monsoon and vegetation context](https://science.nasa.gov/earth/earth-observatory/global-maps/total-rainfall-vegetation/)"
    )
with col_season:
    climatology = dseries.groupby("month_number")["value"].agg(["mean", "std"]).reindex(range(1, 13))
    season_fig = go.Figure(go.Bar(
        x=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        y=climatology["mean"],
        error_y={"type": "data", "array": climatology["std"].fillna(0), "visible": True},
        marker_color=meta["color"],
        hovertemplate="%{x}<br>Usual mean: %{y:.3f}<extra></extra>",
    ))
    season_fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.55)", height=320,
        margin={"l": 12, "r": 12, "t": 26, "b": 12},
        title=f"{selected_district}: typical seasonal cycle",
        yaxis_title=f"Monthly mean ({meta['unit']})", xaxis_title="",
    )
    season_fig.update_xaxes(gridcolor="#1E2D4A")
    season_fig.update_yaxes(gridcolor="#1E2D4A")
    st.plotly_chart(season_fig, width="stretch", alt=f"Seasonal cycle of {meta['label']} in {selected_district}")
    monthly_means = climatology["mean"].reindex(range(1, 13))
    monthly_std = climatology["std"].reindex(range(1, 13))
    cycle_image = _district_cycle_image_data_uri(
        selected_district,
        meta["label"],
        meta["unit"],
        monthly_means,
        monthly_std,
    )
    high_month = int(monthly_means.idxmax())
    low_month = int(monthly_means.idxmin())
    cycle_context = (
        f"District: {selected_district}, Uttarakhand. Signal: {meta['label']} ({selected_variable}), in {meta['unit']}.\n"
        "The bars are the usual average for each calendar month; whiskers show how much readings varied "
        "from year to year. This is the district's usual yearly pattern, not a long-term trend.\n"
        f"Highest monthly mean: {monthly_means.loc[high_month]:.4g} {meta['unit']} in "
        f"{pd.Timestamp(2000, high_month, 1):%B}; lowest monthly mean: {monthly_means.loc[low_month]:.4g} "
        f"{meta['unit']} in {pd.Timestamp(2000, low_month, 1):%B}.\n"
        f"District trend result for context: {drow['direction']}; estimated change "
        f"{float(drow['trend_per_year']) * 10:+.4g} {meta['unit']} per decade; adjusted q="
        f"{float(drow['q_value']):.3g}.\n"
        "Official background: June–September is Uttarakhand's principal rainy season (IMD); the Asian monsoon "
        "influences plant growth in India (NASA Earth Observatory). These broad facts are contextual, not "
        "district-specific proof of cause.\n\n"
        "Exact plotted values (month, usual average, year-to-year spread):\n"
        f"{climatology.reset_index().to_csv(index=False, float_format='%.4f')}"
    )
    with st.container(border=True, key="ai-district-cycle-response"):
        st.caption("AI EXPLAINS THE USUAL YEARLY PATTERN")
        try:
            with st.spinner("Connecting the monthly cycle to seasonal context…"):
                cycle_explanation = _generate_district_chart_explanation(
                    cycle_image,
                    cycle_context,
                    "seasonal_cycle",
                )
            _render_district_chart_briefing(cycle_explanation)
        except Exception:
            st.markdown(
                f"- The usual monthly average is highest in **{pd.Timestamp(2000, high_month, 1):%B}** "
                f"({monthly_means.loc[high_month]:.3g} {meta['unit']}) and lowest in "
                f"**{pd.Timestamp(2000, low_month, 1):%B}** ({monthly_means.loc[low_month]:.3g} {meta['unit']}).\n"
                "- In Uttarakhand, June–September is the principal rainy season; for vegetation or moisture, "
                "this can be useful seasonal context, but it does not prove the cause of this district pattern."
            )
            st.caption("OpenRouter is unavailable; the seasonal pattern is summarized directly from the plotted data.")
    st.caption(
        "Seasonal context: [IMD Uttarakhand monsoon report](https://mausam.imd.gov.in/imd_latest/monsoon_report_2025_2.pdf) · "
        "[NASA monsoon and vegetation context](https://science.nasa.gov/earth/earth-observatory/global-maps/total-rainfall-vegetation/)"
    )

district_table = map_report.copy()
district_table["Trend"] = district_table["direction"].replace({
    "increasing": "Increasing", "decreasing": "Decreasing",
    "no significant trend": "No reliable trend", "insufficient data": "Insufficient data",
})
district_table["Change / decade"] = district_table["trend_per_year"] * 10
district_table["Adjusted q"] = district_table["q_value"]
district_table["Valid months"] = district_table["valid_months"]
district_table["Mean valid area (%)"] = district_table["mean_coverage_pct"]
section_header("District comparison", "📋", f"{meta['label']} · strict quality mask")
district_table = district_table.rename(columns={
    "district_name": "District",
    "Change / decade": f"Change / decade ({meta['unit']})",
    "Adjusted q": "Adjusted q",
    "Valid months": "Valid months",
    "Mean valid area (%)": "Mean valid area (%)",
})
change_column = f"Change / decade ({meta['unit']})"
district_display = (
    district_table[["District", "Trend", change_column, "Adjusted q", "Valid months", "Mean valid area (%)"]]
    .sort_values(change_column, ascending=False)
    .reset_index(drop=True)
)

def _trend_cell_style(value):
    styles = {
        "Increasing": "color: #63E0B0; background-color: rgba(49,196,141,0.10); font-weight: 700;",
        "Decreasing": "color: #FF8C86; background-color: rgba(239,100,97,0.10); font-weight: 700;",
        "No reliable trend": "color: #B8C6D9; background-color: rgba(170,184,204,0.08); font-weight: 600;",
        "Insufficient data": "color: #F2C477; background-color: rgba(233,163,75,0.10); font-weight: 600;",
    }
    return styles.get(value, "color: #AAB8CC;")

district_styler = (
    district_display.style
    .hide(axis="index")
    .map(_trend_cell_style, subset=["Trend"])
    .set_properties(**{
        "font-family": "Urbanist, sans-serif",
        "font-size": "14px",
        "color": "#D8E2F0",
        "background-color": "#0F1A2E",
        "border-bottom": "1px solid rgba(42,63,95,0.62)",
        "padding": "13px 16px",
        "white-space": "nowrap",
    })
    .set_properties(subset=["District"], **{"font-weight": "700", "color": "#F1F5FC"})
    .set_table_styles([
        {"selector": "table", "props": [
            ("border-collapse", "separate"), ("border-spacing", "0"),
            ("width", "100%"), ("font-family", "Urbanist, sans-serif"),
        ]},
        {"selector": "thead th", "props": [
            ("background-color", "#172640"), ("color", "#B9C9DE"),
            ("font-family", "Urbanist, sans-serif"), ("font-size", "12px"),
            ("font-weight", "700"), ("letter-spacing", "0.035em"),
            ("padding", "14px 16px"), ("border-bottom", "1px solid #2A3F5F"),
            ("text-align", "left"), ("white-space", "nowrap"),
        ]},
        {"selector": "tbody tr:nth-child(even) td", "props": [("background-color", "#111E33")]},
        {"selector": "tbody tr:hover td", "props": [("background-color", "#182B45")]},
    ])
)
st.dataframe(
    district_styler,
    width="stretch",
    height=min(610, 54 + 42 * len(district_display)),
    hide_index=True,
    alt=f"District trend comparison for {meta['label']}",
    column_config={
        change_column: st.column_config.NumberColumn(format="%.4g"),
        "Adjusted q": st.column_config.NumberColumn(format="%.3g"),
        "Valid months": st.column_config.NumberColumn(format="%.0f"),
        "Mean valid area (%)": st.column_config.NumberColumn(format="%.0f%%"),
    },
)


# ── Cross-variable visual and scientific interpretation ───────────────────
section_header("How the variables move together over time", "🌐", "Monthly anomalies, standardised within each variable")
anomaly_columns = {
    "LST": "lst_anomaly", "NDVI": "ndvi_anomaly", "SMAP_AM": "smap_am_anomaly",
    "SMAP_PM": "smap_pm_anomaly", "GPM": "gpm_anomaly",
}
available_anomalies = {key: col for key, col in anomaly_columns.items() if col in anomalies.columns}
heat = anomalies.set_index("month")[[available_anomalies[key] for key in available_anomalies]].copy()
heat = heat.apply(lambda column: (column - column.mean()) / column.std() if column.std() else column * 0)
heat_for_ai = heat.copy()
heat_for_ai.columns = list(available_anomalies)
heat.columns = [f"{VAR_CONFIG[key]['emoji']} {VAR_CONFIG[key]['label']}" for key in available_anomalies]
heat_fig = go.Figure(go.Heatmap(
    z=heat.to_numpy(), x=heat.columns, y=heat.index.astype(str),
    colorscale=[[0, "#4385C5"], [0.5, "#111C2D"], [1, "#EF6461"]],
    zmid=0, colorbar={"title": "Relative difference from usual"},
    hovertemplate="%{y}<br>%{x}<br>Relative reading: %{z:.2f}<extra></extra>",
))
heat_fig.update_layout(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,26,46,0.55)", height=450,
    margin={"l": 12, "r": 12, "t": 18, "b": 12},
    xaxis={"side": "top"}, yaxis={"autorange": "reversed", "title": "Month"},
)
st.plotly_chart(heat_fig, width="stretch", alt="Heatmap of monthly environmental anomalies from 2015 to 2025")
st.caption("Each row is a month. Red is higher than usual and blue is lower for that signal. This shows unusual months, not the long-term direction; use the trend results above for that.")

regional_context_lines = []
for _, row in regional_trends.iterrows():
    key = row["variable"]
    if key not in VAR_CONFIG:
        continue
    status = str(row["modified_mk_trend"]) if bool(row["fdr_significant"]) else "no reliable trend"
    rate = float(row["trend_slope_per_year"]) * 10
    q_value = float(row["fdr_adjusted_p_value_modified"])
    regional_context_lines.append(
        f"{key}: {status}; estimated change {rate:+.4g} {VAR_CONFIG[key]['unit']} per decade; "
        f"adjusted q={q_value:.3g}; {int(row['valid_months'])} months."
    )

district_context_lines = []
for key in VAR_CONFIG:
    group = district_report[district_report["variable"] == key]
    reliable = group[group["significant"]].copy()
    if reliable.empty:
        district_context_lines.append(f"{key}: no district passed the adjusted significance threshold.")
        continue
    reliable["abs_rate"] = reliable["trend_per_year"].abs()
    examples = ", ".join(
        f"{item.district_name} ({item.direction}, {item.trend_per_year * 10:+.3g} {VAR_CONFIG[key]['unit']}/decade)"
        for item in reliable.nlargest(2, "abs_rate").itertuples()
    )
    district_context_lines.append(
        f"{key}: {len(reliable)} of 13 districts have a reliable adjusted trend; strongest-rate examples: {examples}."
    )

correlations = heat_for_ai.corr(method="spearman")
fallback_explanation = _heatmap_fallback(heat_for_ai, correlations)
vision_image = _heatmap_image_data_uri(
    heat_for_ai.rename(columns={key: VAR_CONFIG[key]["label"] for key in heat_for_ai.columns})
)
section_header("AI interpretation", "🤖", "Automatic explanation of this heatmap using the plotted values and EARTHPULSE-X analysis")
with st.container(border=True, key="ai-heatmap-response"):
    try:
        with st.spinner("Reading the monthly pattern and project findings…"):
            ai_explanation = _generate_heatmap_explanation(
                image_data_uri=vision_image,
                regional_context="\n".join(regional_context_lines),
                district_context="\n".join(district_context_lines),
                monthly_values=heat_for_ai.to_csv(index_label="month", float_format="%.2f"),
                correlation_context=correlations.to_csv(float_format="%.2f"),
            )
        st.markdown(ai_explanation)
        st.caption("Explanation based on the heatmap, its monthly values, and this project's regional and district findings.")
    except Exception:
        st.markdown(fallback_explanation)
        st.caption("OpenRouter is temporarily unavailable. This explanation is computed directly from the plotted data.")

section_header("How to read the evidence", "🧭")
with st.container(border=True):
    st.markdown(
        "**Regional trend:** Modified Mann–Kendall accounts for month-to-month dependence; "
        "Benjamini–Hochberg adjusts the five regional tests together. Sen’s slope gives the rate.\n\n"
        "**District map:** Each district’s strict-mask grid-cell average is seasonally adjusted before testing. "
        "Modified Mann–Kendall accounts for serial dependence, then all 65 district-variable tests are "
        "FDR-adjusted together. Grey means the evidence did not pass q < 0.05—not that change is impossible.\n\n"
        "**What the data cannot say:** Statistical trends show patterns in the satellite/model record. "
        "They do not identify a cause, guarantee future conditions, or replace ground observations. "
        "District averages are based on the harmonized equal-area grid and strict quality masks."
    )

footer()
