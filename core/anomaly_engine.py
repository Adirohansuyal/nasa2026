"""
UG-ESI Contribution 1: Adaptive Variable Selection Engine
==========================================================
Ranks environmental variables by signal quality for a
given region and time window, based on:
  - Data completeness (valid coverage %)
  - Temporal variability (coefficient of variation or robust proxy)
  - Trend strength (Mann-Kendall |tau|)
  - Complementary information (pairwise correlation penalty)
  - Relevance scoring by scientific objective

Two-pass greedy forward selection:
  Pass 1: Score all candidates without redundancy penalty.
  Pass 2: Re-score greedily, applying redundancy penalty against
          already-confirmed top-ranked variables only. This avoids
          order-dependent bias from registry iteration order.

Scientific notes:
  - Variability is measured via CV, which is unit-dependent and NOT
    directly comparable across variable types (K vs mm vs m³/m³).
    It is used only as one component of a composite rank.
  - High variability is not automatically "useful signal" — it can
    also represent noise. Trend strength (MK |tau|) provides a
    complementary signal-quality measure.
  - Variables are NOT selected based on significance p-values
    (that would introduce selection bias). They are ranked by data
    quality and signal properties only.
"""

import numpy as np
import pandas as pd
from scipy import stats


# -----------------------------------------
# Variable metadata registry
# -----------------------------------------

VARIABLE_REGISTRY = {
    "lst_strict_mean": {
        "label": "Land Surface Temperature",
        "short": "LST",
        "unit": "K",
        "coverage_col": "lst_strict_coverage_pct",
        "category": "temperature",
        "emoji": "🌡️",
    },
    "ndvi_strict_mean": {
        "label": "Vegetation Greenness (NDVI)",
        "short": "NDVI",
        "unit": "index",
        "coverage_col": "ndvi_strict_coverage_pct",
        "category": "vegetation",
        "emoji": "🌿",
    },
    "smap_am_strict_mean": {
        "label": "Morning Soil Moisture",
        "short": "SMAP AM",
        "unit": "m³/m³",
        "coverage_col": "smap_am_strict_coverage_pct",
        "category": "soil_moisture",
        "emoji": "💧",
    },
    "smap_pm_strict_mean": {
        "label": "Evening Soil Moisture",
        "short": "SMAP PM",
        "unit": "m³/m³",
        "coverage_col": "smap_pm_strict_coverage_pct",
        "category": "soil_moisture",
        "emoji": "💧",
    },
    "gpm_monthly_precipitation_mean": {
        "label": "Precipitation",
        "short": "GPM",
        "unit": "mm",
        "coverage_col": "gpm_monthly_precipitation_coverage_pct",
        "category": "precipitation",
        "emoji": "🌧️",
    },
}

# Scientific objectives → preferred variable categories
OBJECTIVE_WEIGHTS = {
    "drought": {
        "precipitation": 1.0,
        "soil_moisture": 1.0,
        "temperature": 0.8,
        "vegetation": 0.7,
    },
    "flood": {
        "precipitation": 1.0,
        "soil_moisture": 0.9,
        "vegetation": 0.5,
        "temperature": 0.4,
    },
    "vegetation_change": {
        "vegetation": 1.0,
        "precipitation": 0.8,
        "temperature": 0.7,
        "soil_moisture": 0.8,
    },
    "temperature_trend": {
        "temperature": 1.0,
        "vegetation": 0.6,
        "precipitation": 0.5,
        "soil_moisture": 0.4,
    },
    "general": {
        "temperature": 0.8,
        "vegetation": 0.8,
        "precipitation": 0.8,
        "soil_moisture": 0.7,
    },
}


# -----------------------------------------
# Scoring functions
# -----------------------------------------

