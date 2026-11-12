"""
UG-ESI Mission Control
======================
The interactive UG-ESI research workflow page.

Runs all four UG-ESI contributions end-to-end:
  1. Adaptive Variable Selection
  2. Multi-Scale Trend Intelligence
  3. Uncertainty-Guided Interaction Graph
  4. Evidence-Grounded Research Report (AI)
"""

import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from core.data_loader import load_regional_timeseries
from core.anomaly_engine import (
    adaptive_variable_selection,
    selection_summary_text,
    VARIABLE_REGISTRY,
    OBJECTIVE_WEIGHTS,
)
from core.trend_engine import (
    full_trend_report,
    multi_variable_trend_report,
)
from core.interaction_engine import build_interaction_graph
from core.ai_agent import (
    explain_variable_selection,
    explain_trend,
    explain_interaction_graph,
    generate_research_report,
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
from components.charts import (
    trend_timeseries,
    seasonal_bars,
    anomaly_bars,
    network_graph,
    _apply_layout,
    COLORS,
)


# -----------------------------------------
# PAGE CONFIG
# -----------------------------------------

st.set_page_config(
    page_title="UG-ESI Mission Control | EARTHPULSE-X",
    page_icon="🧭",
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
except Exception as e:
    st.error(f"Data load failed: {e}")
    st.stop()


# -----------------------------------------
# HEADER
# -----------------------------------------

page_header(
    "UG-ESI MISSION CONTROL",
    "Uncertainty-Guided Earth System Intelligence — Live Research Workflow",
    "🧭",
)

st.caption(
    "Uttarakhand, India · 2015–2025 · "
    "Run all four UG-ESI contributions interactively on real NASA data."
)

info_banner(
    "**How this works:** Choose a research objective → "
    "the system selects the best variables → runs multi-method trend analysis → "
    "builds an uncertainty-guided interaction graph → "
    "generates an evidence-grounded AI research report.",
)

st.divider()


# ============================================================
# STEP 1: OBJECTIVE & VARIABLE SELECTION
# ============================================================

st.markdown(
    '<div class="contribution-badge">UG-ESI CONTRIBUTION 1</div>',
    unsafe_allow_html=True,
)
st.markdown("## 🎯 Step 1 — Adaptive Variable Selection")

st.markdown(
    "Select a research objective. The system will score all available "
    "environmental variables based on data quality, signal strength, "
    "temporal variability, and relevance — then recommend the best combination."
)
st.caption(
    "⚠️ Variables are NOT selected based on statistical significance. "
    "That would introduce selection bias. They are ranked by data quality "
    "and signal properties only."
)

objective_labels = {
    "general": "🌍 General Earth System Analysis",
    "drought": "🏜️ Drought Investigation",
    "flood": "🌊 Flood & Excess Rainfall",
    "vegetation_change": "🌿 Vegetation Change",
    "temperature_trend": "🌡️ Temperature Trend",
}

selected_objective = st.selectbox(
    "RESEARCH OBJECTIVE",
    list(objective_labels.keys()),
    format_func=lambda k: objective_labels[k],
)

with st.spinner("Scoring variables..."):
    scores = adaptive_variable_selection(df, objective=selected_objective)

# Show score cards
st.markdown("### Variable Ranking Results")

score_cols = st.columns(len(scores))

for col, item in zip(score_cols, scores):
    with col:
        border_color = "#35C9D0" if item["recommended"] else "#26374F"
        rec_label = "✅ Recommended" if item["recommended"] else "—"
        st.markdown(f"""
        <div style="
            background:#111C2D;
            border:2px solid {border_color};
            border-radius:12px;
            padding:14px;
            text-align:center;
            min-height:180px;
        ">
            <div style="font-size:22px;">{item["emoji"]}</div>
            <div style="font-size:13px;font-weight:700;
                        color:#F1F5FC;margin:4px 0;">
                {item["short"]}
            </div>
            <div style="font-size:11px;color:#A0AEC0;margin-bottom:8px;">
                {item["label"]}
            </div>
            <div style="font-size:20px;font-weight:800;color:#35C9D0;">
                {item["composite_score"]:.2f}
            </div>
            <div style="font-size:10px;color:#6B8099;">composite score</div>
            <div style="font-size:11px;color:#A0AEC0;margin-top:6px;">
                {item["quality_label"]}
            </div>
            <div style="font-size:11px;color:#35C9D0;margin-top:4px;">
                {rec_label}
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("")

# Score breakdown table
with st.expander("📊 Full Scoring Breakdown"):
    score_df = pd.DataFrame([{
        "Variable": s["short"],
        "Composite": s["composite_score"],
        "Coverage": s["coverage_score"],
        "Variability": s["variability_score"],
        "Trend Strength": s["trend_strength"],
        "Obj. Weight": s["objective_weight"],
        "Redundancy Penalty": s["redundancy_penalty"],
        "Quality": s["quality_label"],
        "Rationale": s["rationale"],
    } for s in scores])
    st.dataframe(score_df, use_container_width=True, hide_index=True)

# AI explanation for variable selection
if st.button("🤖 Explain this variable selection", key="ai_step1"):
    summary_text = selection_summary_text(scores, selected_objective)
    with st.spinner("AI is reading the scores..."):
        try:
            explanation = explain_variable_selection(
                summary_text, selected_objective
            )
            ai_card(explanation)
        except Exception as e:
            st.error(f"AI unavailable: {e}")

# Collect recommended variables for next steps
recommended_vars = [s["variable"] for s in scores if s["recommended"]]
recommended_meta = {s["variable"]: s for s in scores if s["recommended"]}

st.divider()


# ============================================================
# STEP 2: MULTI-SCALE TREND INTELLIGENCE
# ============================================================

st.markdown(
    '<div class="contribution-badge">UG-ESI CONTRIBUTION 2</div>',
    unsafe_allow_html=True,
)
st.markdown("## 📈 Step 2 — Multi-Scale Trend Intelligence")

st.markdown(
    "Statistical trend analysis using three complementary methods "
    "on each recommended variable. "
    "Results include trend direction, magnitude, statistical significance, "
    "and detected change points."
)

st.caption(
    "Methods: Modified Mann-Kendall (autocorrelation-adjusted, Hamed & Rao 1998) · "
    "Sen's Slope (robust magnitude estimate) · "
    "OLS Linear Regression · CUSUM Change-Point Detection"
)

# Variable selector (from recommended set)
var_options = {
    recommended_meta[v]["label"]: v
    for v in recommended_vars
    if v in df.columns
}

selected_var_label = st.selectbox(
    "SELECT VARIABLE FOR TREND ANALYSIS",
    list(var_options.keys()),
)
selected_var = var_options[selected_var_label]
selected_unit = recommended_meta[selected_var].get("unit", "")

# Run trend analysis (cached by variable + data hash)
@st.cache_data(show_spinner=False)
def run_trend(var_key: str, data_hash: int) -> dict:
    return full_trend_report(
        df,
        date_col="date",
        value_col=var_key,
        variable_label=selected_var_label,
    )

data_hash = len(df)
with st.spinner("Running trend analysis..."):
    report = run_trend(selected_var, data_hash)

# Use modified Mann-Kendall (autocorrelation-adjusted) as the primary
# significance determination — consistent with Trend Detective page
mmk = report["modified_mann_kendall"]
ols = report["ols"]
ss = report["sens_slope"]
cp = report["change_points"]

# KPI tiles
k1, k2, k3, k4 = st.columns(4)

direction_color = (
    "#31C48D" if mmk["direction"] == "increasing"
    else "#EF6461" if mmk["direction"] == "decreasing"
    else "#A0AEC0"
)

k1.metric(
    "Trend Direction",
    mmk["direction"].title(),
    help="Modified Mann-Kendall (autocorrelation-adjusted) direction.",
)
k2.metric(
    "Annual Change (Sen's)",
    f"{report['annualised_sens_slope']:.4g} {selected_unit}/yr"
    if not np.isnan(report["annualised_sens_slope"]) else "N/A",
    help="Robust Sen's slope × 12 months.",
)
k3.metric(
    "Modified MK p-value",
    f"{mmk['p_value']:.4g}" if not np.isnan(mmk["p_value"]) else "N/A",
    help="Autocorrelation-adjusted p-value (Hamed & Rao 1998).",
)
k4.metric(
    "Lag-1 Autocorr.",
    f"{mmk.get('lag1_autocorrelation', 0):.3f}" if not np.isnan(mmk.get('lag1_autocorrelation', np.nan)) else "N/A",
    help="Lag-1 autocorrelation used for effective sample size correction.",
)

# Significance badge — uses modified MK for consistency
sig = mmk.get("significant", False)
autocorr = mmk.get("lag1_autocorrelation", 0.0)
st.markdown(
    f"**Trend significance (autocorrelation-adjusted):** "
    f"{'✅ Statistically significant (p < 0.05)' if sig else '⚪ Not statistically significant'} "
    f"· Modified MK τ = {mmk.get('tau', float('nan')):.3f} "
    f"· Lag-1 autocorrelation = {autocorr:.3f} "
    f"· Effective N = {mmk.get('effective_n', '?')}"
)

# Also show naive MK for comparison
mk_basic = report.get("mann_kendall", {})
if not np.isnan(mk_basic.get("p_value", np.nan)):
    naive_sig = "significant" if mk_basic.get("significant", False) else "not significant"
    st.caption(
        f"⚠️ For comparison: naive Mann-Kendall (no autocorrection) "
        f"p = {mk_basic['p_value']:.4g} ({naive_sig}). "
        f"The autocorrelation correction {'reduces' if mmk['p_value'] > mk_basic['p_value'] else 'preserves'} "
        f"significance by accounting for serial dependence in the time series."
    )

# --- Trend chart ---
st.markdown("### Time Series + Trend Line")

trend_series = ols.get("trend_series", pd.Series(dtype=float))
series_clean = df.set_index("date")[selected_var].dropna()

fig_trend = go.Figure()

# Observed
fig_trend.add_trace(go.Scatter(
    x=series_clean.index,
    y=series_clean.values,
    mode="lines",
    name=f"{selected_var_label} (observed)",
    line=dict(color="#35C9D0", width=1.8),
    fill="tozeroy",
    fillcolor="rgba(53,201,208,0.07)",
))

# OLS trend
if not trend_series.empty:
    fig_trend.add_trace(go.Scatter(
        x=trend_series.index,
        y=trend_series.values,
        mode="lines",
        name="OLS trend",
        line=dict(color="#E9A34B", width=2, dash="dash"),
    ))

# Change points
cp_list = cp.get("change_points", [])
for cp_item in cp_list[:3]:
    idx = cp_item.get("index")
    direction_cp = cp_item.get("direction", "")
    if idx is not None:
        y_val = series_clean.get(idx, None)
        if y_val is not None:
            # Use add_shape + add_annotation separately to avoid
            # Plotly's annotation positioning bug with datetime axes
            fig_trend.add_vline(
                x=str(idx),
                line_dash="dot",
                line_color="#EF6461",
            )
            fig_trend.add_annotation(
                x=str(idx),
                yref="paper",
                y=1.0,
                text=f"⚡ {direction_cp}",
                showarrow=False,
                font=dict(color="#EF6461", size=11),
                textangle=-90,
                xanchor="left",
            )

fig_trend.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=420,
    hovermode="x unified",
    xaxis_title="Year",
    yaxis_title=f"{selected_var_label} ({selected_unit})",
    legend=dict(x=0.01, y=0.99),
)

st.plotly_chart(fig_trend, use_container_width=True)

# --- Seasonal climatology chart ---
st.markdown("### Monthly Seasonality (Climatological Mean)")
st.caption(
    "Average value for each calendar month across all years. "
    "Shows the typical seasonal cycle."
)

clim = report["climatology"]

fig_clim = go.Figure()
fig_clim.add_trace(go.Bar(
    x=clim["month_name"],
    y=clim["clim_mean"],
    error_y=dict(
        type="data",
        array=clim["clim_std"].fillna(0).tolist(),
        visible=True,
        color="#A0AEC0",
    ),
    marker_color="#35C9D0",
    name="Climatological Mean",
))
fig_clim.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=320,
    xaxis_title="Month",
    yaxis_title=f"{selected_unit}",
)
st.plotly_chart(fig_clim, use_container_width=True)

# --- Anomaly chart ---
st.markdown("### Deseasonalised Anomaly")
st.caption(
    "Observed value minus the climatological monthly mean. "
    "Positive = above normal, negative = below normal."
)

anom_df = report["anomalies"]
anom_df = anom_df.dropna(subset=["anomaly"])
anom_df["date"] = pd.to_datetime(anom_df["date"])

colors = anom_df["anomaly"].apply(
    lambda x: "#31C48D" if x > 0 else "#EF6461"
)

fig_anom = go.Figure()
fig_anom.add_trace(go.Bar(
    x=anom_df["date"],
    y=anom_df["anomaly"],
    marker_color=colors,
    name="Anomaly",
    hovertemplate="<b>%{x}</b><br>Anomaly: %{y:.4f}<extra></extra>",
))
fig_anom.add_hline(y=0, line_color="#A0AEC0", line_width=1)
fig_anom.update_layout(
    template="plotly_dark",
    paper_bgcolor="#080D18",
    plot_bgcolor="#111C2D",
    height=320,
    xaxis_title="Year",
    yaxis_title=f"Anomaly ({selected_unit})",
)
st.plotly_chart(fig_anom, use_container_width=True)

# Change points table
if cp_list:
    st.markdown("### Detected Change Points")
    st.caption(
        "CUSUM-detected structural shifts. "
        "Red = sudden increase in value, Blue = sudden decrease."
    )
    cp_rows = []
    for item in cp_list:
        cp_rows.append({
            "Date": str(item.get("index", "?"))[:7],
            "Direction": item.get("direction", "?"),
            "CUSUM Strength": f"{item.get('cusum_value', 0):.2f}",
        })
    st.dataframe(
        pd.DataFrame(cp_rows),
        use_container_width=True,
        hide_index=True,
    )

# AI explanation for trend
if st.button(
    f"🤖 Explain {selected_var_label} trend in simple terms",
    key="ai_step2",
):
    with st.spinner("AI is reading the trend results..."):
        try:
            explanation = explain_trend(
                selected_var_label,
                report,
                selected_unit,
            )
            ai_card(explanation)
        except Exception as e:
            st.error(f"AI unavailable: {e}")

st.divider()


# ============================================================
# STEP 3: UNCERTAINTY-GUIDED INTERACTION GRAPH
# ============================================================

st.markdown(
    '<div class="contribution-badge">UG-ESI CONTRIBUTION 3</div>',
    unsafe_allow_html=True,
)
st.markdown("## 🕸️ Step 3 — Uncertainty-Guided Interaction Graph")

st.markdown(
    "Builds a statistically-evaluated relationship network between the "
    "recommended variables. Each edge carries a **composite confidence indicator** based on "
    "effect size, FDR-corrected statistical certainty, data volume, and "
    "temporal stability across rolling time windows. Partial correlations "
    "control for confounding variables to detect potentially spurious edges."
)
st.caption(
    "⚠️ Graph edges indicate statistical association, not causal mechanisms. "
    "Lag N means variable X at month t is paired with variable Y at month t+N "
    "(testing whether X predicts Y N months later). "
    "Confidence is a composite indicator, not a calibrated probability."
)

lag_max = st.slider(
    "Maximum temporal lag to test (months)",
    min_value=0,
    max_value=6,
    value=3,
    help="Lag N tests whether variable X at month t predicts variable Y at month t+N.",
)

min_conf = st.slider(
    "Minimum edge confidence score",
    min_value=0.0,
    max_value=1.0,
    value=0.30,
    step=0.05,
    help="Filter out low-confidence relationships.",
)

@st.cache_data(show_spinner=False)
def run_graph(vars_tuple, lag_max_val, min_conf_val, data_hash):
    return build_interaction_graph(
        df,
        variables=list(vars_tuple),
        lag_range=range(0, lag_max_val + 1),
        min_confidence=min_conf_val,
    )

with st.spinner("Building uncertainty-guided interaction graph..."):
    graph_result = run_graph(
        tuple(recommended_vars),
        lag_max,
        min_conf,
        data_hash,
    )

edges = graph_result["edges"]
sig_edges = graph_result["significant_edges"]

# Graph metrics
g1, g2, g3, g4 = st.columns(4)
g1.metric("Relationships Tested", len(edges))
g2.metric("FDR Significant", int(edges["fdr_significant"].sum()) if not edges.empty else 0)
g3.metric("High-Confidence Edges", len(sig_edges))
g4.metric("Lags Tested", lag_max + 1)

if sig_edges.empty:
    st.warning(
        "No high-confidence relationships found with current settings. "
        "Try lowering the confidence threshold or increasing lag range."
    )
else:
    # --- Network visualisation ---
    st.markdown("### Interaction Network")
    st.caption(
        "Edge thickness = |correlation strength|. "
        "🟢 Green = positive. 🔴 Red = negative. "
        "Node size = number of connections."
    )

    import networkx as nx

    G = nx.Graph()

    for var in recommended_vars:
        meta = recommended_meta.get(var, {})
        G.add_node(var, label=meta.get("short", var))

    for _, row in sig_edges.iterrows():
        G.add_edge(
            row["variable_x"],
            row["variable_y"],
            rho=row["spearman_rho"],
            confidence=row["confidence_score"],
            lag=row["lag_months"],
            q=row["fdr_q_value"],
        )

    pos = nx.spring_layout(G, seed=42, k=1.2)

    edge_traces = []
    for src, tgt, attr in G.edges(data=True):
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        rho = attr["rho"]
        color = "#31C48D" if rho >= 0 else "#EF6461"
        width = 1.5 + abs(rho) * 6

        # Lag direction label
        lag_val = attr["lag"]
        if lag_val == 0:
            lag_text = "Lag: 0 (concurrent)"
        else:
            lag_text = f"Lag: {lag_val} month(s) ({src} → {tgt})"

        edge_traces.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(color=color, width=width),
            hoverinfo="text",
            text=[
                f"{src} ↔ {tgt}<br>"
                f"Correlation: {rho:.3f}<br>"
                f"Confidence: {attr['confidence']:.2f}<br>"
                f"{lag_text}<br>"
                f"q-value: {attr['q']:.4g}"
            ] * 3,
            showlegend=False,
        ))

    node_x, node_y, node_text, node_hover, node_size = [], [], [], [], []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        meta = recommended_meta.get(node, {})
        node_text.append(meta.get("short", node))
        node_hover.append(
            f"{meta.get('label', node)}<br>"
            f"Connections: {G.degree(node)}"
        )
        node_size.append(30 + G.degree(node) * 10)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        hovertext=node_hover,
        hoverinfo="text",
        marker=dict(
            size=node_size,
            color="#35C9D0",
            line=dict(width=2, color="#FFFFFF"),
        ),
        showlegend=False,
    )

    net_fig = go.Figure(data=edge_traces + [node_trace])
    net_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#080D18",
        plot_bgcolor="#111C2D",
        height=520,
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    st.plotly_chart(net_fig, use_container_width=True)
    st.markdown("🟢 Positive correlation  |  🔴 Negative correlation")

    # --- Edge table ---
    st.markdown("### All Significant Edges")
    display_cols = [
        "variable_x", "variable_y", "lag_months",
        "spearman_rho", "fdr_q_value",
        "confidence_score", "temporal_stability",
        "sample_size",
    ]
    # Include partial correlation if available
    if "partial_rho" in sig_edges.columns:
        display_cols += ["partial_rho", "partial_control_var"]
    if "spurious_flag" in sig_edges.columns:
        display_cols += ["spurious_flag"]

    display_edges = sig_edges[display_cols].sort_values("confidence_score", ascending=False)

    # Rename columns for display
    rename_map = {
        "variable_x": "Variable X",
        "variable_y": "Variable Y",
        "lag_months": "Lag (months)",
        "spearman_rho": "Correlation",
        "fdr_q_value": "FDR q-value",
        "confidence_score": "Confidence",
        "temporal_stability": "Temporal Stability",
        "sample_size": "N",
        "partial_rho": "Partial ρ",
        "partial_control_var": "Control Var",
        "spurious_flag": "Spurious?",
    }

    display_edges = display_edges.rename(columns=rename_map)

    st.dataframe(
        display_edges.round(4),
        use_container_width=True,
        hide_index=True,
    )

    # Note about partial correlation
    if "partial_rho" in sig_edges.columns:
        n_spurious = int(sig_edges["spurious_flag"].sum()) if "spurious_flag" in sig_edges.columns else 0
        if n_spurious > 0:
            st.warning(
                f"⚠️ {n_spurious} edge(s) show substantial correlation drop "
                f"after controlling for confounders — these may be partially "
                f"spurious (driven by a third variable rather than a direct link)."
            )
        st.caption(
            "Partial ρ = correlation after controlling for the strongest "
            "confounding variable. A large drop from the raw ρ suggests the "
            "relationship may be indirect. 'Spurious?' flags edges where "
            "partial ρ drops below 50% of raw ρ."
        )

    # AI explanation for graph
    if st.button("🤖 Explain this interaction graph", key="ai_step3"):
        with st.spinner("AI is reading the graph..."):
            try:
                explanation = explain_interaction_graph(
                    graph_summary=graph_result["graph_summary"],
                    variables_used=[
                        recommended_meta[v]["label"]
                        for v in recommended_vars
                        if v in recommended_meta
                    ],
                    lag_range=f"0–{lag_max} months",
                )
                ai_card(explanation)
            except Exception as e:
                st.error(f"AI unavailable: {e}")

st.divider()


# ============================================================
# STEP 4: EVIDENCE-GROUNDED RESEARCH REPORT
# ============================================================

st.markdown(
    '<div class="contribution-badge">UG-ESI CONTRIBUTION 4</div>',
    unsafe_allow_html=True,
)
st.markdown("## 📄 Step 4 — Evidence-Grounded Research Report")

st.markdown(
    "Generate a structured research report that synthesises all three previous "
    "steps. The AI is given only the actual statistical outputs — it explains "
    "findings, does not invent them."
)
st.caption(
    "Every claim in this report is traceable to the statistical results above."
)

if st.button(
    "🧠 GENERATE UG-ESI RESEARCH REPORT",
    use_container_width=True,
    key="ai_step4",
):
    with st.spinner(
        "Generating evidence-grounded report — "
        "synthesising variable selection, trends, and interaction results..."
    ):
        # Build trend summaries for all recommended vars using modified MK
        trend_summaries = []
        for var in recommended_vars:
            if var not in df.columns:
                continue
            meta = recommended_meta.get(var, {})
            tr = full_trend_report(
                df, "date", var, meta.get("label", var)
            )
            mmk_r = tr["modified_mann_kendall"]
            ss_r = tr["sens_slope"]
            trend_summaries.append(
                f"{meta.get('label', var)}: "
                f"direction={mmk_r.get('direction','?')}, "
                f"tau={mmk_r.get('tau',float('nan')):.3f}, "
                f"p={mmk_r.get('p_value',float('nan')):.4g} "
                f"(autocorrelation-adjusted), "
                f"lag1_autocorr={mmk_r.get('lag1_autocorrelation',float('nan')):.3f}, "
                f"annual change={tr.get('annualised_sens_slope',float('nan')):.4g} "
                f"{meta.get('unit','')}/yr"
            )

        selection_text = selection_summary_text(scores, selected_objective)
        graph_text = graph_result.get("graph_summary", "No interaction data.")

        # Coverage note
        coverage_cols = [
            v for v in [
                "lst_strict_coverage_pct",
                "ndvi_strict_coverage_pct",
                "smap_am_strict_coverage_pct",
                "gpm_monthly_precipitation_coverage_pct",
            ] if v in df.columns
        ]
        coverage_notes = ""
        if coverage_cols:
            for col in coverage_cols:
                mean_cov = df[col].mean()
                min_cov = df[col].min()
                coverage_notes += (
                    f"{col}: mean {mean_cov:.1f}%, "
                    f"min {min_cov:.1f}%. "
                )

        try:
            report_text = generate_research_report(
                objective=objective_labels[selected_objective],
                variable_selection_summary=selection_text,
                trend_summaries=trend_summaries,
                interaction_summary=graph_text,
                coverage_notes=coverage_notes,
            )
            ai_card(report_text)
        except Exception as e:
            st.error(f"AI report generation failed: {e}")


st.divider()

# -----------------------------------------
# FOOTER
# -----------------------------------------

footer()
