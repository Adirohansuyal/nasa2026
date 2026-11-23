"""
Interaction Network — Premium Variable Relationship Explorer
==============================================================
Network graph + correlation matrix + relationship table.
"""

import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import os
from groq import Groq
import plotly.graph_objects as go

from core.data_loader import load_interaction_results

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
from components.charts import correlation_heatmap, _apply_layout, COLORS

# ──────────────────────────────────────────────────────────────
# Human-readable variable labels + styling
# ──────────────────────────────────────────────────────────────

VAR_META = {
    "lst_strict_mean":                  {"label": "🌡️ Land Surface\nTemperature",  "short": "Temperature",   "color": "#EF6461", "emoji": "🌡️"},
    "ndvi_strict_mean":                 {"label": "🌿 Vegetation\nGreenness",       "short": "Vegetation",    "color": "#31C48D", "emoji": "🌿"},
    "smap_am_strict_mean":              {"label": "💧 Morning\nSoil Moisture",      "short": "Soil (Morning)","color": "#6C8EE6", "emoji": "💧"},
    "smap_pm_strict_mean":              {"label": "💧 Evening\nSoil Moisture",      "short": "Soil (Evening)","color": "#A78BFA", "emoji": "💧"},
    "gpm_monthly_precipitation_mean":   {"label": "🌧️ Rainfall",                   "short": "Rainfall",      "color": "#35C9D0", "emoji": "🌧️"},
}

# Fallback: map old-style short codes used in precomputed CSV
_CODE_MAP = {
    "LST":     "lst_strict_mean",
    "NDVI":    "ndvi_strict_mean",
    "SMAP_AM": "smap_am_strict_mean",
    "SMAP_PM": "smap_pm_strict_mean",
    "GPM":     "gpm_monthly_precipitation_mean",
}

def _resolve(var_id: str) -> dict:
    """Return VAR_META entry for a variable id, resolving short codes."""
    if var_id in VAR_META:
        return VAR_META[var_id]
    resolved = _CODE_MAP.get(var_id)
    if resolved and resolved in VAR_META:
        return VAR_META[resolved]
    return {"label": var_id, "short": var_id, "color": COLORS["primary"], "emoji": "📊"}

def _short(var_id: str) -> str:
    return _resolve(var_id)["short"]

def _color(var_id: str) -> str:
    return _resolve(var_id)["color"]

def _label(var_id: str) -> str:
    return _resolve(var_id)["label"]

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Interaction Network | EARTHPULSE-X",
    page_icon="🕸️",
    layout="wide",
)

inject_theme()
render_sidebar()

_GROQ_CLIENT = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# ──────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    df = load_interaction_results().copy()
    df["fdr_significant"] = df["fdr_significant"].astype(bool)
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Unable to load interaction data: {e}")
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────

page_header(
    "INTERACTION NETWORK",
    "Earth System Variable Relationship Intelligence · Spearman + FDR + Lag-Aware",
    "🕸️",
)

info_banner(
    "Explore how NASA-measured environmental variables influence each other across Uttarakhand. "
    "Each connection shows how strongly two variables move together — and whether one leads the other in time. "
    "All relationships are corrected for multiple statistical tests. "
    "⚠️ Association does not mean causation.",
    kind="info",
)

# ──────────────────────────────────────────────────────────────
# OVERVIEW METRICS
# ──────────────────────────────────────────────────────────────

