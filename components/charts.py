"""
Premium Chart Components for EARTHPULSE-X
==========================================
All Plotly charts use these helpers for consistent premium styling.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from scipy.stats import linregress, theilslopes

# ──────────────────────────────────────────────────────────────
# Premium Plotly Layout
# ──────────────────────────────────────────────────────────────

_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,26,46,0.6)",
    font=dict(family="Urbanist, sans-serif", size=12, color="#AAB8CC"),
    margin=dict(l=20, r=20, t=40, b=20),
    hoverlabel=dict(
        bgcolor="#0F1A2E",
        bordercolor="#2A3F5F",
        font=dict(family="Urbanist", size=12, color="#F1F5FC"),
    ),
    hovermode="x unified",
)

_AXES = dict(
    gridcolor="#1E2D4A",
    zerolinecolor="#1E2D4A",
    linecolor="#1E2D4A",
    tickfont=dict(size=11, color="#6B7B91"),
)

_LEGEND = dict(
    orientation="h",
    yanchor="bottom",
    y=-0.15,
    x=0.5,
    xanchor="center",
    font=dict(size=11, family="Urbanist"),
    bgcolor="rgba(0,0,0,0)",
)

# Premium color palette
COLORS = {
    "primary": "#35C9D0",
    "secondary": "#6C8EE6",
    "accent": "#E9A34B",
    "green": "#31C48D",
    "red": "#EF6461",
    "purple": "#A78BFA",
    "pink": "#F472B6",
    "gray": "#6B7B91",
    "fill": "rgba(53,201,208,0.08)",
}

VAR_COLORS = {
    "lst": "#EF6461",
    "ndvi": "#31C48D",
    "smap_am": "#6C8EE6",
    "smap_pm": "#A78BFA",
    "gpm": "#35C9D0",
}


def _apply_layout(fig: go.Figure, height=420, **kwargs) -> go.Figure:
    """Apply premium layout defaults to any figure."""
    layout = {**_LAYOUT, "height": height, **kwargs}
    fig.update_layout(**layout)
    fig.update_xaxes(**_AXES)
    fig.update_yaxes(**_AXES)
    return fig


# ──────────────────────────────────────────────────────────────
# 1. Trend Time Series + Trend Lines
# ──────────────────────────────────────────────────────────────

def trend_timeseries(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    label: str = "",
    unit: str = "",
    show_ols: bool = True,
    show_sens: bool = True,
    change_points: list = None,
    height: int = 460,
) -> go.Figure:
    """
    Premium time series with OLS + Sen's slope trend lines
    and optional change-point markers.
    """
    work = df[[date_col, value_col]].dropna().sort_values(date_col).reset_index(drop=True)
    values = work[value_col].astype(float).values
    t = np.arange(len(values))

    fig = go.Figure()

    # Observed values — area fill
    fig.add_trace(go.Scatter(
        x=work[date_col],
        y=values,
        mode="lines",
        name=f"{label} (observed)" if label else "Observed",
        line=dict(color=COLORS["primary"], width=1.8),
        fill="tozeroy",
        fillcolor=COLORS["fill"],
        hovertemplate=f"<b>%{{x|%Y-%m}}</b><br>{label}: %{{y:.3f}} {unit}<extra></extra>",
    ))

    # OLS trend
    if show_ols and len(values) >= 4:
        lr = linregress(t, values)
        ols_line = lr.intercept + lr.slope * t
        fig.add_trace(go.Scatter(
            x=work[date_col],
            y=ols_line,
            mode="lines",
            name=f"OLS (R²={lr.rvalue**2:.2f})",
            line=dict(color=COLORS["accent"], width=2.5, dash="dash"),
            hovertemplate=f"OLS: %{{y:.3f}} {unit}<extra></extra>",
        ))

    # Sen's slope
    if show_sens and len(values) >= 4:
        ts = theilslopes(values, t, alpha=0.95)
        sen_line = ts.intercept + ts.slope * t
        fig.add_trace(go.Scatter(
            x=work[date_col],
            y=sen_line,
            mode="lines",
            name="Sen's slope",
            line=dict(color=COLORS["purple"], width=2, dash="dot"),
            hovertemplate=f"Sen's: %{{y:.3f}} {unit}<extra></extra>",
        ))

    # Change points
    if change_points:
        for cp in change_points[:3]:
            idx = cp.get("index")
            direction = cp.get("direction", "")
            if idx is not None and idx in work[date_col].values:
                fig.add_vline(
                    x=str(idx),
                    line_dash="dot",
                    line_color=COLORS["red"],
                )
                fig.add_annotation(
                    x=str(idx),
                    yref="paper",
                    y=1.0,
                    text=f"⚡ {direction}",
                    showarrow=False,
                    font=dict(color=COLORS["red"], size=10, family="Urbanist"),
                    textangle=-90,
                    xanchor="left",
                )

    _apply_layout(fig, height=height)
    fig.update_layout(
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.2,
            x=0.5, xanchor="center",
            font=dict(size=11, family="Urbanist"),
            bgcolor="rgba(0,0,0,0)",
        ),
        yaxis_title=f"{label} ({unit})" if unit else label,
    )
    return fig


# ──────────────────────────────────────────────────────────────
# 2. Anomaly Bar Chart
# ──────────────────────────────────────────────────────────────

def anomaly_bars(
    df: pd.DataFrame,
    date_col: str,
    anomaly_col: str,
    label: str = "",
    unit: str = "",
    height: int = 340,
) -> go.Figure:
    """
    Deseasonalised anomaly bar chart.
    Green = above normal, Red = below normal.
    """
    work = df[[date_col, anomaly_col]].dropna()
    work = work.sort_values(date_col)

    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in work[anomaly_col]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=work[date_col],
        y=work[anomaly_col],
        marker_color=colors,
        name="Anomaly",
        hovertemplate=f"<b>%{{x|%Y-%m}}</b><br>Anomaly: %{{y:.3f}} {unit}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="#6B7B91", line_width=1, line_dash="solid")

    _apply_layout(fig, height=height)
    fig.update_layout(yaxis_title=f"Anomaly ({unit})" if unit else "Anomaly")
    return fig


# ──────────────────────────────────────────────────────────────
# 3. Seasonal Climatology Bar Chart
# ──────────────────────────────────────────────────────────────

def seasonal_bars(
    clim_df: pd.DataFrame,
    label: str = "",
    unit: str = "",
    height: int = 320,
) -> go.Figure:
    """
    Monthly climatology with error bars.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=clim_df["month_name"],
        y=clim_df["clim_mean"],
        error_y=dict(
            type="data",
            array=clim_df["clim_std"].fillna(0).tolist(),
            visible=True,
            color="#6B7B91",
            thickness=1,
        ),
        marker_color=COLORS["primary"],
        marker_line_width=0,
        name="Climatological Mean",
        hovertemplate=f"<b>%{{x}}</b><br>Mean: %{{y:.3f}} {unit}<br>±%{{error_y.array:.3f}}<extra></extra>",
    ))

    _apply_layout(fig, height=height)
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title=f"{label} ({unit})" if unit else label,
    )
    return fig


