"""
Early Warning System — Multi-Hazard Edition
=============================================
6 hazard types · 5 NASA sensors · 10-year alert timeline

NOT just flood/rain — detects:
  🌊 FLOOD           — excess rain + saturated soil
  🏜️ DROUGHT         — dry rain + dry soil + hot surface
  🔥 HEAT WAVE       — surface temp anomaly
  🍂 VEGETATION LOSS — NDVI crash + stress co-signal
  ❄️ COLD STRESS     — anomalous cooling in warm season
  ⚡ COMPOUND        — 3+ sensors anomalous together
"""

import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from groq import Groq

from core.data_loader import (
    load_seasonal_anomalies,
    load_spatial_anomaly_events,
    load_district_boundaries,
)
from core.early_warning_engine import (
    compute_monthly_alerts,
    compute_district_risk_from_spatial,
    generate_alert_strings,
    chamoli_2021_validation,
    top_anomalous_months,
    hazard_frequency_summary,
    HAZARD_CATALOGUE,
    VAR_META,
    alert_color,
    alert_emoji,
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

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Early Warning System | EARTHPULSE-X",
    page_icon="🚨",
    layout="wide",
)

inject_theme()
render_sidebar()

_GROQ_CLIENT = Groq(
    api_key=os.getenv("GROQ_API_KEY_EWS") or os.getenv("GROQ_API_KEY")
)

# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("### 🚨 Alert Settings")
    thresh_info     = st.slider("INFO threshold (σ)",     1.0, 3.0, 2.0, 0.1)
    thresh_warning  = st.slider("WARNING threshold (σ)",  2.0, 4.5, 3.0, 0.1)
    thresh_critical = st.slider("CRITICAL threshold (σ)", 3.0, 6.0, 4.0, 0.1)
    st.markdown("---")
    n_alerts_show = st.slider("Max alerts to show", 5, 20, 12)
    min_alert_level = st.selectbox("Min alert level in feed",
                                   ["INFO", "WARNING", "CRITICAL"], index=0)
    st.markdown("---")
    selected_hazard_filter = st.selectbox(
        "Filter feed by hazard type",
        ["All hazards"] + list(HAZARD_CATALOGUE.keys()),
        key="hazard_filter",
    )
    st.markdown(
        "<div style='font-size:0.72rem;color:#6B7B91;'>"
        "6 hazard types · 5 sensors<br>"
        "50,449 pixel records · 126 months"
        "</div>", unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────
# LOAD + COMPUTE
# ──────────────────────────────────────────────────────────────

@st.cache_data
def load_all():
    an = load_seasonal_anomalies()
    sp = load_spatial_anomaly_events()
    try:
        bnd = load_district_boundaries()
    except Exception:
        bnd = None
    return an, sp, bnd

try:
    anomalies, spatial_df, boundaries = load_all()
except Exception as e:
    st.error(f"❌ Data load failed: {e}")
    st.stop()

@st.cache_data
def _alerts(ti, tw, tc):
    return compute_monthly_alerts(anomalies, ti, tw, tc)

monthly_alerts = _alerts(thresh_info, thresh_warning, thresh_critical)
hazard_freq    = hazard_frequency_summary(monthly_alerts)

alert_feed = generate_alert_strings(
    monthly_alerts, top_n=n_alerts_show, min_level=min_alert_level
)
if selected_hazard_filter != "All hazards":
    alert_feed = [a for a in alert_feed if a["primary_hazard"] == selected_hazard_filter]

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "EARLY WARNING SYSTEM",
    "Multi-Hazard · 6 Hazard Types · 5 NASA Sensors · Decision Support",
    "🚨",
)

info_banner(
    "**6 hazard types detected** from 5 NASA sensors simultaneously. "
    "Flood, drought, heat wave, vegetation loss, cold stress, and compound events "
    "each have distinct multi-variable signatures — "
    "**no single-sensor bias**. Every variable matters.",
    kind="warning",
)

