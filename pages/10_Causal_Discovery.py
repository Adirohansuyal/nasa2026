"""
Causal Discovery — PCMCI
=========================
"Not correlation. Actual causation."

Discovers the TRUE causal structure of Uttarakhand's climate system
using PCMCI (Runge et al., 2019, Science Advances).

Standard tools show: "GPM and NDVI are correlated at lag 2."
This page reveals: "GPM CAUSES SMAP at lag 1 — SMAP CAUSES NDVI at lag 1.
                    GPM→NDVI is SPURIOUS (blocked by conditioning on SMAP)."

Features:
  1. Animated Directed Causal Graph (arrows = causation, not correlation)
  2. Monsoon Propagation Chain — Rain → Soil → Vegetation → Temperature
  3. Chamoli 2021 Causal Destabilisation Test
  4. Rolling Causal Stability Timeline
  5. AI Scientific Interpretation
"""

import os
import time
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from groq import Groq

from core.data_loader import load_regional_timeseries
from core.causal_engine import (
    run_pcmci,
    build_causal_edges,
    detect_lag_chain,
    chamoli_causal_shift,
    rolling_causal_stability,
    causal_summary_text,
    VAR_META,
    TIGRAMITE_AVAILABLE,
)
from components.theme import (
    inject_theme, page_header, section_header,
    info_banner, ai_card, footer,
)
from components.sidebar import render_sidebar
from components.charts import _apply_layout, COLORS

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Causal Discovery | EARTHPULSE-X",
    page_icon="🔗",
    layout="wide",
)
inject_theme()
render_sidebar()

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

VARIABLES = [
    "gpm_monthly_precipitation_mean",
    "smap_am_strict_mean",
    "ndvi_strict_mean",
    "lst_strict_mean",
]

VAR_COLORS = {
    "GPM":  "#6C8EE6",
    "SMAP": "#2D7DD2",
    "NDVI": "#31C48D",
    "LST":  "#EF6461",
}

VAR_SHORT_TO_KEY = {
    VAR_META[k]["short"]: k for k in VARIABLES
}

# Node positions for causal graph (fixed layout — physically meaningful)
NODE_POS = {
    "GPM":  (0.0, 0.5),
    "SMAP": (0.33, 0.8),
    "NDVI": (0.67, 0.8),
    "LST":  (1.0, 0.5),
}

# ──────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    df = load_regional_timeseries().copy()
    df["month"] = pd.to_datetime(df.get("month", df.get("date")), errors="coerce")
    return df.dropna(subset=["month"]).sort_values("month").reset_index(drop=True)

try:
    df = load_data()
except Exception as e:
    st.error(f"❌ Data load failed: {e}")
    st.stop()

if not TIGRAMITE_AVAILABLE:
    st.error("❌ tigramite not installed. Run: pip install tigramite")
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "CAUSAL DISCOVERY",
    "PCMCI Algorithm · Directed Causal Graph · Monsoon Propagation Chain · Chamoli Validation",
    "🔗",
)

info_banner(
    "**Not correlation — actual causation.** "
    "Standard interaction graphs show statistical associations. "
    "PCMCI conditions on ALL other variables to reveal which signals "
    "are TRUE causes and which are spurious byproducts. "
    "Method: Runge et al. (2019), *Science Advances*.",
    kind="info",
)

# ──────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS
# ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔗 Causal Discovery Settings")
    tau_max = st.slider("Max lag (months)", 2, 8, 6, 1,
                        help="Maximum causal lag to test. 6 months covers full monsoon cycle.")
    pc_alpha = st.select_slider("Significance threshold (α)",
                                options=[0.01, 0.05, 0.10], value=0.05)
    show_lag0 = st.checkbox("Show same-month links (lag 0)", value=False)
    min_strength = st.slider("Min causal strength to show", 0.0, 0.5, 0.05, 0.01)
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.72rem;color:#6B7B91;'>"
        "PCMCI: Peter & Clark + MCI test<br>"
        "FDR: Benjamini-Hochberg<br>"
        "126 monthly observations"
        "</div>", unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────
# RUN PCMCI (cached by settings)
# ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _run_pcmci(tau_max, pc_alpha):
    return run_pcmci(df, VARIABLES, tau_max=tau_max, pc_alpha=pc_alpha)

@st.cache_data(show_spinner=False)
def _build_edges(tau_max, pc_alpha):
    result = _run_pcmci(tau_max, pc_alpha)
    return build_causal_edges(result)

