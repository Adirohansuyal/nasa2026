"""
Predictive Intelligence — "What Will Happen Next?"
====================================================
Answers NASA's implicit 5th question: SO WHAT?

Features:
  ① 3–6 month point forecast with 80% + 95% uncertainty bands
  ② Variable-by-variable: "In August 2026, LST will be X ± Y K"
  ③ Multi-variable Drought Risk Score for the next season
  ④ Walk-forward cross-validation (model skill certificate)
  ⑤ AI narrative: interprets forecast + risk in plain English
"""

import os
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from groq import Groq
from config import BOUNDARIES_DIR

from core.data_loader import (
    get_monthly_files,
    load_district_boundaries,
    load_monthly_dataset,
    load_regional_timeseries,
    load_seasonal_anomalies,
    load_spatial_anomaly_events,
)
from core.early_warning_engine import compute_district_risk_from_spatial
from core.spatial_hotspot_engine import cluster_spatial_anomaly_points
from core.openrouter_client import explain_text
from core.forecast_engine import (
    run_all_forecasts,
    run_variable_forecast,
    compute_drought_risk_score,
    drought_risk_label,
    walk_forward_cv,
    SeasonalARModel,
    select_model_config,
)
from core.spatial_trend_engine import build_district_monthly_series
from core.lagged_dynamics import (
    fit_ridge_var,
    forecast_var,
    granger_screen,
    prepare_anomaly_matrix,
)
from components.theme import (
    inject_theme,
    page_header,
    section_header,
    info_banner,
    ai_card,
    footer,
)
from components.sidebar import render_sidebar
from components.charts import _apply_layout, COLORS
from components.maps import choropleth_map, satellite_layer, spatial_hotspot_map

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Predictive Intelligence | EARTHPULSE-X",
    page_icon="🔮",
    layout="wide",
)

inject_theme()
render_sidebar()

_GROQ_CLIENT = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# ──────────────────────────────────────────────────────────────
# VARIABLE CONFIG  (mirrors Trend Detective)
# ──────────────────────────────────────────────────────────────

VAR_CONFIG = {
    "LST":     {"col": "lst_strict_mean",                   "label": "Land Surface Temperature", "unit": "K",       "emoji": "🌡️"},
    "NDVI":    {"col": "ndvi_strict_mean",                  "label": "Vegetation Greenness",      "unit": "index",   "emoji": "🌿"},
    "SMAP_AM": {"col": "smap_am_strict_mean",               "label": "Morning Soil Moisture",     "unit": "m³/m³",  "emoji": "💧"},
    "SMAP_PM": {"col": "smap_pm_strict_mean",               "label": "Evening Soil Moisture",     "unit": "m³/m³",  "emoji": "💧"},
    "GPM":     {"col": "gpm_monthly_precipitation_mean",    "label": "Precipitation",             "unit": "mm/mo",  "emoji": "🌧️"},
}

# Variable accent colors
VAR_COLORS = {
    "LST":     "#EF6461",
    "NDVI":    "#31C48D",
    "SMAP_AM": "#6C8EE6",
    "SMAP_PM": "#A78BFA",
    "GPM":     "#35C9D0",
}


def _build_forecast_echoes(frame: pd.DataFrame, forecasts: dict) -> list[dict]:
    """Match each future multi-signal forecast with the closest historical same-month pattern."""
    signal_keys = [key for key in VAR_CONFIG if key in forecasts]
    if len(signal_keys) < 3:
        return []

    echoes = []
    forecast_dates = next(iter(forecasts.values()))["forecast_dates"]
    for step, future_date in enumerate(forecast_dates):
        month_history = frame.loc[frame["date"].dt.month == future_date.month].copy()
        if month_history.empty:
            continue

        reference = {}
        future_z = {}
        historical_z = {}
        for key in signal_keys:
            column = VAR_CONFIG[key]["col"]
            values = pd.to_numeric(month_history[column], errors="coerce")
            mean = float(values.mean())
            std = float(values.std(ddof=1))
            if not np.isfinite(std) or std <= 1e-12:
                continue
            reference[key] = (mean, std)
            future_z[key] = (float(forecasts[key]["point"][step]) - mean) / std
            historical_z[key] = (values - mean) / std

        usable_keys = list(future_z)
        if len(usable_keys) < 3:
            continue

        candidates = []
        for row_index, row in month_history.iterrows():
            candidate_values = {}
            for key in usable_keys:
                value = pd.to_numeric(pd.Series([row[VAR_CONFIG[key]["col"]]]), errors="coerce").iloc[0]
                if pd.notna(value):
                    candidate_values[key] = float(historical_z[key].loc[row_index])
            shared = [key for key in usable_keys if key in candidate_values]
            if len(shared) < 3:
                continue
            gap = float(np.sqrt(np.mean([
                (candidate_values[key] - future_z[key]) ** 2 for key in shared
            ])))
            candidates.append({
                "date": row["date"],
                "gap": gap,
                "values_z": candidate_values,
                "shared": shared,
            })

        candidates.sort(key=lambda item: item["gap"])
        if candidates:
            echoes.append({
                "future_date": future_date,
                "forecast_z": future_z,
                "candidates": candidates,
                "signals": usable_keys,
            })
    return echoes


@st.cache_data(show_spinner="Summarising historical district anomaly exposure…")
def _cached_district_anomaly_history() -> pd.DataFrame:
    """Reuse the project district risk aggregation as a historical exposure proxy."""
    spatial = load_spatial_anomaly_events()
    boundaries = load_district_boundaries()
    return compute_district_risk_from_spatial(
        spatial, month_filter=None, boundaries_gdf=boundaries, threshold=3.0
    )


@st.cache_data(ttl=3600, show_spinner="Training district forecasts from the harmonized satellite grids…")
def _cached_district_satellite_forecasts(horizon: int) -> pd.DataFrame:
    """Fit separate models to district-level area averages from each monthly grid."""
    monthly = build_district_monthly_series(
        get_monthly_files(),
        str(BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"),
    )
    forecasts = []
    for (district, variable), group in monthly.groupby(["district_name", "variable"]):
        series = group.dropna(subset=["value"]).sort_values("month").reset_index(drop=True)
        if len(series) < 60:
            continue
        values = series["value"].to_numpy(dtype=float)
        dates = pd.to_datetime(series["month"])
        months = dates.dt.month.to_numpy(dtype=int)
        config = select_model_config(values, months, h=horizon, min_train=60, n_splits=4)
        model = SeasonalARModel(**config, n_bootstrap=0).fit(values, months)
        point = model._single_forecast_path(horizon)
        seasonal_mean = series.assign(month_number=months).groupby("month_number")["value"].mean()
        seasonal_std = series.assign(month_number=months).groupby("month_number")["value"].std(ddof=1)
        last_date = dates.iloc[-1]
        for step, value in enumerate(point):
            forecast_date = last_date + pd.DateOffset(months=step + 1)
            month_mean = float(seasonal_mean.get(forecast_date.month, np.nan))
            month_std = float(seasonal_std.get(forecast_date.month, np.nan))
            anomaly_z = (float(value) - month_mean) / month_std if np.isfinite(month_std) and month_std > 1e-12 else 0.0
            forecasts.append({
                "district_name": district,
                "variable": variable,
                "forecast_date": forecast_date,
                "forecast_value": float(value),
                "seasonal_mean": month_mean,
                "seasonal_anomaly_z": float(anomaly_z),
                "valid_months": int(len(series)),
                "mean_coverage_pct": float(series["coverage_pct"].mean()),
            })
    return pd.DataFrame(forecasts)

# ──────────────────────────────────────────────────────────────
# DATA LOAD
# ──────────────────────────────────────────────────────────────

@st.cache_data
def load_all():
    df = load_regional_timeseries().copy()
    df["date"] = pd.to_datetime(df["month"], format="%Y-%m")
    anomalies = load_seasonal_anomalies()
    return df, anomalies

try:
    df, anomalies = load_all()
except Exception as e:
    st.error(f"❌ Data load failed: {e}")
    st.stop()

# ──────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔮 Forecast Settings")
    horizon = st.slider(
        "Forecast Horizon (months)", min_value=1, max_value=6, value=6, step=1,
        help="How many months ahead to forecast"
    )
    show_cv = st.checkbox("Show model skill (CV)", value=True)
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.72rem; color:#6B7B91;'>"
        "Model: Rolling-CV-tuned AR + Ridge<br>"
        "Prediction bands: bootstrap + held-out error calibration<br>"
        "Data: 126 months (Apr 2015 – Sep 2025)"
        "</div>", unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "PREDICTIVE INTELLIGENCE",
    f"Multi-Variable Outlook · Uttarakhand · Forecast anchored after {df['date'].max():%b %Y}",
    "🔮",
)

info_banner(
    "**NASA's 5th Implicit Question:** *So What?* — "
    f"The available satellite record ends in **{df['date'].max():%B %Y}**. This page extends that record by "
    f"**{horizon} modelled months**, shows how uncertain those estimates are, and combines several signals into a "
    "**Drought Risk Score**. This is an outlook from the last data month, not a live forecast for today's date.",
    kind="info",
)

# ──────────────────────────────────────────────────────────────
# 1. RUN ALL FORECASTS  (cached)
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _cached_forecasts(horizon: int, run_cv: bool):
    return run_all_forecasts(
        df, "date", VAR_CONFIG, h=horizon, run_cv=run_cv
    )

with st.spinner("🔮 Running forecasts for all 5 variables…"):
    all_forecasts = _cached_forecasts(horizon, show_cv)

# Check how many variables worked
ok_vars = {k: v for k, v in all_forecasts.items() if "error" not in v}
err_vars = {k: v for k, v in all_forecasts.items() if "error" in v}
if err_vars:
    for k, v in err_vars.items():
        st.warning(f"⚠️ {k}: {v['error']}")

if not ok_vars:
    st.error("No variables could be forecast. Check data availability.")
    st.stop()

# ──────────────────────────────────────────────────────────────
# 2. FORECAST HEADLINE CARDS
# ──────────────────────────────────────────────────────────────

section_header("First Modelled Month — Headline Numbers", "📡", "Point estimate ± 95% uncertainty after the last observed month")