def _coverage_score(df: pd.DataFrame, var_key: str) -> float:
    """Mean coverage % normalised to [0, 1]."""
    meta = VARIABLE_REGISTRY.get(var_key, {})
    cov_col = meta.get("coverage_col")

    if cov_col and cov_col in df.columns:
        return float(df[cov_col].mean()) / 100.0

    # Fallback: count non-NaN in value column
    if var_key in df.columns:
        return float(df[var_key].notna().mean())

    return 0.0


def _variability_score(df: pd.DataFrame, var_key: str) -> float:
    """
    Signal-quality variability score in [0, 1].

    Uses the Coefficient of Variation (CV) only if the variable is
    physically meaningful with a non-zero baseline. For variables
    near zero (e.g. anomalies) or with negative means (not applicable
    here), falls back to a normalised standard deviation proxy.

    Important limitation: CV is unit-dependent. Variables in
    different units (K vs mm vs m³/m³) have inherently different
    baseline magnitudes, so CV values are not directly comparable
    across variable types. This score is used only as one component
    of a composite rank, not interpreted in isolation.

    Higher = more temporal spread relative to baseline
    (but may include noise — not all variability is useful signal).
    """
    if var_key not in df.columns:
        return 0.0

    series = df[var_key].dropna()

    if len(series) < 4:
        return 0.0

    mean_val = series.mean()
    std_val = series.std()

    if std_val == 0:
        return 0.0

    if abs(mean_val) > 1e-6:
        # Coefficient of variation (relative variability)
        cv = std_val / abs(mean_val)
    else:
        # Fallback: normalised std against a robust reference range
        iqr = series.quantile(0.75) - series.quantile(0.25)
        if iqr > 0:
            cv = std_val / iqr
        else:
            cv = 0.0

    return float(min(cv, 1.0))