@st.cache_data(show_spinner=False)
def _chain(tau_max, pc_alpha):
    edges = _build_edges(tau_max, pc_alpha)
    return detect_lag_chain(edges)

with st.spinner("🔗 Running PCMCI causal discovery on 126 months of NASA satellite data..."):
    pcmci_result = _run_pcmci(tau_max, pc_alpha)

if pcmci_result.get("error"):
    st.error(f"PCMCI failed: {pcmci_result['error']}")
    st.stop()

edges      = _build_edges(tau_max, pc_alpha)
chain_info = _chain(tau_max, pc_alpha)

# Filter edges by settings
if not show_lag0:
    edges_disp = edges[edges["lag"] > 0]
else:
    edges_disp = edges.copy()
edges_disp = edges_disp[edges_disp["strength"] >= min_strength]

# ──────────────────────────────────────────────────────────────
# SECTION 1: OVERVIEW METRICS
# ──────────────────────────────────────────────────────────────

section_header("Causal Discovery Results", "📊",
               f"{len(edges)} significant causal links · {pcmci_result['n_obs']} months")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Significant Links",   len(edges))
m2.metric("Observations",        pcmci_result["n_obs"])
m3.metric("Max Lag Tested",      f"{tau_max} months")
m4.metric("Chain Complete",      "✅" if chain_info["chain_complete"] else "⚠️ Partial")
m5.metric("FDR α",               f"{pc_alpha}")

st.markdown("")

# ──────────────────────────────────────────────────────────────
# SECTION 2: ANIMATED DIRECTED CAUSAL GRAPH
# ──────────────────────────────────────────────────────────────

section_header("Directed Causal Graph — Animated by Lag", "🕸️",
               "Arrows = causation · Width = strength · Color = lag depth")

info_banner(
    "Each **arrow** means: the source variable **causally predicts** the target, "
    "even after controlling for all other variables. "
    "Bidirectional arrows = mutual causation at different lags. "
    "No arrow = correlation was spurious.",
    kind="info",
)

def build_causal_graph_fig(edges_subset: pd.DataFrame, title_suffix: str = "") -> go.Figure:
    """Build an animated directed causal graph using fixed node positions."""

    fig = go.Figure()

    if edges_subset.empty:
        fig.add_annotation(
            text="No significant causal links found with current settings.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=16, color="#6B7B91"),
        )
        _apply_layout(fig, height=500)
        return fig

    # ── Draw edges (arrows) ──
    all_lag_colors = {
        0: "#F5D842", 1: "#35C9D0", 2: "#6C8EE6",
        3: "#E9A34B", 4: "#EF6461", 5: "#A78BFA", 6: "#F472B6",
    }

    for _, row in edges_subset.iterrows():
        x0, y0 = NODE_POS.get(row["source"], (0.5, 0.5))
        x1, y1 = NODE_POS.get(row["target"], (0.5, 0.5))
        color  = all_lag_colors.get(row["lag"], "#AAB8CC")
        width  = 1.5 + row["strength"] * 10

        # Slight curve offset so both directions of a bidirectional link are visible
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2 + 0.07 * (1 if row["source"] < row["target"] else -1)

        hover = (
            f"<b>{row['source']} → {row['target']}</b><br>"
            f"Lag: {row['lag']} month{'s' if row['lag']!=1 else ''}<br>"
            f"Partial corr: {row['val']:+.3f}<br>"
            f"Strength: {row['strength']:.3f}<br>"
            f"q-value: {row['q_value']:.4g}<br>"
            f"Direction: {row['direction']}"
        )

        # Line
        fig.add_trace(go.Scatter(
            x=[x0, mid_x, x1], y=[y0, mid_y, y1],
            mode="lines",
            line=dict(color=color, width=width),
            hovertemplate=hover + "<extra></extra>",
            showlegend=False,
        ))

        # Arrowhead approximation — dot at target
        fig.add_trace(go.Scatter(
            x=[x1], y=[y1],
            mode="markers",
            marker=dict(
                symbol="arrow", size=14,
                color=color,
                angle=np.degrees(np.arctan2(y1 - y0, x1 - x0)),
                line=dict(width=0),
            ),
            hovertemplate=hover + "<extra></extra>",
            showlegend=False,
        ))

        # Lag label on edge midpoint
        fig.add_annotation(
            x=mid_x, y=mid_y,
            text=f"L{row['lag']} | {row['strength']:.2f}",
            showarrow=False,
            font=dict(size=9, color=color),
            bgcolor="rgba(6,11,20,0.75)",
        )

    # ── Draw nodes ──
    var_names = list(NODE_POS.keys())
    node_x    = [NODE_POS[v][0] for v in var_names]
    node_y    = [NODE_POS[v][1] for v in var_names]
    node_col  = [VAR_COLORS[v] for v in var_names]

    emojis = {"GPM": "🌧️", "SMAP": "💧", "NDVI": "🌿", "LST": "🌡️"}
    full_labels = {
        "GPM":  "Rain<br>(GPM)",
        "SMAP": "Soil Moisture<br>(SMAP)",
        "NDVI": "Vegetation<br>(NDVI)",
        "LST":  "Surface Temp<br>(LST)",
    }

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(
            size=52,
            color=[c + "33" for c in node_col],
            line=dict(width=3, color=node_col),
        ),
        text=[f"{emojis[v]}<br>{v}" for v in var_names],
        textposition="middle center",
        textfont=dict(size=11, color="#F1F5FC"),
        hovertemplate=[
            f"<b>{v}</b><br>{full_labels[v]}<extra></extra>"
            for v in var_names
        ],
        showlegend=False,
    ))

    # ── Lag legend ──
    for lag_val, lag_color in list(all_lag_colors.items())[:tau_max + 1]:
        if lag_val == 0 and not show_lag0:
            continue
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="lines",
            line=dict(color=lag_color, width=3),
            name=f"Lag {lag_val} month{'s' if lag_val != 1 else ''}",
            showlegend=True,
        ))

    _apply_layout(fig, height=560)
    fig.update_layout(
        title=dict(
            text=f"<b>Causal Graph — Uttarakhand Climate System</b>{title_suffix}",
            font=dict(size=15, color="#F1F5FC"),
            x=0.0,
        ),
        xaxis=dict(
            range=[-0.15, 1.15], showgrid=False,
            zeroline=False, showticklabels=False,
        ),
        yaxis=dict(
            range=[0.3, 1.1], showgrid=False,
            zeroline=False, showticklabels=False,
        ),
        legend=dict(
            x=0.01, y=0.01,
            bgcolor="rgba(10,16,32,0.8)",
            bordercolor="#1E2D4A",
            font=dict(size=11),
        ),
    )
    return fig

