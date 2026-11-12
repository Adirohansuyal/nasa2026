"""
Earth Observation — Premium Satellite Data Explorer
====================================================
Shows NASA satellite data rendered on geographic coordinates.
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import plotly.graph_objects as go
import plotly.express as px

from core.data_loader import (
    load_regional_timeseries,
    get_monthly_files,
    load_monthly_dataset,
)

from components.theme import (
    inject_theme,
    page_header,
    section_header,
    badge,
    info_banner,
    footer,
)
from components.sidebar import render_sidebar
from components.maps import satellite_layer, validity_grid, validity_statistics, VAR_UNITS
from components.charts import trend_timeseries, _apply_layout, COLORS

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Earth Observation | EARTHPULSE-X",
    page_icon="🛰️",
    layout="wide",
)

inject_theme()
render_sidebar()

# ──────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────

@st.cache_data
def get_data():
    df = load_regional_timeseries().copy()
    df["date"] = pd.to_datetime(df["month"], format="%Y-%m")
    return df

try:
    df = get_data()
    monthly_files = get_monthly_files()
except Exception as e:
    st.error(f"Data loading failed: {e}")
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "EARTH OBSERVATION",
    "Multi-Sensor Satellite Data Explorer · MODIS · SMAP · GPM",
    "🛰️",
)

info_banner(
    "Explore NASA satellite observations across Uttarakhand. "
    "Each variable is rendered on a geographic map (lat/lon) from the native "
    "equal-area grid. District boundaries overlaid for spatial context.",
    kind="info",
)

variable_options = {
    "Land Surface Temperature": "lst",
    "Vegetation Index (NDVI)": "ndvi",
    "Morning Soil Moisture": "smap_am",
    "Evening Soil Moisture": "smap_pm",
    "Precipitation": "gpm_monthly_precipitation",
}

@st.fragment(run_every="1s")
def render_observation_timeline():
    if "eo_selected_file" not in st.session_state:
        st.session_state.eo_selected_file = monthly_files[0]
    if "eo_playing" not in st.session_state:
        st.session_state.eo_playing = True
    if "eo_last_tick" not in st.session_state:
        st.session_state.eo_last_tick = time.monotonic()

    now = time.monotonic()
    elapsed = now - st.session_state.eo_last_tick
    if st.session_state.eo_playing and elapsed >= 0.95:
        current_index = monthly_files.index(st.session_state.eo_selected_file)
        steps = max(1, int(elapsed))
        st.session_state.eo_selected_file = monthly_files[(current_index + steps) % len(monthly_files)]
        st.session_state.eo_last_tick = now

    controls = st.columns([1, 5, 2, 3])
    with controls[0]:
        button_label = "⏸ Pause" if st.session_state.eo_playing else "▶ Play"
        if st.button(button_label, key="eo_playback_toggle", width="stretch"):
            st.session_state.eo_playing = not st.session_state.eo_playing
            st.session_state.eo_last_tick = time.monotonic()
    with controls[1]:
        selected_file = st.select_slider(
            "Observation timeline",
            options=monthly_files,
            value=st.session_state.eo_selected_file,
            format_func=lambda x: f"{x.split('_')[-2]}-{x.split('_')[-1].replace('.nc', '')}",
            key="eo_selected_file",
        )
    with controls[2]:
        quality = st.selectbox("Data Quality", ["Strict", "Relaxed"], key="eo_quality")
    with controls[3]:
        selected_var_label = st.selectbox(
            "Satellite Variable",
            list(variable_options.keys()),
            key="eo_satellite_variable",
        )

    selected_var = variable_options[selected_var_label]
    quality_key = quality.lower()

    # ──────────────────────────────────────────────────────────────
    # LOAD NETCDF
    # ──────────────────────────────────────────────────────────────

    try:
        ds = load_monthly_dataset(selected_file)
    except Exception as e:
        st.error(f"NetCDF loading failed: {e}")
        st.stop()

    month_label = f"{selected_file.split('_')[-2]}-{selected_file.split('_')[-1].replace('.nc', '')}"

    # ──────────────────────────────────────────────────────────────
    var_name = f"{selected_var}_{quality_key}" if selected_var != "gpm_monthly_precipitation" else "gpm_monthly_precipitation"
    valid_var = f"{var_name}_valid"
    current_valid, current_total, current_coverage, current_region_mask = validity_statistics(
        ds, selected_var, quality_key
    )

    if var_name in ds.data_vars:
        data = ds[var_name].load()
        valid_mask = ds[valid_var].values if valid_var in ds.data_vars else ~np.isnan(data.values)
        valid_vals = data.values[
            (valid_mask == 1) & np.isfinite(data.values) & current_region_mask
        ]
    else:
        valid_vals = np.array([])

    if valid_vals.size:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Mean", f"{float(valid_vals.mean()):.3f}")
        m2.metric("Min", f"{float(valid_vals.min()):.3f}")
        m3.metric("Max", f"{float(valid_vals.max()):.3f}")
        m4.metric("Std Dev", f"{float(valid_vals.std()):.3f}")
        m5.metric("Valid Pixels", f"{len(valid_vals):,}")
    else:
        st.info(f"No valid satellite pixels are available for {month_label} with the current settings.")

    current_month_index = monthly_files.index(selected_file)
    history_key = f"{selected_var}:{quality_key}"
    if st.session_state.get("eo_mean_history_key") != history_key:
        st.session_state.eo_mean_history_key = history_key
        st.session_state.eo_mean_history = []
    mean_history = st.session_state.eo_mean_history

    def _mean_for_month(file_path):
        month_ds = load_monthly_dataset(file_path)
        month_var = (
            selected_var
            if selected_var == "gpm_monthly_precipitation"
            else f"{selected_var}_{quality_key}"
        )
        if month_var not in month_ds.data_vars:
            return float("nan")
        _, _, _, month_region_mask = validity_statistics(month_ds, selected_var, quality_key)
        month_values = month_ds[month_var].values
        month_valid_name = f"{month_var}_valid"
        month_mask = (
            month_ds[month_valid_name].values
            if month_valid_name in month_ds.data_vars
            else np.isfinite(month_values)
        )
        month_valid_values = month_values[
            (month_mask == 1) & np.isfinite(month_values) & month_region_mask
        ]
        return float(month_valid_values.mean()) if month_valid_values.size else float("nan")

    history_indexes = {entry["index"] for entry in mean_history}
    if current_month_index not in history_indexes:
        previous_indexes = [index for index in history_indexes if index < current_month_index]
        first_new_index = max(previous_indexes) + 1 if previous_indexes else current_month_index
        for month_index in range(first_new_index, current_month_index + 1):
            month_file = monthly_files[month_index]
            month_name = f"{month_file.split('_')[-2]}-{month_file.split('_')[-1].replace('.nc', '')}"
            month_mean = (
                float(valid_vals.mean())
                if month_index == current_month_index and valid_vals.size
                else _mean_for_month(month_file)
            )
            mean_history.append({"index": month_index, "month": month_name, "mean": month_mean})
        mean_history.sort(key=lambda entry: entry["index"])

    visible_history = [entry for entry in mean_history if entry["index"] <= current_month_index]

    coverage_history_key = f"{selected_var}:{quality_key}"
    if st.session_state.get("eo_coverage_history_key") != coverage_history_key:
        st.session_state.eo_coverage_history_key = coverage_history_key
        st.session_state.eo_coverage_history = []
    coverage_history = st.session_state.eo_coverage_history
    known_coverage_indexes = {entry["index"] for entry in coverage_history}
    if current_month_index not in known_coverage_indexes:
        previous_coverage_indexes = [index for index in known_coverage_indexes if index < current_month_index]
        first_coverage_index = max(previous_coverage_indexes) + 1 if previous_coverage_indexes else current_month_index
        for month_index in range(first_coverage_index, current_month_index + 1):
            month_file = monthly_files[month_index]
            month_ds = ds if month_index == current_month_index else load_monthly_dataset(month_file)
            month_valid, month_total, month_coverage, _ = validity_statistics(month_ds, selected_var, quality_key)
            month_name = f"{month_file.split('_')[-2]}-{month_file.split('_')[-1].replace('.nc', '')}"
            coverage_history.append({
                "index": month_index,
                "month": month_name,
                "valid": month_valid,
                "total": month_total,
                "coverage": month_coverage,
            })
        coverage_history.sort(key=lambda entry: entry["index"])
    visible_coverage = [entry for entry in coverage_history if entry["index"] <= current_month_index]

    # SATELLITE IMAGERY — Geographic Map
    # ──────────────────────────────────────────────────────────────

    section_header(
        f"Satellite Imagery — {selected_var_label}",
        "🗺️",
        f"{month_label} · {quality} quality · EPSG:6933 → WGS84",
    )

    sat_fig = satellite_layer(ds, selected_var, quality_key, show_valid_mask=False, month_key=month_label)
    st.plotly_chart(sat_fig, width="stretch", key=f"eo_satellite_map_{month_label}_{selected_var}_{quality_key}", alt=f"{selected_var_label} satellite map for {month_label}")
    st.caption(
        "Native equal-area satellite pixels reprojected to latitude and longitude; "
        "district boundaries are outlined for context."
    )

    section_header(
        "Regional mean over time",
        "📈",
        f"Average across valid pixels · {VAR_UNITS.get(selected_var, 'index') or 'index'}",
    )
    mean_fig = go.Figure()
    visible_dates = [pd.to_datetime(f"{entry['month']}-01") for entry in visible_history]
    visible_means = [entry["mean"] for entry in visible_history]
    timeline_dates = [
        pd.to_datetime(f"{path.split('_')[-2]}-{path.split('_')[-1].replace('.nc', '')}-01")
        for path in monthly_files
    ]
    finite_means = np.asarray(visible_means, dtype=float)
    finite_means = finite_means[np.isfinite(finite_means)]
    if finite_means.size:
        observed_min = float(finite_means.min())
        observed_max = float(finite_means.max())
        padding = max((observed_max - observed_min) * 0.16, abs(float(finite_means.mean())) * 0.002, 0.01)
        mean_axis_range = [observed_min - padding, observed_max + padding]
        mean_fig.add_trace(go.Scatter(
            x=visible_dates,
            y=visible_means,
            mode="lines+markers",
            line={"color": "#35C9D0", "width": 2.5, "shape": "spline", "smoothing": 0.55},
            marker={"color": "#7BE7E0", "size": 4, "line": {"color": "#0A1020", "width": 1}},
            connectgaps=False,
            hovertemplate="%{x}<br>Regional mean: %{y:.3f}<extra></extra>",
            name="Monthly mean",
        ))
    else:
        mean_axis_range = None
    current_point = next(
        (
            entry for entry in visible_history
            if entry["index"] == current_month_index and np.isfinite(entry["mean"])
        ),
        None,
    )
    previous_points = [
        entry for entry in visible_history
        if entry["index"] < current_month_index and np.isfinite(entry["mean"])
    ]
    if current_point:
        current_date = pd.to_datetime(f"{current_point['month']}-01")
        mean_fig.add_trace(go.Scatter(
            x=[current_date], y=[current_point["mean"]],
            mode="markers", marker={"color": "#F5B84B", "size": 11, "line": {"color": "#FFF2CC", "width": 2}},
            hovertemplate="Current month · %{x|%b %Y}<br>Mean: %{y:.3f}<extra></extra>",
            name="Current month",
        ))

        if previous_points:
            previous_point = max(previous_points, key=lambda entry: entry["index"])
            change = float(current_point["mean"] - previous_point["mean"])
            neutral_band = max(abs(float(previous_point["mean"])) * 0.001, 0.001)
            if change > neutral_band:
                signal, signal_color = "Increasing", "#31C48D"
                signal_icon = "↑"
                signal_detail = f"Regional mean rose by {change:+.3f} {VAR_UNITS.get(selected_var, 'index') or 'index'} since {previous_point['month']}."
            elif change < -neutral_band:
                signal, signal_color = "Decreasing", "#EF6461"
                signal_icon = "↓"
                signal_detail = f"Regional mean fell by {change:+.3f} {VAR_UNITS.get(selected_var, 'index') or 'index'} since {previous_point['month']}."
            else:
                signal, signal_color = "Neutral", "#AAB8CC"
                signal_icon = "↔"
                signal_detail = f"Regional mean changed very little since {previous_point['month']} ({change:+.3f} {VAR_UNITS.get(selected_var, 'index') or 'index'})."
        else:
            signal, signal_color = "Building baseline", "#AAB8CC"
            signal_icon = "•"
            signal_detail = "The chart needs one more valid month before it can compare direction."
    else:
        signal, signal_color = "No valid reading", "#AAB8CC"
        signal_icon = "•"
        signal_detail = f"No valid pixels were available for {month_label}. The previous chart points are retained."

    st.markdown(
        f"""<div role="status" style="display:flex;align-items:center;gap:14px;padding:13px 17px;margin:0 0 12px;border:1px solid {signal_color}55;border-left:4px solid {signal_color};border-radius:12px;background:linear-gradient(100deg,{signal_color}16,rgba(15,26,46,.72));font-family:Urbanist,sans-serif">