total_pairs = len(df)
significant_pairs = int(df["fdr_significant"].sum())
unique_variables = len(set(df["variable_x"]).union(set(df["variable_y"])))
lag_count = df["lag_months"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Interaction Records", f"{total_pairs:,}")
c2.metric("FDR Significant", f"{significant_pairs:,}")
c3.metric("Environmental Variables", unique_variables)
c4.metric("Lag Windows", lag_count)

# ──────────────────────────────────────────────────────────────
# FILTERS
# ──────────────────────────────────────────────────────────────

section_header("Interaction Filters", "🎛️")

f1, f2, f3 = st.columns(3)

with f1:
    available_lags = sorted(df["lag_months"].unique().tolist())
    selected_lag = st.selectbox(
        "Temporal Lag",
        available_lags,
        format_func=lambda x: "No lag — same month" if x == 0 else f"Variable A leads B by {x} month(s)",
        index=available_lags.index(0) if 0 in available_lags else 0,
    )

with f2:
    significance_filter = st.selectbox("Significance Filter", ["All relationships", "FDR significant only"])

with f3:
    min_strength = st.slider("Minimum |Correlation|", 0.0, 1.0, 0.0, 0.05)

# Filter
filtered = df[df["lag_months"] == selected_lag].copy()
if significance_filter == "FDR significant only":
    filtered = filtered[filtered["fdr_significant"]]
filtered = filtered[filtered["spearman_rho"].abs() >= min_strength].copy()

st.write(f"Displaying **{len(filtered)}** relationships for selected lag.")

# ──────────────────────────────────────────────────────────────
# NETWORK GRAPH
# ──────────────────────────────────────────────────────────────

section_header("Environmental Interaction Graph", "🌐", "🟢 Positive · 🔴 Negative · Edge width = |ρ|")

G = nx.Graph()

for _, row in filtered.iterrows():
    source = row["variable_x"]
    target = row["variable_y"]
    G.add_node(source)
    G.add_node(target)
    G.add_edge(
        source, target,
        rho=float(row["spearman_rho"]),
        q=float(row["fdr_q_value"]),
        significant=bool(row["fdr_significant"]),
        sample_size=int(row["sample_size"]),
        confidence_score=float(row.get("confidence_score", 0.5)),
        lag_months=int(row["lag_months"]),
    )

if G.number_of_nodes() == 0:
    st.warning("No relationships match the selected filters.")
else:
    positions = nx.spring_layout(G, seed=42, k=1.5, iterations=120)

    # ── Build premium Plotly figure ──────────────────────────────
    net_fig = go.Figure()

    # Draw edges first (behind nodes)
    for src, tgt, attr in G.edges(data=True):
        x0, y0 = positions[src]
        x1, y1 = positions[tgt]
        rho      = attr.get("rho", attr.get("spearman_rho", 0))
        conf     = attr.get("confidence_score", attr.get("confidence", 0.5))
        lag_v    = attr.get("lag_months", attr.get("lag", 0))
        q_v      = attr.get("fdr_q_value", attr.get("q", 0))
        sig      = attr.get("significant", True)

        # Color: green = positive, red = negative
        # Opacity varies with confidence
        opacity  = max(0.35, min(1.0, 0.35 + conf * 0.65))
        if rho >= 0:
            r, g_c, b = 49, 196, 141   # #31C48D
        else:
            r, g_c, b = 239, 100, 97   # #EF6461

        edge_color = f"rgba({r},{g_c},{b},{opacity:.2f})"
        width = 1.5 + abs(rho) * 7

        src_short = _short(src)
        tgt_short = _short(tgt)
        direction_word = "positively" if rho >= 0 else "negatively"
        lag_text  = "same month" if lag_v == 0 else f"{src_short} → {tgt_short} after {lag_v} month(s)"

        net_fig.add_trace(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(color=edge_color, width=width),
            hoverinfo="text",
            text=[
                f"<b>{src_short} ↔ {tgt_short}</b><br>"
                f"Association: {direction_word}<br>"
                f"Strength: {abs(rho):.3f}  {'(strong)' if abs(rho)>0.6 else '(moderate)' if abs(rho)>0.3 else '(weak)'}<br>"
                f"Confidence: {conf:.2f}<br>"
                f"Lag: {lag_text}<br>"
                f"Statistical q-value: {q_v:.4g}"
            ] * 3,
            showlegend=False,
        ))

    # Draw nodes on top
    for node in G.nodes():
        x, y       = positions[node]
        deg        = G.degree(node)
        meta       = _resolve(node)
        node_color = meta["color"]
        short_lbl  = meta["short"]
        emoji      = meta["emoji"]
        size       = 38 + deg * 10

        # Connections summary
        neighbours = [_short(n) for n in G.neighbors(node)]
        hover_txt = (
            f"<b>{emoji} {short_lbl}</b><br>"
            f"Connections: {deg}<br>"
            f"Connected to: {', '.join(neighbours) if neighbours else 'none'}"
        )

        # Node circle
        net_fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers",
            marker=dict(
                size=size,
                color=node_color,
                opacity=0.92,
                line=dict(width=3, color="rgba(255,255,255,0.6)"),
            ),
            hovertext=hover_txt,
            hoverinfo="text",
            showlegend=False,
        ))

        # Node label below the circle
        net_fig.add_annotation(
            x=x, y=y - 0.13,
            text=f"<b>{emoji} {short_lbl}</b>",
            showarrow=False,
            font=dict(size=13, color="#F1F5FC", family="Urbanist"),
            xanchor="center",
            yanchor="top",
            bgcolor="rgba(8,13,24,0.75)",
            borderpad=3,
        )

    # Legend items (dummy traces)
    net_fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#31C48D", width=3),
        name="🟢 Positive association",
        showlegend=True,
    ))
    net_fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#EF6461", width=3),
        name="🔴 Negative association",
        showlegend=True,
    ))
    net_fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="#FFFFFF", width=6),
        name="Thicker = stronger",
        showlegend=True,
    ))

    net_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080D18",
        plot_bgcolor="#080D18",
        height=560,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.08,
            x=0.5,
            xanchor="center",
            font=dict(size=12, family="Urbanist", color="#AAB8CC"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="#0F1A2E",
            bordercolor="#2A3F5F",
            font=dict(family="Urbanist", size=12, color="#F1F5FC"),
        ),
    )

    st.plotly_chart(net_fig, use_container_width=True, key="interaction_network_main")

    st.markdown("🟢 Positive correlation | 🔴 Negative correlation | Edge width = correlation strength")

    # ── AI EXPLANATION ──────────────────────────────────────────

    if st.button("🤖 Explain this interaction graph", use_container_width=True):
        edges_info = []
        for src, tgt, attr in G.edges(data=True):
            rho = attr.get("rho", attr.get("spearman_rho", 0))
            direction = "positively" if rho >= 0 else "negatively"
            strength = abs(rho)
            sig = "statistically significant" if attr.get("significant", True) else "not significant"
            lag_v = attr.get("lag_months", attr.get("lag", 0))
            edges_info.append(
                f"- {_short(src)} and {_short(tgt)} are {direction} associated "
                f"(strength: {strength:.2f}, {sig}, lag: {lag_v} month(s))"
            )

        node_degrees = sorted(
            [(n, G.degree(n)) for n in G.nodes()],
            key=lambda x: x[1], reverse=True,
        )
        top_nodes = ", ".join(
            f"{_short(n)} ({d} connections)" for n, d in node_degrees[:5]
        )

        graph_summary = (
            f"Temporal lag: {selected_lag} month(s).\n"
            f"Total relationships shown: {G.number_of_edges()}.\n"
            f"Most connected variables: {top_nodes}.\n\n"
            f"All relationships:\n{chr(10).join(edges_info) if edges_info else 'No relationships found.'}"
        )

        prompt = f"""You are an AI analyst. A user is looking at a network graph showing statistical relationships between environmental variables (temperature, vegetation greenness, soil moisture, rainfall) measured by NASA satellites over Uttarakhand, India.

Graph summary:
{graph_summary}

Give a direct, factual explanation. No intro sentences. Just:
- Which connections are the strongest (give actual strength numbers)
- What each strong connection means in plain terms (e.g. "more rain → wetter soil 1 month later")
- Which variable is the most connected hub and what that implies
- Whether connections make physical sense for a Himalayan monsoon region
- One-line verdict: what does this graph tell us about how Uttarakhand's environment works?

Short bullets. Numbers. Plain English. No technical jargon."""

        with st.spinner("AI scientist is thinking..."):
            try:
                response = _GROQ_CLIENT.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=600,
                )
                ai_card(response.choices[0].message.content.strip())
            except Exception as e:
                st.error(f"AI unavailable: {e}")