# Full causal graph
fig_full = build_causal_graph_fig(edges_disp, "")
st.plotly_chart(fig_full, use_container_width=True)

st.caption(
    "Arrow direction = causal direction · Width = causal strength · "
    "Color = lag depth · Lag labels show [L{months} | strength] · "
    "Only FDR-significant links shown (q < 0.05)"
)

# ── Animated version: build one frame per lag ──
st.markdown("#### 🎬 Animated — Watch Causation Unfold Lag by Lag")
st.caption("Each frame adds the causal links at that lag — see how monsoon signal propagates through the system.")

if not edges_disp.empty:
    unique_lags = sorted(edges_disp["lag"].unique())

    frames_data = []
    for lag_cutoff in unique_lags:
        subset = edges_disp[edges_disp["lag"] <= lag_cutoff]
        frames_data.append({
            "lag":   lag_cutoff,
            "edges": subset,
            "n":     len(subset),
        })

    if "causal_anim_frame" not in st.session_state:
        st.session_state.causal_anim_frame = 0
    if "causal_anim_playing" not in st.session_state:
        st.session_state.causal_anim_playing = False

    ctrl1, ctrl2, ctrl3, _ = st.columns([1, 1, 1, 5])
    with ctrl1:
        if st.button("▶ Play", key="causal_play"):
            st.session_state.causal_anim_playing = True
    with ctrl2:
        if st.button("⏹ Stop", key="causal_stop"):
            st.session_state.causal_anim_playing = False
    with ctrl3:
        if st.button("⏮ Reset", key="causal_reset"):
            st.session_state.causal_anim_frame = 0
            st.session_state.causal_anim_playing = False

    frame_idx = st.session_state.causal_anim_frame
    frame_idx = min(frame_idx, len(frames_data) - 1)

    current_frame = frames_data[frame_idx]
    fig_anim = build_causal_graph_fig(
        current_frame["edges"],
        f" — Up to Lag {current_frame['lag']} month{'s' if current_frame['lag']!=1 else ''}",
    )
    anim_slot = st.plotly_chart(fig_anim, use_container_width=True)

    lag_progress = st.progress(
        (frame_idx + 1) / len(frames_data),
        text=f"Lag {current_frame['lag']} month{'s' if current_frame['lag']!=1 else ''} · {current_frame['n']} causal links shown",
    )

    if st.session_state.causal_anim_playing:
        time.sleep(1.2)
        if frame_idx < len(frames_data) - 1:
            st.session_state.causal_anim_frame += 1
        else:
            st.session_state.causal_anim_playing = False
        st.rerun()

