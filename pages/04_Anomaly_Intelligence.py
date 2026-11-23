"""
Anomaly Intelligence — Multi-Hazard District Analysis
======================================================
Overview + per-hazard drill-down for all 6 hazard types.

Top section  : overview catalogue + frequency chart (all hazards)
Tab section  : one tab per hazard — district cards + choropleth +
               per-district month list + AI briefing
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from google.genai import types
from core.gemini_client import GEMINI_CLIENT, GEMINI_MODEL

from core.data_loader import (
    load_district_results,
    load_district_boundaries,
    load_seasonal_anomalies,
    load_spatial_anomaly_events,
)
from core.early_warning_engine import (
    compute_monthly_alerts,
    compute_district_risk_from_spatial,
    district_hazard_breakdown,
    hazard_frequency_summary,
    HAZARD_CATALOGUE,
    VAR_META,
    alert_color,
    alert_emoji,
    chamoli_2021_validation,
)
from components.theme import (
    inject_theme,
    page_header,
    section_header,
    badge,
    info_banner,
    ai_card,
    footer,
)
from components.sidebar import render_sidebar
from components.maps import choropleth_map
from components.charts import _apply_layout, COLORS

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Anomaly Intelligence | EARTHPULSE-X",
    page_icon="🌍",
    layout="wide",
)

inject_theme()
render_sidebar()

# ──────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────

@st.cache_data
def load_all():
    results    = load_district_results()
    boundaries = load_district_boundaries()
    merged     = boundaries.merge(results, on="district_name", how="left")
    merged     = merged.to_crs("EPSG:4326")
    anomalies  = load_seasonal_anomalies()
    spatial    = load_spatial_anomaly_events()
    return merged, anomalies, spatial, boundaries

try:
    districts, anomalies, spatial_df, boundaries = load_all()
except Exception as e:
    st.error(f"❌ Data load failed: {e}")
    st.stop()

@st.cache_data
def _alerts():
    return compute_monthly_alerts(anomalies)

monthly_alerts = _alerts()
hazard_freq    = hazard_frequency_summary(monthly_alerts)

# Heavy computation: per-hazard district breakdown (cached)
@st.cache_data(ttl=1)  # ttl=1 forces recompute on next run
def _hazard_breakdown():
    return district_hazard_breakdown(
        monthly_alerts, spatial_df, boundaries_gdf=boundaries
    )

with st.spinner("Computing per-hazard district intelligence…"):
    hazard_district_data = _hazard_breakdown()

# Overall district risk (composite, for the overview map)
@st.cache_data
def _overall_risk():
    return compute_district_risk_from_spatial(
        spatial_df, month_filter=None, boundaries_gdf=boundaries, threshold=3.0
    )

overall_risk = _overall_risk()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "ANOMALY INTELLIGENCE",
    "Multi-Hazard District Analysis · 6 Hazard Types · 5 NASA Sensors · Uttarakhand",
    "🌍",
)

info_banner(
    "**Overview** shows all hazards together. "
    "**Each tab below** drills into one specific hazard type — "
    "see exactly which districts were affected, how many months, and when.",
    kind="info",
)

# ──────────────────────────────────────────────────────────────
# SECTION A: OVERVIEW  (catalogue + frequency — stays on top)
# ──────────────────────────────────────────────────────────────

section_header("Hazard Overview — All 6 Types", "📖",
               "10-year frequency · Apr 2015 – Sep 2025")

# Catalogue cards
haz_cols = st.columns(3)
for i, (htype, meta) in enumerate(HAZARD_CATALOGUE.items()):
    freq_row   = hazard_freq[hazard_freq["hazard_type"] == htype]
    freq_count = int(freq_row["months_triggered"].iloc[0]) if not freq_row.empty else 0
    with haz_cols[i % 3]:
        st.markdown(f"""
        <div class="glass-card" style="border-left:4px solid {meta['color']};
             padding:14px 16px; margin-bottom:12px; min-height:148px;">
          <div style="font-size:1.5rem;">{meta['emoji']}</div>
          <div style="font-size:0.85rem; font-weight:700; color:{meta['color']}; margin:4px 0;">
              {meta['label']}
          </div>
          <div style="font-size:0.72rem; color:#AAB8CC; line-height:1.5;">
              {meta['description']}
          </div>
          <div style="font-size:0.68rem; color:#6B7B91; margin-top:8px;">
              Triggered: <b style="color:{meta['color']}">{freq_count}</b> months in 10yr record
          </div>
        </div>
        """, unsafe_allow_html=True)

# Frequency bar chart
if not hazard_freq.empty:
    freq_fig = go.Figure(go.Bar(
        x=hazard_freq["label"],
        y=hazard_freq["months_triggered"],
        marker=dict(color=hazard_freq["color"].tolist(),
                    line=dict(color="rgba(0,0,0,0)")),
        text=[f"{HAZARD_CATALOGUE.get(ht,{}).get('emoji','')}{v}"
              for ht, v in zip(hazard_freq["hazard_type"], hazard_freq["months_triggered"])],
        textposition="outside",
        textfont=dict(size=13, color="#F1F5FC"),
        hovertemplate="<b>%{x}</b><br>%{y} months triggered<extra></extra>",
    ))
    _apply_layout(freq_fig, height=280)
    freq_fig.update_layout(
        yaxis=dict(title="Months triggered"),
        xaxis=dict(tickangle=-15),
        showlegend=False, bargap=0.3,
    )
    st.plotly_chart(freq_fig, use_container_width=True)
    st.caption("A month can trigger multiple hazard types → totals may exceed 126")

st.divider()

# ──────────────────────────────────────────────────────────────
# SECTION B: PER-HAZARD TABS
# ──────────────────────────────────────────────────────────────

section_header("Per-Hazard District Intelligence", "🔍",
               "Select a hazard type → see exactly which districts, which months, how intense")

tab_labels = [
    f"{HAZARD_CATALOGUE[ht]['emoji']} {HAZARD_CATALOGUE[ht]['label'].split('/')[0].strip()}"
    for ht in HAZARD_CATALOGUE
]
tabs = st.tabs(tab_labels)

for tab, (htype, meta) in zip(tabs, HAZARD_CATALOGUE.items()):
    with tab:
        df_h = hazard_district_data.get(htype, pd.DataFrame())

        # ── Hazard header
        freq_row   = hazard_freq[hazard_freq["hazard_type"] == htype]
        freq_count = int(freq_row["months_triggered"].iloc[0]) if not freq_row.empty else 0

        affected   = df_h[df_h["months_triggered"] > 0] if not df_h.empty else pd.DataFrame()
        n_affected = len(affected)

        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:16px; margin-bottom:16px;
             padding:16px 20px; background:rgba(0,0,0,0.2); border-radius:12px;
             border-left:4px solid {meta['color']};">
          <div style="font-size:2.5rem;">{meta['emoji']}</div>
          <div>
            <div style="font-size:1.1rem; font-weight:800; color:{meta['color']};">
                {meta['label']}
            </div>
            <div style="font-size:0.82rem; color:#AAB8CC; margin-top:4px;">
                {meta['description']}
            </div>
            <div style="font-size:0.72rem; color:#6B7B91; margin-top:6px;">
                ⏱ {freq_count} regional months triggered &nbsp;·&nbsp;
                🗺 {n_affected} of 13 districts exposed &nbsp;·&nbsp;
                🎯 Action: {meta['action']}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if df_h.empty or freq_count == 0:
            st.info(f"No {meta['label']} events detected in the 10-year record at current thresholds.")
            continue

        # ── KPI row  — always re-sort by risk_score desc to get true top district
        top_district = df_h[df_h["months_triggered"] > 0].sort_values("risk_score", ascending=False)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Regional months triggered", freq_count)
        k2.metric("Districts exposed", n_affected)
        if not top_district.empty:
            k3.metric("Highest-risk district", top_district.iloc[0]["district_name"])
            k4.metric("Risk score", f"{top_district.iloc[0]['risk_score']:.0f}/100")

        # ────────────────────────────────────────────────────
        # ── FULL-WIDTH CHOROPLETH MAP
        # ────────────────────────────────────────────────────
        try:
            import plotly.express as px
            import json as _json

            def _fmt_month(m):
                try:    return pd.to_datetime(m).strftime("%b %Y")
                except: return str(m)

            def _hex_to_rgb(h):
                h = h.lstrip("#")
                return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

            map_data = boundaries.to_crs("EPSG:4326").merge(
                df_h[["district_name", "risk_score", "months_triggered",
                      "mean_intensity_z", "max_intensity_z", "worst_month"]],
                on="district_name", how="left",
            ).fillna({"risk_score": 0, "months_triggered": 0,
                      "mean_intensity_z": 0.0, "max_intensity_z": 0.0,
                      "worst_month": "—"})

            map_data["worst_month_label"] = map_data["worst_month"].apply(_fmt_month)
            map_data["intensity_label"]   = map_data["mean_intensity_z"].apply(
                lambda v: f"{v:+.2f}σ"
            )

            # ── Colour column selection per hazard ───────────────────────
            # Rule: use the column that best shows *geographic* variation.
            # For hazards where risk_score is elevation-weighted (Cold, Heat, Flood,
            # VegLoss) use risk_score directly — it already captures the geo signal.
            # For Drought & Compound use mean_intensity_z (abs) since risk_score
            # has no strong elevation correction there.
            GEO_WEIGHTED = {"COLD_STRESS", "HEAT_WAVE", "FLOOD", "VEGETATION_LOSS"}
            if htype in GEO_WEIGHTED:
                map_data["_color_val"] = map_data["risk_score"]
            elif htype == "DROUGHT":
                map_data["_color_val"] = map_data["mean_intensity_z"].abs()
            else:   # COMPOUND
                map_data["_color_val"] = map_data["mean_intensity_z"]

            # Clamp negatives to 0 (unexposed districts)
            map_data["_color_val"] = map_data["_color_val"].clip(lower=0)

            c_min = float(map_data["_color_val"].min())
            c_max = float(map_data["_color_val"].max())
            if c_max - c_min < 0.1:   # truly flat → fall back to risk_score
                map_data["_color_val"] = map_data["risk_score"]
                c_min = float(map_data["_color_val"].min())
                c_max = float(map_data["_color_val"].max())

            # Hazard-specific colorscale: dark bg → full hazard colour
            hr, hg, hb = _hex_to_rgb(meta["color"])
            custom_cs = [
                [0.00, "rgba(10,16,32,1.0)"],
                [0.20, f"rgba({hr},{hg},{hb},0.25)"],
                [0.50, f"rgba({hr},{hg},{hb},0.55)"],
                [0.75, f"rgba({hr},{hg},{hb},0.80)"],
                [1.00, f"rgba({hr},{hg},{hb},1.00)"],
            ]

            haz_fig = px.choropleth(
                map_data,
                geojson=_json.loads(map_data.geometry.to_json()),
                locations=map_data.index,
                color="_color_val",
                color_continuous_scale=custom_cs,
                range_color=[c_min, c_max],
                custom_data=[
                    "district_name", "risk_score", "months_triggered",
                    "intensity_label", "worst_month_label",
                ],
            )

            haz_fig.update_traces(
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    f"{meta['emoji']} Risk: <b>%{{customdata[1]:.0f}}</b>/100<br>"
                    "⏱ Months exposed: <b>%{customdata[2]}</b><br>"
                    "📊 Mean intensity: <b>%{customdata[3]}</b><br>"
                    "📅 Worst month: <b>%{customdata[4]}</b>"
                    "<extra></extra>"
                ),
                marker_line_color="rgba(241,245,252,0.30)",
                marker_line_width=1.2,
            )

            haz_fig.update_geos(
                fitbounds="locations",
                visible=False,
                bgcolor="rgba(0,0,0,0)",
            )

            # District name labels directly on map
            label_pts = map_data.to_crs("EPSG:32644").copy()
            label_pts["geometry"] = label_pts.geometry.representative_point()
            label_pts = label_pts.to_crs("EPSG:4326")

            haz_fig.add_scattergeo(
                lon=label_pts.geometry.x,
                lat=label_pts.geometry.y,
                text=label_pts["district_name"],
                mode="text",
                textfont=dict(size=9, color="rgba(241,245,252,0.92)", family="Urbanist"),
                showlegend=False,
                hoverinfo="skip",
            )

            haz_fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(10,16,32,0.5)",
                font=dict(family="Urbanist, sans-serif", size=12, color="#AAB8CC"),
                height=580,
                margin=dict(l=0, r=0, t=10, b=10),
                coloraxis_colorbar=dict(
                    title=dict(
                        text=f"{meta['emoji']} Intensity (σ)",
                        font=dict(size=12, color="#AAB8CC"),
                    ),
                    thickness=14,
                    len=0.7,
                    tickfont=dict(size=10, color="#AAB8CC"),
                    bgcolor="rgba(10,16,32,0.7)",
                    bordercolor="#1E2D4A",
                    borderwidth=1,
                ),
            )

            st.plotly_chart(
                haz_fig,
                use_container_width=True,
                key=f"haz_map_{htype}",
            )
            st.caption(
                f"Light = low intensity · Dark = high {meta['label']} signal · "
                "Colour = mean sensor z-score intensity across district pixels · "
                "Hover on any district for risk score details"
            )

        except Exception as e:
            st.warning(f"Map render issue: {e}")

        # ────────────────────────────────────────────────────
        # ── RANKED LIST — district mini-map cards
        # ────────────────────────────────────────────────────
        st.markdown(
            f"<div style='font-size:0.82rem; font-weight:700; color:{meta['color']};"
            f" margin: 14px 0 8px 0;'>{meta['emoji']} Districts — ranked by exposure</div>",
            unsafe_allow_html=True,
        )

        ranked = df_h.sort_values("risk_score", ascending=False)

        # ── Pre-computed SVG paths (W=200, H=125 canvas, tolerance=0.008°)
        # Format: district_name -> (svg_path_d, (vx, vy, vw, vh))
        _DISTRICT_SVG = {
            "Almora":            ("M 131.03,92.73 L 129.73,92.95 L 127.03,91.76 L 126.32,92.52 L 124.54,92.67 L 124.47,91.31 L 123.22,91.4 L 121.81,90.52 L 121.43,88.28 L 117.66,86.99 L 114.96,87.79 L 112.68,87.38 L 111.74,89.29 L 109.78,89.75 L 106.72,87.23 L 101.49,84.42 L 98.75,85.45 L 98.77,86.04 L 95.03,88.57 L 90.71,87.75 L 90.35,87.14 L 88.47,87.52 L 88.61,86.93 L 86.79,85.82 L 84.4,85.7 L 85.69,85.57 L 86.11,84.03 L 86.8,84.21 L 86.94,82.68 L 87.82,81.62 L 88.51,82.04 L 88.94,81.19 L 88.31,80.47 L 89.23,79.59 L 88.48,78.61 L 88.58,76.9 L 89.18,77.1 L 89.57,76.55 L 89.17,75.38 L 87.8,73.59 L 86.1,72.96 L 86.3,72.52 L 87.15,71.67 L 89.57,70.96 L 91.47,70.52 L 92.46,70.92 L 93.35,69.23 L 95.34,69.12 L 95.2,67.62 L 98.66,68.91 L 98.47,70.1 L 100.93,69.91 L 101.55,69.3 L 101.11,67.96 L 101.74,67.93 L 103.8,70.04 L 105.68,69.29 L 106.68,69.67 L 109.12,67.69 L 110.14,67.82 L 110.01,68.63 L 111.5,69.65 L 110.98,69.73 L 111.34,71.03 L 110.76,71.65 L 111.57,72.81 L 116.83,74.18 L 121.38,74.47 L 122.66,76.15 L 122.36,77.4 L 126.48,81.42 L 128.28,81.79 L 130.59,79.64 L 135.58,80.43 L 137.51,81.49 L 139.83,86.79 L 143.71,87.83 L 144.39,88.59 L 141.68,89.17 L 139.91,90.28 L 136.47,90.64 L 136.17,91.13 L 135.01,90.12 L 133.32,89.96 L 131.97,91.84 L 131.24,91.71 L 131.03,92.73 Z",         (73.53, 63.04, 81.66, 34.52)),
            "Bageshwar":         ("M 133.71,79.81 L 130.51,79.66 L 128.28,81.79 L 126.29,81.35 L 125.79,80.18 L 122.36,77.4 L 122.66,76.15 L 121.38,74.47 L 116.83,74.18 L 111.55,72.79 L 110.76,71.65 L 111.34,71.03 L 110.98,69.73 L 111.5,69.65 L 110.01,68.63 L 110.4,68.08 L 109.43,67.63 L 109.37,66.88 L 110.15,65.62 L 113.8,66.86 L 117.49,65.76 L 123.77,66.61 L 126.95,66.49 L 129.0,65.7 L 129.93,64.02 L 127.61,63.05 L 126.15,60.65 L 127.24,59.76 L 127.28,58.47 L 128.37,57.0 L 129.53,56.37 L 128.31,53.66 L 130.89,53.49 L 132.52,54.28 L 135.92,53.02 L 137.65,53.32 L 139.12,52.18 L 141.03,52.23 L 143.79,53.79 L 143.36,54.29 L 144.35,55.78 L 146.55,56.27 L 143.79,65.77 L 144.29,67.24 L 148.12,69.37 L 148.95,70.61 L 148.72,71.35 L 145.87,71.58 L 140.57,70.96 L 140.32,73.05 L 138.52,73.47 L 138.51,73.94 L 139.53,73.78 L 141.63,75.08 L 141.96,76.06 L 139.12,77.52 L 135.91,77.37 L 135.94,76.29 L 134.36,75.92 L 132.37,77.36 L 129.65,76.72 L 130.27,78.15 L 132.27,78.63 L 133.71,79.81 Z",         (102.2, 46.83, 53.89, 40.29)),
            "Chamoli":           ("M 145.57,30.42 L 144.78,31.24 L 145.71,33.47 L 141.38,33.04 L 138.68,34.17 L 138.94,35.09 L 141.81,37.57 L 141.56,38.47 L 142.33,39.27 L 140.59,40.37 L 139.65,42.07 L 141.04,44.64 L 140.38,45.19 L 142.04,46.34 L 142.05,48.07 L 139.71,49.94 L 138.76,52.75 L 137.28,53.4 L 135.92,53.02 L 132.52,54.28 L 130.89,53.49 L 128.2,53.82 L 129.53,56.37 L 128.37,57.0 L 127.28,58.47 L 127.24,59.76 L 126.15,60.65 L 127.61,63.05 L 129.93,64.02 L 129.0,65.7 L 126.95,66.49 L 123.77,66.61 L 117.49,65.76 L 113.8,66.86 L 110.15,65.62 L 109.43,67.63 L 106.91,69.58 L 105.66,69.3 L 103.8,70.04 L 101.58,67.89 L 101.07,67.98 L 101.55,69.3 L 100.93,69.91 L 98.47,70.1 L 98.66,68.91 L 94.91,67.42 L 94.76,65.63 L 93.11,64.93 L 93.93,63.77 L 93.39,62.85 L 91.53,62.44 L 89.97,61.27 L 90.54,59.4 L 87.86,57.68 L 88.07,57.02 L 87.03,56.76 L 86.57,56.59 L 87.42,56.76 L 86.71,54.37 L 86.89,53.64 L 87.78,53.69 L 87.15,53.28 L 87.98,51.23 L 87.76,49.21 L 91.56,49.11 L 92.29,47.02 L 91.81,46.24 L 93.25,44.83 L 95.05,44.17 L 96.41,41.08 L 99.23,41.0 L 99.94,39.73 L 101.77,39.35 L 102.75,37.79 L 102.17,36.72 L 99.69,35.6 L 99.34,33.75 L 98.07,33.54 L 98.9,32.34 L 95.11,29.23 L 98.13,26.32 L 98.55,23.65 L 97.66,22.79 L 100.81,22.16 L 100.01,20.26 L 103.24,19.17 L 105.89,17.15 L 106.86,19.82 L 111.41,19.4 L 111.86,20.84 L 113.62,21.37 L 113.18,21.87 L 114.13,22.84 L 116.97,23.94 L 120.46,22.47 L 120.62,21.65 L 123.52,22.02 L 124.67,21.74 L 125.63,20.59 L 129.24,22.16 L 132.6,22.39 L 133.45,24.66 L 134.69,24.84 L 135.82,26.32 L 137.68,25.99 L 139.68,27.03 L 140.3,26.73 L 141.64,27.92 L 142.85,27.86 L 145.57,30.42 Z",    (75.91,  7.62, 80.55, 72.01)),
            "Champawat":         ("M 144.22,114.79 L 142.81,113.25 L 143.27,112.33 L 140.89,108.27 L 140.16,109.2 L 138.08,110.02 L 137.24,108.66 L 138.46,106.96 L 136.53,106.38 L 134.78,106.6 L 132.86,105.27 L 132.91,104.58 L 135.66,102.66 L 134.51,101.02 L 132.13,100.55 L 131.52,99.81 L 130.61,99.99 L 130.38,98.3 L 128.65,98.07 L 127.98,97.08 L 130.12,96.98 L 130.16,97.62 L 131.67,98.2 L 132.77,96.48 L 134.1,96.57 L 133.65,95.55 L 131.7,95.55 L 131.84,95.08 L 130.24,94.02 L 131.58,92.66 L 131.24,91.71 L 131.97,91.84 L 133.32,89.96 L 135.01,90.12 L 136.17,91.13 L 136.47,90.64 L 139.94,90.28 L 141.68,89.17 L 145.82,88.47 L 148.47,90.86 L 153.72,92.06 L 153.72,93.46 L 155.61,94.38 L 155.41,95.69 L 158.11,98.48 L 156.52,101.63 L 156.59,103.29 L 154.78,102.86 L 154.4,102.19 L 153.82,102.57 L 155.39,105.88 L 153.23,106.85 L 150.42,106.04 L 149.31,106.55 L 147.16,109.51 L 147.62,109.61 L 146.94,111.78 L 147.57,111.97 L 146.56,113.15 L 145.54,112.93 L 144.22,114.79 Z",         (122.56, 83.72, 40.97, 35.85)),
            "Dehradun":          ("M 4.67,48.15 L 0.13,48.28 L 0.0,47.85 L 1.14,47.12 L 4.06,46.9 L 4.5,46.18 L 6.74,46.16 L 8.42,45.05 L 13.98,43.52 L 14.64,42.44 L 13.96,40.82 L 11.44,40.96 L 9.73,39.39 L 10.5,38.98 L 11.38,39.36 L 11.44,38.42 L 12.83,38.57 L 11.99,37.03 L 12.63,36.54 L 10.02,35.42 L 10.52,34.3 L 9.1,32.85 L 7.46,32.5 L 7.77,31.31 L 10.82,28.83 L 9.96,27.75 L 10.59,26.62 L 11.34,26.43 L 11.9,27.3 L 13.38,27.61 L 13.14,25.74 L 13.91,25.29 L 13.84,24.48 L 11.05,24.49 L 10.22,23.46 L 10.39,22.54 L 11.47,22.05 L 14.92,23.17 L 15.01,22.68 L 13.97,22.55 L 14.74,22.07 L 14.56,21.28 L 15.48,21.14 L 16.13,22.97 L 17.14,23.43 L 20.39,22.16 L 22.83,21.94 L 25.76,24.6 L 23.11,25.94 L 24.06,28.21 L 26.11,29.78 L 25.95,30.51 L 29.15,32.75 L 29.43,33.74 L 28.13,36.19 L 26.43,37.14 L 25.2,36.85 L 25.41,39.61 L 23.13,42.05 L 23.91,43.09 L 22.7,43.34 L 21.64,42.84 L 20.99,43.51 L 23.87,45.33 L 25.07,44.54 L 26.69,45.36 L 27.18,44.5 L 29.24,45.32 L 30.6,44.76 L 38.36,47.28 L 37.57,48.09 L 33.7,49.3 L 32.27,50.93 L 32.83,51.8 L 36.17,53.24 L 36.92,52.54 L 38.24,52.97 L 38.24,53.52 L 39.44,53.61 L 40.02,52.83 L 40.99,53.31 L 40.63,54.24 L 41.71,55.99 L 38.05,58.19 L 38.53,59.08 L 39.63,59.28 L 39.31,60.33 L 42.51,61.7 L 41.36,62.16 L 40.76,63.91 L 38.85,64.77 L 38.89,65.69 L 37.7,65.9 L 37.84,67.2 L 35.36,68.36 L 36.0,67.19 L 35.51,66.84 L 34.39,68.31 L 33.18,68.16 L 32.2,66.72 L 30.07,66.1 L 30.34,65.44 L 28.57,64.7 L 28.55,63.18 L 26.64,61.91 L 24.98,58.79 L 22.02,56.11 L 22.2,55.35 L 21.09,55.53 L 18.35,54.36 L 15.28,53.97 L 8.43,51.39 L 4.67,48.15 Z",          (-7.65, 12.64, 57.83, 64.22)),
            "Haridwar":          ("M 11.39,64.58 L 13.11,62.31 L 14.84,62.69 L 16.48,61.5 L 19.54,58.29 L 19.88,57.01 L 22.35,55.57 L 22.02,56.11 L 24.98,58.79 L 26.64,61.91 L 28.55,63.18 L 28.57,64.7 L 30.34,65.44 L 30.07,66.1 L 32.2,66.72 L 33.18,68.16 L 34.39,68.31 L 35.54,66.85 L 36.0,67.19 L 35.36,68.36 L 36.26,68.25 L 40.26,70.11 L 39.91,71.07 L 42.72,72.85 L 43.69,75.99 L 39.44,78.49 L 36.22,78.54 L 35.76,80.58 L 34.36,80.63 L 31.99,82.42 L 29.16,83.22 L 29.46,83.68 L 27.77,83.42 L 25.52,84.91 L 25.71,85.71 L 24.18,85.02 L 22.65,85.7 L 23.97,82.63 L 22.4,81.57 L 21.41,79.68 L 20.22,79.6 L 19.42,80.44 L 17.7,80.14 L 17.24,80.83 L 14.67,81.7 L 13.08,80.97 L 13.54,80.14 L 11.3,79.61 L 12.03,78.8 L 11.33,78.26 L 11.95,77.43 L 11.58,76.27 L 10.37,75.31 L 9.58,73.29 L 8.14,72.59 L 8.29,71.83 L 10.07,70.75 L 9.11,69.74 L 10.78,68.31 L 9.81,67.44 L 12.36,65.53 L 11.39,64.58 Z",           (1.74, 50.13, 48.38, 41.03)),
            "Nainital":          ("M 77.74,92.42 L 79.46,91.21 L 80.53,87.79 L 82.49,87.13 L 82.74,85.65 L 83.79,85.49 L 86.79,85.82 L 88.61,86.93 L 88.47,87.52 L 90.35,87.14 L 90.71,87.75 L 95.03,88.57 L 98.77,86.04 L 98.75,85.45 L 101.49,84.42 L 106.72,87.23 L 109.81,89.76 L 111.74,89.29 L 112.74,87.36 L 114.94,87.79 L 117.65,86.99 L 118.78,87.69 L 119.6,87.4 L 121.48,88.35 L 122.11,90.93 L 124.48,91.32 L 124.54,92.67 L 126.32,92.52 L 127.03,91.76 L 129.73,92.95 L 131.58,92.63 L 130.27,94.31 L 131.84,95.08 L 131.7,95.55 L 133.65,95.55 L 134.1,96.57 L 132.77,96.48 L 131.67,98.2 L 130.16,97.62 L 130.12,96.98 L 127.98,97.08 L 128.65,98.07 L 130.38,98.3 L 130.61,99.99 L 131.52,99.81 L 132.13,100.55 L 134.51,101.02 L 135.66,102.66 L 132.97,104.52 L 132.84,105.22 L 134.78,106.6 L 136.53,106.38 L 138.46,106.96 L 137.24,108.66 L 138.19,110.05 L 134.8,110.97 L 133.95,112.75 L 133.0,112.77 L 132.79,113.45 L 131.63,111.87 L 129.19,113.13 L 128.08,112.15 L 128.7,111.77 L 128.36,111.34 L 126.81,111.34 L 126.28,110.77 L 125.29,111.3 L 123.16,111.04 L 121.9,109.78 L 119.74,108.99 L 118.27,110.14 L 106.68,109.75 L 103.01,107.56 L 102.01,105.86 L 101.26,106.27 L 97.2,103.58 L 97.64,103.39 L 96.97,103.33 L 96.94,102.46 L 98.5,101.1 L 90.26,99.43 L 88.8,100.17 L 87.65,99.37 L 84.59,99.87 L 83.52,97.6 L 81.32,97.95 L 78.48,96.47 L 74.28,96.03 L 77.96,93.62 L 78.83,92.4 L 77.74,92.42 Z",          (62.52, 79.17, 87.66, 39.51)),
            "Pauri Garhwal":     ("M 43.7,75.89 L 42.72,72.85 L 39.91,71.07 L 40.34,70.18 L 36.26,68.25 L 37.89,67.16 L 37.67,65.94 L 38.89,65.69 L 38.93,64.68 L 40.79,63.87 L 41.36,62.16 L 43.85,60.55 L 46.1,61.33 L 47.99,60.39 L 49.89,61.56 L 49.61,62.96 L 52.11,63.65 L 52.25,64.14 L 53.21,63.22 L 54.05,64.14 L 55.31,63.2 L 58.51,64.26 L 59.3,63.55 L 58.19,63.38 L 58.73,62.71 L 57.97,61.92 L 59.25,60.88 L 59.01,59.71 L 60.12,59.82 L 60.42,58.48 L 61.89,57.16 L 63.97,56.56 L 63.98,55.74 L 65.85,55.82 L 67.66,56.9 L 68.76,56.2 L 71.14,56.47 L 72.15,55.39 L 74.12,55.53 L 75.43,54.71 L 77.28,56.69 L 77.34,57.26 L 76.46,56.99 L 75.81,57.87 L 76.77,58.95 L 81.64,58.11 L 84.56,56.62 L 87.65,56.8 L 87.86,57.68 L 90.54,59.4 L 89.96,61.26 L 91.53,62.44 L 93.39,62.85 L 93.93,63.77 L 93.12,64.96 L 94.76,65.63 L 94.84,67.33 L 95.62,68.17 L 95.24,69.17 L 93.31,69.25 L 92.46,70.92 L 91.47,70.52 L 89.57,70.96 L 87.15,71.67 L 86.3,72.52 L 86.1,72.96 L 88.64,74.39 L 89.57,76.55 L 89.18,77.1 L 88.58,76.91 L 88.5,78.88 L 89.23,79.59 L 88.31,80.47 L 88.94,81.19 L 88.35,82.23 L 87.95,81.62 L 87.3,82.11 L 87.15,83.53 L 86.78,84.24 L 86.11,84.03 L 85.72,85.55 L 82.76,85.64 L 82.49,87.13 L 80.53,87.79 L 79.46,91.21 L 77.74,92.43 L 70.56,91.03 L 67.41,89.37 L 64.83,89.15 L 57.97,85.49 L 55.65,83.6 L 53.67,78.9 L 43.7,75.89 Z",   (25.57, 47.92, 80.74, 51.29)),
            "Pithoragarh":       ("M 153.67,92.04 L 148.47,90.86 L 146.08,88.54 L 144.27,88.56 L 142.87,87.53 L 140.48,87.21 L 137.49,82.43 L 137.49,81.47 L 135.57,80.42 L 133.51,80.24 L 133.65,79.59 L 130.28,78.16 L 129.53,77.07 L 129.8,76.73 L 132.37,77.36 L 134.36,75.92 L 135.94,76.29 L 135.91,77.37 L 139.12,77.52 L 141.96,76.06 L 141.63,75.08 L 139.53,73.78 L 138.51,73.94 L 138.52,73.47 L 140.32,73.05 L 140.57,70.96 L 145.87,71.58 L 148.72,71.35 L 148.83,69.94 L 144.29,67.24 L 143.79,65.77 L 146.55,56.27 L 144.31,55.74 L 143.36,54.29 L 143.79,53.79 L 142.28,53.35 L 141.29,52.3 L 139.12,52.18 L 139.71,49.94 L 142.05,48.07 L 142.04,46.34 L 140.38,45.19 L 141.04,44.64 L 139.67,41.98 L 140.59,40.37 L 142.33,39.27 L 141.56,38.47 L 141.81,37.57 L 138.94,35.09 L 138.68,34.17 L 141.38,33.04 L 145.71,33.47 L 145.15,30.75 L 148.75,30.44 L 149.11,29.57 L 150.01,29.64 L 151.8,32.05 L 153.37,31.78 L 154.1,32.62 L 153.15,34.86 L 151.19,35.07 L 150.9,35.94 L 152.43,37.17 L 152.1,39.91 L 154.52,40.8 L 158.04,40.81 L 159.79,42.83 L 163.71,42.66 L 165.52,43.9 L 168.54,44.35 L 170.97,46.13 L 174.74,45.12 L 179.54,47.72 L 180.6,47.58 L 182.1,48.35 L 186.1,51.85 L 190.8,52.94 L 192.1,52.74 L 193.72,54.63 L 197.11,54.39 L 200.0,56.91 L 199.04,57.56 L 193.95,58.28 L 193.13,57.92 L 192.8,56.13 L 192.06,56.31 L 189.45,58.75 L 190.3,60.62 L 188.34,61.23 L 187.98,62.01 L 186.74,62.07 L 183.63,64.24 L 182.64,66.31 L 181.19,66.49 L 178.61,68.47 L 176.06,68.11 L 174.08,68.66 L 172.86,70.02 L 171.61,73.37 L 169.0,74.61 L 168.19,75.88 L 164.85,75.39 L 163.21,75.93 L 162.67,77.53 L 160.75,78.41 L 161.93,81.44 L 163.74,82.45 L 163.27,85.04 L 161.59,86.6 L 159.51,86.99 L 160.28,88.1 L 157.92,89.4 L 157.81,90.13 L 157.02,89.84 L 156.2,90.56 L 157.09,91.64 L 155.67,91.32 L 153.67,92.04 Z",       (116.85, 18.28, 95.83, 85.03)),
            "Rudraprayag":       ("M 84.2,29.58 L 85.88,29.6 L 86.97,30.7 L 89.56,31.35 L 90.43,32.44 L 91.71,32.03 L 93.72,33.09 L 99.21,33.59 L 99.69,35.6 L 102.17,36.72 L 102.76,37.76 L 101.77,39.35 L 99.94,39.73 L 99.23,41.0 L 96.41,41.08 L 95.05,44.17 L 93.25,44.83 L 91.81,46.24 L 92.29,47.02 L 91.56,49.11 L 87.76,49.21 L 87.98,51.23 L 87.15,53.28 L 87.78,53.69 L 86.89,53.64 L 86.71,54.37 L 87.42,56.76 L 84.56,56.62 L 81.64,58.11 L 76.77,58.95 L 75.81,57.9 L 76.46,56.99 L 77.34,57.26 L 77.06,56.06 L 74.04,52.92 L 74.98,50.49 L 72.73,50.31 L 72.78,48.78 L 71.6,48.29 L 73.25,47.02 L 73.64,45.78 L 71.94,44.49 L 73.62,44.18 L 74.67,43.19 L 74.11,41.41 L 77.07,37.83 L 77.08,35.08 L 77.89,33.9 L 79.47,33.09 L 81.78,33.16 L 82.23,32.38 L 83.29,32.33 L 84.2,29.58 Z",           (65.99, 24.21, 42.39, 40.04)),
            "Tehri Garhwal":     ("M 42.42,61.42 L 39.31,60.33 L 39.63,59.28 L 38.53,59.08 L 38.05,58.19 L 41.71,55.99 L 40.63,54.24 L 40.99,53.31 L 40.02,52.83 L 39.44,53.61 L 38.24,53.52 L 38.24,52.97 L 36.92,52.54 L 36.17,53.24 L 32.83,51.8 L 32.27,50.93 L 33.7,49.3 L 37.57,48.09 L 38.36,47.28 L 30.6,44.76 L 29.24,45.32 L 27.18,44.5 L 26.69,45.36 L 25.07,44.54 L 23.87,45.33 L 21.04,43.59 L 21.64,42.84 L 22.7,43.34 L 23.91,43.09 L 23.13,42.05 L 23.48,41.24 L 24.84,40.75 L 25.32,38.44 L 27.12,39.15 L 28.9,38.89 L 28.34,38.13 L 29.59,37.64 L 33.47,37.57 L 34.42,39.0 L 34.06,39.73 L 36.42,40.22 L 38.2,39.8 L 38.91,38.68 L 40.55,38.63 L 41.95,39.78 L 41.2,40.46 L 41.98,40.82 L 41.09,40.86 L 41.12,41.35 L 42.58,41.06 L 42.13,40.46 L 44.12,40.85 L 44.73,42.25 L 47.27,43.5 L 47.95,45.1 L 48.52,45.24 L 49.87,41.34 L 49.2,39.98 L 49.99,38.33 L 51.93,37.91 L 53.33,38.61 L 54.16,39.43 L 53.38,40.09 L 53.28,42.36 L 55.69,42.53 L 56.27,40.41 L 59.02,37.79 L 59.18,35.92 L 58.31,35.51 L 58.58,35.14 L 62.4,35.1 L 62.66,34.3 L 64.85,33.97 L 66.05,33.07 L 67.93,34.13 L 73.48,32.9 L 74.3,29.28 L 73.56,27.88 L 74.9,26.58 L 77.91,26.46 L 79.1,27.58 L 81.92,27.24 L 82.9,27.82 L 84.02,29.6 L 83.83,31.58 L 81.78,33.16 L 79.47,33.09 L 77.89,33.9 L 77.08,35.08 L 77.07,37.83 L 74.11,41.41 L 74.67,43.19 L 73.62,44.18 L 71.94,44.49 L 73.64,45.78 L 73.25,47.02 L 71.6,48.29 L 72.78,48.78 L 72.73,50.31 L 74.98,50.49 L 74.04,52.92 L 76.29,55.21 L 75.31,54.72 L 74.12,55.53 L 72.15,55.39 L 71.14,56.47 L 68.76,56.2 L 67.66,56.9 L 65.85,55.82 L 63.92,55.75 L 63.97,56.56 L 61.89,57.16 L 60.42,58.48 L 60.12,59.82 L 59.01,59.71 L 59.25,60.88 L 57.97,61.92 L 58.73,62.71 L 58.19,63.38 L 59.3,63.55 L 58.51,64.26 L 55.31,63.2 L 54.05,64.14 L 53.21,63.22 L 52.25,64.14 L 52.11,63.65 L 49.61,62.96 L 49.89,61.56 L 48.05,60.39 L 46.1,61.33 L 44.13,60.5 L 42.42,61.42 Z",    (9.57, 19.63, 85.8, 51.45)),
            "Udham Singh Nagar": ("M 73.21,96.54 L 75.68,95.99 L 76.09,96.45 L 78.48,96.47 L 81.32,97.95 L 83.52,97.6 L 84.59,99.87 L 87.65,99.37 L 88.8,100.17 L 90.26,99.43 L 98.5,101.1 L 96.74,102.95 L 98.34,104.67 L 101.26,106.27 L 102.01,105.86 L 103.01,107.56 L 108.0,110.0 L 115.51,109.7 L 118.46,110.13 L 119.74,108.99 L 121.9,109.78 L 123.16,111.04 L 125.29,111.3 L 126.28,110.77 L 126.81,111.34 L 128.36,111.34 L 128.7,111.77 L 128.08,112.15 L 129.19,113.13 L 131.63,111.87 L 132.79,113.45 L 133.0,112.77 L 133.95,112.75 L 134.8,110.97 L 137.94,110.27 L 140.87,108.25 L 143.27,112.33 L 142.81,113.25 L 144.39,114.4 L 143.13,116.14 L 143.5,119.79 L 141.93,121.76 L 142.75,122.47 L 141.49,123.82 L 137.11,125.0 L 136.48,123.3 L 135.5,122.76 L 136.28,122.03 L 134.07,122.29 L 132.51,121.64 L 132.92,120.9 L 135.0,121.45 L 134.82,120.62 L 133.77,120.54 L 133.31,119.79 L 131.87,119.62 L 130.89,120.4 L 131.07,121.48 L 128.85,121.55 L 130.36,120.46 L 130.09,119.15 L 130.84,119.29 L 131.13,118.72 L 129.26,117.44 L 127.27,118.2 L 125.29,118.18 L 122.84,119.59 L 119.92,118.27 L 116.23,119.14 L 115.64,118.75 L 116.24,117.64 L 114.62,116.72 L 112.65,118.31 L 107.18,118.22 L 107.32,115.78 L 106.15,114.3 L 104.85,114.32 L 104.11,112.69 L 102.96,113.51 L 100.65,113.15 L 100.55,113.56 L 94.84,110.88 L 92.68,111.54 L 92.04,110.89 L 92.78,109.91 L 91.31,109.44 L 90.89,108.54 L 91.55,106.75 L 84.98,104.41 L 83.82,104.71 L 83.91,105.63 L 83.15,105.22 L 82.98,106.22 L 84.44,106.45 L 84.05,106.94 L 83.14,107.0 L 81.67,105.56 L 80.33,106.44 L 77.61,106.55 L 77.84,105.09 L 76.98,104.34 L 77.45,104.0 L 75.45,102.7 L 75.95,102.43 L 75.38,101.55 L 71.32,101.14 L 69.05,99.28 L 66.78,98.45 L 68.57,96.91 L 70.06,97.19 L 70.34,98.03 L 71.66,97.45 L 71.11,96.78 L 72.19,95.97 L 73.21,96.54 Z M 70.76,97.23 L 70.86,97.21 L 70.69,97.45 L 70.76,97.23 Z M 84.38,105.05 L 84.14,105.06 L 84.04,105.02 L 84.38,105.05 Z M 84.88,104.98 L 84.85,104.83 L 85.01,104.83 L 84.88,104.98 Z M 100.11,113.47 L 100.09,113.43 L 100.13,113.45 L 100.11,113.47 Z",  (52.75, 90.74, 105.63, 39.48)),
            "Uttarkashi":        ("M 42.38,8.17 L 46.64,7.91 L 48.04,9.77 L 49.75,9.24 L 52.48,11.76 L 56.26,11.56 L 58.37,10.71 L 61.89,11.14 L 62.39,12.24 L 63.87,11.65 L 68.63,12.38 L 71.2,11.81 L 71.25,13.02 L 72.41,14.44 L 75.41,16.31 L 77.64,15.81 L 79.48,16.39 L 82.62,15.68 L 82.61,14.96 L 81.47,14.26 L 81.29,12.75 L 79.72,12.19 L 79.09,10.78 L 78.02,10.77 L 77.36,9.52 L 80.1,5.95 L 83.15,4.97 L 82.67,3.56 L 83.15,1.49 L 85.61,1.36 L 86.35,0.0 L 90.11,1.02 L 92.12,3.14 L 91.86,4.35 L 95.24,5.34 L 94.63,6.41 L 96.31,7.43 L 95.03,9.0 L 98.32,9.93 L 99.19,10.75 L 99.45,13.08 L 100.46,14.49 L 103.91,15.69 L 105.59,15.65 L 105.95,16.98 L 103.33,19.13 L 100.01,20.26 L 101.04,21.62 L 100.43,22.49 L 99.31,22.18 L 97.66,22.79 L 98.55,23.65 L 98.13,26.32 L 95.11,29.23 L 98.9,32.34 L 98.07,33.54 L 93.72,33.09 L 91.71,32.03 L 90.42,32.44 L 89.56,31.35 L 86.97,30.7 L 85.88,29.6 L 84.02,29.6 L 81.93,27.24 L 79.1,27.58 L 77.91,26.46 L 74.9,26.58 L 73.56,27.88 L 74.3,29.28 L 73.57,32.84 L 67.93,34.13 L 66.05,33.07 L 64.85,33.97 L 62.66,34.3 L 62.4,35.1 L 58.58,35.14 L 58.31,35.51 L 59.18,35.92 L 59.02,37.79 L 56.27,40.41 L 55.69,42.53 L 53.28,42.36 L 53.38,40.09 L 54.16,39.43 L 53.33,38.61 L 51.93,37.91 L 49.99,38.33 L 49.2,39.98 L 49.87,41.34 L 48.36,45.25 L 47.27,43.5 L 44.73,42.25 L 44.12,40.85 L 42.13,40.46 L 42.58,41.06 L 41.12,41.35 L 41.09,40.86 L 41.98,40.82 L 41.2,40.46 L 41.95,39.78 L 40.55,38.63 L 38.91,38.68 L 38.2,39.8 L 36.42,40.22 L 34.06,39.73 L 34.42,39.0 L 33.47,37.57 L 29.59,37.64 L 28.34,38.13 L 28.9,38.89 L 27.02,39.16 L 25.08,38.29 L 25.21,36.84 L 26.43,37.14 L 28.13,36.19 L 29.43,33.74 L 28.34,31.92 L 25.95,30.51 L 26.11,29.78 L 24.36,28.61 L 23.11,25.94 L 25.52,25.05 L 25.7,24.39 L 22.8,21.93 L 20.39,22.16 L 17.91,23.37 L 16.16,23.01 L 13.91,18.22 L 15.94,17.48 L 16.75,15.87 L 18.35,15.31 L 19.01,13.9 L 20.24,14.0 L 22.74,12.97 L 23.72,13.69 L 26.25,13.99 L 26.97,12.71 L 30.5,12.4 L 33.77,10.56 L 36.08,10.94 L 37.21,10.18 L 38.69,10.37 L 40.9,8.7 L 42.27,8.97 L 42.38,8.17 Z",         (-2.67, -8.15, 125.24, 61.54)),
        }

        # All-districts combined background path
        _ALL_BG_PATHS = " ".join(path_d for path_d, _ in _DISTRICT_SVG.values())

        def _district_svg_card(district_name, fill_color, exposed,
                                medal, score, sc_color, intens, wm, months):
            """Return a pure-HTML card with an inline SVG mini-map — zero JS overhead."""
            path_d, (vx, vy, vw, vh) = _DISTRICT_SVG.get(
                district_name,
                (_ALL_BG_PATHS, (-5, -5, 210, 135))
            )
            hi_fill   = fill_color if exposed else "#1A2D45"
            hi_stroke = fill_color if exposed else "#2A3F5F"
            bg_fill   = "#0D1B2E"
            bg_stroke = "#1E3050"
            opacity   = "1" if exposed else "0.42"

            # Hex → rgba for fill
            hx = hi_fill.lstrip("#")
            r2, g2, b2 = int(hx[0:2],16), int(hx[2:4],16), int(hx[4:6],16)
            hi_alpha   = 0.50 if exposed else 0.12
            glow_color = f"rgba({r2},{g2},{b2},0.25)" if exposed else "none"

            info_line = (
                f"⏱ {months} mo &nbsp;·&nbsp; {intens}"
                + (f" &nbsp;·&nbsp; {wm}" if wm != "—" else "")
            )

            return f"""