# ──────────────────────────────────────────────────────────────
# 1. STATUS DASHBOARD
# ──────────────────────────────────────────────────────────────

level_rank  = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
latest_row  = monthly_alerts.sort_values("month").iloc[-1]
latest_str  = pd.to_datetime(latest_row["month"]).strftime("%B %Y")
latest_lvl  = latest_row["max_alert_level"]
latest_haz  = latest_row.get("primary_hazard", "NONE")
latest_meta = HAZARD_CATALOGUE.get(latest_haz, {"emoji": "✅", "color": "#31C48D", "label": "Normal"})

n_critical = int((monthly_alerts["max_alert_level"] == "CRITICAL").sum())
n_warning  = int((monthly_alerts["max_alert_level"] == "WARNING").sum())
n_info     = int((monthly_alerts["max_alert_level"] == "INFO").sum())
n_normal   = int((monthly_alerts["max_alert_level"] == "NORMAL").sum())

top_row = st.columns(6)

with top_row[0]:
    st.markdown(f"""
    <div class="glass-card" style="text-align:center;padding:18px 10px;
         border-top:4px solid {latest_meta['color']};">
      <div style="font-size:0.68rem;color:#6B7B91;">LATEST ({latest_str})</div>
      <div style="font-size:1.8rem;margin:6px 0;">{latest_meta['emoji']}</div>
      <div style="font-size:0.9rem;font-weight:800;color:{latest_meta['color']};">{latest_lvl}</div>
      <div style="font-size:0.68rem;color:#AAB8CC;margin-top:3px;">{latest_meta['label']}</div>
    </div>""", unsafe_allow_html=True)

for col_w, (lvl, color, label) in zip(
    top_row[1:5],
    [("CRITICAL","#EF6461","🔴 CRITICAL"), ("WARNING","#E9A34B","🟠 WARNING"),
     ("INFO","#F5D842","🟡 INFO"), ("NORMAL","#31C48D","🟢 NORMAL")]
):
    count = {"CRITICAL": n_critical, "WARNING": n_warning, "INFO": n_info, "NORMAL": n_normal}[lvl]
    with col_w:
        st.markdown(f"""
        <div class="glass-card" style="text-align:center;padding:18px 10px;
             border-top:3px solid {color};">
          <div style="font-size:0.68rem;color:#6B7B91;">{label}</div>
          <div style="font-size:1.8rem;font-weight:800;color:{color};margin:4px 0;">{count}</div>
          <div style="font-size:0.68rem;color:#AAB8CC;">of 126 months</div>
        </div>""", unsafe_allow_html=True)

