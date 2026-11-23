"""
UG-ESI Contribution 3: Uncertainty-Guided Interaction Graph Engine
==================================================================
Builds a statistically-evaluated interaction graph between
environmental variables with:
  - Spearman rank correlation (lag 0 to lag_max)
    Lag direction: x(t) paired with y(t+lag) — tests whether
    variable X predicts variable Y `lag` months later.
  - False Discovery Rate (Benjamini-Hochberg) correction
  - Composite confidence indicator (NOT a calibrated probability)
    based on effect size, q-value, sample size, and temporal stability
  - Lag-aware temporal stability check (rolling window consistency
    using the same lag alignment as the edge being evaluated)
  - Partial correlation (controls for confounding variables;
    integrated into the graph builder to detect spurious edges)
"""

import numpy as np
import pandas as pd
from scipy import stats
from itertools import combinations


# -----------------------------------------
# 1. Pairwise Spearman Correlation
# -----------------------------------------

def spearman_pairs(
    df: pd.DataFrame,
    variables: list,
    lag: int = 0,
) -> pd.DataFrame:
    """
    Compute Spearman correlations for all variable pairs
    at a given temporal lag.

    Returns DataFrame with columns:
      variable_x, variable_y, lag, spearman_rho, p_value, n
    """
    rows = []
    n_total = len(df)

    for var_x, var_y in combinations(variables, 2):
        if var_x not in df.columns or var_y not in df.columns:
            continue

        if lag == 0:
            pair = df[[var_x, var_y]].dropna()
            x_vals = pair[var_x].values
            y_vals = pair[var_y].values
        else:
            # Lag alignment: x(t) paired with y(t+lag)
            # This tests whether var_x at time t predicts var_y
            # `lag` months later.
            # e.g. rainfall (var_x) at month t → soil moisture (var_y)
            # at month t+lag.
            x_series = df[var_x].iloc[:-lag].reset_index(drop=True)
            y_series = df[var_y].iloc[lag:].reset_index(drop=True)
            combined = pd.DataFrame({
                "x": x_series,
                "y": y_series,
            }).dropna()
            x_vals = combined["x"].values
            y_vals = combined["y"].values

        n = len(x_vals)

        if n < 6:
            continue

        rho, p_value = stats.spearmanr(x_vals, y_vals)

        rows.append({
            "variable_x": var_x,
            "variable_y": var_y,
            "lag_months": lag,
            "spearman_rho": round(float(rho), 6),
            "p_value": round(float(p_value), 8),
            "sample_size": n,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# -----------------------------------------
# 2. Benjamini-Hochberg FDR Correction
# -----------------------------------------

def apply_fdr(
    results: pd.DataFrame,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """
    Apply Benjamini-Hochberg False Discovery Rate correction
    to a column of p-values in a results DataFrame.
    Adds columns: fdr_q_value, fdr_significant.
    """
    if results.empty or "p_value" not in results.columns:
        return results

    df = results.copy()
    n = len(df)

    # Sort by p-value
    order = df["p_value"].argsort()
    ranked = np.arange(1, n + 1)
    sorted_p = df["p_value"].values[order]

    # BH threshold
    thresholds = (ranked / n) * alpha
    below = sorted_p <= thresholds
    if below.any():
        max_k = np.max(np.where(below))
        bh_threshold = thresholds[max_k]
    else:
        bh_threshold = 0.0

    # Q-values (Simes estimate)
    q_values = np.zeros(n)
    q_values[order] = sorted_p * n / ranked

    # Clip to [0, 1]
    q_values = np.minimum.accumulate(
        q_values[order][::-1]
    )[::-1][np.argsort(order)]
    q_values = np.clip(q_values, 0, 1)

    df["fdr_q_value"] = np.round(q_values, 8)
    df["fdr_significant"] = df["p_value"] <= bh_threshold

    return df


# -----------------------------------------
# 3. Edge Confidence Score
# -----------------------------------------

def edge_confidence(
    rho: float,
    q_value: float,
    sample_size: int,
    window_stability: float = 1.0,
) -> float:
    """
    Composite confidence indicator for a graph edge [0, 1].

    NOTE: This is a weighted composite indicator, NOT a calibrated
    statistical probability. It combines four factors:
      - |rho|: strength of association
      - 1 - q_value: statistical certainty (FDR-corrected)
      - min(sample_size / 100, 1): data volume
      - window_stability: consistency over time windows

    Higher score = more reliable edge. Interpret as a relative
    ranking metric, not as the probability that the edge is true.
    """
    strength = min(abs(rho), 1.0)
    certainty = max(0.0, 1.0 - q_value)
    volume = min(sample_size / 100.0, 1.0)

    score = (
        0.35 * strength
        + 0.35 * certainty
        + 0.15 * volume
        + 0.15 * window_stability
    )

    return round(float(score), 4)


# -----------------------------------------
# 4. Rolling-Window Temporal Stability
# -----------------------------------------

def temporal_stability(
    df: pd.DataFrame,
    var_x: str,
    var_y: str,
    window: int = 24,
    lag: int = 0,
) -> float:
    """
    Measure how stable the Spearman correlation between
    two variables is across rolling time windows.

    When lag > 0, applies the same lag alignment as
    spearman_pairs: x(t) paired with y(t+lag). This ensures
    the stability score reflects the actual lagged relationship,
    not a lag-0 relationship.

    Returns stability score in [0, 1]:
      1.0 = correlation consistent across all windows
      0.0 = highly variable / unreliable
    """
    if var_x not in df.columns or var_y not in df.columns:
        return 0.5

    if lag == 0:
        pair = df[[var_x, var_y]].dropna().reset_index(drop=True)
        x_col = var_x
        y_col = var_y
    else:
        # Apply lag alignment: x(t) with y(t+lag)
        x_series = df[var_x].iloc[:-lag].reset_index(drop=True)
        y_series = df[var_y].iloc[lag:].reset_index(drop=True)
        pair = pd.DataFrame({
            "x": x_series,
            "y": y_series,
        }).dropna().reset_index(drop=True)
        x_col = "x"
        y_col = "y"

    n = len(pair)

    if n < window + 4:
        return 0.5  # Insufficient data; neutral score

    window_rhos = []
    step = max(1, window // 4)

    for start in range(0, n - window + 1, step):
        chunk = pair.iloc[start : start + window]
        if len(chunk) < 6:
            continue
        rho, _ = stats.spearmanr(
            chunk[x_col].values,
            chunk[y_col].values,
        )
        if not np.isnan(rho):
            window_rhos.append(rho)

    if len(window_rhos) < 2:
        return 0.5

    # Stability = 1 - coefficient of variation of rho
    rho_array = np.array(window_rhos)
    cv = np.std(rho_array) / (np.abs(np.mean(rho_array)) + 1e-6)
    stability = max(0.0, min(1.0, 1.0 - cv))

    return round(stability, 4)


# -----------------------------------------
# 5. Partial Correlation
# -----------------------------------------

def partial_correlation(
    df: pd.DataFrame,
    var_x: str,
    var_y: str,
    control_var: str,
) -> dict:
    """
    Compute the Spearman partial correlation between
    var_x and var_y after controlling for control_var.

    Uses residuals from rank-based linear regression.
    """
    cols = [var_x, var_y, control_var]
    work = df[cols].dropna()

    if len(work) < 8:
        return {
            "partial_rho": np.nan,
            "p_value": np.nan,
            "n": len(work),
        }

    # Convert to ranks
    rx = stats.rankdata(work[var_x].values)
    ry = stats.rankdata(work[var_y].values)
    rc = stats.rankdata(work[control_var].values)

    # Residuals of rx ~ rc and ry ~ rc
    _, res_x, _, _ = np.linalg.lstsq(
        np.column_stack([np.ones(len(rc)), rc]),
        rx,
        rcond=None,
    )
    _, res_y, _, _ = np.linalg.lstsq(
        np.column_stack([np.ones(len(rc)), rc]),
        ry,
        rcond=None,
    )

    # Predicted values (residuals = actual - predicted)
    pred_x = (
        np.column_stack([np.ones(len(rc)), rc])
        @ np.linalg.lstsq(
            np.column_stack([np.ones(len(rc)), rc]),
            rx,
            rcond=None,
        )[0]
    )
    pred_y = (
        np.column_stack([np.ones(len(rc)), rc])
        @ np.linalg.lstsq(
            np.column_stack([np.ones(len(rc)), rc]),
            ry,
            rcond=None,
        )[0]
    )

    resid_x = rx - pred_x
    resid_y = ry - pred_y

    partial_rho, p_val = stats.pearsonr(resid_x, resid_y)

    return {
        "partial_rho": round(float(partial_rho), 6),
        "p_value": round(float(p_val), 8),
        "control_variable": control_var,
        "n": len(work),
    }


# -----------------------------------------
# 6. Full Uncertainty-Guided Graph Builder
# -----------------------------------------

def build_interaction_graph(
    df: pd.DataFrame,
    variables: list,
    lag_range: range = range(0, 4),
    fdr_alpha: float = 0.05,
    min_confidence: float = 0.30,
) -> dict:
    """
    Build the full uncertainty-guided interaction graph.

    Returns a dict with:
      - edges: DataFrame of all evaluated edges with
               rho, q_value, confidence, stability, lag
      - significant_edges: filtered to FDR-significant only
      - graph_summary: text summary for AI context
    """
    all_rows = []

    for lag in lag_range:
        pairs = spearman_pairs(df, variables, lag=lag)
        if pairs.empty:
            continue
        all_rows.append(pairs)

    if not all_rows:
        return {
            "edges": pd.DataFrame(),
            "significant_edges": pd.DataFrame(),
            "graph_summary": "No interaction data available.",
        }

    edges = pd.concat(all_rows, ignore_index=True)
    edges = apply_fdr(edges, alpha=fdr_alpha)

    # Add temporal stability and confidence for each edge
    stabilities = []
    confidences = []
    partial_rho_values = []

    # Identify control variable candidates (all variables not in this edge)
    control_candidates = [
        v for v in variables
        if v in df.columns
    ]

    for _, row in edges.iterrows():
        lag_val = int(row["lag_months"])
        stab = temporal_stability(
            df, row["variable_x"], row["variable_y"],
            lag=lag_val,
        )
        conf = edge_confidence(
            rho=row["spearman_rho"],
            q_value=row.get("fdr_q_value", 1.0),
            sample_size=row["sample_size"],
            window_stability=stab,
        )
        stabilities.append(stab)
        confidences.append(conf)

        # Compute partial correlation against the strongest
        # third variable to detect spurious associations
        edge_vars = {row["variable_x"], row["variable_y"]}
        controls = [v for v in control_candidates if v not in edge_vars]
        best_partial = {"partial_rho": np.nan, "control_variable": None, "p_value": np.nan}

        if controls and len(df) >= 8:
            # Test against the control variable with highest
            # correlation to either endpoint
            best_control = None
            best_corr = 0.0
            for ctrl in controls:
                for endpoint in [row["variable_x"], row["variable_y"]]:
                    pair = df[[endpoint, ctrl]].dropna()
                    if len(pair) > 5:
                        r, _ = stats.pearsonr(
                            pair[endpoint], pair[ctrl]
                        )
                        if abs(r) > best_corr:
                            best_corr = abs(r)
                            best_control = ctrl

            if best_control and best_corr > 0.3:
                pc = partial_correlation(
                    df, row["variable_x"], row["variable_y"],
                    best_control,
                )
                if not np.isnan(pc["partial_rho"]):
                    best_partial = pc

        partial_rho_values.append(best_partial)

    edges["temporal_stability"] = stabilities
    edges["confidence_score"] = confidences
    edges["partial_rho"] = [p.get("partial_rho", np.nan) for p in partial_rho_values]
    edges["partial_control_var"] = [p.get("control_variable", "") for p in partial_rho_values]
    edges["partial_p_value"] = [p.get("p_value", np.nan) for p in partial_rho_values]

    # Flag edges where partial correlation drops substantially
    # (suggesting the association is largely explained by a confounder)
    edges["spurious_flag"] = edges.apply(
        lambda r: (
            not np.isnan(r["partial_rho"])
            and abs(r["spearman_rho"]) > 0.3
            and abs(r["partial_rho"]) < abs(r["spearman_rho"]) * 0.5
        ),
        axis=1,
    )

    # Filter by minimum confidence
    significant_edges = edges[
        edges["fdr_significant"] & (edges["confidence_score"] >= min_confidence)
    ].copy()

    # Build text summary
    graph_summary = _build_graph_summary(edges, significant_edges)

    return {
        "edges": edges,
        "significant_edges": significant_edges,
        "graph_summary": graph_summary,
    }


# -----------------------------------------
# Internal: graph summary for AI context
# -----------------------------------------

def _build_graph_summary(
    all_edges: pd.DataFrame,
    sig_edges: pd.DataFrame,
) -> str:
    lines = [
        f"Total evaluated relationships: {len(all_edges)}",
        f"FDR-significant relationships: {len(sig_edges)}",
        "",
    ]

    if sig_edges.empty:
        lines.append("No significant relationships found.")
        return "\n".join(lines)

    # Top 5 by |rho|
    top = sig_edges.nlargest(5, "spearman_rho", keep="all")
    top = top.reindex(
        top["spearman_rho"].abs().sort_values(ascending=False).index
    ).head(5)

    lines.append("Strongest significant relationships:")
    for _, row in top.iterrows():
        direction = "positively" if row["spearman_rho"] > 0 else "negatively"
        partial_info = ""
        if "partial_rho" in row.index and not pd.isna(row.get("partial_rho", np.nan)):
            partial_info = (
                f", partial_rho={row['partial_rho']:.2f}"
                f" (controlling for {row.get('partial_control_var', '?')})"
            )
        lines.append(
            f"  - {row['variable_x']} ↔ {row['variable_y']} "
            f"({direction} correlated, "
            f"strength {abs(row['spearman_rho']):.2f}, "
            f"lag {row['lag_months']} months, "
            f"confidence {row['confidence_score']:.2f}, "
            f"q={row['fdr_q_value']:.4g}"
            f"{partial_info})"
        )

    # Note spurious flags
    if "spurious_flag" in sig_edges.columns and sig_edges["spurious_flag"].any():
        spurious = sig_edges[sig_edges["spurious_flag"]]
        lines.append("")
        lines.append(
            f"⚠️ {len(spurious)} relationship(s) show substantial drop "
            f"after controlling for confounders — may be partially spurious."
        )

    return "\n".join(lines)