def _trend_strength_score(df: pd.DataFrame, var_key: str) -> float:
    """
    Absolute Mann-Kendall tau as a proxy for trend signal.
    This is NOT used to select variables based on p-value.
    """
    if var_key not in df.columns:
        return 0.0

    series = df[var_key].dropna().values
    n = len(series)

    if n < 6:
        return 0.0

    # Fast MK tau computation
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = series[j] - series[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    tau = abs(s) / (0.5 * n * (n - 1))
    return float(tau)


def _redundancy_penalty(
    df: pd.DataFrame,
    var_key: str,
    already_selected: list,
) -> float:
    """
    Correlation-based redundancy penalty [0, 1].
    Returns average |correlation| with already-selected vars.
    High penalty = variable adds little new information.
    """
    if not already_selected or var_key not in df.columns:
        return 0.0

    corrs = []
    for sel in already_selected:
        if sel in df.columns:
            pair = df[[var_key, sel]].dropna()
            if len(pair) > 4:
                r, _ = stats.pearsonr(pair[var_key], pair[sel])
                corrs.append(abs(r))

    return float(np.mean(corrs)) if corrs else 0.0


# -----------------------------------------
# Main adaptive selection function
# -----------------------------------------

def adaptive_variable_selection(
    df: pd.DataFrame,
    objective: str = "general",
    top_n: int = 4,
) -> list:
    """
    Score and rank available environmental variables.

    Uses a two-pass approach to avoid order-dependent redundancy:
      Pass 1: Score all variables without redundancy penalty.
      Pass 2: Re-score with redundancy penalty applied against
              already-confirmed top-ranked variables (greedy forward
              selection), ensuring the penalty reflects genuine
              overlap with confirmed selections — not iteration order.

    Parameters
    ----------
    df : DataFrame with regional timeseries columns
    objective : scientific objective key
    top_n : number of variables to return

    Returns
    -------
    List of dicts sorted by composite score (descending),
    each with variable key, scores, label, and rationale.
    """
    weights = OBJECTIVE_WEIGHTS.get(
        objective,
        OBJECTIVE_WEIGHTS["general"],
    )

    candidates = [k for k in VARIABLE_REGISTRY if k in df.columns]

    # --- Pass 1: Score all candidates without redundancy ---
    pass1_scores = []
    for var_key in candidates:
        meta = VARIABLE_REGISTRY[var_key]
        category = meta["category"]

        cov = _coverage_score(df, var_key)
        var = _variability_score(df, var_key)
        trend = _trend_strength_score(df, var_key)
        obj_weight = weights.get(category, 0.5)

        # Composite without redundancy (base score)
        base_score = (
            0.30 * cov
            + 0.25 * var
            + 0.20 * trend
            + 0.25 * obj_weight
        )

        pass1_scores.append({
            "variable": var_key,
            "meta": meta,
            "coverage_score": cov,
            "variability_score": var,
            "trend_strength": trend,
            "objective_weight": obj_weight,
            "base_score": base_score,
        })

    # Sort by base score for Pass 2
    pass1_scores.sort(key=lambda x: x["base_score"], reverse=True)

    # --- Pass 2: Apply redundancy penalty greedily ---
    selected_so_far = []
    final_scores = []

    for item in pass1_scores:
        var_key = item["variable"]
        meta = item["meta"]

        redundancy = _redundancy_penalty(
            df, var_key, selected_so_far
        )

        # Composite score with redundancy penalty
        composite = (
            item["base_score"] - 0.15 * redundancy
        )

        # Determine signal quality label
        if composite >= 0.65:
            quality = "High signal"
        elif composite >= 0.45:
            quality = "Moderate signal"
        else:
            quality = "Low signal"

        # Rationale sentence
        rationale_parts = []
        if item["coverage_score"] >= 0.85:
            rationale_parts.append(
                f"good data coverage ({item['coverage_score']*100:.0f}%)"
            )
        elif item["coverage_score"] < 0.60:
            rationale_parts.append(
                f"limited coverage ({item['coverage_score']*100:.0f}%)"
            )
        if item["variability_score"] >= 0.3:
            rationale_parts.append("high temporal variability")
        if item["trend_strength"] >= 0.3:
            rationale_parts.append("detectable monotonic trend")
        if redundancy >= 0.7:
            rationale_parts.append(
                "highly correlated with another selected variable"
            )

        rationale = (
            "; ".join(rationale_parts)
            if rationale_parts
            else "moderate overall signal"
        )

        final_scores.append({
            "variable": var_key,
            "label": meta["label"],
            "short": meta["short"],
            "unit": meta["unit"],
            "emoji": meta["emoji"],
            "category": meta["category"],
            "composite_score": round(composite, 4),
            "coverage_score": round(item["coverage_score"], 4),
            "variability_score": round(item["variability_score"], 4),
            "trend_strength": round(item["trend_strength"], 4),
            "objective_weight": round(item["objective_weight"], 4),
            "redundancy_penalty": round(redundancy, 4),
            "quality_label": quality,
            "rationale": rationale,
        })

        selected_so_far.append(var_key)

    # Sort by final composite score
    scores = sorted(
        final_scores, key=lambda x: x["composite_score"], reverse=True
    )

    # Mark top-N as recommended
    for i, item in enumerate(scores):
        item["recommended"] = i < top_n

    return scores


# -----------------------------------------
# Quick summary string for AI context
# -----------------------------------------

def selection_summary_text(
    scores: list,
    objective: str,
) -> str:
    """
    Build a short text summary of variable selection results
    for use in AI prompts.
    """
    top = [s for s in scores if s["recommended"]]
    rest = [s for s in scores if not s["recommended"]]

    lines = [
        f"Adaptive variable selection for objective: {objective}",
        "",
        "Recommended variables (top-ranked):",
    ]
    for v in top:
        lines.append(
            f"  - {v['label']} ({v['short']}): "
            f"score {v['composite_score']:.2f}, "
            f"{v['quality_label']}, {v['rationale']}"
        )

    if rest:
        lines.append("")
        lines.append("Lower-ranked variables:")
        for v in rest:
            lines.append(
                f"  - {v['label']}: "
                f"score {v['composite_score']:.2f}, "
                f"{v['rationale']}"
            )

    return "\n".join(lines)