# ──────────────────────────────────────────────────────────────
# SECTION 3: MONSOON PROPAGATION CHAIN
# ──────────────────────────────────────────────────────────────

section_header("Monsoon Propagation Chain", "🌊",
               "Rain → Soil → Vegetation → Temperature — How fast does it travel?")

info_banner(
    "The physical hypothesis: **rainfall enters the system first**, "
    "then saturates soil (1 month lag), then vegetation responds to wet soil "
    "(another month), then surface temperature cools due to evapotranspiration. "
    "PCMCI either confirms or falsifies this chain from the data itself.",
    kind="warning",
)

chain_links = chain_info["chain_links"]
found_count  = chain_info["found_count"]
phys_count   = chain_info.get("physics_count", 0)

# Chain visualization — horizontal flow
chain_fig = go.Figure()

chain_nodes = [
    {"name": "Rain\n(GPM)",       "short": "GPM",  "x": 0.0,  "emoji": "🌧️"},
    {"name": "Soil Moisture\n(SMAP)", "short": "SMAP", "x": 0.33, "emoji": "💧"},
    {"name": "Vegetation\n(NDVI)", "short": "NDVI", "x": 0.67, "emoji": "🌿"},
    {"name": "Surface Temp\n(LST)","short": "LST",  "x": 1.0,  "emoji": "🌡️"},
]

for node in chain_nodes:
    color = VAR_COLORS[node["short"]]
    chain_fig.add_trace(go.Scatter(
        x=[node["x"]], y=[0.5],
        mode="markers+text",
        marker=dict(size=65, color=color + "22", line=dict(width=3, color=color)),
        text=[f"{node['emoji']}\n{node['short']}"],
        textposition="middle center",
        textfont=dict(size=12, color="#F1F5FC", family="Urbanist"),
        hovertemplate=f"<b>{node['name']}</b><extra></extra>",
        showlegend=False,
    ))

# Draw chain arrows
for lnk in chain_links:
    if not lnk["found"]:
        continue
    src_node = next((n for n in chain_nodes if n["short"] == lnk["source"]), None)
    tgt_node = next((n for n in chain_nodes if n["short"] == lnk["target"]), None)
    if not src_node or not tgt_node:
        continue

    x0, x1 = src_node["x"], tgt_node["x"]
    color   = "#31C48D" if lnk["matches_physics"] else "#E9A34B"
    lag_str = f"Lag {lnk['lag']}m" if lnk["lag"] else "Lag 0"

    chain_fig.add_annotation(
        ax=x0 + 0.07, ay=0.5, axref="x", ayref="y",
        x=x1 - 0.07, y=0.5,
        xref="x", yref="y",
        showarrow=True,
        arrowhead=3, arrowsize=1.5,
        arrowwidth=2 + lnk["strength"] * 8,
        arrowcolor=color,
    )
    chain_fig.add_annotation(
        x=(x0 + x1) / 2, y=0.62,
        text=f"<b>{lag_str}</b><br>strength {lnk['strength']:.2f}",
        showarrow=False,
        font=dict(size=10, color=color),
        bgcolor="rgba(6,11,20,0.8)",
        bordercolor=color,
        borderwidth=1,
        borderpad=4,
    )

chain_fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=320,
    xaxis=dict(range=[-0.15, 1.15], showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(range=[0.2, 0.9], showgrid=False, zeroline=False, showticklabels=False),
    margin=dict(l=20, r=20, t=40, b=20),
    title=dict(
        text="<b>Monsoon Causal Propagation Chain</b> · Green = matches physics · Orange = unexpected",
        font=dict(size=13, color="#F1F5FC"), x=0.0,
    ),
)
st.plotly_chart(chain_fig, use_container_width=True)

