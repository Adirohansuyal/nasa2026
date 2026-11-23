"""
UG-ESI Contribution 2: Multi-Scale Trend Intelligence Engine
============================================================
Implements statistical trend detection methods:
  - Ordinary Least Squares (OLS) linear regression
  - Mann-Kendall monotonic trend test
  - Modified Mann-Kendall (Hamed & Rao 1998) with autocorrelation correction
  - Sen's slope estimator (Theil-Sen)
  - Seasonal decomposition (month-wise climatology)
  - Change-point detection (CUSUM-based)
  - FDR (Benjamini-Hochberg) correction for multiple testing
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks


# -----------------------------------------
# 1. OLS Linear Trend
# -----------------------------------------

def ols_trend(values: pd.Series) -> dict:
    """
    Fit an ordinary least squares linear trend.

    Returns slope (per step), r_squared, p_value,
    intercept, and the fitted trend series.
    """
    clean = values.dropna()

    if len(clean) < 4:
        return {
            "slope": np.nan,
            "r_squared": np.nan,
            "p_value": np.nan,
            "intercept": np.nan,
            "trend_series": pd.Series(
                np.nan, index=values.index
            ),
            "method": "OLS",
            "n": len(clean),
        }

    x = np.arange(len(clean), dtype=float)
    result = stats.linregress(x, clean.values)

    trend_series = pd.Series(
        result.intercept + result.slope * x,
        index=clean.index,
    )

    return {
        "slope": result.slope,
        "r_squared": result.rvalue ** 2,
        "p_value": result.pvalue,
        "intercept": result.intercept,
        "trend_series": trend_series,
        "method": "OLS",
        "n": len(clean),
    }


# -----------------------------------------
# 2. Mann-Kendall Trend Test
# -----------------------------------------

def mann_kendall(values: pd.Series) -> dict:
    """
    Non-parametric Mann-Kendall monotonic trend test.
    Returns tau, p_value, trend direction, and significance flag.
    Does NOT assume normality or linearity.
    """
    clean = values.dropna().values
    n = len(clean)

    if n < 4:
        return {
            "tau": np.nan,
            "p_value": np.nan,
            "significant": False,
            "direction": "insufficient data",
            "method": "Mann-Kendall",
            "n": n,
        }

    # Compute S statistic
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = clean[j] - clean[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Variance with tie correction
    unique, counts = np.unique(clean, return_counts=True)
    tie_sum = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_sum) / 18

    if var_s <= 0:
        return {
            "tau": 0.0,
            "p_value": 1.0,
            "significant": False,
            "direction": "no trend",
            "method": "Mann-Kendall",
            "n": n,
        }

    # Z-score
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0

    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))

    significant = p_value < 0.05
    if not significant:
        direction = "no significant trend"
    elif tau > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return {
        "tau": tau,
        "p_value": p_value,
        "z_score": z,
        "significant": significant,
        "direction": direction,
        "method": "Mann-Kendall",
        "n": n,
    }


# -----------------------------------------
# 2b. Modified Mann-Kendall (Hamed & Rao 1998)
# -----------------------------------------

def modified_mann_kendall(values: pd.Series) -> dict:
    """
    Modified Mann-Kendall trend test (Hamed & Rao 1998).

    Adjusts for serial autocorrelation by computing an effective
    sample size from the lag-1 autocorrelation of the detrended
    series, then inflating the variance of S accordingly.

    This is the same method used in the precomputed trend results
    consumed by the Trend Detective page, ensuring statistical
    consistency across all UG-ESI pages.

    Returns tau, p_value (autocorrelation-adjusted), z_score,
    lag1_autocorrelation, effective_n, trend direction, and
    significance flag.
    """
    clean = values.dropna().values
    n = len(clean)

    if n < 4:
        return {
            "tau": np.nan,
            "p_value": np.nan,
            "z_score": np.nan,
            "significant": False,
            "direction": "insufficient data",
            "method": "Modified Mann-Kendall (Hamed & Rao 1998)",
            "n": n,
            "lag1_autocorrelation": np.nan,
            "effective_n": n,
        }

    # Step 1: Compute S statistic (same as standard MK)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = clean[j] - clean[i]
            if diff > 0:
                s += 1
            elif diff < 0:
                s -= 1

    # Step 2: Compute base variance with tie correction
    unique, counts = np.unique(clean, return_counts=True)
    tie_sum = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_sum) / 18

    if var_s <= 0:
        return {
            "tau": 0.0,
            "p_value": 1.0,
            "z_score": 0.0,
            "significant": False,
            "direction": "no trend",
            "method": "Modified Mann-Kendall (Hamed & Rao 1998)",
            "n": n,
            "lag1_autocorrelation": 0.0,
            "effective_n": n,
        }

    # Step 3: Detrend using Sen's slope to remove the trend component
    x = np.arange(n, dtype=float)
    sen = stats.theilslopes(clean, x)
    detrended = clean - (sen.slope * x + sen.intercept)

    # Step 4: Compute lag-1 autocorrelation of detrended series
    # Use ranks for robustness against non-normality
    ranks = stats.rankdata(detrended)
    if n > 2:
        r1 = np.corrcoef(ranks[:-1], ranks[1:])[0, 1]
    else:
        r1 = 0.0

    if np.isnan(r1):
        r1 = 0.0

    # Step 5: Apply Hamed & Rao variance correction
    # Only inflate if positive autocorrelation (negative AC reduces variance,
    # but the standard practice is to only correct for positive AC)
    if r1 > 0:
        # Variance inflation factor (Hamed & Rao 1998)
        # correction = 1 + (2/n) * sum_{i=1}^{n-1} (n-i)/n * rho_i
        # For lag-1 only: correction = 1 + 2*(n-1)/n * r1
        correction = 1.0 + 2.0 * (n - 1) / n * r1
        var_s_corrected = var_s * correction
    else:
        correction = 1.0
        var_s_corrected = var_s

    # Step 6: Effective sample size
    if r1 > 0:
        n_eff = n / correction
    else:
        n_eff = n

    # Step 7: Compute corrected Z-score
    if s > 0:
        z = (s - 1) / np.sqrt(var_s_corrected)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s_corrected)
    else:
        z = 0.0

    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))

    significant = p_value < 0.05
    if not significant:
        direction = "no significant trend"
    elif tau > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return {
        "tau": tau,
        "p_value": p_value,
        "z_score": z,
        "significant": significant,
        "direction": direction,
        "method": "Modified Mann-Kendall (Hamed & Rao 1998)",
        "n": n,
        "lag1_autocorrelation": round(float(r1), 6),
        "effective_n": round(float(n_eff), 2),
        "variance_inflation_factor": round(float(correction), 4),
    }


# -----------------------------------------
# 2c. FDR Correction (Benjamini-Hochberg)
# -----------------------------------------

def apply_fdr_correction(p_values: list) -> list:
    """
    Apply Benjamini-Hochberg FDR correction to a list of p-values.
    Returns a list of FDR-adjusted q-values (same order as input).
    """
    n = len(p_values)
    if n == 0:
        return []

    p_arr = np.array(p_values)
    order = np.argsort(p_arr)

    # BH q-values
    q = np.zeros(n)
    q[order[-1]] = p_arr[order[-1]]
    for i in range(n - 2, -1, -1):
        q[order[i]] = min(
            q[order[i + 1]],
            p_arr[order[i]] * n / (i + 1)
        )

    q = np.clip(q, 0, 1)
    return q.tolist()


# -----------------------------------------
# 3. Sen's Slope (Theil-Sen estimator)
# -----------------------------------------

def sens_slope(values: pd.Series) -> dict:
    """
    Non-parametric slope estimator robust to outliers.
    Returns median slope, lower/upper 95% CI bounds.
    """
    clean = values.dropna()

    if len(clean) < 4:
        return {
            "slope": np.nan,
            "slope_lower": np.nan,
            "slope_upper": np.nan,
            "method": "Sen's Slope",
            "n": len(clean),
        }

    x = np.arange(len(clean), dtype=float)
    result = stats.theilslopes(clean.values, x, alpha=0.95)

    return {
        "slope": result.slope,
        "intercept": result.intercept,
        "slope_lower": result.low_slope,
        "slope_upper": result.high_slope,
        "method": "Sen's Slope",
        "n": len(clean),
    }


# -----------------------------------------
# 4. Seasonal Climatology
# -----------------------------------------

def seasonal_climatology(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
) -> pd.DataFrame:
    """
    Compute month-wise climatological mean and std dev.
    Returns DataFrame with month, mean, std, count.
    """
    work = df[[date_col, value_col]].dropna()
    work["month_num"] = pd.to_datetime(
        work[date_col]
    ).dt.month

    clim = (
        work.groupby("month_num")[value_col]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    clim.columns = ["month", "clim_mean", "clim_std", "count"]

    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }
    clim["month_name"] = clim["month"].map(month_names)

    return clim


# -----------------------------------------
# 5. Anomaly from Climatology
# -----------------------------------------

def compute_anomalies(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
) -> pd.DataFrame:
    """
    Subtract the month-wise climatological mean from
    each observation to produce a deseasonalised anomaly.
    """
    work = df[[date_col, value_col]].copy()
    work["month_num"] = pd.to_datetime(
        work[date_col]
    ).dt.month

    clim = seasonal_climatology(df, date_col, value_col)
    clim_map = dict(zip(clim["month"], clim["clim_mean"]))

    work["anomaly"] = (
        work[value_col] - work["month_num"].map(clim_map)
    )

    return work


# -----------------------------------------
# 6. Change-Point Detection (CUSUM)
# -----------------------------------------

def detect_change_points(
    values: pd.Series,
    threshold_sigma: float = 2.0,
) -> dict:
    """
    CUSUM-based change-point detection.
    Returns list of detected change-point indices and
    direction at each point (mean shift up/down).
    """
    clean = values.dropna()

    if len(clean) < 8:
        return {
            "change_points": [],
            "n": len(clean),
            "method": "CUSUM",
        }

    arr = clean.values
    mu = arr.mean()
    sigma = arr.std()

    if sigma == 0:
        return {
            "change_points": [],
            "n": len(clean),
            "method": "CUSUM",
        }

    cusum_pos = np.zeros(len(arr))
    cusum_neg = np.zeros(len(arr))
    k = 0.5  # allowance

    for i in range(1, len(arr)):
        cusum_pos[i] = max(
            0, cusum_pos[i - 1] + (arr[i] - mu) / sigma - k
        )
        cusum_neg[i] = max(
            0, cusum_neg[i - 1] - (arr[i] - mu) / sigma - k
        )

    # Find peaks above threshold
    h = threshold_sigma
    peaks_pos, _ = find_peaks(cusum_pos, height=h)
    peaks_neg, _ = find_peaks(cusum_neg, height=h)

    change_points = []

    for idx in peaks_pos:
        actual_idx = clean.index[idx]
        change_points.append({
            "index": actual_idx,
            "cusum_type": "positive",
            "direction": "upward shift",
            "cusum_value": float(cusum_pos[idx]),
        })

    for idx in peaks_neg:
        actual_idx = clean.index[idx]
        change_points.append({
            "index": actual_idx,
            "cusum_type": "negative",
            "direction": "downward shift",
            "cusum_value": float(cusum_neg[idx]),
        })

    change_points.sort(
        key=lambda x: x["cusum_value"],
        reverse=True,
    )

    return {
        "change_points": change_points[:5],
        "cusum_pos": cusum_pos,
        "cusum_neg": cusum_neg,
        "clean_index": clean.index,
        "n": len(clean),
        "method": "CUSUM",
    }


# -----------------------------------------
# 7. Full Multi-Scale Trend Report
# -----------------------------------------

def full_trend_report(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    variable_label: str = "",
) -> dict:
    """
    Run all trend methods on a single variable and
    return a unified report dict.
    """
    series = df.set_index(date_col)[value_col].sort_index()

    ols = ols_trend(series)
    mk = mann_kendall(series)
    mmk = modified_mann_kendall(series)
    ss = sens_slope(series)
    cp = detect_change_points(series)
    clim = seasonal_climatology(df, date_col, value_col)
    anom = compute_anomalies(df, date_col, value_col)

    # Annualised slope (monthly data → multiply by 12)
    ols_annual = ols["slope"] * 12 if not np.isnan(
        ols.get("slope", np.nan)
    ) else np.nan

    ss_annual = ss["slope"] * 12 if not np.isnan(
        ss.get("slope", np.nan)
    ) else np.nan

    return {
        "variable": variable_label or value_col,
        "n_months": int(series.dropna().__len__()),
        "ols": ols,
        "mann_kendall": mk,
        "modified_mann_kendall": mmk,
        "sens_slope": ss,
        "change_points": cp,
        "climatology": clim,
        "anomalies": anom,
        "annualised_ols_slope": ols_annual,
        "annualised_sens_slope": ss_annual,
        # Use modified MK as the primary significance determination
        # for consistency with precomputed Trend Detective results
        "overall_direction": mmk.get("direction", "unknown"),
        "significant": mmk.get("significant", False),
        "lag1_autocorrelation": mmk.get("lag1_autocorrelation", 0.0),
        "effective_n": mmk.get("effective_n", len(series)),
    }


# -----------------------------------------
# 8. Multi-Variable Trend Report with FDR
# -----------------------------------------

def multi_variable_trend_report(
    df: pd.DataFrame,
    date_col: str,
    variables: list,
    variable_labels: dict = None,
) -> dict:
    """
    Run modified Mann-Kendall trend analysis on multiple variables
    and apply FDR (Benjamini-Hochberg) correction across all variables.

    This ensures statistical consistency with the precomputed
    autocorrelation-adjusted + FDR-corrected results used in the
    Trend Detective page.

    Parameters
    ----------
    df : DataFrame with time-series columns
    date_col : name of the date column
    variables : list of variable column names to analyze
    variable_labels : optional dict mapping column names to display labels

    Returns
    -------
    Dict with:
      - 'per_variable': dict of full_trend_report results keyed by variable
      - 'fdr_summary': DataFrame with FDR-adjusted p-values for all variables
    """
    variable_labels = variable_labels or {}

    reports = {}
    p_values = []
    var_keys = []

    for var in variables:
        if var not in df.columns:
            continue

        label = variable_labels.get(var, var)
        report = full_trend_report(df, date_col, var, label)
        reports[var] = report

        mmk = report.get("modified_mann_kendall", {})
        p_val = mmk.get("p_value", 1.0)
        if np.isnan(p_val):
            p_val = 1.0
        p_values.append(p_val)
        var_keys.append(var)

    # Apply FDR correction across all variables
    q_values = apply_fdr_correction(p_values) if p_values else []

    fdr_rows = []
    for i, var in enumerate(var_keys):
        mmk = reports[var].get("modified_mann_kendall", {})
        fdr_rows.append({
            "variable": var,
            "label": variable_labels.get(var, var),
            "modified_mk_trend": mmk.get("direction", "unknown"),
            "modified_mk_tau": mmk.get("tau", np.nan),
            "modified_mk_p_value": mmk.get("p_value", np.nan),
            "fdr_adjusted_p_value": q_values[i] if i < len(q_values) else 1.0,
            "fdr_significant": q_values[i] < 0.05 if i < len(q_values) else False,
            "lag1_autocorrelation": mmk.get("lag1_autocorrelation", np.nan),
            "effective_n": mmk.get("effective_n", np.nan),
            "annualised_sens_slope": reports[var].get(
                "annualised_sens_slope", np.nan
            ),
        })

    fdr_df = pd.DataFrame(fdr_rows)

    return {
        "per_variable": reports,
        "fdr_summary": fdr_df,
    }