<div style="border-radius:10px; border:1px solid {hi_stroke};
     background:#080F1C; overflow:hidden; margin-bottom:8px; opacity:{opacity};
     box-shadow: 0 0 12px {glow_color};">
  <svg xmlns="http://www.w3.org/2000/svg"
       viewBox="{vx} {vy} {vw} {vh}"
       width="100%" height="120"
       style="display:block; background:{bg_fill};">
    <!-- all districts: subtle filled background -->
    <path d="{_ALL_BG_PATHS}"
          fill="rgba(14,30,56,0.95)" stroke="{bg_stroke}" stroke-width="0.4"
          stroke-linejoin="round"/>
    <!-- highlighted district: bright fill + thick border -->
    <path d="{path_d}"
          fill="rgba({r2},{g2},{b2},{hi_alpha})"
          stroke="{hi_stroke}" stroke-width="1.4"
          stroke-linejoin="round" stroke-linecap="round"/>
  </svg>
  <div style="padding:7px 10px 9px; border-top:1px solid rgba(255,255,255,0.05);">
    <div style="display:flex; justify-content:space-between; align-items:baseline;">
      <div style="font-size:0.76rem; font-weight:700; color:{hi_stroke};
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:72%;">
        {medal} {district_name}
      </div>
      <div style="font-size:1.05rem; font-weight:800; color:{sc_color}; white-space:nowrap;">
        {score}<span style="font-size:0.58rem; color:#6B7B91;">/100</span>
      </div>
    </div>
    <div style="font-size:0.63rem; color:#6B7B91; margin-top:3px;">{info_line}</div>
  </div>