# ──────────────────────────────────────────────────────────────
# 4. Multi-Variable Overview (Faceted)
# ──────────────────────────────────────────────────────────────

def multi_variable_overview(
    df: pd.DataFrame,
    date_col: str,
    variables: dict,
    height: int = 760,
) -> go.Figure:
    """
    Faceted multi-variable time series.
    variables = {column_name: display_label}
    """
    plot_df = df[[date_col] + list(variables.keys())].melt(
        id_vars=date_col,
        var_name="Variable",
        value_name="Value",
    )
    plot_df["Variable"] = plot_df["Variable"].map(variables)

    fig = px.line(
        plot_df,
        x=date_col,
        y="Value",
        color="Variable",
        facet_row="Variable",
        height=height,
    )

    fig.update_traces(line=dict(width=1.5))
    fig.for_each_trace(lambda t: t.update(
        line=dict(color={
            "LST": COLORS["red"],
            "NDVI": COLORS["green"],
            "Soil Moisture": COLORS["secondary"],
            "Precipitation": COLORS["primary"],
        }.get(t.name, COLORS["gray"]))
    ))

    _apply_layout(fig, height=height)
    fig.update_yaxes(matches=None, showticklabels=True)
    fig.update_layout(showlegend=False)
    fig.for_each_annotation(lambda a: a.update(
        text=f"<b>{a.text.split('=')[-1]}</b>",
        font=dict(size=12, family="Urbanist", color="#AAB8CC"),
    ))
    return fig


# ──────────────────────────────────────────────────────────────
# 5. Coverage Chart
# ──────────────────────────────────────────────────────────────

def coverage_chart(
    df: pd.DataFrame,
    date_col: str,
    coverage_cols: dict,
    height: int = 400,
) -> go.Figure:
    """
    Multi-line coverage chart.
    coverage_cols = {display_name: column_name}
    """
    fig = go.Figure()

    palette = [COLORS["red"], COLORS["green"], COLORS["secondary"],
               COLORS["purple"], COLORS["primary"]]

    for i, (name, col) in enumerate(coverage_cols.items()):
        fig.add_trace(go.Scatter(
            x=df[date_col],
            y=df[col],
            mode="lines",
            name=name,
            line=dict(color=palette[i % len(palette)], width=1.8),
            hovertemplate=f"<b>%{{x|%Y-%m}}</b><br>{name}: %{{y:.1f}}%<extra></extra>",
        ))

    _apply_layout(fig, height=height)
    fig.update_layout(
        yaxis_title="Valid Coverage (%)",
        yaxis=dict(range=[0, 105]),
        legend=_LEGEND,
    )
    return fig


# ──────────────────────────────────────────────────────────────
# 6. Annual Mean Bar Chart
# ──────────────────────────────────────────────────────────────