# ──────────────────────────────────────────────────────────────
# CORRELATION HEATMAP
# ──────────────────────────────────────────────────────────────

section_header("Correlation Matrix", "🔥", "Spearman rank correlation")

variables_list = sorted(set(df["variable_x"]).union(set(df["variable_y"])))
friendly_vars  = [_short(v) for v in variables_list]

matrix = pd.DataFrame(np.nan, index=friendly_vars, columns=friendly_vars)

for _, row in filtered.iterrows():
    x_lbl = _short(row["variable_x"])
    y_lbl = _short(row["variable_y"])
    rho   = row["spearman_rho"]
    matrix.loc[x_lbl, y_lbl] = rho
    matrix.loc[y_lbl, x_lbl] = rho

for v in friendly_vars:
    matrix.loc[v, v] = 1.0

heat_fig = correlation_heatmap(matrix, height=460)
st.plotly_chart(heat_fig, use_container_width=True, key="corr_heatmap")

# ──────────────────────────────────────────────────────────────
# RELATIONSHIP TABLE
# ──────────────────────────────────────────────────────────────

section_header("Relationship Explorer", "📋")

display_df = filtered[[
    "variable_x", "variable_y", "lag_months", "sample_size",
    "spearman_rho", "p_value", "fdr_q_value", "fdr_significant",
]].copy()