</div>"""

        # Render in rows of 4
        for row_start in range(0, len(ranked), 4):
            chunk = ranked.iloc[row_start:row_start + 4]
            rcols = st.columns(len(chunk))
            for rc, (_, dr) in zip(rcols, chunk.iterrows()):
                rank_i   = int(ranked.index.get_loc(dr.name)) + 1
                exposed  = dr["months_triggered"] > 0
                r_color  = meta["color"] if exposed else "#2A3F5F"
                sc_color = alert_color(dr["risk_level"]) if exposed else "#6B7B91"
                score    = f"{dr['risk_score']:.0f}" if exposed else "—"
                intens   = f"{dr['mean_intensity_z']:+.2f}σ" if exposed else "—"
                try:
                    wm = pd.to_datetime(dr["worst_month"]).strftime("%b %Y")
                except Exception:
                    wm = "—"
                medal = {1:"🥇", 2:"🥈", 3:"🥉"}.get(rank_i, f"#{rank_i}")
                with rc:
                    st.markdown(
                        _district_svg_card(
                            dr["district_name"], r_color, exposed,
                            medal, score, sc_color, intens, wm,
                            dr["months_triggered"],
                        ),
                        unsafe_allow_html=True,
                    )

        # ── Triggered months detail table
        with st.expander(f"📅 Month-by-month record — {meta['label']}", expanded=True):
            # Build a table: months × districts (which districts had active pixels)
            active_months_list = sorted(set(
                m for ms in df_h["triggered_months"].tolist() for m in ms
            ))

            if active_months_list:
                records = []
                for mon in active_months_list:
                    try:
                        mon_label = pd.to_datetime(mon).strftime("%B %Y")
                    except Exception:
                        mon_label = mon

                    # Regional alert level for that month
                    ma_row = monthly_alerts[
                        pd.to_datetime(monthly_alerts["month"]).dt.strftime("%Y-%m") == mon
                    ]
                    reg_level = ma_row["max_alert_level"].iloc[0] if not ma_row.empty else "—"

                    # Which districts had pixels active this month
                    active_dists = [
                        dr["district_name"]
                        for _, dr in df_h.iterrows()
                        if mon in dr["triggered_months"]
                    ]

                    records.append({
                        "Month":          mon_label,
                        "Regional Level": reg_level,
                        "Districts Exposed": len(active_dists),
                        "Districts":      ", ".join(sorted(active_dists)) if active_dists else "—",
                    })

                st.dataframe(
                    pd.DataFrame(records),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No pixel-level month records available for this hazard.")

        # ── Full district intensity table
        with st.expander(f"📋 Full district table — {meta['label']}", expanded=True):
            disp = df_h[["district_name", "risk_level", "risk_score",
                          "months_triggered", "mean_intensity_z",
                          "max_intensity_z", "worst_month"]].copy()
            disp.columns = ["District", "Risk Level", "Risk Score",
                            "Months Triggered", "Mean Intensity z",
                            "Max Intensity z", "Worst Month"]
            st.dataframe(disp, hide_index=True, use_container_width=True)

        # ── Per-hazard AI briefing
        st.markdown("")
        if st.button(
            f"🤖 Explain top 5 {meta['label']} rankings",
            key=f"ai_haz_{htype}",
            use_container_width=True,
        ):
            top5 = (
                df_h[df_h["months_triggered"] > 0]
                .sort_values("risk_score", ascending=False)
                .head(5)
            )
            ranked_rows = list(top5.iterrows())
            next_districts = (
                df_h[df_h["months_triggered"] > 0]
                .sort_values("risk_score", ascending=False)
                .iloc[len(top5):len(top5) + 1]
            )
            comparison_rows = ranked_rows[1:] + list(next_districts.iterrows())
            while len(comparison_rows) < len(ranked_rows):
                comparison_rows.append((None, None))
            geography_notes = {
                "COLD_STRESS": "thand ke risk mein model zyada unchai wale ilaqon ko extra importance deta hai",
                "HEAT_WAVE": "garmi ke risk mein model kam unchai wale ilaqon ko extra importance deta hai",
                "FLOOD": "baadh ke risk mein model beech ki unchai wale ilaqon ko extra importance deta hai",
                "VEGETATION_LOSS": "jangal aur paudhon ke risk mein model zyada unchai wale ilaqon ko extra importance deta hai",
                "DROUGHT": "sookhe ke risk mein unchai se extra points nahi milte",
                "COMPOUND": "mixed hazard mein unchai se extra points nahi milte",
            }
            plain_hazards = {
                "COLD_STRESS": "thand ka",
                "HEAT_WAVE": "garmi ka",
                "FLOOD": "baarish/baadh ka",
                "DROUGHT": "sookhe ka",
                "VEGETATION_LOSS": "paudhon ke stress ka",
                "COMPOUND": "kai tarah ke badlav ka",
            }
            rank_explanations = []
            history_context = []
            shared_month_counts = {int(row["months_triggered"]) for _, row in ranked_rows}
            if len(shared_month_counts) == 1 and ranked_rows:
                shared_count = next(iter(shared_month_counts))
                shared_frequency_note = (
                    f"Top {len(ranked_rows)} ke sabhi districts mein {freq_count} mein se "
                    f"{shared_count} mahino mein {plain_hazards[htype]} signal mila, "
                    "isliye mahino ki ginti se inki ranking alag nahi hui."
                )
            else:
                shared_frequency_note = ""
            for rank, ((_, row), comparison) in enumerate(
                zip(ranked_rows, comparison_rows), start=1
            ):
                other = comparison[1] if comparison[1] is not None else row
                has_comparison = comparison[1] is not None
                row_months = row.get("triggered_months", []) or []
                history_context.append(
                    f"{row['district_name']}: {', '.join(row_months) or 'no month list'} "
                    f"(worst month: {row['worst_month']})"
                )

                reasons = []
                offsets = []
                freq_delta = float(row.get("frequency_score", 0)) - float(other.get("frequency_score", 0))
                intensity_delta = float(row.get("intensity_score", 0)) - float(other.get("intensity_score", 0))
                geo_delta = float(row.get("geo_weight", 1)) - float(other.get("geo_weight", 1))
                if not has_comparison and len(ranked_rows) == 1:
                    reasons.append("sirf isi district mein exposure detect hua")
                elif not has_comparison:
                    reasons.append("ye paanchva district hai jahan exposure detect hua")
                elif other is row:
                    reasons.append("sirf isi district mein exposure detect hua")
                elif freq_delta > 0.001:
                    reasons.append(f"yahan {int(row['months_triggered'])} mahino mein anomaly mili, {other['district_name']} mein {int(other['months_triggered'])} mahino mein")
                elif freq_delta < -0.001:
                    offsets.append(f"yahan {int(row['months_triggered'])} mahino mein anomaly mili, {other['district_name']} mein {int(other['months_triggered'])} mahino mein")
                if other is not row and intensity_delta > 0.001:
                    reasons.append(f"yahan satellite ka {plain_hazards[htype]} signal {other['district_name']} se zyada strong tha")
                elif other is not row and intensity_delta < -0.001:
                    offsets.append(f"yahan satellite signal {other['district_name']} se kam strong tha")
                if other is not row and geo_delta > 0.001:
                    reasons.append(geography_notes[htype])
                elif other is not row and geo_delta < -0.001:
                    offsets.append("model ke hisaab se unchai ka extra faayda kam tha")
                if not reasons and not offsets:
                    reasons.append("dono ke signals lagbhag barabar the, isliye score ka farq bahut halka hai")
                rank_explanations.append(
                    f"**#{rank} {row['district_name']}:** "
                    + (
                        f"{other['district_name']} se upar isliye hai kyunki {', aur '.join(reasons)}"
                        + (f". Halaanki, {', aur '.join(offsets)}" if offsets else "")
                        + "."
                        if has_comparison else f"{reasons[0]} (in {freq_count} event months mein se)."
                    )
                )

            historic_check = chamoli_2021_validation(monthly_alerts, spatial_df)
            prompt = f"""You are EARTHPULSE-X's concise historical context assistant. Answer in friendly, simple Roman Hindi/Hinglish, not formal report language.