# Chain detail cards
cl1, cl2 = st.columns(2)
for i, lnk in enumerate(chain_links):
    col = cl1 if i % 2 == 0 else cl2
    with col:
        status_color = "#31C48D" if lnk["found"] and lnk["matches_physics"] else \
                       "#E9A34B" if lnk["found"] else "#EF6461"
        status_icon  = "✅" if lnk["found"] and lnk["matches_physics"] else \
                       "⚠️" if lnk["found"] else "❌"
        lag_disp = f"Lag {lnk['lag']} month{'s' if lnk.get('lag',0) != 1 else ''}" if lnk["found"] and lnk["lag"] is not None else "—"
        str_disp = f"{lnk['strength']:.3f}" if lnk["found"] else "—"

        st.markdown(f"""
        <div class="glass-card" style="padding:14px 16px;border-left:3px solid {status_color};margin-bottom:10px;">
          <div style="font-size:0.9rem;font-weight:700;color:{status_color};">
            {status_icon} {lnk['source']} → {lnk['target']}
          </div>
          <div style="font-size:0.78rem;color:#AAB8CC;margin:4px 0;">{lnk['description']}</div>
          <div style="font-size:0.75rem;color:#6B7B91;">
            {lag_disp} · Strength: {str_disp}
            {"· Physics match ✅" if lnk.get('matches_physics') else ("· Unexpected direction ⚠️" if lnk["found"] else "· Not detected")}
          </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown(
    f"**Chain Summary:** {found_count}/{len(chain_links)} links detected · "
    f"{phys_count} match expected monsoon physics"
)

# ──────────────────────────────────────────────────────────────
# SECTION 4: CAUSAL STRENGTH HEATMAP (all variable pairs × lags)
# ──────────────────────────────────────────────────────────────

section_header("Causal Strength Matrix", "🔥",
               "Partial correlation strength for every variable pair × lag")

if not edges.empty:
    var_names_all = pcmci_result["var_names"]
    n_vars        = len(var_names_all)
    tau_range     = range(0, tau_max + 1)

    # Build strength matrix: n_vars × n_vars × (tau_max+1) → pivot to 2D
    # Rows = "source → target @ lag", Columns = lags
    heatmap_rows = []
    for src in var_names_all:
        for tgt in var_names_all:
            if src == tgt:
                continue
            for lag in tau_range:
                match = edges[(edges["source"] == src) & (edges["target"] == tgt) & (edges["lag"] == lag)]
                val = float(match["val"].values[0]) if not match.empty else 0.0
                sig = not match.empty
                heatmap_rows.append({
                    "pair":  f"{src}→{tgt}",
                    "lag":   lag,
                    "val":   val,
                    "sig":   sig,
                })

    hm_df = pd.DataFrame(heatmap_rows)
    hm_pivot = hm_df.pivot(index="pair", columns="lag", values="val").fillna(0)

    # Only show pairs that have at least one significant link
    sig_pairs = hm_df[hm_df["sig"]]["pair"].unique()
    if len(sig_pairs) > 0:
        hm_pivot = hm_pivot.loc[hm_pivot.index.isin(sig_pairs)]

    hm_fig = go.Figure(go.Heatmap(
        z=hm_pivot.values,
        x=[f"Lag {l}m" for l in hm_pivot.columns],
        y=hm_pivot.index.tolist(),
        colorscale=[
            [0.0, "#1A4A8A"], [0.35, "#2D7DD2"],
            [0.5, "#1E2D4A"],
            [0.65, "#E9A34B"], [1.0, "#EF2461"],
        ],
        zmid=0,
        colorbar=dict(
            title="Partial corr", thickness=12, len=0.7,
            tickvals=[-0.4, -0.2, 0, 0.2, 0.4],
        ),
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.3f}<extra></extra>",
        xgap=2, ygap=2,
    ))
    _apply_layout(hm_fig, height=max(300, 55 * len(hm_pivot) + 80))
    hm_fig.update_layout(
        xaxis=dict(tickfont=dict(size=11)),
        yaxis=dict(tickfont=dict(size=11)),
        margin=dict(l=120, r=80, t=40, b=60),
        title=dict(
            text="<b>Causal Partial Correlation — Variable Pairs × Lag</b>"
                 " · Blue = negative · Red = positive · Only FDR-significant pairs shown",
            font=dict(size=12, color="#F1F5FC"), x=0.0,
        ),
    )
    st.plotly_chart(hm_fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# SECTION 5: CHAMOLI 2021 CAUSAL DESTABILISATION TEST
# ──────────────────────────────────────────────────────────────

section_header("Chamoli 2021 — Causal Destabilisation Test", "🏔️",
               "Did the causal structure break down before the Feb 7, 2021 disaster?")

info_banner(
    "**New question:** We already know anomalous z-scores appeared near Chamoli 2021. "
    "Now we ask something deeper: did the **causal wiring** of the ecosystem "
    "change in the 24 months BEFORE the disaster? "
    "A destabilising system should show fewer, weaker causal links — "
    "the ecosystem 'disconnecting' before it collapses.",
    kind="warning",
)

@st.cache_data(show_spinner=False)
def _chamoli_test():
    return chamoli_causal_shift(df, VARIABLES, date_col="month", tau_max=3)

with st.spinner("Running Chamoli causal shift test..."):
    chamoli = _chamoli_test()

if chamoli.get("error"):
    st.error(f"Chamoli test failed: {chamoli['error']}")
else:
    verdict_color = {
        "⚠️ CAUSAL DESTABILISATION DETECTED": "#EF6461",
        "🔶 PARTIAL SIGNAL — Minor structural change": "#E9A34B",
        "✅ NO STRUCTURAL CHANGE DETECTED": "#31C48D",
    }.get(chamoli["verdict"], "#6B7B91")

    st.markdown(f"""
    <div class="glass-card" style="border:2px solid {verdict_color};padding:22px 26px;border-radius:14px;margin-bottom:18px;">
      <div style="font-size:1.2rem;font-weight:800;color:{verdict_color};margin-bottom:10px;">
        {chamoli['verdict']}
      </div>
      <div style="font-size:0.9rem;color:#AAB8CC;line-height:1.7;">
        {chamoli['verdict_detail']}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Side-by-side comparison
    ch1, ch2 = st.columns(2)

    def _render_epoch_card(title, period, n_links, mean_str, gpm_smap, smap_ndvi, border_col):
        gpm_smap_str  = f"strength {gpm_smap['strength']:.3f} @ lag {gpm_smap['lag']}m" if gpm_smap else "❌ not detected"
        smap_ndvi_str = f"strength {smap_ndvi['strength']:.3f} @ lag {smap_ndvi['lag']}m" if smap_ndvi else "❌ not detected"
        st.markdown(f"""
        <div class="glass-card" style="border-left:4px solid {border_col};padding:18px;">
          <div style="font-size:0.85rem;font-weight:700;color:{border_col};margin-bottom:10px;">{title}</div>
          <div style="font-size:0.75rem;color:#6B7B91;margin-bottom:12px;">{period}</div>
          {"".join([
            f"<div style='display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1E2D4A;'>"
            f"<span style='color:#6B7B91;font-size:0.8rem;'>{k}</span>"
            f"<span style='color:#F1F5FC;font-size:0.8rem;font-weight:600;'>{v}</span>"
            f"</div>"
            for k, v in [
                ("Significant links",    n_links),
                ("Mean causal strength", f"{mean_str:.4f}"),
                ("GPM → SMAP link",      gpm_smap_str),
                ("SMAP → NDVI link",     smap_ndvi_str),
            ]
          ])}
        </div>
        """, unsafe_allow_html=True)

    with ch1:
        _render_epoch_card(
            "🟢 Baseline Period",
            chamoli["baseline_period"],
            chamoli["baseline_n_links"],
            chamoli["baseline_mean_strength"],
            chamoli.get("baseline_gpm_smap"),
            chamoli.get("baseline_smap_ndvi"),
            "#31C48D",
        )
    with ch2:
        _render_epoch_card(
            "🔴 Pre-Disaster Period",
            chamoli["pre_disaster_period"],
            chamoli["pre_disaster_n_links"],
            chamoli["pre_disaster_mean_str"],
            chamoli.get("pre_disaster_gpm_smap"),
            chamoli.get("pre_disaster_smap_ndvi"),
            "#EF6461",
        )

    # Delta metrics
    st.markdown("")
    dm1, dm2, dm3 = st.columns(3)
    dm1.metric(
        "Links Lost",
        chamoli["links_lost"],
        delta=f"{-chamoli['links_lost']} from baseline",
        delta_color="inverse",
    )
    dm2.metric(
        "Strength Drop",
        f"{chamoli['strength_drop']:.4f}",
        delta=f"{-chamoli['strength_drop']:.4f}",
        delta_color="inverse",
    )
    dm3.metric(
        "Baseline → Pre-Disaster",
        f"{chamoli['baseline_n_links']} → {chamoli['pre_disaster_n_links']} links",
    )

    # Side-by-side causal graphs
    if not chamoli["baseline_edges"].empty or not chamoli["pre_disaster_edges"].empty:
        st.markdown("#### Causal Graph: Baseline vs Pre-Disaster")
        cg1, cg2 = st.columns(2)
        with cg1:
            fig_bl = build_causal_graph_fig(
                chamoli["baseline_edges"][chamoli["baseline_edges"]["lag"] > 0]
                if not chamoli["baseline_edges"].empty else pd.DataFrame(),
                " — Baseline",
            )
            st.plotly_chart(fig_bl, use_container_width=True)
            st.caption("Baseline — normal causal structure")
        with cg2:
            fig_pd = build_causal_graph_fig(
                chamoli["pre_disaster_edges"][chamoli["pre_disaster_edges"]["lag"] > 0]
                if not chamoli["pre_disaster_edges"].empty else pd.DataFrame(),
                " — Pre-Disaster (2019–2021)",
            )
            st.plotly_chart(fig_pd, use_container_width=True)
            st.caption("Pre-disaster — did links disappear?")

# ──────────────────────────────────────────────────────────────
# SECTION 6: ROLLING CAUSAL STABILITY TIMELINE
# ──────────────────────────────────────────────────────────────

section_header("Rolling Causal Stability — 10-Year Timeline", "📉",
               "Is the causal network strengthening or eroding over time?")

info_banner(
    "A **stable ecosystem** shows consistent causal strength over time. "
    "An **eroding ecosystem** shows fewer and weaker causal links as years pass. "
    "This is the satellite-data equivalent of an EEG flatline — "
    "the system's internal communication breaking down.",
    kind="info",
)

@st.cache_data(show_spinner=False)
def _rolling_stability():
    return rolling_causal_stability(
        df, VARIABLES, date_col="month",
        window_months=36, step_months=6, tau_max=3,
    )

with st.spinner("Computing rolling causal stability across 10-year window..."):
    stab_df = _rolling_stability()

if not stab_df.empty:
    fig_stab = go.Figure()

    # Overall mean strength
    fig_stab.add_trace(go.Scatter(
        x=stab_df["window_mid"],
        y=stab_df["mean_strength"],
        mode="lines+markers",
        name="Overall causal strength",
        line=dict(color="#35C9D0", width=2.5),
        marker=dict(size=7),
        hovertemplate="<b>%{x}</b><br>Overall: %{y:.4f}<extra></extra>",
        fill="tozeroy",
        fillcolor="rgba(53,201,208,0.08)",
    ))

    # GPM→SMAP link
    fig_stab.add_trace(go.Scatter(
        x=stab_df["window_mid"],
        y=stab_df["gpm_smap_strength"],
        mode="lines+markers",
        name="GPM → SMAP (rain→soil)",
        line=dict(color="#6C8EE6", width=1.8, dash="dot"),
        marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>GPM→SMAP: %{y:.4f}<extra></extra>",
    ))

    # SMAP→NDVI link
    fig_stab.add_trace(go.Scatter(
        x=stab_df["window_mid"],
        y=stab_df["smap_ndvi_strength"],
        mode="lines+markers",
        name="SMAP → NDVI (soil→veg)",
        line=dict(color="#31C48D", width=1.8, dash="dot"),
        marker=dict(size=6),
        hovertemplate="<b>%{x}</b><br>SMAP→NDVI: %{y:.4f}<extra></extra>",
    ))

    # Number of links (secondary axis)
    fig_stab.add_trace(go.Bar(
        x=stab_df["window_mid"],
        y=stab_df["n_links"],
        name="# Causal links",
        marker_color="rgba(233,163,75,0.3)",
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>Links: %{y}<extra></extra>",
    ))

    # Chamoli marker
    chamoli_mid = "2020-02"
    if chamoli_mid in stab_df["window_mid"].values:
        fig_stab.add_vline(
            x=chamoli_mid,
            line_dash="dash", line_color="#EF6461", line_width=1.5,
        )
        fig_stab.add_annotation(
            x=chamoli_mid, yref="paper", y=1.0,
            text="← Chamoli 2021", showarrow=False,
            font=dict(color="#EF6461", size=10), xanchor="left",
        )

    _apply_layout(fig_stab, height=400)
    fig_stab.update_layout(
        yaxis=dict(title="Causal Strength (partial corr)", rangemode="tozero"),
        yaxis2=dict(
            title="# Links",
            overlaying="y", side="right",
            showgrid=False, rangemode="tozero",
        ),
        xaxis=dict(title="Rolling Window Midpoint", tickangle=-30),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(10,16,32,0.8)"),
        barmode="overlay",
    )
    st.plotly_chart(fig_stab, use_container_width=True)
    st.caption(
        "Each point = PCMCI run on a 36-month rolling window · "
        "Declining trend = causal network weakening = ecosystem becoming less predictable"
    )

    # Trend in stability
    if len(stab_df) >= 4:
        from scipy.stats import linregress
        x_arr = np.arange(len(stab_df))
        slope, _, r2, pval, _ = linregress(x_arr, stab_df["mean_strength"])
        slope_color = "#EF6461" if slope < 0 else "#31C48D"
        direction   = "DECLINING ↘" if slope < 0 else "STABLE / IMPROVING ↗"
        st.markdown(
            f"**Stability trend:** "
            f"<span style='color:{slope_color};font-weight:700;'>{direction}</span> · "
            f"slope = {slope:.5f}/window · R² = {r2:.3f} · p = {pval:.4g}",
            unsafe_allow_html=True,
        )

# ──────────────────────────────────────────────────────────────
# SECTION 7: FULL EDGE TABLE
# ──────────────────────────────────────────────────────────────

with st.expander("📋 Full Causal Edge Table"):
    if not edges.empty:
        display_edges = edges[[
            "source", "target", "lag", "val", "strength",
            "direction", "p_value", "q_value",
        ]].copy()
        display_edges.columns = [
            "Source", "Target", "Lag (months)", "Partial Corr", "Strength",
            "Direction", "p-value", "q-value (FDR)",
        ]
        st.dataframe(
            display_edges.style.background_gradient(
                subset=["Strength"], cmap="Blues"
            ),
            use_container_width=True, hide_index=True,
        )
        st.download_button(
            "⬇️ Download Causal Edges CSV",
            data=display_edges.to_csv(index=False),
            file_name="earthpulse_x_causal_edges.csv",
            mime="text/csv",
        )
    else:
        st.info("No significant causal edges found with current settings.")

# ──────────────────────────────────────────────────────────────
# SECTION 8: AI SCIENTIFIC INTERPRETATION
# ──────────────────────────────────────────────────────────────

section_header("AI Scientific Interpretation", "🧠",
               "Evidence-grounded interpretation of causal discovery results")

causal_ctx = causal_summary_text(edges, chain_info)

col_ai1, col_ai2 = st.columns(2)
with col_ai1:
    if st.button("🤖 Interpret Causal Graph", key="ai_causal", use_container_width=True):
        st.session_state["causal_ai_question"] = (
            "Interpret this PCMCI causal discovery result for Uttarakhand's climate system. "
            "Which causal links are strongest? Does the monsoon propagation chain match "
            "physical expectations? Are there any surprising causal directions? "
            "Be specific about partial correlation values and lag times."
        )
with col_ai2:
    if st.button("🏔️ Interpret Chamoli Findings", key="ai_chamoli", use_container_width=True):
        chamoli_ctx = json.dumps({
            "verdict": chamoli.get("verdict"),
            "baseline_links": chamoli.get("baseline_n_links"),
            "pre_disaster_links": chamoli.get("pre_disaster_n_links"),
            "links_lost": chamoli.get("links_lost"),
            "strength_drop": chamoli.get("strength_drop"),
        }, default=str) if not chamoli.get("error") else "Chamoli test failed."
        st.session_state["causal_ai_question"] = (
            f"Interpret the Chamoli 2021 causal destabilisation result: {chamoli_ctx}. "
            "What does the change in causal network structure before the disaster mean? "
            "Is this evidence of ecosystem destabilisation? What are the limitations?"
        )

if "causal_ai_question" in st.session_state:
    question = st.session_state.pop("causal_ai_question")
    groq_key = os.getenv("GROQ_API_KEY")

    if not groq_key:
        st.warning("GROQ_API_KEY not set — add it to your .env file.")
    else:
        with st.spinner("AI is reading the causal graph..."):
            try:
                client = Groq(api_key=groq_key)
                resp   = client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a scientific analyst for EARTHPULSE-X. "
                                "Interpret PCMCI causal discovery results for a Himalayan climate system. "
                                "Rules: use only supplied data, distinguish observations from interpretations, "
                                "correlation ≠ causation but PCMCI partial correlations ARE causal evidence, "
                                "state limitations explicitly. Use bullet points with actual numbers."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"CAUSAL DISCOVERY CONTEXT:\n{causal_ctx}\n\nQUESTION:\n{question}",
                        },
                    ],
                    temperature=0.2,
                    max_tokens=700,
                )
                ai_card(resp.choices[0].message.content.strip())
            except Exception as exc:
                st.error(f"AI call failed: {exc}")

# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "PCMCI: Runge, J., et al. (2019). Detecting and quantifying causal associations in large "
    "nonlinear time series datasets. *Science Advances*, 5(11), eaau4996. · "
    "FDR correction: Benjamini & Hochberg (1995) · "
    "Data: NASA MODIS, SMAP, GPM · Period: 2015–2025"
)
footer()