# Replace internal codes with friendly names
display_df["variable_x"] = display_df["variable_x"].apply(_short)
display_df["variable_y"] = display_df["variable_y"].apply(_short)

display_df = display_df.rename(columns={
    "variable_x":    "Variable A",
    "variable_y":    "Variable B",
    "lag_months":    "Lag (months)",
    "sample_size":   "Data Points",
    "spearman_rho":  "Association Strength",
    "p_value":       "p-value",
    "fdr_q_value":   "FDR q-value",
    "fdr_significant": "Significant?",
})

display_df = display_df.sort_values(
    "Association Strength", key=lambda x: x.abs(), ascending=False
)

st.dataframe(display_df, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────
# STRONGEST RELATIONSHIP
# ──────────────────────────────────────────────────────────────

if not filtered.empty:
    strongest = filtered.loc[filtered["spearman_rho"].abs().idxmax()]

    section_header("Strongest Filtered Relationship", "💪")

    src_name = _short(strongest["variable_x"])
    tgt_name = _short(strongest["variable_y"])
    direction_word = "positive" if strongest["spearman_rho"] >= 0 else "negative"

    st.subheader(f"{_resolve(strongest['variable_x'])['emoji']} {src_name}  ↔  {_resolve(strongest['variable_y'])['emoji']} {tgt_name}")
    st.caption(f"{direction_word.title()} association · Lag {int(strongest['lag_months'])} month(s)")

    a, b, c, d = st.columns(4)
    a.metric("Association Strength", f"{strongest['spearman_rho']:.4f}")
    b.metric("FDR q-value", f"{strongest['fdr_q_value']:.4g}")
    c.metric("Data Points", f"{int(strongest['sample_size']):,}")
    d.metric("Lag (months)", int(strongest["lag_months"]))

# ──────────────────────────────────────────────────────────────
# METHODOLOGY
# ──────────────────────────────────────────────────────────────

with st.expander("📖 Scientific Methodology & Limitations"):
    st.markdown("""
    **Spearman Rank Correlation:** Measures monotonic statistical association.
    Non-parametric — does not assume linearity or normality.

    **Lagged Analysis:** Tests relationships at different temporal offsets.
    Lag 0 = same month. Lag 1 = X predicts Y 1 month later.

    **False Discovery Rate (FDR):** Benjamini-Hochberg correction for
    testing multiple variable pairs simultaneously.

    **Interpretation:**
    - Positive correlation: variables move in the same direction.
    - Negative correlation: variables move in opposite directions.
    - Larger |ρ| = stronger monotonic association.

    **Important limitations:**
    - Correlation does not establish causation.
    - Lagged association does not establish a physical causal mechanism.
    - Seasonal cycles may contribute to observed correlations.
    - Statistical significance does not establish environmental impact.
    """)

footer()