The app has ALREADY computed and will separately show the exact data-based ranking explanation:
{chr(10).join(rank_explanations)}

Do NOT repeat the ranking, scores, formulas, z-scores, sensor tables, or generic hazard news. Your only task is historical context for these districts and the exact dates below.
Hazard: {meta['label']}.
Districts and anomaly months: {chr(10).join(history_context)}
Detection rule: {meta['description']}
Historical Chamoli check: {historic_check.get('validation_verdict', 'Not available')} — {historic_check.get('validation_detail', 'No detail available.')}

Use browser search. For each district, look for a documented event matching one of its listed months and this hazard. Prefer IMD, NDMA, Uttarakhand government, NASA/NOAA, peer-reviewed research, then established news. Write at most one short bullet per district, in plain language: what verifiable event happened, when, and how it could provide context for the observed anomaly. Do not merely list headlines. Say clearly when you found no reliable district-and-month match. A past event is context only: it was NOT used by the current ranking formula and does not prove the cause of this anomaly. Avoid tables, confidence labels, broad trend claims, and made-up causal explanations. At most 5 bullets."""

            st.markdown("#### Ranking ka data-based reason")
            st.caption(
                shared_frequency_note + " Purane events score mein nahi judte; unka context neeche alag milega. "
                "Unchai ka asar model ke ek simple rule se aata hai."
            )
            for explanation in rank_explanations:
                st.markdown(f"- {explanation}")
            st.markdown("#### Pichhle events se historical context")

            with st.spinner(f"🤖 Generating {meta['label']} briefing…"):
                try:
                    resp = GEMINI_CLIENT.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=900,
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                        ),
                    )
                    ai_card((resp.text or "").strip())

                    sources = []
                    candidate = resp.candidates[0] if resp.candidates else None
                    grounding = candidate.grounding_metadata if candidate else None
                    for chunk in grounding.grounding_chunks if grounding else []:
                        if chunk.web:
                            sources.append((chunk.web.title, chunk.web.uri))
                    unique_sources = list(dict.fromkeys(
                        (title, url) for title, url in sources
                        if title and url and url.startswith(("https://", "http://"))
                    ))
                    if unique_sources:
                        st.markdown("**Web sources**")
                        for title, url in unique_sources[:8]:
                            st.markdown(f"- [{title}]({url})")
                    else:
                        st.caption("Gemini did not return any linkable web sources for this answer.")
                except Exception as e:
                    st.error(f"AI unavailable: {e}")

# ──────────────────────────────────────────────────────────────
# SECTION C: LEGACY GPM-ONLY VIEW
# ──────────────────────────────────────────────────────────────

with st.expander("📌 Legacy: August 2025 GPM-only District Analysis (single-sensor)", expanded=True):
    if "anomaly_pixel_percentage" in districts.columns:
        dist_sel = st.selectbox(
            "Highlight district", sorted(districts["district_name"].tolist()),
            key="legacy_dist",
        )
        total_v = int(districts["valid_pixels"].sum())
        total_h = int(districts["high_anomaly_pixels"].sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Districts", len(districts))
        c2.metric("Valid Pixels", f"{total_v:,}")
        c3.metric("High Anomaly Pixels", f"{total_h:,}")
        c4.metric("High Anomaly %", f"{total_h/total_v*100:.1f}%" if total_v else "—")

        map2 = choropleth_map(
            districts,
            color_column="anomaly_pixel_percentage",
            color_label="GPM High Anomaly (%)",
            range_color=(0, max(districts["anomaly_pixel_percentage"].max(), 1)),
            highlight_district=dist_sel,
        )
        st.plotly_chart(map2, use_container_width=True)

        row2 = districts[districts["district_name"] == dist_sel].iloc[0]
        a, b, c, d, e, f = st.columns(6)
        a.metric("High Anomaly %",  f"{row2['anomaly_pixel_percentage']:.2f}%")
        b.metric("High Anomaly Px", f"{int(row2['high_anomaly_pixels']):,}")
        c.metric("Valid Pixels",    f"{int(row2['valid_pixels']):,}")
        d.metric("Mean Precip",     f"{row2['mean_precipitation_mm']:.2f} mm")
        e.metric("Mean |Z|",        f"{row2['mean_absolute_robust_z']:.2f}")
        f.metric("Max |Z|",         f"{row2['maximum_absolute_robust_z']:.2f}")

# ──────────────────────────────────────────────────────────────
# SECTION D: METHODOLOGY
# ──────────────────────────────────────────────────────────────

with st.expander("📖 Methodology — Multi-Hazard + Per-Hazard District Detection", expanded=True):
    st.markdown("""
    ### Two-Level Analysis

    **Level 1 — Regional monthly alerts** (`earthpulse_x_monthly_seasonal_anomalies.csv`)
    Z-scores all 5 sensors → runs 6-rule hazard detector → assigns `primary_hazard` per month.

    **Level 2 — Per-hazard district breakdown** (`earthpulse_x_spatial_isolation_forest_events.csv`)
    For each hazard type, filters the 50,449-pixel spatial dataset to only the months
    when that hazard was regionally active. Then aggregates per-district:
    - How many of those months had active pixels in that district
    - Mean + max intensity z-score for the hazard's primary sensor
    - Worst month (highest anomaly)

    ### Hazard Detection Rules

    | Hazard | Trigger | Primary Sensor |
    |---|---|---|
    | 🌊 FLOOD | GPM high + SMAP high | GPM z-score |
    | 🏜️ DROUGHT | GPM low + SMAP low + LST high (≥2 signals) | GPM z-score |
    | 🔥 HEAT WAVE | LST high, SMAP near normal | LST z-score |
    | 🍂 VEG LOSS | NDVI low + (LST high or SMAP low) | NDVI z-score |
    | ❄️ COLD STRESS | LST low in warm months (Apr–Sep) | LST z-score |
    | ⚡ COMPOUND | ≥ 3 sensors simultaneously anomalous | All sensors |

    ### District Risk Score (per-hazard)
    `risk_score = 0.6 × (months_exposed / total_hazard_months) + 0.4 × (mean_intensity / 3σ)` × 100

    This rewards districts that were *consistently* exposed AND had *intense* signals —
    not just any single extreme month.
    """)

footer()