<span style="font-size:24px;color:{signal_color};font-weight:800">{signal_icon}</span>
<div><div style="font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:#91A2B8">Month-to-month signal</div><strong style="font-size:17px;color:{signal_color}">{signal}</strong><div style="font-size:13px;color:#C4D0E0;margin-top:2px">{signal_detail}</div></div>
</div>""",
        unsafe_allow_html=True,
    )
    mean_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.45)",
        font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 12},
        height=320,
        margin={"l": 58, "r": 24, "t": 12, "b": 52},
        showlegend=False,
        hovermode="x",
        transition={"duration": 800, "easing": "cubic-in-out"},
        uirevision=history_key,
        xaxis={
            "title": "Month",
            "type": "date",
            "range": [timeline_dates[0], timeline_dates[-1]],
            "tickformat": "%b<br>%Y",
            "dtick": "M12",
            "gridcolor": "rgba(42,63,95,0.45)",
        },
        yaxis={
            "title": f"Mean ({VAR_UNITS.get(selected_var, 'index') or 'index'})",
            "gridcolor": "rgba(42,63,95,0.45)",
            "range": mean_axis_range,
            "fixedrange": False,
        },
    )
    if finite_means.size:
        st.plotly_chart(mean_fig, width="stretch", key=f"eo_monthly_mean_chart_{month_label}_{selected_var}_{quality_key}", alt=f"Monthly regional mean for {selected_var_label} through {month_label}")
    else:
        st.info("No valid pixels are available yet to plot a regional mean for this month.")
    st.caption(f"{len(visible_history)} month{'s' if len(visible_history) != 1 else ''} in playback · gold marker = selected month")

    section_header(
        "Observation Validity Map",
        "✅",
        f"{month_label} · {selected_var_label} · {quality} quality",
    )
    with st.container(border=True):
        st.markdown("**How to read this map**")
        st.markdown(
            "This map shows **where satellite readings are available**, not how hot, wet, or unusual those readings are. "
            "Each colored cell represents one satellite grid cell within Uttarakhand. "
            "**Teal** means a valid reading is available; **red** means a reading is missing for this month, variable, and quality filter. "
            "Areas outside the Uttarakhand outline are left blank and excluded from the counts and coverage percentage. "
            "The map's count reports valid and missing grid cells inside the state boundary. "
            "It follows autoplay, so the map and its counts update together for every month."
        )
    validity_fig = validity_grid(ds, selected_var, quality_key, month_label=month_label)
    st.plotly_chart(
        validity_fig,
        width="stretch",
        key=f"eo_validity_map_{month_label}_{selected_var}_{quality_key}",
        alt=f"Data coverage for {selected_var_label} in Uttarakhand for {month_label}",
    )

    section_header(
        "Monthly data coverage",
        "📶",
        "Valid satellite pixels inside Uttarakhand · 50% minimum coverage guide",
    )
    if current_coverage >= 50:
        coverage_status, coverage_color = "Consistent coverage", "#31C48D"
        coverage_detail = f"{current_coverage:.1f}% of in-state grid cells have valid readings ({current_valid:,} of {current_total:,}). This meets the 50% coverage guide."
    else:
        coverage_status, coverage_color = "Inconsistent coverage", "#EF6461"
        coverage_detail = f"Only {current_coverage:.1f}% of in-state grid cells have valid readings ({current_valid:,} of {current_total:,}), below the 50% coverage guide."
    st.markdown(
        f"""<div role="status" style="display:flex;align-items:center;gap:14px;padding:12px 16px;margin:0 0 10px;border:1px solid {coverage_color}55;border-left:4px solid {coverage_color};border-radius:12px;background:linear-gradient(100deg,{coverage_color}16,rgba(15,26,46,.72));font-family:Urbanist,sans-serif">