def annual_bars(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    label: str = "",
    unit: str = "",
    height: int = 340,
) -> go.Figure:
    """
    Annual mean with color by direction vs first year.
    """
    work = df[[date_col, value_col]].dropna().copy()
    work["year"] = pd.to_datetime(work[date_col]).dt.year
    annual = work.groupby("year")[value_col].mean().reset_index()
    annual.columns = ["Year", "Mean"]

    base = annual["Mean"].iloc[0]
    colors = [COLORS["green"] if v >= base else COLORS["red"] for v in annual["Mean"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=annual["Year"],
        y=annual["Mean"],
        marker_color=colors,
        marker_line_width=0,
        name="Annual Mean",
        hovertemplate=f"<b>%{{x}}</b><br>{label}: %{{y:.3f}} {unit}<extra></extra>",
    ))

    fig.add_hline(
        y=base,
        line_color="#6B7B91",
        line_width=1,
        line_dash="dash",
        annotation_text=f"2015 baseline ({base:.3f})",
        annotation_font_color="#6B7B91",
        annotation_font_size=10,
        annotation_font_family="Urbanist",
    )

    _apply_layout(fig, height=height)
    fig.update_layout(yaxis_title=unit if unit else label)
    return fig


# ──────────────────────────────────────────────────────────────
# 7. Correlation Heatmap
# ──────────────────────────────────────────────────────────────

def correlation_heatmap(
    matrix: pd.DataFrame,
    height: int = 460,
) -> go.Figure:
    """Premium correlation matrix heatmap."""
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=matrix.columns,
        y=matrix.index,
        zmin=-1,
        zmax=1,
        colorscale="RdBu_r",
        colorbar=dict(
            title=dict(text="Spearman ρ", font=dict(size=13)),
            thickness=12,
            len=0.7,
        ),
        text=np.round(matrix.values, 3),
        texttemplate="%{text}",
        textfont=dict(size=11, family="Urbanist"),
        hovertemplate="%{y} ↔ %{x}<br>Correlation: %{z:.3f}<extra></extra>",
    ))

    _apply_layout(fig, height=height)
    return fig


# ──────────────────────────────────────────────────────────────
# 8. Network Graph
# ──────────────────────────────────────────────────────────────

def network_graph(
    G,
    pos,
    node_labels: dict,
    height: int = 540,
) -> go.Figure:
    """
    Premium network visualization.
    G: networkx Graph
    pos: layout positions
    node_labels: {node_id: display_label}
    """
    fig = go.Figure()

    # Edge traces
    for src, tgt, attr in G.edges(data=True):
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        rho = attr.get("rho", attr.get("spearman_rho", 0))
        color = COLORS["green"] if rho >= 0 else COLORS["red"]
        width = 1.5 + abs(rho) * 6

        fig.add_trace(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(color=color, width=width),
            hoverinfo="text",
            text=(
                f"{node_labels.get(src, src)} ↔ {node_labels.get(tgt, tgt)}<br>"
                f"Correlation: {rho:.3f}<br>"
                f"Confidence: {attr.get('confidence_score', attr.get('confidence', 0)):.2f}<br>"
                f"Lag: {attr.get('lag_months', attr.get('lag', 0))} month(s)<br>"
                f"q-value: {attr.get('fdr_q_value', attr.get('q', 0)):.4g}"
            ) * 3,
            showlegend=False,
        ))

    # Node traces
    node_x, node_y, node_text, node_hover, node_size = [], [], [], [], []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node_labels.get(node, node))
        deg = G.degree(node)
        node_hover.append(
            f"{node_labels.get(node, node)}<br>Connections: {deg}"
        )
        node_size.append(28 + deg * 12)

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont=dict(size=12, family="Urbanist", color="#F1F5FC"),
        hovertext=node_hover,
        hoverinfo="text",
        marker=dict(
            size=node_size,
            color=COLORS["primary"],
            line=dict(width=2, color="rgba(241,245,252,0.8)"),
        ),
        showlegend=False,
    ))

    _apply_layout(fig, height=height)
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=30, b=20),
    )
    return fig


# ──────────────────────────────────────────────────────────────
# 9. Anomaly Heatmap (time × variable)
# ──────────────────────────────────────────────────────────────

def anomaly_heatmap(
    matrix: pd.DataFrame,
    x_labels: list,
    y_labels: list,
    height: int = 380,
) -> go.Figure:
    """
    Monthly anomaly heatmap: rows = variables, cols = months.
    """
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values.T,
        x=[str(x) for x in x_labels],
        y=y_labels,
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(
            title=dict(text="Normalised Anomaly (σ)", font=dict(size=12)),
            thickness=10,
            len=0.7,
        ),
        hovertemplate="Month: %{x}<br>Variable: %{y}<br>Anomaly: %{z:.2f}σ<extra></extra>",
    ))

    _apply_layout(fig, height=height)
    fig.update_layout(
        xaxis=dict(tickangle=45, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=12)),
        margin=dict(l=10, r=10, t=30, b=60),
    )
    return fig