# Most common hazard
if not hazard_freq.empty:
    top_haz = hazard_freq.iloc[0]
    with top_row[5]:
        st.markdown(f"""
        <div class="glass-card" style="text-align:center;padding:18px 10px;
             border-top:3px solid {top_haz['color']};">
          <div style="font-size:0.68rem;color:#6B7B91;">TOP HAZARD</div>
          <div style="font-size:1.8rem;margin:6px 0;">{top_haz['emoji']}</div>
          <div style="font-size:0.78rem;font-weight:700;color:{top_haz['color']};">
              {top_haz['label'].split('/')[0].strip()}
          </div>
          <div style="font-size:0.68rem;color:#AAB8CC;margin-top:3px;">
              {int(top_haz['months_triggered'])} months
          </div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 2. HAZARD FREQUENCY OVERVIEW
# ──────────────────────────────────────────────────────────────

section_header("Hazard Type Frequency — 10-Year Record", "📊",
               "How many months each hazard type was detected · not just flood")

if not hazard_freq.empty:
    hf_fig = go.Figure()
    hf_fig.add_trace(go.Bar(
        x=hazard_freq["label"],
        y=hazard_freq["months_triggered"],
        marker=dict(color=hazard_freq["color"].tolist()),
        text=[f"{r['emoji']} {r['months_triggered']}" for _, r in hazard_freq.iterrows()],
        textposition="outside",
        textfont=dict(size=13, color="#F1F5FC"),
        hovertemplate="<b>%{x}</b><br>Triggered: %{y} months<extra></extra>",
    ))
    _apply_layout(hf_fig, height=300)
    hf_fig.update_layout(
        yaxis=dict(title="Months triggered"),
        xaxis=dict(tickangle=-15),
        showlegend=False, bargap=0.3,
    )
    st.plotly_chart(hf_fig, use_container_width=True)
    st.caption("A month can trigger multiple hazard types simultaneously → totals may exceed 126")

# ──────────────────────────────────────────────────────────────
# 3. MULTI-HAZARD ALERT FEED
# ──────────────────────────────────────────────────────────────

section_header("Multi-Hazard Alert Feed", "📡",
               f"{'All hazards' if selected_hazard_filter == 'All hazards' else selected_hazard_filter} · "
               f"min level: {min_alert_level}")

if not alert_feed:
    st.success("✅ No alerts matching current filter. Adjust thresholds or hazard type in sidebar.")
else:
    for alert in alert_feed:
        lvl        = alert["alert_level"]
        a_color    = alert["color"]
        a_emoji    = alert["emoji"]
        month      = alert["month_str"]
        h_emoji    = alert["hazard_emoji"]
        h_label    = alert["hazard_label"]
        h_color    = alert["hazard_color"]
        h_action   = alert["hazard_action"]
        msg        = alert["message"]
        count      = alert["active_count"]
        details    = alert["details"]
        all_haz    = alert.get("all_hazards", [])

        # Sensor detail pills
        detail_html = " &nbsp;|&nbsp; ".join([
            f"<span style='color:{d['color']};font-weight:600;'>{d['var']}</span> "
            f"{d['z']:.1f}σ {d['direction']}"
            for d in details
        ])

        # Co-occurring hazards
        haz_pills = ""
        for h in all_haz:
            hm = HAZARD_CATALOGUE.get(h["hazard_type"], {})
            haz_pills += (
                f"<span style='background:rgba(0,0,0,0.3);border:1px solid {hm.get('color','#6B7B91')};"
                f"color:{hm.get('color','#AAB8CC')};font-size:0.68rem;padding:2px 7px;"
                f"border-radius:4px;margin-right:4px;'>"
                f"{hm.get('emoji','⚠️')} {hm.get('label',h['hazard_type'])} "
                f"({h['severity_score']:.0f}%)</span>"
            )

        st.markdown(f"""
        <div class="glass-card" style="border-left:4px solid {h_color};
             padding:14px 18px; margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
            <div>
              <span style="font-size:0.72rem;color:#6B7B91;font-family:'Urbanist';">{month}</span>
              <span style="margin-left:10px;font-size:0.72rem;font-weight:700;color:{a_color};
                           background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:4px;">
                  {a_emoji} {lvl}
              </span>
              <span style="margin-left:6px;font-size:0.7rem;color:#6B7B91;">{count} sensor{'s' if count!=1 else ''} elevated</span>
            </div>
            <div style="font-size:1.1rem;">{h_emoji}
              <span style="font-size:0.78rem;font-weight:700;color:{h_color};">{h_label}</span>
            </div>
          </div>
          <div style="margin-top:8px;font-size:0.9rem;color:#F1F5FC;font-weight:600;">{msg}</div>
          <div style="margin-top:6px;font-size:0.75rem;color:#AAB8CC;">{detail_html}</div>
          {f'<div style="margin-top:8px;">{haz_pills}</div>' if haz_pills else ''}
          {f'<div style="margin-top:8px;font-size:0.72rem;color:#6B7B91;font-style:italic;">→ {h_action}</div>' if h_action else ''}
        </div>
        """, unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# 4. ALERT TIMELINE — all 5 sensors, all hazards
# ──────────────────────────────────────────────────────────────

section_header("Multi-Sensor Alert Timeline — 10 Years", "⏱️",
               "All 5 sensors · Blue = below normal · Red = above normal · Annotated hazard events")

z_var_map = {
    "🌡️ LST":     "LST_z",
    "🌿 NDVI":    "NDVI_z",
    "💧 SMAP AM": "SMAP_AM_z",
    "💧 SMAP PM": "SMAP_PM_z",
    "🌧️ GPM":    "GPM_z",
}

ma_sorted     = monthly_alerts.sort_values("month")
month_labels  = [pd.to_datetime(m).strftime("%Y-%m") for m in ma_sorted["month"]]
matrix_data, row_labels = [], []
for disp, col in z_var_map.items():
    if col in ma_sorted.columns:
        matrix_data.append(ma_sorted[col].values)
        row_labels.append(disp)

if matrix_data:
    tl_fig = go.Figure(go.Heatmap(
        z=np.array(matrix_data),
        x=month_labels,
        y=row_labels,
        colorscale=[
            [0.0, "#1A4A8A"], [0.25, "#2D7DD2"], [0.45, "#1E2D4A"],
            [0.55, "#1E2D4A"], [0.75, "#E9A34B"], [0.90, "#EF8461"], [1.0, "#EF2461"],
        ],
        zmid=0, zmin=-5, zmax=5,
        colorbar=dict(
            title="z-score", thickness=12, len=0.6,
            tickvals=[-4,-2,0,2,4], ticktext=["−4σ","−2σ","0","+2σ","+4σ"],
        ),
        hovertemplate="<b>%{x}</b><br>%{y}: %{z:.2f}σ<extra></extra>",
        xgap=1, ygap=2,
    ))

    # Annotate top WARNING+ events
    for _, arow in ma_sorted[ma_sorted["max_alert_level"].isin(["WARNING","CRITICAL"])].iterrows():
        m_str = pd.to_datetime(arow["month"]).strftime("%Y-%m")
        if m_str not in month_labels:
            continue
        idx = month_labels.index(m_str)
        haz = arow.get("primary_hazard", "NONE")
        meta = HAZARD_CATALOGUE.get(haz, {})
        em = meta.get("emoji", "⚠️")
        tl_fig.add_annotation(
            x=m_str, y=row_labels[-1],
            text=em, showarrow=False,
            font=dict(size=11), yshift=22,
            xanchor="center",
        )

    # Mark Chamoli 2021
    if "2021-02" in month_labels:
        tl_fig.add_vrect(
            x0=month_labels.index("2021-02") - 0.5,
            x1=month_labels.index("2021-02") + 0.5,
            fillcolor="rgba(255,255,255,0.1)",
            line=dict(color="#FFFFFF", width=1.5),
            annotation_text="Chamoli 2021",
            annotation_font_color="#FFFFFF",
            annotation_font_size=9,
            annotation_position="top left",
        )

    _apply_layout(tl_fig, height=270)
    tl_fig.update_layout(
        xaxis=dict(tickangle=-45, tickfont=dict(size=9), nticks=24),
        yaxis=dict(tickfont=dict(size=11)),
        margin=dict(l=100, r=80, t=50, b=70),
    )
    st.plotly_chart(tl_fig, use_container_width=True)
    st.caption(
        "Emoji annotations = WARNING/CRITICAL hazard events · "
        "Blue = below normal · Red = above normal · "
        "Horizontal bands = multi-sensor co-occurrence = compound hazard"
    )

# ──────────────────────────────────────────────────────────────
# 5. TOP ANOMALOUS MONTHS — all hazard types
# ──────────────────────────────────────────────────────────────

section_header("Most Anomalous Months — All Time", "🏆",
               "Ranked by severity + sensor co-occurrence + hazard type")

top_months = top_anomalous_months(monthly_alerts, n=15)

display_cols_avail = [c for c in [
    "month", "max_alert_level", "primary_hazard",
    "active_alerts", "LST_z", "NDVI_z", "SMAP_AM_z", "GPM_z", "alert_message"
] if c in top_months.columns]

top_disp = top_months[display_cols_avail].copy()
top_disp["month"] = pd.to_datetime(top_disp["month"]).dt.strftime("%B %Y")
top_disp.columns = [c.replace("_z","z").replace("_"," ").title() for c in top_disp.columns]

st.dataframe(top_disp, hide_index=True, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 6. DISTRICT MULTI-HAZARD RISK
# ──────────────────────────────────────────────────────────────

section_header("District Risk — Multi-Hazard", "🗺️",
               "Which districts face which hazard? Aggregated from 50,449 pixel records")

col_dm1, col_dm2 = st.columns([3, 1])
with col_dm1:
    sel_month_d = st.selectbox(
        "Drill down by month",
        ["All months (aggregated)"] + sorted(spatial_df["month"].astype(str).unique()),
        key="ews_month_d",
    )
with col_dm2:
    ews_thr = st.slider("Alert |z| threshold", 2.0, 5.0, 3.0, 0.5, key="ews_thr")

@st.cache_data
def _drisk(mf, thr):
    return compute_district_risk_from_spatial(
        spatial_df, month_filter=mf, boundaries_gdf=boundaries, threshold=thr
    )

mf_d = None if sel_month_d == "All months (aggregated)" else sel_month_d
with st.spinner("Computing district risk..."):
    drisk_df = _drisk(mf_d, ews_thr)

if drisk_df.empty:
    st.warning("No data for selected month.")
else:
    # Group cards by primary hazard
    for htype in list(HAZARD_CATALOGUE.keys()) + ["NONE"]:
        chunk = drisk_df[drisk_df["primary_hazard"] == htype]
        if chunk.empty:
            continue
        meta  = HAZARD_CATALOGUE.get(htype, {"emoji":"⚪","color":"#6B7B91","label":"No pattern","action":""})
        color = meta["color"]

        st.markdown(
            f"<div style='font-size:0.8rem;font-weight:700;color:{color};margin:14px 0 6px;'>"
            f"{meta['emoji']} {meta['label']} — {len(chunk)} district{'s' if len(chunk)>1 else ''}"
            f"</div>", unsafe_allow_html=True,
        )
        ncols = min(len(chunk), 4)
        for start in range(0, len(chunk), ncols):
            sub = chunk.iloc[start:start + ncols]
            wcols = st.columns(len(sub))
            for wc, (_, dr) in zip(wcols, sub.iterrows()):
                sigs = []
                if abs(dr["mean_gpm_z"]) >= 1.5:  sigs.append(f"🌧️ {dr['mean_gpm_z']:+.1f}σ")
                if abs(dr["mean_lst_z"]) >= 1.5:   sigs.append(f"🌡️ {dr['mean_lst_z']:+.1f}σ")
                if abs(dr["mean_ndvi_z"]) >= 1.5:  sigs.append(f"🌿 {dr['mean_ndvi_z']:+.1f}σ")
                if abs(dr["mean_smap_z"]) >= 1.5:  sigs.append(f"💧 {dr['mean_smap_z']:+.1f}σ")
                rc = alert_color(dr["risk_level"])
                with wc:
                    st.markdown(f"""
                    <div class="glass-card" style="padding:12px 10px;border-left:3px solid {color};min-height:120px;">
                      <div style="font-size:0.75rem;font-weight:700;color:{color};">{meta['emoji']} {dr['district_name']}</div>
                      <div style="font-size:1.25rem;font-weight:800;color:{rc};margin:3px 0;">
                          {dr['risk_score']:.0f}<span style="font-size:0.68rem;color:#6B7B91;">/100</span>
                      </div>
                      <div style="font-size:0.68rem;color:#6B7B91;">{dr['risk_level']} · {dr['alert_pct']:.0f}% alert px</div>
                      <div style="font-size:0.68rem;color:#AAB8CC;margin-top:4px;">{"  ".join(sigs) if sigs else "Mild"}</div>
                    </div>
                    """, unsafe_allow_html=True)

    with st.expander("📋 Full district table"):
        dcols = [c for c in [
            "district_name","primary_hazard","risk_level","risk_score","alert_pct",
            "mean_gpm_z","mean_lst_z","mean_ndvi_z","mean_smap_z","total_pixels"
        ] if c in drisk_df.columns]
        st.dataframe(drisk_df[dcols], hide_index=True, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 7. CHAMOLI 2021 VALIDATION
# ──────────────────────────────────────────────────────────────

section_header("Chamoli 2021 — Historical Validation", "🏔️",
               "Did the system detect the Feb 7, 2021 glacial outburst?")

info_banner(
    "The **Chamoli Glacier Burst** (7 Feb 2021) destroyed the Tapovan hydropower dam "
    "and killed ~200 people. This is our ground-truth test: "
    "**does a multi-variable system outperform single-sensor detection?**",
    kind="info",
)

@st.cache_data
def _chamoli():
    return chamoli_2021_validation(monthly_alerts, spatial_df)

chamoli = _chamoli()

vc_color = {"✅ CONFIRMED": "#31C48D", "⚠️ PARTIAL SIGNAL": "#E9A34B",
            "❌ NOT DETECTED": "#EF6461"}.get(chamoli["validation_verdict"], "#6B7B91")

st.markdown(f"""
<div class="glass-card" style="border:2px solid {vc_color};padding:22px 26px;border-radius:14px;margin-bottom:18px;">
  <div style="font-size:1.25rem;font-weight:800;color:{vc_color};margin-bottom:10px;">
      {chamoli['validation_verdict']}
  </div>
  <div style="font-size:0.88rem;color:#AAB8CC;line-height:1.7;">
      {chamoli['validation_detail']}
  </div>
</div>
""", unsafe_allow_html=True)

ch1, ch2 = st.columns(2)

with ch1:
    st.markdown("**Regional Signal — February 2021**")
    if chamoli["regional_row"] is not None:
        rr = chamoli["regional_row"]
        regional_hazards = chamoli.get("regional_hazards", [])
        for k, v in {
            "Alert Level": chamoli["regional_alert_level"],
            "Active Sensors": int(rr.get("active_alerts", 0)),
            "Primary Hazard": rr.get("primary_hazard", "NONE"),
            "GPM z": f"{rr.get('GPM_z', 0):.2f}σ",
            "LST z": f"{rr.get('LST_z', 0):.2f}σ",
            "NDVI z": f"{rr.get('NDVI_z', 0):.2f}σ",
            "SMAP AM z": f"{rr.get('SMAP_AM_z', 0):.2f}σ",
        }.items():
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:5px 0;"
                f"border-bottom:1px solid #1E2D4A;'>"
                f"<span style='color:#6B7B91;font-size:0.82rem;'>{k}</span>"
                f"<span style='color:#F1F5FC;font-size:0.82rem;font-weight:600;'>{v}</span>"
                f"</div>", unsafe_allow_html=True,
            )
    else:
        st.warning("Feb 2021 not in time-series.")

with ch2:
    st.markdown("**Pixel-Level Signal — February 2021**")
    ps = chamoli["pixel_stats"]
    if ps:
        for k, v in {
            "Total Pixels": ps.get("total_pixels", 0),
            "IF-Flagged (2%)": ps.get("if_anomaly_pixels", 0),
            "IF-Flagged %": f"{ps.get('if_anomaly_pct', 0):.1f}%",
            "High GPM-z pixels": ps.get("high_gpm_z_pixels", 0),
            "High LST-z pixels": ps.get("high_lst_z_pixels", 0),
            "High NDVI-z pixels": ps.get("high_ndvi_z_pixels", 0),
            "Mean GPM z": f"{ps.get('mean_gpm_z', 0):.3f}σ",
            "Mean LST z": f"{ps.get('mean_lst_z', 0):.3f}σ",
        }.items():
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:5px 0;"
                f"border-bottom:1px solid #1E2D4A;'>"
                f"<span style='color:#6B7B91;font-size:0.82rem;'>{k}</span>"
                f"<span style='color:#F1F5FC;font-size:0.82rem;font-weight:600;'>{v}</span>"
                f"</div>", unsafe_allow_html=True,
            )
    else:
        st.info("No pixel data for Feb 2021.")

# Context chart 2020-2022
ma_ctx = monthly_alerts[
    pd.to_datetime(monthly_alerts["month"]).dt.year.isin([2020, 2021, 2022])
].sort_values("month")

if len(ma_ctx) >= 3:
    ctx_fig = go.Figure()
    var_colors_c = {"GPM_z": "#35C9D0", "LST_z": "#EF6461", "NDVI_z": "#31C48D", "SMAP_AM_z": "#6C8EE6"}
    var_names_c  = {"GPM_z": "🌧️ GPM", "LST_z": "🌡️ LST", "NDVI_z": "🌿 NDVI", "SMAP_AM_z": "💧 SMAP AM"}
    x_ctx = [pd.to_datetime(m).strftime("%Y-%m") for m in ma_ctx["month"]]

    for col, color in var_colors_c.items():
        if col not in ma_ctx.columns:
            continue
        ctx_fig.add_trace(go.Scatter(
            x=x_ctx, y=ma_ctx[col].values,
            mode="lines+markers", name=var_names_c[col],
            line=dict(color=color, width=1.8), marker=dict(size=5),
            hovertemplate=f"{var_names_c[col]}: %{{y:.2f}}σ (%{{x}})<extra></extra>",
        ))

    if "2021-02" in x_ctx:
        ctx_fig.add_vrect(
            x0=x_ctx.index("2021-02") - 0.4,
            x1=x_ctx.index("2021-02") + 0.4,
            fillcolor="rgba(239,100,97,0.15)",
            line=dict(color="#EF6461", width=2),
            annotation_text="Feb 2021 — Chamoli",
            annotation_font_color="#EF6461",
            annotation_font_size=10,
            annotation_position="top",
        )
    for thr, c, lbl in [
        (thresh_warning, "#E9A34B", f"WARNING ({thresh_warning}σ)"),
        (-thresh_warning, "#E9A34B", None),
    ]:
        ctx_fig.add_hline(y=thr, line_dash="dot", line_color=c, line_width=1,
                          annotation_text=lbl or "", annotation_font_color=c,
                          annotation_font_size=9, annotation_position="right")

    _apply_layout(ctx_fig, height=300)
    ctx_fig.update_layout(
        yaxis=dict(title="z-score", zeroline=True, zerolinecolor="#2A3F5F"),
        legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center"),
        title=dict(text="All sensors around Chamoli 2021 (2020–2022)",
                   font=dict(size=13, color="#AAB8CC")),
    )
    st.plotly_chart(ctx_fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 8. AI MULTI-HAZARD BRIEFING
# ──────────────────────────────────────────────────────────────

section_header("AI Multi-Hazard Briefing", "🤖",
               "Decision-ready, hazard-typed report for disaster managers")

if st.button("🤖 Generate multi-hazard early warning briefing", use_container_width=True, key="ai_ews"):

    freq_lines = [
        f"  {r['emoji']} {r['label']}: {r['months_triggered']} months triggered"
        for _, r in hazard_freq.iterrows()
    ] if not hazard_freq.empty else ["  No hazards detected"]

    top_alert_lines = [
        f"  [{a['alert_level']}] {a['month_str']} — "
        f"{a['hazard_emoji']} {a['hazard_label']}: {a['message']}"
        for a in alert_feed[:8]
    ] if alert_feed else ["  No alerts above threshold"]

    dist_lines = []
    if not drisk_df.empty:
        for _, dr in drisk_df.head(5).iterrows():
            dist_lines.append(
                f"  {dr['district_name']}: {dr['primary_hazard']} "
                f"risk={dr['risk_score']:.0f}/100 "
                f"GPM={dr['mean_gpm_z']:+.2f}σ LST={dr['mean_lst_z']:+.2f}σ "
                f"NDVI={dr['mean_ndvi_z']:+.2f}σ"
            )

    prompt = f"""You are an expert multi-hazard analyst for NASA EARTHPULSE-X, Uttarakhand, India (2015–2025).

The system detects 6 hazard types from 5 NASA sensors:
🌊 FLOOD (GPM high + SMAP high), 🏜️ DROUGHT (GPM+SMAP low + LST high),
🔥 HEAT WAVE (LST high alone), 🍂 VEGETATION LOSS (NDVI low + stress),
❄️ COLD STRESS (LST low in warm season), ⚡ COMPOUND (3+ sensors)

HAZARD FREQUENCY (10-year record, Apr 2015 – Sep 2025):
{chr(10).join(freq_lines)}

TOP ALERT EVENTS:
{chr(10).join(top_alert_lines)}

DISTRICT RISK (top 5 by risk score):
{chr(10).join(dist_lines) if dist_lines else "  No district data."}

CHAMOLI 2021: {chamoli['validation_verdict']}
{chamoli['validation_detail']}

Write a multi-hazard early warning briefing. Structure EXACTLY:

**HAZARD PROFILE — Uttarakhand 2015–2025**
- What are the dominant hazard types and why? (use actual month counts)
- What does the combination of hazard types tell us about the region's vulnerability?

**CRITICAL EVENTS**
- List 3 most severe events with month, hazard type, which sensors fired, practical implication

**DISTRICT VULNERABILITY**
- Which districts face which hazard types? Be specific (district name + hazard + z-scores)

**CHAMOLI 2021 — WHAT DID THE MULTI-HAZARD SYSTEM SHOW?**
- Is multi-sensor detection better than single-sensor for this event?

**RECOMMENDED ACTIONS — 3 specific bullets**
- Hazard-specific, district-specific, actionable

Rules: Actual numbers. No generic climate disclaimers. Hazard-typed, not flood-only."""

    with st.spinner("🤖 Generating multi-hazard briefing…"):
        try:
            response = _GROQ_CLIENT.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=950,
            )
            ai_card(response.choices[0].message.content.strip())
        except Exception as e:
            st.error(f"AI unavailable: {e}")

# ──────────────────────────────────────────────────────────────
# 9. METHODOLOGY
# ──────────────────────────────────────────────────────────────

with st.expander("🔬 Multi-Hazard Detection Methodology"):
    st.markdown(f"""
    ### Why Multi-Hazard?

    Single-sensor systems miss critical events:
    - **Drought** requires GPM + SMAP + LST — rain alone doesn't tell you if soils are dry
    - **Heat waves** kill vegetation even when rain is normal
    - **Vegetation collapse** is invisible in precipitation data
    - **Cold stress** signals glacier activity — invisible to GPM entirely

    ### Detection Rules

    | Hazard | Trigger Pattern | Sensors Used |
    |---|---|---|
    | 🌊 FLOOD | GPM z ≥ {thresh_info}σ **AND** SMAP z ≥ {thresh_info}σ | GPM + SMAP |
    | 🏜️ DROUGHT | ≥ 2 of (GPM low, SMAP low, LST high) | GPM + SMAP + LST |
    | 🔥 HEAT WAVE | LST z ≥ {thresh_info}σ, SMAP near normal | LST only |
    | 🍂 VEG LOSS | NDVI z ≤ −{thresh_info}σ **AND** (LST high or SMAP low) | NDVI + LST/SMAP |
    | ❄️ COLD STRESS | LST z ≤ −{thresh_info}σ in Apr–Sep | LST (seasonal-aware) |
    | ⚡ COMPOUND | ≥ 3 sensors simultaneously ≥ {thresh_info}σ | All 5 |

    ### Severity Score
    Each hazard's severity is computed from the magnitude of triggering z-scores (0–100).
    Multiple hazards can fire in the same month.

    ### Chamoli Caveat
    GLOF = glacial lake outburst flood (single-day event).
    Monthly 1km² satellite data cannot resolve sub-daily events.
    Honest absence of signal is itself scientifically valuable.
    """)

footer()