<span style="font-size:23px;color:{coverage_color};font-weight:800">{'✓' if current_coverage >= 50 else '!'}</span>
<div><div style="font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:#91A2B8">Current month · {month_label}</div><strong style="font-size:16px;color:{coverage_color}">{coverage_status}</strong><div style="font-size:13px;color:#C4D0E0;margin-top:2px">{coverage_detail}</div></div>
</div>""",
        unsafe_allow_html=True,
    )

    coverage_dates = [pd.to_datetime(f"{entry['month']}-01") for entry in visible_coverage]
    coverage_values = [entry["coverage"] for entry in visible_coverage]
    coverage_fig = go.Figure()
    coverage_fig.add_trace(go.Scatter(
        x=coverage_dates,
        y=coverage_values,
        mode="lines+markers",
        line={"color": "#63A9E8", "width": 2.5, "shape": "spline", "smoothing": 0.45},
        marker={
            "color": ["#31C48D" if value >= 50 else "#EF6461" for value in coverage_values],
            "size": 6,
            "line": {"color": "#0A1020", "width": 1},
        },
        hovertemplate="%{x|%b %Y}<br>Valid coverage: %{y:.1f}%<extra></extra>",
        name="Valid coverage",
    ))
    current_coverage_point = next(
        (entry for entry in visible_coverage if entry["index"] == current_month_index),
        None,
    )
    if current_coverage_point:
        coverage_fig.add_trace(go.Scatter(
            x=[pd.to_datetime(f"{current_coverage_point['month']}-01")],
            y=[current_coverage_point["coverage"]],
            mode="markers",
            marker={"color": "#F5B84B", "size": 11, "line": {"color": "#FFF2CC", "width": 2}},
            hovertemplate="Selected month · %{x|%b %Y}<br>Valid coverage: %{y:.1f}%<extra></extra>",
            name="Selected month",
        ))
    coverage_fig.add_hline(
        y=50,
        line_dash="dash",
        line_color="#E9A34B",
        line_width=2,
        annotation_text="50% coverage guide",
        annotation_position="top left",
        annotation_font_color="#F2C477",
    )
    coverage_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.45)",
        font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 12},
        height=300,
        margin={"l": 58, "r": 24, "t": 24, "b": 48},
        showlegend=False,
        hovermode="x",
        transition={"duration": 800, "easing": "cubic-in-out"},
        uirevision=coverage_history_key,
        xaxis={
            "title": "Month",
            "type": "date",
            "range": [timeline_dates[0], timeline_dates[-1]],
            "tickformat": "%b<br>%Y",
            "dtick": "M12",
            "gridcolor": "rgba(42,63,95,0.45)",
        },
        yaxis={"title": "Valid pixels (%)", "range": [0, 100], "ticksuffix": "%", "gridcolor": "rgba(42,63,95,0.45)"},
    )
    st.plotly_chart(
        coverage_fig,
        width="stretch",
        key=f"eo_coverage_history_chart_{month_label}_{selected_var}_{quality_key}",
        alt=f"Monthly in-state satellite data coverage through {month_label}",
    )
    st.caption(
        "Coverage at or above 50% is marked consistent; coverage below 50% is marked inconsistent. "
        "This checks data availability only, not whether the environmental readings themselves are consistent."
    )

render_observation_timeline()

# Everything below is rendered once per full page run. The timed fragment above
# owns the playback controls and the three month-specific observation views.
selected_file = st.session_state.eo_selected_file
quality = st.session_state.eo_quality
selected_var_label = st.session_state.eo_satellite_variable
selected_var = variable_options[selected_var_label]
quality_key = quality.lower()
month_label = f"{selected_file.split('_')[-2]}-{selected_file.split('_')[-1].replace('.nc', '')}"

try:
    ds = load_monthly_dataset(selected_file)
except Exception as e:
    st.error(f"NetCDF loading failed: {e}")
    st.stop()

var_name = f"{selected_var}_{quality_key}" if selected_var != "gpm_monthly_precipitation" else "gpm_monthly_precipitation"
valid_var = f"{var_name}_valid"
if var_name in ds.data_vars:
    data = ds[var_name].load()
    valid_mask = ds[valid_var].values if valid_var in ds.data_vars else ~np.isnan(data.values)
    valid_vals = data.values[(valid_mask == 1) & np.isfinite(data.values)]
else:
    valid_vals = np.array([])

# ──────────────────────────────────────────────────────────────
# SIDE-BY-SIDE COMPARISON — Strict vs Relaxed
# ──────────────────────────────────────────────────────────────

if selected_var != "gpm_monthly_precipitation":
    section_header("Quality Comparison — Strict vs Relaxed", "🔬", "Same month, same variable, different quality filters")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Strict Quality")
        st.caption("Only the cleanest, highest-confidence readings")
        fig_strict = satellite_layer(ds, selected_var, "strict", month_key=month_label)
        st.plotly_chart(fig_strict, use_container_width=True, key=f"strict_quality_map_{month_label}_{selected_var}")

    with col_right:
        st.markdown("#### Relaxed Quality")
        st.caption("More readings accepted, some borderline quality")
        fig_relaxed = satellite_layer(ds, selected_var, "relaxed", month_key=month_label)
        st.plotly_chart(fig_relaxed, use_container_width=True, key=f"relaxed_quality_map_{month_label}_{selected_var}")

# ──────────────────────────────────────────────────────────────
# PIXEL VALUE DISTRIBUTION
# ──────────────────────────────────────────────────────────────

section_header("Pixel Value Distribution", "📊")

if len(valid_vals) > 0:
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=valid_vals,
        nbinsx=35,
        marker_color=COLORS["primary"],
        marker_line_width=0,
        name="Distribution",
        hovertemplate="Value: %{x:.3f}<br>Count: %{y}<extra></extra>",
    ))
    _apply_layout(fig_hist, height=340)
    fig_hist.update_layout(
        xaxis_title="Observed Value",
        yaxis_title="Pixel Count",
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# TEMPORAL HISTORY
# ──────────────────────────────────────────────────────────────

section_header("Temporal History", "📈", "10-year regional monthly time series")

regional_map = {
    "Land Surface Temperature": ("lst_strict_mean", "LST", "K"),
    "Vegetation Index (NDVI)": ("ndvi_strict_mean", "NDVI", ""),
    "Morning Soil Moisture": ("smap_am_strict_mean", "SMAP AM", "m³/m³"),
    "Evening Soil Moisture": ("smap_pm_strict_mean", "SMAP PM", "m³/m³"),
    "Precipitation": ("gpm_monthly_precipitation_mean", "GPM", "mm"),
}

reg_col, reg_label, reg_unit = regional_map[selected_var_label]

trend_fig = trend_timeseries(
    df, "date", reg_col,
    label=reg_label, unit=reg_unit,
    show_ols=True, show_sens=True,
    height=400,
)
st.plotly_chart(trend_fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# DATASET METADATA
# ──────────────────────────────────────────────────────────────

with st.expander("📖 Dataset Metadata"):
    st.write("**Dimensions:**")
    st.json(dict(ds.sizes))
    st.write("**Data Variables:**")
    st.write(list(ds.data_vars))
    st.write("**Attributes:**")
    st.json(dict(ds.attrs))

footer()