cols = st.columns(len(ok_vars))
for col_widget, (key, fc) in zip(cols, ok_vars.items()):
    meta = VAR_CONFIG[key]
    color = VAR_COLORS.get(key, "#35C9D0")

    # First forecast step = month after the latest observation in the source data.
    next_val   = fc["point"][0]
    next_lo95  = fc["lower_95"][0]
    next_hi95  = fc["upper_95"][0]
    uncertainty = (next_hi95 - next_lo95) / 2
    next_date  = fc["forecast_dates"][0]

    # Historical mean for comparison
    hist_mean = np.nanmean(fc["historical_values"])
    delta = next_val - hist_mean
    delta_str = f"{'+' if delta >= 0 else ''}{delta:.3f} {meta['unit']} vs mean"

    with col_widget:
        st.markdown(f"""
        <div class="glass-card" style="text-align:center; min-height:160px;
             border-top: 3px solid {color}; padding:18px 12px;">
          <div style="font-size:22px; margin-bottom:4px;">{meta['emoji']}</div>
          <div style="font-size:0.7rem; color:#6B7B91; margin-bottom:2px;">
              {next_date.strftime('%b %Y')}
          </div>
          <div style="font-size:1.45rem; font-weight:800; color:{color}; letter-spacing:-0.02em;">
              {next_val:.3f}
          </div>
          <div style="font-size:0.72rem; color:#AAB8CC;">
              {meta['unit']}
          </div>
          <div style="font-size:0.68rem; color:#6B7B91; margin-top:6px;">
              ±{uncertainty:.3f} (95% PI)
          </div>
          <div style="font-size:0.68rem; color:{'#EF6461' if delta < 0 else '#31C48D'}; margin-top:3px;">
              {delta_str}
          </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 3. FULL FORECAST CHART — selected variable
# ──────────────────────────────────────────────────────────────

section_header("Forecast with Uncertainty Bands", "📈", "Historical · Point forecast · 80% & 95% prediction intervals")

sel_key = st.selectbox(
    "Select variable to inspect",
    list(ok_vars.keys()),
    format_func=lambda k: f"{VAR_CONFIG[k]['emoji']}  {VAR_CONFIG[k]['label']}",
    key="forecast_var_select",
)

fc = ok_vars[sel_key]
meta = VAR_CONFIG[sel_key]
color = VAR_COLORS.get(sel_key, "#35C9D0")

# ── Build the chart ──
fig = go.Figure()

hist_dates = fc["historical_dates"]
hist_vals  = fc["historical_values"]
fitted_vals = fc["in_sample_fitted"]
fc_dates   = fc["forecast_dates"]
point      = fc["point"]
lo80, hi80 = fc["lower_80"], fc["upper_80"]
lo95, hi95 = fc["lower_95"], fc["upper_95"]

# 95% PI shaded area
fig.add_trace(go.Scatter(
    x=list(fc_dates) + list(fc_dates[::-1]),
    y=list(hi95) + list(lo95[::-1]),
    fill="toself",
    fillcolor="rgba(53,201,208,0.08)",
    line=dict(color="rgba(0,0,0,0)"),
    name="95% Prediction Interval",
    showlegend=True,
    hoverinfo="skip",
))

# 80% PI shaded area
fig.add_trace(go.Scatter(
    x=list(fc_dates) + list(fc_dates[::-1]),
    y=list(hi80) + list(lo80[::-1]),
    fill="toself",
    fillcolor="rgba(53,201,208,0.16)",
    line=dict(color="rgba(0,0,0,0)"),
    name="80% Prediction Interval",
    showlegend=True,
    hoverinfo="skip",
))

# Historical observed line
fig.add_trace(go.Scatter(
    x=hist_dates,
    y=hist_vals,
    mode="lines",
    name="Historical (observed)",
    line=dict(color=color, width=1.8),
    hovertemplate=f"<b>%{{x|%Y-%m}}</b><br>{meta['label']}: %{{y:.4f}} {meta['unit']}<extra></extra>",
))

# In-sample fitted line
if fitted_vals is not None:
    fig.add_trace(go.Scatter(
        x=hist_dates,
        y=fitted_vals,
        mode="lines",
        name="Model fit (in-sample)",
        line=dict(color="#E9A34B", width=1.2, dash="dot"),
        opacity=0.7,
        hovertemplate=f"Fit: %{{y:.4f}} {meta['unit']}<extra></extra>",
    ))

# Vertical separator at last historical date
last_date = fc["last_date"]
fig.add_vrect(
    x0=last_date, x1=last_date + pd.DateOffset(days=5),
    fillcolor="#6B7B91", opacity=0.25,
    line_width=0,
    annotation_text="← History | Forecast →",
    annotation_font_color="#6B7B91",
    annotation_font_size=11,
    annotation_position="top left",
)

# Point forecast line
fig.add_trace(go.Scatter(
    x=fc_dates,
    y=point,
    mode="lines+markers",
    name=f"Point forecast ({horizon}mo)",
    line=dict(color=color, width=2.5, dash="dash"),
    marker=dict(size=7, color=color, symbol="circle"),
    hovertemplate=(
        f"<b>%{{x|%b %Y}}</b><br>"
        f"Forecast: %{{y:.4f}} {meta['unit']}<extra></extra>"
    ),
))

# Annotate each forecast point with value + CI
for i, (fd, pv, l95, h95) in enumerate(zip(fc_dates, point, lo95, hi95)):
    fig.add_annotation(
        x=fd,
        y=h95,
        text=f"{pv:.3f}",
        showarrow=False,
        font=dict(size=9, color=color, family="Urbanist"),
        yanchor="bottom",
        yshift=4,
    )

_apply_layout(fig, height=500)
fig.update_layout(
    yaxis_title=f"{meta['label']} ({meta['unit']})",
    legend=dict(
        orientation="h", yanchor="bottom", y=-0.22,
        x=0.5, xanchor="center",
        font=dict(size=11, family="Urbanist"),
        bgcolor="rgba(0,0,0,0)",
    ),
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    f"🔵 Teal = observed · 🟡 Dashed = model fit · "
    f"Bold dashed = point forecast · Dark fill = 80% PI · Light fill = 95% PI"
)

# ── Forecast table ──
fc_table_rows = []
for i, fd in enumerate(fc_dates):
    label_lo, _ = drought_risk_label(50)   # placeholder
    fc_table_rows.append({
        "Month":        fd.strftime("%B %Y"),
        "Forecast":     f"{point[i]:.4f}",
        "Unit":         meta["unit"],
        "80% PI":       f"[{lo80[i]:.4f}, {hi80[i]:.4f}]",
        "95% PI":       f"[{lo95[i]:.4f}, {hi95[i]:.4f}]",
        "Uncertainty±": f"±{(hi95[i]-lo95[i])/2:.4f}",
    })

st.markdown(f"#### {meta['label']} — Full forecast table")
st.dataframe(pd.DataFrame(fc_table_rows), hide_index=True, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 4. DROUGHT RISK SCORE
# ──────────────────────────────────────────────────────────────

section_header("Drought Risk Score — Next Season", "🏜️", "Composite multi-signal risk index (0 = no risk · 100 = extreme drought)")

info_banner(
    "The Drought Risk Score fuses all 4 sensor forecasts (LST, NDVI, SMAP, GPM) "
    "weighted by a PDSI-inspired scheme. Signals are z-scored against their "
    "10-year climatological baseline. Higher score = more drought-like conditions.",
    kind="warning",
)

# Build climatological baselines from anomaly data
def _clim_stats(key: str) -> tuple[float, float]:
    """Extract climatological mean + std from the historical series."""
    if key in ok_vars:
        v = ok_vars[key]["historical_values"]
        return float(np.nanmean(v)), float(np.nanstd(v))
    return 0.0, 1.0

# Check if all 4 drought-signal variables are available
drought_vars = ["LST", "NDVI", "SMAP_AM", "GPM"]
drought_ok = all(k in ok_vars for k in drought_vars)

if not drought_ok:
    missing = [k for k in drought_vars if k not in ok_vars]
    st.warning(f"Missing variables for full drought score: {missing}. Showing partial score.")

# Pad missing variables with climatological mean (zero anomaly)
def _get_forecast_array(key: str) -> np.ndarray:
    if key in ok_vars:
        return ok_vars[key]["point"]
    clim_mean, _ = _clim_stats(key)
    return np.full(horizon, clim_mean)

lst_fc   = _get_forecast_array("LST")
ndvi_fc  = _get_forecast_array("NDVI")
smap_fc  = _get_forecast_array("SMAP_AM")
gpm_fc   = _get_forecast_array("GPM")

lst_mean,  lst_std  = _clim_stats("LST")
ndvi_mean, ndvi_std = _clim_stats("NDVI")
smap_mean, smap_std = _clim_stats("SMAP_AM")
gpm_mean,  gpm_std  = _clim_stats("GPM")

risk_scores = compute_drought_risk_score(
    lst_fc,   lst_mean,   lst_std,
    ndvi_fc,  ndvi_mean,  ndvi_std,
    smap_fc,  smap_mean,  smap_std,
    gpm_fc,   gpm_mean,   gpm_std,
)

# Get forecast dates from any available variable
any_fc = next(iter(ok_vars.values()))
fc_dates_risk = any_fc["forecast_dates"][:horizon]
month_labels  = [d.strftime("%b %Y") for d in fc_dates_risk]

# ── Risk gauge chart ──
risk_fig = go.Figure()

bar_colors = []
for score in risk_scores:
    _, hex_c = drought_risk_label(score)
    bar_colors.append(hex_c)

risk_fig.add_trace(go.Bar(
    x=month_labels,
    y=risk_scores,
    marker=dict(
        color=bar_colors,
        line=dict(color="rgba(0,0,0,0)", width=0),
    ),
    text=[f"{s:.0f}" for s in risk_scores],
    textposition="outside",
    textfont=dict(size=13, family="Urbanist", color="#F1F5FC"),
    hovertemplate="<b>%{x}</b><br>Drought Risk: %{y:.1f}/100<extra></extra>",
    name="Drought Risk Score",
))

# Reference lines
for level, label, color in [(75, "Extreme", "#EF6461"), (60, "High", "#E9A34B"),
                              (45, "Moderate", "#F5D842"), (30, "Low", "#31C48D")]:
    risk_fig.add_hline(
        y=level,
        line_dash="dot",
        line_color=color,
        line_width=1,
        annotation_text=label,
        annotation_font_color=color,
        annotation_font_size=10,
        annotation_position="right",
    )

_apply_layout(risk_fig, height=360)
risk_fig.update_layout(
    yaxis=dict(title="Drought Risk Score (0–100)", range=[0, 105]),
    showlegend=False,
    bargap=0.35,
)
st.plotly_chart(risk_fig, use_container_width=True)

# ── Risk summary cards ──
risk_cols = st.columns(min(len(risk_scores), 6))
for col_w, (month, score) in zip(risk_cols, zip(month_labels, risk_scores)):
    label, hex_c = drought_risk_label(score)
    with col_w:
        st.markdown(f"""
        <div class="glass-card" style="text-align:center; padding:14px 8px;
             border-top: 3px solid {hex_c}; min-height:110px;">
          <div style="font-size:0.68rem; color:#6B7B91; margin-bottom:4px;">{month}</div>
          <div style="font-size:1.6rem; font-weight:800; color:{hex_c};">{score:.0f}</div>
          <div style="font-size:0.7rem; color:#AAB8CC; margin-top:2px;">/100</div>
          <div style="font-size:0.72rem; color:{hex_c}; margin-top:6px; font-weight:600;">{label}</div>
        </div>
        """, unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 4A. FORECAST ECHOES — compare each forecast with past same-season patterns
# ──────────────────────────────────────────────────────────────

section_header(
    "Forecast Echoes · Have we seen a similar pattern before?",
    "🪞",
    "Compare each future month with past months from the same time of year",
)
st.markdown(
    "A forecast is easier to picture when we compare its **five-signal pattern** with real past observations. "
    "For each future month, this view finds the closest historical match from the same calendar month, using temperature, "
    "vegetation, morning/evening soil moisture, and rainfall. The match is a resemblance in the data—not a claim that the same event will happen again."
)

forecast_echoes = _build_forecast_echoes(df, ok_vars)
if forecast_echoes:
    brief_cols = st.columns(len(forecast_echoes))
    drought_weights = {"LST": 0.20, "NDVI": 0.25, "SMAP_AM": 0.35, "GPM": 0.20}
    drought_direction = {"LST": 1.0, "NDVI": -1.0, "SMAP_AM": -1.0, "GPM": -1.0}
    for step, (brief_col, echo) in enumerate(zip(brief_cols, forecast_echoes)):
        score = float(risk_scores[step]) if step < len(risk_scores) else float("nan")
        risk_label, risk_color = drought_risk_label(score)
        pressure_terms = {}
        for key, weight in drought_weights.items():
            if key not in ok_vars:
                continue
            historic = np.asarray(ok_vars[key]["historical_values"], dtype=float)
            spread = float(np.nanstd(historic))
            if not np.isfinite(spread) or spread <= 1e-12:
                continue
            z_value = (float(ok_vars[key]["point"][step]) - float(np.nanmean(historic))) / spread
            pressure_terms[key] = weight * drought_direction[key] * z_value
        positive_pressure = {key: value for key, value in pressure_terms.items() if value > 0}
        main_pressure = max(positive_pressure, key=positive_pressure.get) if positive_pressure else None
        departure_key = max(echo["forecast_z"], key=lambda key: abs(echo["forecast_z"][key]))
        departure = echo["forecast_z"][departure_key]
        with brief_col:
            st.markdown(
                f"""<div class="glass-card" style="height:100%;min-height:155px;padding:13px;border-top:3px solid {risk_color};">
<div style="font-size:.72rem;color:#AAB8CC;letter-spacing:.04em">{echo['future_date'].strftime('%b %Y')}</div>
<div style="font-size:1.25rem;font-weight:800;color:{risk_color};margin:5px 0">{score:.0f}<span style="font-size:.72rem;color:#91A2B8"> / 100 · {risk_label.split()[-1]}</span></div>
<div style="font-size:.72rem;color:#D3DCE8">Largest seasonal shift<br><b>{VAR_CONFIG[departure_key]['emoji']} {VAR_CONFIG[departure_key]['label']}</b> · {departure:+.1f} usual-month SD</div>
<div style="font-size:.68rem;color:#91A2B8;margin-top:7px">Main drought pressure: {VAR_CONFIG[main_pressure]['label'] if main_pressure else 'No signal adds clear upward pressure'}</div>
</div>""",
                unsafe_allow_html=True,
            )
    st.caption("The risk number is a model-built indicator, not a percentage chance of drought. ‘Usual-month SD’ compares a forecast with past observations from that same calendar month.")

    echo_labels = [echo["future_date"].strftime("%B %Y") for echo in forecast_echoes]
    selected_echo_label = st.selectbox("Choose a forecast month to inspect its historical echo", echo_labels, key="forecast_echo_month")
    selected_echo = forecast_echoes[echo_labels.index(selected_echo_label)]
    closest = selected_echo["candidates"][0]
    common_signals = [key for key in selected_echo["signals"] if key in closest["values_z"]]
    strongest_echo_signal = max(common_signals, key=lambda key: abs(closest["values_z"][key]))
    echo_z = closest["values_z"][strongest_echo_signal]
    echo_month = pd.Timestamp(closest["date"]).strftime("%B %Y")

    echo_summary, echo_chart = st.columns([0.85, 1.35], gap="medium")
    with echo_summary:
        with st.container(border=True):
            st.markdown(f"### {selected_echo_label}: closest past echo")
            st.markdown(f"## {echo_month}")
            st.write(
                f"The closest same-month pattern in the record is **{echo_month}**. "
                f"Its multi-signal pattern gap is **{closest['gap']:.2f} standard deviations** on average; lower means closer."
            )
            past_unusual = abs(echo_z) >= 2
            st.markdown(
                f"**Past-month clue:** {VAR_CONFIG[strongest_echo_signal]['emoji']} "
                f"{VAR_CONFIG[strongest_echo_signal]['label']} was **{echo_z:+.1f} usual-month SD** "
                f"in that historical month{'—an unusually high/low reading by a 2-SD guide' if past_unusual else '—within the 2-SD guide used here'}."
            )
            st.caption("This describes what the satellite record measured then. It does not identify a news event or prove a cause.")
            if len(selected_echo["candidates"]) > 1:
                st.markdown("**Other close matches**")
                alternatives = selected_echo["candidates"][1:4]
                st.write(" · ".join(
                    f"{pd.Timestamp(item['date']).strftime('%b %Y')} (gap {item['gap']:.2f})"
                    for item in alternatives
                ))

    with echo_chart:
        st.markdown("#### Forecast pattern vs the past match")
        st.caption("Each bar shows how far a signal sits above or below its usual level for that month of the year. This puts different units on one readable scale.")
        display_keys = [key for key in selected_echo["signals"] if key in closest["values_z"]]
        labels = [f"{VAR_CONFIG[key]['emoji']} {VAR_CONFIG[key]['label']}" for key in display_keys]
        compare_fig = go.Figure()
        compare_fig.add_trace(go.Bar(
            x=labels, y=[selected_echo["forecast_z"][key] for key in display_keys],
            name="Forecast", marker_color="#35C9D0",
            hovertemplate="%{x}<br>Forecast: %{y:+.2f} usual-month SD<extra></extra>",
        ))
        compare_fig.add_trace(go.Bar(
            x=labels, y=[closest["values_z"][key] for key in display_keys],
            name=f"Past match · {echo_month}", marker_color="#A78BFA",
            hovertemplate="%{x}<br>Past reading: %{y:+.2f} usual-month SD<extra></extra>",
        ))
        compare_fig.add_hline(y=0, line_color="rgba(210,220,235,.45)", line_width=1)
        compare_fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,26,46,.48)",
            font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 11},
            height=390, margin={"l": 52, "r": 12, "t": 28, "b": 100},
            barmode="group", bargap=0.24, legend={"orientation": "h", "y": 1.12, "x": 0},
            xaxis={"tickangle": -25, "gridcolor": "rgba(42,63,95,.35)"},
            yaxis={"title": "Difference from that month’s usual level (SD)", "gridcolor": "rgba(42,63,95,.45)"},
        )
        st.plotly_chart(compare_fig, use_container_width=True, config={"displayModeBar": False})

    map_variable = {
        "LST": "lst", "NDVI": "ndvi", "SMAP_AM": "smap_am",
        "SMAP_PM": "smap_pm", "GPM": "gpm_monthly_precipitation",
    }.get(sel_key)
    st.markdown(f"#### 🗺️ Satellite map from the past match · {echo_month}")
    with st.container(border=True):
        try:
            month_files = get_monthly_files()
            past_month_key = pd.Timestamp(closest["date"]).strftime("%Y-%m")
            past_file = next((
                path for path in month_files
                if os.path.basename(path).replace(".nc", "").endswith(past_month_key.replace("-", "_"))
            ), None)
            if past_file and map_variable:
                past_ds = load_monthly_dataset(past_file)
                past_map = satellite_layer(past_ds, map_variable, "strict")
                past_map.update_layout(height=440, margin={"l": 8, "r": 8, "t": 25, "b": 8})
                st.plotly_chart(
                    past_map, use_container_width=True,
                    key=f"forecast_echo_map_{past_month_key}_{sel_key}",
                    config={"displayModeBar": False},
                )
                st.caption(f"This is an observed {VAR_CONFIG[sel_key]['label']} map for {echo_month}, not a map of future conditions.")
            else:
                st.info("A matching monthly satellite map is not available for this historical echo.")
        except Exception as exc:
            st.info(f"Historical map unavailable for this match: {exc}")
else:
    st.info("Not enough overlapping historical signals are available to build a reliable past-pattern comparison.")

# ──────────────────────────────────────────────────────────────
# 5. LAGGED CROSS-VARIABLE DYNAMICS + WHAT-IF SCENARIO
# ──────────────────────────────────────────────────────────────

section_header(
    "Lagged Earth-System Links · What can lead what?",
    "🔗",
    "A multivariable monthly model checks whether earlier signals help anticipate later ones",
)
st.markdown(
    "Rain can come before greener vegetation; hotter-than-usual conditions can come before drier soil. "
    "This lab learns those **month-by-month links together**, instead of forecasting each signal in isolation. "
    "Choose a one-month scenario and compare the model’s target outlook with its no-change baseline."
)

st.caption(
    "How to read this carefully: the model uses monthly regional averages, so it can test 1–3 month delays, not a 2–4 week delay. "
    "A Granger link means one signal’s past improves prediction of another after accounting for the other signals’ past; it does not prove physical cause."
)

baseline_path = None
dynamics_frame = None
dynamics_keys = []
try:
    dynamics_columns = {key: VAR_CONFIG[key]["col"] for key in VAR_CONFIG if key in ok_vars}
    dynamics_frame, dynamics_scales, seasonal_means = prepare_anomaly_matrix(
        df, "date", dynamics_columns
    )
    dynamics_keys = list(dynamics_frame.columns)
    lag_depth = st.select_slider(
        "How many past months should the model look at?",
        options=[1, 2, 3], value=3, key="cross_var_lag_depth",
        help="A three-month setting checks whether the previous one, two, and three months help predict this month.",
    )
    if len(dynamics_keys) < 3:
        st.warning("The lag model needs at least three complete environmental signals; the available data does not meet that requirement.")
    else:
        z_values = dynamics_frame[dynamics_keys].to_numpy(dtype=float)
        var_model = fit_ridge_var(z_values, lags=lag_depth, alpha=1.0)
        granger_links = granger_screen(z_values, dynamics_keys, lags=lag_depth)
        baseline_path = forecast_var(var_model, z_values, steps=horizon)

        label_to_key = {f"{VAR_CONFIG[key]['emoji']} {VAR_CONFIG[key]['label']}": key for key in dynamics_keys}
        control_cols = st.columns(4)
        with control_cols[0]:
            source_label = st.selectbox(
                "Set a signal for next month", list(label_to_key),
                index=list(label_to_key).index("🌧️ Precipitation") if "🌧️ Precipitation" in label_to_key else 0,
                key="cross_var_source",
            )
        source_key = label_to_key[source_label]
        target_labels = [label for label, key in label_to_key.items() if key != source_key]
        default_target_label = next((label for label, key in label_to_key.items() if key == "NDVI" and key != source_key), target_labels[0])
        with control_cols[1]:
            target_label = st.selectbox(
                "See the response in", target_labels,
                index=target_labels.index(default_target_label), key="cross_var_target",
            )
        target_key = label_to_key[target_label]
        with control_cols[2]:
            scenario_z = st.slider(
                "Source signal vs its usual level (SD)", -2.5, 2.5, 1.0, 0.25,
                key="cross_var_scenario_z",
                help="0 = usual level; +1 = one standard deviation above its usual level; −1 = one below.",
            )
        with control_cols[3]:
            response_lead = st.select_slider(
                "Check target after", options=list(range(1, horizon + 1)),
                value=min(2, horizon), format_func=lambda n: f"{n} month{'s' if n != 1 else ''}",
                key="cross_var_response_lead",
            )

        key_index = {key: index for index, key in enumerate(dynamics_keys)}
        scenario_path = forecast_var(
            var_model,
            z_values,
            steps=horizon,
            intervention=(0, key_index[source_key], float(scenario_z)),
        )
        target_index = key_index[target_key]
        source_index = key_index[source_key]
        selected_target_date = ok_vars[target_key]["forecast_dates"][response_lead - 1]
        target_scale = dynamics_scales[target_key]
        target_season_mean = seasonal_means.get(selected_target_date.month, {}).get(target_key, 0.0)
        baseline_target = target_season_mean + baseline_path[response_lead - 1, target_index] * target_scale
        scenario_target = target_season_mean + scenario_path[response_lead - 1, target_index] * target_scale
        target_shift = scenario_target - baseline_target

        source_date = ok_vars[source_key]["forecast_dates"][0]
        source_usual = seasonal_means.get(source_date.month, {}).get(source_key, 0.0)
        scenario_source_value = source_usual + scenario_z * dynamics_scales[source_key]
        source_meta = VAR_CONFIG[source_key]
        target_meta = VAR_CONFIG[target_key]
        summary_cols = st.columns(3)
        summary_cols[0].metric(
            "Scenario set for next month",
            f"{scenario_source_value:.3f} {source_meta['unit']}",
            f"{scenario_z:+.2f} SD vs usual {source_date:%b}",
        )
        summary_cols[1].metric(
            f"{target_meta['label']} · {selected_target_date:%b %Y}",
            f"{scenario_target:.4f} {target_meta['unit']}",
            f"{target_shift:+.4f} {target_meta['unit']} vs model baseline",
        )
        summary_cols[2].metric(
            "Monthly signals available",
            f"{len(dynamics_keys)}",
            f"{len(dynamics_frame)} complete months · {lag_depth}-month lag model",
        )

        response_fig = go.Figure()
        recent_target = df[["date", target_meta["col"]]].dropna().tail(24)
        response_fig.add_trace(go.Scatter(
            x=recent_target["date"], y=recent_target[target_meta["col"]],
            mode="lines", name="Observed history",
            line={"color": "#71829A", "width": 1.8},
            hovertemplate="%{x|%b %Y}<br>Observed: %{y:.4f} " + target_meta["unit"] + "<extra></extra>",
        ))
        target_dates = ok_vars[target_key]["forecast_dates"][:horizon]
        target_means = [seasonal_means.get(date.month, {}).get(target_key, 0.0) for date in target_dates]
        base_physical = [target_means[i] + baseline_path[i, target_index] * target_scale for i in range(horizon)]
        scenario_physical = [target_means[i] + scenario_path[i, target_index] * target_scale for i in range(horizon)]
        response_fig.add_trace(go.Scatter(
            x=target_dates, y=base_physical, mode="lines+markers", name="VAR baseline",
            line={"color": "#AAB8CC", "width": 2, "dash": "dot"},
            hovertemplate="%{x|%b %Y}<br>Baseline: %{y:.4f} " + target_meta["unit"] + "<extra></extra>",
        ))
        response_fig.add_trace(go.Scatter(
            x=target_dates, y=scenario_physical, mode="lines+markers", name="What-if scenario",
            line={"color": "#35C9D0", "width": 3},
            hovertemplate="%{x|%b %Y}<br>Scenario: %{y:.4f} " + target_meta["unit"] + "<extra></extra>",
        ))
        # Plotly's add_vline can fail on pandas Timestamps in some versions.
        response_fig.add_shape(
            type="line", x0=selected_target_date, x1=selected_target_date,
            y0=0, y1=1, yref="paper", line={"dash": "dash", "color": "#F5B84B"},
        )
        response_fig.add_annotation(
            x=selected_target_date, y=1, yref="paper", yshift=8,
            text=f"Read response · month {response_lead}", showarrow=False,
            font={"color": "#F5B84B"},
        )
        _apply_layout(response_fig, height=390)
        response_fig.update_layout(
            title=f"What if {source_meta['label'].lower()} is {scenario_z:+.1f} SD in {source_date:%b %Y}?",
            xaxis_title="Month", yaxis_title=f"{target_meta['label']} ({target_meta['unit']})",
            legend={"orientation": "h", "y": 1.12, "x": 0}, hovermode="x unified",
        )
        st.plotly_chart(response_fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("The what-if lines are model scenarios without their own uncertainty band; use the forecast intervals above to understand uncertainty in the independent forecasts.")
        source_link = granger_links.loc[
            (granger_links["source"] == source_key) & (granger_links["target"] == target_key)
        ]
        link_evidence = None
        if not source_link.empty:
            link_row = source_link.iloc[0]
            link_evidence = {
                "adjusted_q_value": float(link_row["q_value"]),
                "passes_q_0_10_guide": bool(link_row["q_value"] <= 0.10),
            }
        satellite_for_signal = {
            "LST": "NASA MODIS land-surface temperature",
            "NDVI": "NASA MODIS vegetation greenness (NDVI)",
            "SMAP_AM": "NASA SMAP morning soil moisture",
            "SMAP_PM": "NASA SMAP evening soil moisture",
            "GPM": "NASA GPM precipitation",
        }
        ai_scenario_data = {
            "source_signal": source_meta["label"],
            "target_signal": target_meta["label"],
            "source_satellite_product": satellite_for_signal[source_key],
            "target_satellite_product": satellite_for_signal[target_key],
            "region": "Uttarakhand, India",
            "historical_record_ends": pd.to_datetime(df["date"]).max().strftime("%B %Y"),
            "source_month": source_date.strftime("%B %Y"),
            "target_month": selected_target_date.strftime("%B %Y"),
            "source_usual_seasonal_value": float(source_usual),
            "source_scenario_value": float(scenario_source_value),
            "source_unit": source_meta["unit"],
            "source_departure_from_usual_sd": float(scenario_z),
            "target_baseline_value": float(baseline_target),
            "target_scenario_value": float(scenario_target),
            "target_scenario_minus_baseline": float(target_shift),
            "target_unit": target_meta["unit"],
            "response_after_months": int(response_lead),
            "lag_depth_months": int(lag_depth),
            "complete_months_used": int(len(dynamics_frame)),
            "granger_evidence_for_this_direction": link_evidence,
            "target_baseline_path": [float(value) for value in base_physical],
            "target_scenario_path": [float(value) for value in scenario_physical],
            "forecast_months": [date.strftime("%B %Y") for date in target_dates],
        }
        scenario_prompt = f"""Explain this what-if scenario to a general audience in very clear, easy English. Sound natural and helpful, not like a scientific report.

Give a useful explanation, not just a restatement of the numbers. In 3 short sections, explain:
1. **What the NASA data and model say:** name the NASA satellite product for both signals. Explain that NASA satellites measured the historical record through {ai_scenario_data['historical_record_ends']}; this model uses that record to estimate the selected later months. Clearly distinguish measured past data from modelled future values. Give the target estimate versus baseline and say whether the difference is small or meaningful.
2. **Why it could happen:** give one or two scientifically plausible ways the source signal could affect the target in {ai_scenario_data['region']}. These are possible explanations from general Earth-science knowledge; clearly say the model did not test or prove the mechanism.
3. **What to watch or do:** describe a realistic possible effect and one proportionate precaution. Make advice conditional and practical. For a small or uncertain change, recommend monitoring rather than alarm or costly action. Do not invent a local impact or imply an emergency.

Use simple words and short sentences. Mention the strength of the historical lead-link evidence in one brief sentence. Never say the source caused the target. State once that this is a model scenario, not a guaranteed real-world outcome. Keep the whole answer under 140 words. Avoid repeating the same caveat or number. Do not begin with an intro such as “Let’s break this down.” The data record ends in {ai_scenario_data['historical_record_ends']}; describe the displayed dates as model dates, not as a current forecast.

Scenario results (JSON):
{json.dumps(ai_scenario_data, ensure_ascii=False, indent=2)}"""
        explanation_cache = st.session_state.setdefault("cross_variable_ai_explanations", {})
        if scenario_prompt not in explanation_cache:
            with st.spinner("🤖 AI is interpreting this scenario…"):
                try:
                    explanation_cache[scenario_prompt] = explain_text(
                        scenario_prompt,
                        max_tokens=500,
                        system_prompt=(
                            "Use plain, easy English. Give plausible scientific reasoning when asked, but clearly separate "
                            "general possibilities from findings actually measured by the model. Keep advice proportionate."
                        ),
                    )
                except Exception as exc:
                    st.error(f"AI explanation unavailable: {exc}")
        if scenario_prompt in explanation_cache:
            ai_card(explanation_cache[scenario_prompt])

        st.markdown("#### Which signals statistically lead other signals?")
        link_col, note_col = st.columns([1.25, 0.75], gap="medium")
        signal_names = dynamics_keys
        q_lookup = {
            (row.source, row.target): float(row.q_value)
            for row in granger_links.itertuples(index=False)
        }
        q_grid = np.ones((len(signal_names), len(signal_names)), dtype=float)
        hover_text = []
        for source_i, source_name in enumerate(signal_names):
            hover_row = []
            for target_i, target_name in enumerate(signal_names):
                q_value = q_lookup.get((source_name, target_name))
                if q_value is not None:
                    q_grid[source_i, target_i] = q_value
                    mark = " · passes q ≤ 0.10" if q_value <= 0.10 else ""
                    hover_row.append(f"{source_name} → {target_name}<br>Adjusted q = {q_value:.3g}{mark}")
                else:
                    hover_row.append("Same signal")
            hover_text.append(hover_row)
        strength_grid = -np.log10(np.clip(q_grid, 1e-12, 1.0))
        text_grid = [
            ["—" if i == j else (f"{q_grid[i, j]:.2f}" + (" ✓" if q_grid[i, j] <= 0.10 else "")) for j in range(len(signal_names))]
            for i in range(len(signal_names))
        ]
        with link_col:
            link_fig = go.Figure(go.Heatmap(
                z=strength_grid,
                x=[VAR_CONFIG[key]["label"] for key in signal_names],
                y=[VAR_CONFIG[key]["label"] for key in signal_names],
                text=text_grid, texttemplate="%{text}", textfont={"size": 11},
                customdata=hover_text, hovertemplate="%{customdata}<extra></extra>",
                colorscale="Viridis", colorbar={"title": "Evidence<br>−log₁₀(q)"},
            ))
            link_fig.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,26,46,.48)",
                font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 10},
                height=440, margin={"l": 145, "r": 20, "t": 20, "b": 110},
                xaxis={"title": "Predicted signal (target)", "tickangle": -30},
                yaxis={"title": "Earlier signal (source)", "autorange": "reversed"},
            )
            st.plotly_chart(link_fig, use_container_width=True, config={"displayModeBar": False})
            st.caption("Cell text is the adjusted q value; ✓ marks q ≤ 0.10 after correcting for all tested signal pairs. Lower q means stronger evidence of added predictive value.")
        with note_col:
            significant_links = granger_links.loc[granger_links["q_value"] <= 0.10].copy()
            st.metric("Links passing the exploratory evidence guide", f"{len(significant_links)} / {len(granger_links)}")
            if significant_links.empty:
                st.write("No directed pair passed the q ≤ 0.10 guide in this run. The model can still show scenario responses, but the historical record does not provide strong evidence for a specific lead link after correction.")
            else:
                for link in significant_links.head(6).itertuples(index=False):
                    st.markdown(
                        f"**{VAR_CONFIG[link.source]['label']} → {VAR_CONFIG[link.target]['label']}**  "
                        f"\nAdjusted q = {link.q_value:.3g}"
                    )
            st.caption("Method: 3-month (or selected lag-depth) conditional Granger screen with Benjamini–Hochberg correction. These are predictive links, not proof of physical cause.")
except Exception as exc:
    st.warning(f"Cross-variable lag analysis is unavailable for this run: {exc}")

if baseline_path is not None and dynamics_frame is not None:
    # District-level watch index combines the regional forecast setup with
    # historical district anomaly exposure; it is not a district forecast.
    section_header(
        "Uttarakhand District Climate Watch · Where should monitoring focus?",
        "🗺️",
        "A forecast-led district priority index for heat/dryness and heavy-rain conditions",
    )
    st.markdown(
        "The combined overview pairs the **regional forecast pattern** with each district’s **historical satellite-anomaly exposure**. "
        "The separate LST, NDVI, SMAP and GPM tabs below use district-level satellite series and train a model for each district where enough observations are available. "
        "Those forecasts are still exploratory and are not official district warnings."
    )
    st.caption(
        "Index recipe: 70% forecast environmental setup + 30% relative historical district anomaly-exposure rank. "
        "The regional forecast setup gives equal weight to two patterns: warm/dry vegetation stress and heavy rain/wet ground. Together they use land-surface temperature (LST), vegetation greenness (NDVI), SMAP soil moisture and GPM precipitation. "
        "No fire, landslide, flood, or soil-erosion inventory is used to calibrate this prototype score."
    )

    def _pressure_score(value: float) -> float:
        """Map a directional standardized anomaly to a 0–100 evidence component."""
        return float(np.clip(value / 2.5, 0.0, 1.0) * 100.0)

    climate_months = []
    for step, future_date in enumerate(ok_vars[dynamics_keys[0]]["forecast_dates"][:horizon]):
        z = {key: float(baseline_path[step, dynamics_keys.index(key)]) for key in dynamics_keys}
        smap_parts = [z[key] for key in ("SMAP_AM", "SMAP_PM") if key in z]
        soil_z = float(np.mean(smap_parts)) if smap_parts else 0.0
        fire_components = {
            "Hotter land": _pressure_score(z.get("LST", 0.0)),
            "Vegetation stress": _pressure_score(-z.get("NDVI", 0.0)),
            "Dry soil": _pressure_score(-soil_z),
            "Rain deficit": _pressure_score(-z.get("GPM", 0.0)),
        }
        fire_score = (
            0.30 * fire_components["Hotter land"]
            + 0.30 * fire_components["Vegetation stress"]
            + 0.25 * fire_components["Dry soil"]
            + 0.15 * fire_components["Rain deficit"]
        )
        wet_components = {
            "Heavy rain": _pressure_score(z.get("GPM", 0.0)),
            "Wet soil": _pressure_score(soil_z),
            "Vegetation stress": _pressure_score(-z.get("NDVI", 0.0)),
        }
        runoff_score = (
            0.45 * wet_components["Heavy rain"]
            + 0.35 * wet_components["Wet soil"]
            + 0.20 * wet_components["Vegetation stress"]
        )
        # Blend both environmental pathways so every available satellite signal
        # contributes to the shared regional setup used in district ranking.
        combined_score = 0.50 * fire_score + 0.50 * runoff_score
        climate_months.append({
            "month": future_date,
            "fire_score": fire_score,
            "runoff_score": runoff_score,
            "peak_score": combined_score,
            "watch_type": "Warm/dry component stronger" if fire_score >= runoff_score else "Wet-ground component stronger",
            "fire_components": fire_components,
            "runoff_components": wet_components,
        })

    if climate_months:
        peak_setup = max(climate_months, key=lambda item: item["peak_score"])
        try:
            historical_district = _cached_district_anomaly_history()
            district_boundaries = load_district_boundaries().to_crs("EPSG:4326")
            if historical_district.empty:
                raise ValueError("No district anomaly history is available.")

            hist_columns = [
                "district_name", "risk_score", "alert_pct", "if_anomaly_pct",
                "mean_lst_z", "mean_ndvi_z", "mean_smap_z", "mean_gpm_z",
            ]
            hist = historical_district[hist_columns].copy()
            hist["historical_exposure_rank"] = hist["risk_score"].rank(method="average", pct=True) * 100
            district_watch = district_boundaries[["district_name", "geometry"]].merge(
                hist, on="district_name", how="left"
            )
            median_rank = float(hist["historical_exposure_rank"].median())
            district_watch["historical_exposure_rank"] = district_watch["historical_exposure_rank"].fillna(median_rank)
            district_watch["forecast_setup_score"] = float(peak_setup["peak_score"])
            district_watch["watch_score"] = (
                0.70 * district_watch["forecast_setup_score"]
                + 0.30 * district_watch["historical_exposure_rank"]
            ).clip(0, 100).round(1)
            district_watch["watch_type"] = peak_setup["watch_type"]

            # A compact view of whether the future monthly drivers look fire-weather-like or wet/runoff-like.
            monthly_watch_fig = go.Figure()
            monthly_watch_fig.add_trace(go.Scatter(
                x=[item["month"] for item in climate_months],
                y=[item["fire_score"] for item in climate_months],
                mode="lines+markers", name="Warm / dry vegetation stress",
                line={"color": "#EF6461", "width": 3}, marker={"size": 8},
                hovertemplate="%{x|%b %Y}<br>Warm/dry setup index: %{y:.1f}/100<extra></extra>",
            ))
            monthly_watch_fig.add_trace(go.Scatter(
                x=[item["month"] for item in climate_months],
                y=[item["runoff_score"] for item in climate_months],
                mode="lines+markers", name="Heavy rain / wet-ground setup",
                line={"color": "#63A9E8", "width": 3}, marker={"size": 8},
                hovertemplate="%{x|%b %Y}<br>Wet-ground setup index: %{y:.1f}/100<extra></extra>",
            ))
            monthly_watch_fig.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,26,46,.48)",
                font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 11},
                height=330, margin={"l": 55, "r": 15, "t": 28, "b": 48},
                hovermode="x unified", legend={"orientation": "h", "y": 1.12, "x": 0},
                xaxis={"title": "Modelled month", "gridcolor": "rgba(42,63,95,.45)"},
                yaxis={"title": "Setup index (0–100)", "range": [0, 100], "gridcolor": "rgba(42,63,95,.45)"},
            )
            st.plotly_chart(monthly_watch_fig, use_container_width=True, config={"displayModeBar": False})
            st.caption("Higher values mean more of the selected satellite signals match that environmental setup. They are not event probabilities.")

            map_column, ranking_column = st.columns([1.05, 1], gap="medium")
            with map_column:
                leading_district = str(district_watch.sort_values("watch_score", ascending=False).iloc[0]["district_name"])
                district_map = choropleth_map(
                    district_watch,
                    "watch_score",
                    title="District monitoring priority",
                    color_label="Watch index (0–100)",
                    range_color=(0, 100),
                    highlight_district=leading_district,
                )
                district_map.update_layout(height=700)
                district_map.update_geos(projection_scale=1.2)
                st.plotly_chart(district_map, use_container_width=True, config={"displayModeBar": False})
            with ranking_column:
                st.markdown("#### District watch ranking")
                st.caption(
                    f"Combined LST · NDVI · SMAP · GPM setup peaks in {peak_setup['month']:%b %Y}: "
                    f"{peak_setup['watch_type']} · {peak_setup['peak_score']:.1f}/100"
                )
                ranking = district_watch.sort_values("watch_score", ascending=False).copy()
                ranking["district_name"] = ranking["district_name"].astype(str)
                ranking_fig = go.Figure(go.Bar(
                    x=ranking["watch_score"], y=ranking["district_name"], orientation="h",
                    marker={"color": ranking["watch_score"], "colorscale": [[0, "#31C48D"], [0.55, "#E9A34B"], [1, "#EF6461"]], "cmin": 0, "cmax": 100},
                    text=[f"{score:.0f}" for score in ranking["watch_score"]], textposition="outside",
                    hovertemplate="%{y}<br>Prototype watch index: %{x:.1f}/100<extra></extra>",
                ))
                ranking_fig.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,26,46,.48)",
                    font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 11},
                    height=560, margin={"l": 130, "r": 35, "t": 16, "b": 32},
                    xaxis={"title": "Monitoring priority index (0–100)", "range": [0, 108], "gridcolor": "rgba(42,63,95,.45)"},
                    yaxis={"autorange": "reversed", "gridcolor": "rgba(0,0,0,0)"},
                )
                st.plotly_chart(ranking_fig, use_container_width=True, config={"displayModeBar": False})

            st.markdown("#### Satellite category focus by district")
            st.caption(
                "Each district now has its own model trained from its area-averaged NASA satellite grid. "
                "Choose a forecast month to compare the district-level values. Historical seasonal departures are shown alongside them. "
                f"The satellite record ends in {df['date'].max():%B %Y}, so these are dated model examples, not current forecasts."
            )
            district_satellite_fc = _cached_district_satellite_forecasts(horizon)
            category_specs = [
                {
                    "key": "LST", "variable": "LST", "label": "Land-surface temperature · MODIS",
                    "value_unit": "K", "focus_direction": "high_value",
                },
                {
                    "key": "NDVI", "variable": "NDVI", "label": "Vegetation greenness · MODIS",
                    "value_unit": "index", "focus_direction": "low_anomaly",
                },
                {
                    "key": "SMAP", "variable": "SMAP_AM", "label": "Morning soil moisture · SMAP",
                    "value_unit": "m³/m³", "focus_direction": "low_anomaly",
                },
                {
                    "key": "GPM", "variable": "GPM", "label": "Precipitation · GPM",
                    "value_unit": "mm/mo", "focus_direction": "unusual_anomaly",
                },
            ]
            available_dates = sorted(district_satellite_fc["forecast_date"].dropna().unique()) if not district_satellite_fc.empty else []
            if not available_dates:
                st.warning("District-level satellite forecasts could not be built from the available monthly grids.")
            else:
                date_labels = [pd.Timestamp(value).strftime("%B %Y") for value in available_dates]
                selected_date_label = st.selectbox(
                    "Compare districts for forecast month",
                    date_labels,
                    index=0,
                    key="district_satellite_forecast_month",
                )
                selected_forecast_date = pd.Timestamp(available_dates[date_labels.index(selected_date_label)])
            category_tabs = st.tabs([spec["key"] for spec in category_specs])
            for category_tab, spec in zip(category_tabs, category_specs):
                with category_tab:
                    if not available_dates:
                        continue
                    category_rows = district_satellite_fc.loc[
                        (district_satellite_fc["variable"] == spec["variable"])
                        & (district_satellite_fc["forecast_date"] == selected_forecast_date)
                    ].copy()
                    if category_rows.empty:
                        st.info(
                            f"There is not enough district-level {spec['key']} data to train a reliable model. "
                            "Districts without sufficient valid satellite observations are left unranked."
                        )
                        continue
                    category_rows = district_boundaries[["district_name", "geometry"]].merge(
                        category_rows, on="district_name", how="left"
                    )
                    if spec["focus_direction"] == "high_value":
                        category_rows["focus_value"] = category_rows["forecast_value"]
                        sort_ascending = False
                        focus_label = f"Forecast {spec['key']} ({spec['value_unit']})"
                        colorscale_range = None
                    elif spec["focus_direction"] == "low_anomaly":
                        category_rows["focus_value"] = -category_rows["seasonal_anomaly_z"]
                        sort_ascending = False
                        focus_label = "Below-seasonal anomaly (SD; higher = more stress)"
                        colorscale_range = None
                    else:
                        category_rows["focus_value"] = category_rows["seasonal_anomaly_z"].abs()
                        sort_ascending = False
                        focus_label = "Unusual-rainfall departure (SD)"
                        colorscale_range = None
                    category_ranking = category_rows.dropna(subset=["focus_value"]).sort_values(
                        "focus_value", ascending=sort_ascending
                    ).copy()
                    if category_ranking.empty:
                        st.info(f"No reliable {spec['key']} district forecasts are available for {selected_date_label}.")
                        continue
                    direction_note = (
                        "hottest predicted districts first" if spec["key"] == "LST" else
                        "largest below-usual vegetation/soil signal first" if spec["key"] in ("NDVI", "SMAP") else
                        "largest wet or dry rainfall departure first"
                    )
                    st.caption(
                        f"{spec['label']} for {selected_date_label}, ranked by {direction_note}. "
                        f"Separate district models use at least 60 valid historical months; "
                        f"{len(category_ranking)} of 13 districts have enough data for this category."
                    )
                    if len(category_ranking) < 13:
                        st.warning(
                            f"Only {len(category_ranking)} districts have enough valid {spec['key']} observations "
                            "for a separate forecast. Missing districts are unavailable, not low-valued."
                        )
                    category_map_col, category_bar_col = st.columns([1.05, 1], gap="medium")
                    with category_map_col:
                        category_map = choropleth_map(
                            category_ranking,
                            "focus_value",
                            title=f"{spec['key']} forecast · {selected_date_label}",
                            color_label=focus_label,
                            range_color=colorscale_range,
                            highlight_district=str(category_ranking.iloc[0]["district_name"]),
                        )
                        category_map.update_layout(height=700)
                        category_map.update_geos(projection_scale=1.2)
                        st.plotly_chart(
                            category_map,
                            use_container_width=True,
                            config={"displayModeBar": False},
                            key=f"district_category_map_{spec['key']}",
                        )
                    with category_bar_col:
                        category_bar = go.Figure(go.Bar(
                            x=category_ranking["focus_value"],
                            y=category_ranking["district_name"].astype(str),
                            orientation="h",
                            marker={
                                "color": category_ranking["focus_value"],
                                "colorscale": [[0, "#31C48D"], [0.55, "#E9A34B"], [1, "#EF6461"]],
                            },
                            text=[f"{value:.1f} {spec['value_unit']}" for value in category_ranking["forecast_value"]],
                            textposition="outside",
                            customdata=np.column_stack([
                                category_ranking["forecast_value"], category_ranking["seasonal_anomaly_z"]
                            ]),
                            hovertemplate=(
                                "%{y}<br>Focus metric: %{x:.2f}<br>Forecast: %{customdata[0]:.3f} "
                                + spec["value_unit"] + "<br>Seasonal anomaly: %{customdata[1]:+.2f} SD<extra></extra>"
                            ),
                        ))
                        category_bar.update_layout(
                            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,26,46,.48)",
                            font={"family": "Urbanist, sans-serif", "color": "#AAB8CC", "size": 11},
                            height=700, margin={"l": 130, "r": 35, "t": 16, "b": 32},
                            xaxis={"title": focus_label, "gridcolor": "rgba(42,63,95,.45)"},
                            yaxis={"autorange": "reversed", "gridcolor": "rgba(0,0,0,0)"},
                        )
                        st.plotly_chart(
                            category_bar,
                            use_container_width=True,
                            config={"displayModeBar": False},
                            key=f"district_category_ranking_{spec['key']}",
                        )

            district_choices = ranking["district_name"].tolist()
            selected_watch_district = st.selectbox(
                "Inspect a district", district_choices,
                index=0, key="predictive_district_watch",
            )
            district_row = district_watch.loc[district_watch["district_name"] == selected_watch_district].iloc[0]
            history_row = hist.loc[hist["district_name"] == selected_watch_district]
            history_rank = float(district_row["historical_exposure_rank"])
            st.info(
                f"**{selected_watch_district} monitoring index: {district_row['watch_score']:.1f}/100.** "
                f"It combines the shared regional forecast setup ({district_row['forecast_setup_score']:.1f}/100) "
                f"with this district’s relative historical anomaly-exposure rank ({history_rank:.0f}th percentile). "
                f"The regional setup is strongest in {peak_setup['month']:%B %Y}. "
                + (f"Historical alert-pixel share was {float(history_row.iloc[0]['alert_pct']):.1f}%. " if not history_row.empty else "No district-specific history was available; the median rank was used. ")
                + "This prioritises where to review conditions; it does not predict that a disaster will occur."
            )
            district_context_key = (
                "plain-conversation-v4",
                selected_watch_district,
                int(horizon),
                round(float(peak_setup["peak_score"]), 2),
                tuple(round(float(value), 3) for value in baseline_path.flatten()),
            )
            district_ai_slot = "predictive_district_watch_llama"
            if st.button(
                "🦙 Explain this district watch with Llama",
                use_container_width=True,
                key="predictive_district_watch_llama_button",
            ):
                forecast_context = []
                for step, climate in enumerate(climate_months):
                    signal_lines = []
                    for key in dynamics_keys:
                        fc_data = ok_vars[key]
                        signal_lines.append(
                            f"{VAR_CONFIG[key]['label']}: {float(fc_data['point'][step]):.4f} {VAR_CONFIG[key]['unit']} "
                            f"(95% interval {float(fc_data['lower_95'][step]):.4f} to {float(fc_data['upper_95'][step]):.4f}); "
                            f"VAR standardized anomaly {baseline_path[step, dynamics_keys.index(key)]:+.2f} SD"
                        )
                    forecast_context.append(
                        f"{climate['month']:%B %Y}: forecast signals: " + "; ".join(signal_lines)
                        + f". Warm/dry vegetation-stress setup index={climate['fire_score']:.1f}/100 "
                        + f"(components: {climate['fire_components']}). Heavy-rain/wet-ground setup index="
                        + f"{climate['runoff_score']:.1f}/100 (components: {climate['runoff_components']})."
                    )

                top_district_context = "\n".join(
                    f"{int(rank)}. {row.district_name}: watch index {row.watch_score:.1f}/100; "
                    f"historical anomaly-exposure percentile {row.historical_exposure_rank:.1f}; "
                    f"historical alert-pixel share {row.alert_pct if pd.notna(row.alert_pct) else float('nan'):.1f}%"
                    for rank, row in enumerate(ranking.head(5).itertuples(index=False), start=1)
                )
                if history_row.empty:
                    selected_history_context = "No historical district anomaly summary was available; the median exposure rank was substituted."
                else:
                    selected_hist = history_row.iloc[0]
                    selected_history_context = (
                        f"Historical alert pixels: {selected_hist['alert_pct']:.1f}%; "
                        f"Isolation Forest anomaly pixels: {selected_hist['if_anomaly_pct']:.1f}%; "
                        f"mean historical anomaly z values: temperature {selected_hist['mean_lst_z']:+.2f}, "
                        f"vegetation {selected_hist['mean_ndvi_z']:+.2f}, soil moisture {selected_hist['mean_smap_z']:+.2f}, "
                        f"rainfall {selected_hist['mean_gpm_z']:+.2f}."
                    )
                significant_link_context = "No directed links passed the exploratory adjusted q ≤ 0.10 guide."
                if "granger_links" in locals():
                    significant_rows = granger_links.loc[granger_links["q_value"] <= 0.10].head(8)
                    if not significant_rows.empty:
                        significant_link_context = "; ".join(
                            f"{VAR_CONFIG[row.source]['label']} may help predict {VAR_CONFIG[row.target]['label']} "
                            f"(adjusted q={row.q_value:.3g})"
                            for row in significant_rows.itertuples(index=False)
                        )

                llama_system_prompt = """You are the friendly EARTHPULSE-X guide. Explain the numbers as if a knowledgeable teammate is sitting beside the user. Be direct, warm, and natural. Do not sound like an official report, scripted disclaimer, or chatbot template.

Your job is to answer: “Why did this district get this score, what does the forecast actually say, and should I worry?”

STYLE RULES
- Write 2–3 short paragraphs in plain English. No headings, bullets, numbering, step labels, or formal introduction.
- Start with the selected district and the plain meaning of its score. Explain in one sentence what pushed the score up and whether that came from past satellite history or the forecast.
- Then say what the forecast signals show, using the actual month and strength. A small score is a weak signal; never turn it into “heavy rain is expected”, “moderate risk”, or “conditions are extreme”.
- Sound reassuring when the supplied forecast is low: say this score alone is not a reason to panic. Don't repeat generic safety disclaimers.
- Explain “100th percentile” as “ranked highest among districts in this dataset”, never as 100% of the area or a 100% chance.
- Mention that the model's record ends in September 2025, so October 2025 is a dated model example, not a current forecast.
- Don't use these terms in the answer: anomaly-exposure percentile, standard deviation, Granger, VAR, regional forecast setup, monitoring priority, prototype index.
- Don't reveal analysis or planning. Never write “Step 1”, “Let's take a look”, “What this means”, or “Why we built this”.
- Do not invent events, causes, district-specific weather, or confirmed hazards. Use only the context below.

STYLE EXAMPLE (copy the conversational feel, not the facts):
“For Chamoli, 36/100 is mostly being pulled up by unusual satellite readings in its past. The forecast signal itself is low, so this run isn't showing a strong environmental change ahead.

The month shown is October 2025, based on data that ends in September 2025. So treat it as an example from the model, not a forecast for today. This is a prompt to understand and keep an eye on the signals—not a reason to panic.”"""

                llama_context = f"""WHY EARTHPULSE-X BUILT THIS
EARTHPULSE-X is an early-Earth-detection project. It looks for combinations of satellite signals that may deserve a closer look: warm land with dry soil and stressed vegetation is a different pattern from heavy rain over wet ground. This district index is meant to help people understand those patterns and where to review data—not announce a disaster.

PROJECT FACTS
- Region: Uttarakhand, India. Monthly satellite record: April 2015 to September 2025.
- Forecasts are anchored after the final data month. They are modelled outlooks, not live observations.
- Five regional signals are used: land-surface temperature, vegetation greenness (NDVI), morning/evening soil moisture, and precipitation (GPM).
- The combined district-watch index uses one shared regional forecast setup plus historical district exposure. Separate category tabs also show exploratory district-level forecasts trained from the harmonized satellite grids where at least 60 valid months exist.
- The prototype district index = 70% strongest forecast environmental setup + 30% historical district anomaly-exposure percentile. It is a monitoring-priority index from 0 to 100, not a probability, official warning, or calibrated disaster-risk estimate.
- Each directional standardized anomaly is clipped at 2.5 SD and scaled to 0–100. Warm/dry vegetation-stress setup weights hotter land 30%, lower vegetation 30%, drier soil 25%, and lower rainfall 15%. Heavy-rain/wet-ground setup weights higher rainfall 45%, wetter soil 35%, and vegetation stress 20%. These are environmental conditions that may justify closer review; they do not predict a fire, landslide, flood, or erosion event.
- Historical exposure comes from satellite anomaly pixels and an isolation-forest screen, not a verified inventory of past disasters. Do not call these past events.
- The VAR/Granger results are predictive lead-lag associations, not proof of physical causation. Monthly data cannot resolve week-scale delays.
- The modelled dates extend beyond September 2025; do not describe them as a current 2026 forecast.
- A 100th-percentile historical rank means highest relative rank among the district scores in this dataset; it does not mean 100% probability, 100% of the district was affected, or a perfect risk score.
- Describe the strength honestly: a setup value near 12/100 is low on this prototype's scale. One positive rain contribution does not justify saying “heavy rain is expected.” Never call a signal high/moderate unless the supplied score itself supports that wording.

SELECTED DISTRICT
- District: {selected_watch_district}
- Prototype watch index: {district_row['watch_score']:.1f}/100
- Shared regional forecast-setup component: {district_row['forecast_setup_score']:.1f}/100
- Historical anomaly-exposure percentile: {history_rank:.1f}
- Strongest regional setup: {peak_setup['watch_type']} in {peak_setup['month']:%B %Y}, index {peak_setup['peak_score']:.1f}/100
- District history: {selected_history_context}

FORECAST BY MONTH
{chr(10).join(forecast_context)}

TOP DISTRICT RANKING
{top_district_context}

EXPLORATORY LAGGED LINKS
{significant_link_context}

ANSWER THIS FOR THE SELECTED DISTRICT
Explain why its score is what it is, what the dated model outlook says in everyday language, why the project made this index, and whether the reader should worry. Keep the explanation short and human. Do not repeat all the technical recipe.
"""
                with st.spinner("🦙 Llama is reading the forecast, district history, and score recipe…"):
                    try:
                        district_ai_text = explain_text(
                            llama_context,
                            max_tokens=500,
                            system_prompt=llama_system_prompt,
                        )
                        st.session_state[district_ai_slot] = {
                            "context": district_context_key,
                            "text": district_ai_text,
                        }
                    except Exception as ai_exc:
                        st.error(f"Llama explanation is unavailable: {ai_exc}")

            saved_district_ai = st.session_state.get(district_ai_slot)
            if saved_district_ai and saved_district_ai.get("context") == district_context_key:
                ai_card(saved_district_ai["text"])
            st.caption("This prototype has no district-resolved future satellite forecast, slope/fuel inventory, or verified disaster-event calibration. Treat the map as an exploratory monitoring-priority view, not an operational warning.")
        except Exception as exc:
            st.warning(f"District climate-watch index is unavailable for this run: {exc}")

# ──────────────────────────────────────────────────────────────
# 6. PIXEL-LEVEL HISTORICAL ANOMALY HOTSPOTS
# ──────────────────────────────────────────────────────────────

section_header(
    "Pixel Hotspots — Where anomalies cluster",
    "📍",
    "Explore historical satellite anomalies at the native grid-cell scale",
)

st.markdown(
    "Nearby anomalous satellite pixels are grouped into map footprints, so a district-wide average does not hide smaller areas. "
    "Choose one month to inspect a snapshot, or find locations that repeatedly crossed the anomaly threshold across the record."
)

try:
    hotspot_events = load_spatial_anomaly_events()
    hotspot_boundaries = load_district_boundaries()
    hotspot_events["month"] = hotspot_events["month"].astype(str).str[:7]
    hotspot_months = sorted(hotspot_events["month"].dropna().unique())

    control_cols = st.columns([1.2, 1.0, 1.0, 1.0])
    with control_cols[0]:
        hotspot_mode = st.radio(
            "View",
            ["Recurring locations", "Single month"],
            horizontal=True,
            key="pixel_hotspot_mode",
            help="Recurring locations are grid cells flagged in multiple distinct months. Single month groups nearby flagged pixels for one selected month.",
        )
    with control_cols[1]:
        hotspot_variable = st.selectbox(
            "Satellite signal",
            ["LST", "NDVI", "SMAP_AM", "SMAP_PM", "GPM"],
            format_func=lambda key: VAR_CONFIG[key]["label"],
            key="pixel_hotspot_variable",
        )
    with control_cols[2]:
        hotspot_direction = st.selectbox(
            "Unusual direction",
            ["POSITIVE", "NEGATIVE"],
            format_func=lambda value: "Higher than usual" if value == "POSITIVE" else "Lower than usual",
            key="pixel_hotspot_direction",
        )
    with control_cols[3]:
        hotspot_threshold = st.slider(
            "Minimum anomaly strength",
            min_value=2.0,
            max_value=5.0,
            value=3.5,
            step=0.5,
            format="%.1fσ",
            key="pixel_hotspot_threshold",
            help="Only pixels at least this far from their usual seasonal level are considered.",
        )

    clustering_cols = st.columns([1, 1, 1.5])
    with clustering_cols[0]:
        hotspot_eps = st.slider(
            "Neighbourhood distance",
            min_value=9.0,
            max_value=30.0,
            value=13.0,
            step=1.0,
            format="%.0f km",
            key="pixel_hotspot_eps",
            help="The satellite grid is about 9 km across. 13 km allows directly diagonal neighbouring cells to join.",
        )
    with clustering_cols[1]:
        hotspot_min_samples = st.slider(
            "Minimum nearby pixels",
            min_value=2,
            max_value=12,
            value=3,
            step=1,
            key="pixel_hotspot_min_samples",
            help="A location needs at least this many nearby anomalous grid cells to form a cluster.",
        )
    if hotspot_mode == "Single month":
        with clustering_cols[2]:
            hotspot_month = st.select_slider(
                "Month",
                options=hotspot_months,
                value=hotspot_months[-1] if hotspot_months else None,
                key="pixel_hotspot_month",
            )
        recurrence_months = 1
    else:
        with clustering_cols[2]:
            recurrence_months = st.slider(
                "Minimum months at the same grid cell",
                min_value=2,
                max_value=24,
                value=3,
                step=1,
                key="pixel_hotspot_recurrence",
                help="A recurring location must cross the selected anomaly threshold in this many distinct months.",
            )
        hotspot_month = None

    with st.spinner("Grouping nearby anomalous satellite pixels…"):
        hotspots = cluster_spatial_anomaly_points(
            hotspot_events,
            month=hotspot_month,
            variable=hotspot_variable,
            direction=hotspot_direction,
            threshold_z=hotspot_threshold,
            eps_km=hotspot_eps,
            min_samples=hotspot_min_samples,
            min_recurrence_months=recurrence_months,
            boundaries=hotspot_boundaries,
        )

    if hotspot_mode == "Single month":
        scope_label = hotspot_month or "Selected month"
        definition = f"{hotspot_month} only"
    else:
        scope_label = f"Recurring · {hotspot_months[0]} to {hotspot_months[-1]}" if hotspot_months else "Recurring locations"
        definition = f"at least {recurrence_months} distinct months"

    if hotspots.empty:
        st.info(
            f"No clusters meet these settings. Try a lower anomaly threshold, a wider neighbourhood, or fewer required nearby pixels."
        )
    else:
        clustered_pixel_count = int(hotspots["pixel_count"].sum())
        largest_hotspot = hotspots.iloc[0]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Hotspots found", f"{len(hotspots):,}")
        metric_cols[1].metric("Pixels in clusters", f"{clustered_pixel_count:,}")
        metric_cols[2].metric("Largest cluster", f"{int(largest_hotspot['pixel_count']):,} pixels")
        metric_cols[3].metric("Largest cluster area", f"{largest_hotspot['area_km2']:,.0f} km²")

        st.plotly_chart(
            spatial_hotspot_map(
                hotspots,
                month_label=scope_label,
                variable_label=VAR_CONFIG[hotspot_variable]["label"],
                direction=hotspot_direction,
            ),
            use_container_width=True,
            config={"displayModeBar": True, "scrollZoom": True},
            key="pixel_hotspot_map",
        )

        display_hotspots = hotspots.drop(columns="geometry").copy()
        display_hotspots = display_hotspots.rename(columns={
            "hotspot_id": "Hotspot",
            "district": "Centroid district",
            "pixel_count": "Grid cells",
            "anomaly_pixel_months": "Pixel-month flags",
            "mean_months_flagged": "Avg. flagged months / cell",
            "mean_robust_z": "Mean anomaly (σ)",
            "max_abs_robust_z": "Strongest anomaly (σ)",
            "area_km2": "Approx. footprint (km²)",
        })
        shown_columns = [
            "Hotspot", "Centroid district", "Grid cells", "Pixel-month flags",
            "Avg. flagged months / cell", "Mean anomaly (σ)",
            "Strongest anomaly (σ)", "Approx. footprint (km²)",
        ]
        st.dataframe(
            display_hotspots[shown_columns].round(2),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"DBSCAN groups points within {hotspot_eps:.0f} km; a group needs at least {hotspot_min_samples} nearby cells. "
            f"The selected signal must be at least {hotspot_threshold:.1f}σ {'above' if hotspot_direction == 'POSITIVE' else 'below'} its usual seasonal level. "
            f"Recurring view keeps cells flagged in {definition}. District is the cluster-centre district; footprints are approximate native satellite cells."
        )

    st.markdown(
        "**How to read this:** coloured footprints mark the actual satellite grid cells in each cluster; brighter/larger centre markers indicate stronger or more spatially extensive clusters. "
        "Hover over a marker for its district, pixel count, typical anomaly strength, and approximate area. Isolated anomalous pixels are left out as noise."
    )
    st.caption(
        "These are historical satellite-pattern clusters, not confirmed damage, named valleys, or a prediction of fire, flood, landslide, or future conditions. "
        "The district label describes the cluster centre only; a footprint can cross district boundaries."
    )
except Exception as hotspot_exc:
    st.warning(f"Pixel hotspot mapping is unavailable for this run: {hotspot_exc}")

# ──────────────────────────────────────────────────────────────
# 7. ALL-VARIABLE MINI-FORECASTS (sparklines)
# ──────────────────────────────────────────────────────────────

section_header("All Variables — Forecast Trajectories", "🔭", "Mini-charts showing direction of change")

spark_cols = st.columns(len(ok_vars))
for col_w, (key, fc_data) in zip(spark_cols, ok_vars.items()):
    m = VAR_CONFIG[key]
    c = VAR_COLORS.get(key, "#35C9D0")

    # Last 24 months of history + forecast
    hist_last = fc_data["historical_values"][-24:]
    hist_dates_last = fc_data["historical_dates"][-24:]
    fcd = fc_data["forecast_dates"]
    pt  = fc_data["point"]
    l95 = fc_data["lower_95"]
    h95 = fc_data["upper_95"]

    sfig = go.Figure()

    # 95% PI
    _hx = c.lstrip("#")
    _r, _g, _b = int(_hx[0:2], 16), int(_hx[2:4], 16), int(_hx[4:6], 16)
    sfig.add_trace(go.Scatter(
        x=list(fcd) + list(fcd[::-1]),
        y=list(h95) + list(l95[::-1]),
        fill="toself",
        fillcolor=f"rgba({_r},{_g},{_b},0.12)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip",
    ))

    # History
    sfig.add_trace(go.Scatter(
        x=hist_dates_last, y=hist_last,
        mode="lines", name="hist",
        line=dict(color=c, width=1.5),
        showlegend=False,
        hovertemplate=f"%{{x|%Y-%m}}: %{{y:.3f}}<extra></extra>",
    ))

    # Forecast
    sfig.add_trace(go.Scatter(
        x=fcd, y=pt,
        mode="lines+markers", name="fc",
        line=dict(color=c, width=2, dash="dash"),
        marker=dict(size=5, color=c),
        showlegend=False,
        hovertemplate=f"Forecast: %{{y:.3f}}<extra></extra>",
    ))

    _ld = fc_data["last_date"]
    sfig.add_vrect(
        x0=_ld, x1=_ld + pd.DateOffset(days=5),
        fillcolor="#6B7B91", opacity=0.20, line_width=0,
    )

    sfig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,26,46,0.5)",
        height=180,
        margin=dict(l=8, r=8, t=30, b=30),
        title=dict(text=f"{m['emoji']} {m['label']}", font=dict(size=11, color="#AAB8CC")),
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=9, color="#6B7B91")),
        hovermode="x",
    )

    with col_w:
        st.plotly_chart(sfig, use_container_width=True, config={"displayModeBar": False})

# ──────────────────────────────────────────────────────────────
# 8. MODEL SKILL — Walk-Forward CV
# ──────────────────────────────────────────────────────────────

if show_cv:
    section_header("Model Skill Certificate", "🎯", "Walk-forward cross-validation · Expanding window")

    info_banner(
        "Walk-forward CV trains the model on an expanding history and evaluates "
        "the selected forecast horizon on 12 held-out periods. Each fold retunes the model using earlier months only. "
        "The table compares it with a same-month-last-year seasonal baseline. "
        "Prediction intervals are calibrated from past out-of-sample errors; observed coverage can still differ from 80% / 95% targets.",
        kind="info",
    )

    cv_rows = []
    for key, fc_data in ok_vars.items():
        cv = fc_data.get("cv_metrics", {})
        if not cv:
            continue
        meta = VAR_CONFIG[key]
        cv_rows.append({
            "Variable": f"{meta['emoji']} {meta['label']}",
            "MAE":        f"{cv['mae']:.4f} {meta['unit']}",
            "RMSE":       f"{cv['rmse']:.4f} {meta['unit']}",
            "Seasonal baseline MAE": f"{cv['baseline_mae']:.4f} {meta['unit']}",
            "MAPE":       f"{cv['mape']:.2f}%" if not np.isnan(cv.get("mape", np.nan)) else "N/A",
            "80% PI Coverage": f"{cv['coverage_80']*100:.1f}%",
            "95% PI Coverage": f"{cv['coverage_95']*100:.1f}%",
            "CV Folds":   int(cv.get("n_folds", 0)),
            "_mae":       cv["mae"],
        })

    if cv_rows:
        cv_df = pd.DataFrame(cv_rows)
        st.dataframe(cv_df.drop(columns=["_mae"]), hide_index=True, use_container_width=True)

        # Coverage bar chart
        if len(cv_rows) >= 2:
            cov_fig = go.Figure()
            labels_cv = [r["Variable"] for r in cv_rows]

            cov80_vals = [float(r["80% PI Coverage"].rstrip("%")) for r in cv_rows]
            cov95_vals = [float(r["95% PI Coverage"].rstrip("%")) for r in cv_rows]

            cov_fig.add_trace(go.Bar(
                name="80% PI Coverage",
                x=labels_cv, y=cov80_vals,
                marker_color="#6C8EE6",
                text=[f"{v:.0f}%" for v in cov80_vals],
                textposition="outside",
            ))
            cov_fig.add_trace(go.Bar(
                name="95% PI Coverage",
                x=labels_cv, y=cov95_vals,
                marker_color="#35C9D0",
                text=[f"{v:.0f}%" for v in cov95_vals],
                textposition="outside",
            ))

            cov_fig.add_hline(y=80, line_dash="dot", line_color="#6C8EE6",
                              annotation_text="Target 80%", annotation_font_size=10)
            cov_fig.add_hline(y=95, line_dash="dot", line_color="#35C9D0",
                              annotation_text="Target 95%", annotation_font_size=10)

            _apply_layout(cov_fig, height=300)
            cov_fig.update_layout(
                barmode="group", yaxis=dict(title="Coverage (%)", range=[0, 115]),
                bargap=0.2, bargroupgap=0.05,
                legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
            )
            st.plotly_chart(cov_fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 9. AI FORECAST NARRATIVE
# ──────────────────────────────────────────────────────────────

section_header("AI Forecast Interpretation", "🤖", "Plain-English SO WHAT for decision-makers")

if st.button("🤖 Generate forecast narrative + risk interpretation", use_container_width=True, key="ai_fc"):

    # Build a rich context string for the LLM
    lines = [
        f"Region: Uttarakhand, India",
        f"Historical data: April 2015 – September 2025 (126 months)",
        f"Forecast horizon: {horizon} months",
        "",
        "VARIABLE FORECASTS (point ± 95% PI):",
    ]

    for key, fc_data in ok_vars.items():
        meta = VAR_CONFIG[key]
        for i, fd in enumerate(fc_data["forecast_dates"]):
            lo = fc_data["lower_95"][i]
            hi = fc_data["upper_95"][i]
            pt_val = fc_data["point"][i]
            lines.append(
                f"  {meta['emoji']} {meta['label']} — {fd.strftime('%b %Y')}: "
                f"{pt_val:.4f} {meta['unit']}  [95% PI: {lo:.4f} – {hi:.4f}]"
            )

    lines += [
        "",
        "DROUGHT RISK SCORES:",
    ]
    for month, score in zip(month_labels, risk_scores):
        lbl, _ = drought_risk_label(score)
        lines.append(f"  {month}: {score:.0f}/100  {lbl}")

    cv_summary = []
    for key, fc_data in ok_vars.items():
        cv = fc_data.get("cv_metrics", {})
        if cv:
            cv_summary.append(
                f"  {key}: MAE={cv['mae']:.4f}, RMSE={cv['rmse']:.4f}, "
                f"80%PI coverage={cv['coverage_80']*100:.0f}%"
            )
    if cv_summary:
        lines += ["", "MODEL SKILL (walk-forward CV):"] + cv_summary

    prompt = f"""You are an expert climate scientist and AI analyst for EARTHPULSE-X, a NASA Earth observation project.

{chr(10).join(lines)}

Your task: Write a decision-ready SO WHAT forecast briefing.

Structure your response EXACTLY like this:

**KEY FORECAST FINDINGS** (3–4 bullets with actual numbers)
- What is each variable predicted to do over the forecast window? (use actual values and units)
- Which variables show the most uncertainty? (use PI widths)

**DROUGHT RISK OUTLOOK**
- What does the composite risk score trajectory look like month-by-month?
- What combination of signals is driving the risk?
- Is this a high-risk season or not?

**MODEL CONFIDENCE**
- How reliable are these forecasts? (cite CV metrics — MAE, RMSE, PI coverage)
- What could cause the actual values to fall outside the prediction intervals?

**VERDICT — 2 sentences**
Plain English summary of what Uttarakhand's environment is likely to face over the next {horizon} months.

Rules: Use actual numbers throughout. No generic disclaimers. No AI intro fluff. Be direct."""

    with st.spinner("🤖 AI generating forecast briefing…"):
        try:
            response = _GROQ_CLIENT.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.25,
                max_tokens=800,
            )
            ai_card(response.choices[0].message.content.strip())
        except Exception as e:
            st.error(f"AI unavailable: {e}")

# ──────────────────────────────────────────────────────────────
# 10. METHODOLOGY EXPANDER
# ──────────────────────────────────────────────────────────────

st.markdown("#### 🔬 Methodology — Forecasts, lag links, and uncertainty")
with st.container(border=True):
    st.markdown("""
    ### Forecast Model Architecture

    **Algorithm: Seasonal AutoRegressive + Ridge (SAR-Ridge)**

    This is a custom model designed specifically for Uttarakhand's 10-year monthly 
    environmental time series. It was chosen over LSTM or Prophet because:
    - **Zero new dependencies** — runs on existing scikit-learn + scipy + numpy stack
    - **Interpretable** — Ridge coefficients show the contribution of each lag and harmonic
    - **Statistically valid** — bootstrap PI handles non-Gaussian, autocorrelated residuals
      (same autocorrelation problem addressed by Modified Mann-Kendall in the Trend page)

    ---

    **Feature Engineering (what the model "sees"):**

    | Feature group | Features | Captures |
    |---|---|---|
    | AR lags | t-1, t-2, t-3, t-6, t-12 | Temporal memory (short + annual lag) |
    | Fourier harmonics | sin/cos(2πkm/12), k=1,2,3 | Intra-annual seasonality |
    | Trend index | t/N | Long-term trend direction |

    ---

    **Uncertainty Quantification:**

    Monte Carlo Bootstrap over residuals:
    1. Fit model on full training data → save residuals
    2. For each of 1,000 bootstrap samples: resample residuals + add to each recursive forecast step
    3. Compute empirical 10th/90th percentile → **80% PI**
    4. Compute empirical 2.5th/97.5th percentile → **95% PI**

    This is an *empirical* (not parametric) interval — valid even when residuals 
    are autocorrelated or non-Gaussian (common in satellite time series).

    ---

    **Drought Risk Score:**

    Inspired by the Palmer Drought Severity Index (PDSI) but built entirely from 
    NASA satellite forecasts. Four signals (LST, NDVI, SMAP, GPM) are z-scored 
    against their 10-year climatological baseline, weighted (20/25/35/20), and 
    passed through a logistic sigmoid to yield a 0–100 score.

    ---

    ### Cross-variable lag model

    The **what-if lab** uses a ridge-regularised Vector Autoregression (VAR). First, each signal's average calendar-month cycle is removed, then the remaining monthly values are standardised so temperature, rainfall, soil moisture, and vegetation can be modelled together. The VAR uses the previous 1–3 months of all available signals to estimate the next month for every signal at once. Ridge regularisation limits overfitting on this 126-month record.

    The **Granger screen** asks whether adding one signal's past values improves prediction of another, while accounting for the other signals' past values. Benjamini–Hochberg correction adjusts for all directed pairs. A passing link is a useful lead–lag clue, **not proof that one environmental process physically caused another**; shared drivers and satellite measurement limits can also explain a link.

    In the **what-if scenario**, the selected source signal is set to a chosen number of standard deviations above or below its usual seasonal level in the first forecast month. The VAR then propagates that changed value through later months. The displayed difference is conditional on this model and is not an intervention study or a causal effect estimate. Monthly inputs cannot resolve delays measured in weeks.

    ### District Climate Watch index

    The page converts projected standardized anomalies into two prototype environmental-setup scores: warm/dry vegetation stress and heavy-rain/wet-ground conditions. A directional anomaly is capped at 2.5 standard deviations and scaled to 0–100; the strongest forecast setup across the selected months is combined with the district's percentile rank in historical satellite anomaly exposure (70% forecast setup, 30% historical rank). The historical ranking comes from spatial anomaly pixels, not a verified landslide/fire/flood inventory. Therefore the final 0–100 value is a **relative monitoring-priority index**, not an event probability or operational warning. District-specific forecast data and hazard-outcome validation would be needed before operational use.
    """)

# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────

footer()
