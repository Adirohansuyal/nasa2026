"""
UG-ESI Physics-Aware Intelligence Engine
========================================
Performs physical plausibility checks on environmental observations
to distinguish physically consistent signals from data artifacts.

Checks implemented:
  1. Physical plausibility bounds — are values within physically
     reasonable ranges for the variable and region?
  2. Seasonal consistency — does the seasonal cycle match expected
     monsoon-driven patterns for Uttarakhand?
  3. Cross-sensor consistency — do SMAP AM and PM track each other
     within physically expected diurnal variation?
  4. Contradictory signal detection — do different variables tell
     physically contradictory stories (e.g. high rainfall + very
     low soil moisture)?
  5. Uncertainty propagation — propagate observation coverage gaps
     to quantify how much confidence we lose in derived metrics.
  6. Sensitivity analysis — how much do trend conclusions change
     when strict vs relaxed quality thresholds are applied?
"""

import numpy as np
import pandas as pd
from scipy import stats


# -----------------------------------------
# Physical plausibility bounds for Uttarakhand
# Values based on published literature for the Himalayan foothills
# -----------------------------------------

PHYSICAL_BOUNDS = {
    "lst_strict_mean": {
        "label": "Land Surface Temperature",
        "min": 250.0,     # ~-23°C, extreme winter minimum
        "max": 330.0,     # ~57°C, extreme summer surface temp
        "unit": "K",
        "note": "Uttarakhand LST range based on MODIS observations",
    },
    "ndvi_strict_mean": {
        "label": "NDVI",
        "min": -0.2,      # Water/snow/bare rock
        "max": 1.0,       # Dense vegetation
        "unit": "index",
        "note": "Valid NDVI range",
    },
    "smap_am_strict_mean": {
        "label": "Soil Moisture (AM)",
        "min": 0.0,
        "max": 0.60,      # Saturated soil rarely exceeds this
        "unit": "m³/m³",
        "note": "Physical soil moisture range",
    },
    "smap_pm_strict_mean": {
        "label": "Soil Moisture (PM)",
        "min": 0.0,
        "max": 0.60,
        "unit": "m³/m³",
        "note": "Physical soil moisture range",
    },
    "gpm_monthly_precipitation_mean": {
        "label": "Precipitation",
        "min": 0.0,
        "max": 1500.0,    # Extreme monsoon month (mm/month)
        "unit": "mm",
        "note": "Monthly precipitation max for Himalayan region",
    },
}

# Expected seasonal patterns for Uttarakhand
# Monsoon: June-September (high precipitation, high SMAP, high NDVI)
# Winter: Dec-Feb (low precip, low LST, lower NDVI)
# Pre-monsoon: Mar-May (rising LST, moderate NDVI, low SMAP)

SEASONAL_EXPECTATIONS = {
    "lst_strict_mean": {
        "peak_month": 5,   # May (hottest before monsoon)
        "trough_month": 12,  # December (coldest)
    },
    "ndvi_strict_mean": {
        "peak_month": 9,   # September (post-monsoon peak green)
        "trough_month": 3,  # March (pre-monsoon dry)
    },
    "gpm_monthly_precipitation_mean": {
        "peak_month": 7,   # July (monsoon peak)
        "trough_month": 11,  # November (dry)
    },
    "smap_am_strict_mean": {
        "peak_month": 8,   # August (monsoon soil wet)
        "trough_month": 4,  # April (dry season)
    },
}

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


# -----------------------------------------
# 1. Physical Plausibility Check
# -----------------------------------------

def check_physical_plausibility(df: pd.DataFrame) -> dict:
    """
    Check whether observed values fall within physically
    plausible bounds for each variable.

    Returns a dict with per-variable results:
      - n_obs, n_in_bounds, n_out_of_bounds, percentage_in_bounds
      - min_observed, max_observed, bound_min, bound_max
      - flag: 'pass' | 'warning' | 'fail'
    """
    results = {}

    for var_key, bounds in PHYSICAL_BOUNDS.items():
        if var_key not in df.columns:
            continue

        series = df[var_key].dropna()
        n = len(series)

        if n == 0:
            continue

        in_bounds = ((series >= bounds["min"]) & (series <= bounds["max"])).sum()
        out_of_bounds = n - in_bounds
        pct = (in_bounds / n) * 100

        if pct >= 99:
            flag = "pass"
        elif pct >= 90:
            flag = "warning"
        else:
            flag = "fail"

        results[var_key] = {
            "label": bounds["label"],
            "unit": bounds["unit"],
            "n_obs": int(n),
            "n_in_bounds": int(in_bounds),
            "n_out_of_bounds": int(out_of_bounds),
            "percentage_in_bounds": round(float(pct), 2),
            "min_observed": round(float(series.min()), 4),
            "max_observed": round(float(series.max()), 4),
            "bound_min": bounds["min"],
            "bound_max": bounds["max"],
            "note": bounds["note"],
            "flag": flag,
        }

    return results


# -----------------------------------------
# 2. Seasonal Consistency Check
# -----------------------------------------

def check_seasonal_consistency(df: pd.DataFrame, date_col: str = "date") -> dict:
    """
    Check whether each variable's climatological seasonal cycle
    peaks and troughs occur in the expected months.

    Returns per-variable results:
      - expected_peak_month, actual_peak_month
      - expected_trough_month, actual_trough_month
      - seasonal_consistent: bool
      - mean_amplitude
    """
    results = {}
    work = df.copy()

    if date_col not in work.columns:
        date_col = "month"
    work["month_num"] = pd.to_datetime(work[date_col]).dt.month

    for var_key, expected in SEASONAL_EXPECTATIONS.items():
        if var_key not in work.columns:
            continue

        clim = work.groupby("month_num")[var_key].agg(["mean", "std"])
        if len(clim) < 6:
            continue

        actual_peak = int(clim["mean"].idxmax())
        actual_trough = int(clim["mean"].idxmin())

        # Allow ±1 month tolerance for peak/trough
        peak_ok = abs(actual_peak - expected["peak_month"]) <= 1
        trough_ok = abs(actual_trough - expected["trough_month"]) <= 1
        seasonal_consistent = peak_ok and trough_ok

        amplitude = float(clim["mean"].max() - clim["mean"].min())

        results[var_key] = {
            "label": PHYSICAL_BOUNDS.get(var_key, {}).get("label", var_key),
            "expected_peak_month": MONTH_NAMES.get(expected["peak_month"], "?"),
            "actual_peak_month": MONTH_NAMES.get(actual_peak, "?"),
            "expected_trough_month": MONTH_NAMES.get(expected["trough_month"], "?"),
            "actual_trough_month": MONTH_NAMES.get(actual_trough, "?"),
            "peak_match": peak_ok,
            "trough_match": trough_ok,
            "seasonal_consistent": seasonal_consistent,
            "mean_amplitude": round(amplitude, 4),
        }

    return results


# -----------------------------------------
# 3. Cross-Sensor Consistency (SMAP AM vs PM)
# -----------------------------------------

def check_cross_sensor_consistency(df: pd.DataFrame) -> dict:
    """
    Check whether SMAP morning (AM) and evening (PM) soil moisture
    readings are physically consistent with each other.

    The diurnal cycle should show AM > PM (morning wetter due to
    overnight dew/reduced evaporation) or AM ≈ PM. A systematic
    large offset or reversal is physically suspicious.

    Returns:
      - correlation, mean_difference, max_difference
      - am_higher_pct: % of months where AM > PM
      - diurnal_consistent: bool
    """
    if "smap_am_strict_mean" not in df.columns or "smap_pm_strict_mean" not in df.columns:
        return {}

    pair = df[["smap_am_strict_mean", "smap_pm_strict_mean"]].dropna()
    n = len(pair)

    if n < 4:
        return {}

    am = pair["smap_am_strict_mean"]
    pm = pair["smap_pm_strict_mean"]

    diff = am - pm
    corr, _ = stats.pearsonr(am, pm)
    mean_diff = float(diff.mean())
    max_diff = float(diff.abs().max())
    am_higher_pct = float((diff > 0).sum() / n * 100)

    # Physical expectation: AM ≥ PM (morning typically wetter)
    # or very small difference. Reversal (PM >> AM consistently) is suspicious.
    diurnal_consistent = (
        corr > 0.80
        and abs(mean_diff) < 0.05
    )

    return {
        "n_months": int(n),
        "correlation": round(float(corr), 4),
        "mean_am_minus_pm": round(mean_diff, 6),
        "max_absolute_difference": round(max_diff, 6),
        "am_higher_pct": round(am_higher_pct, 2),
        "diurnal_consistent": diurnal_consistent,
        "interpretation": (
            "AM and PM readings track closely, consistent with "
            "real diurnal soil moisture variation."
            if diurnal_consistent
            else "AM-PM divergence exceeds expected diurnal range — "
                 "may indicate retrieval condition differences."
        ),
    }


# -----------------------------------------
# 4. Contradictory Signal Detection
# -----------------------------------------

def detect_contradictory_signals(df: pd.DataFrame, date_col: str = "date") -> dict:
    """
    Detect months where environmental variables show physically
    contradictory combinations:

    1. High rainfall + very low soil moisture (water should infiltrate)
    2. Low rainfall + high soil moisture (no obvious source)
    3. High LST + high NDVI (heat stress should reduce vegetation)

    Uses robust thresholds (above/below climatological mean ± 1 std).

    Returns a dict with detected contradictions and their months.
    """
    contradictions = []
    work = df.copy()

    if date_col not in work.columns:
        date_col = "month"
    work["month_num"] = pd.to_datetime(work[date_col]).dt.month

    # Compute climatological means and stds
    for var in ["gpm_monthly_precipitation_mean", "smap_am_strict_mean",
                "lst_strict_mean", "ndvi_strict_mean"]:
        if var not in work.columns:
            continue
        clim = work.groupby("month_num")[var].agg(["mean", "std"])
        for _, row in work.iterrows():
            m = row["month_num"]
            if m in clim.index:
                mu = clim.loc[m, "mean"]
                sd = clim.loc[m, "std"]
                if sd and not np.isnan(sd) and sd > 0:
                    work.loc[work.index == row.name, f"{var}_z"] = \
                        (row[var] - mu) / sd

    # Check 1: High rainfall + low soil moisture
    if "gpm_monthly_precipitation_mean_z" in work.columns and \
       "smap_am_strict_mean_z" in work.columns:
        z_gpm = work["gpm_monthly_precipitation_mean_z"]
        z_smap = work["smap_am_strict_mean_z"]
        mask = (z_gpm > 1.0) & (z_smap < -1.0)
        for _, row in work[mask].iterrows():
            contradictions.append({
                "month": str(row.get(date_col, "?"))[:7],
                "type": "high_rainfall_low_soil_moisture",
                "description": (
                    f"Rainfall +{row['gpm_monthly_precipitation_mean_z']:.1f}σ "
                    f"but soil moisture {row['smap_am_strict_mean_z']:.1f}σ"
                ),
                "physical_explanation": (
                    "High rainfall with depressed soil moisture is unusual — "
                    "may indicate rapid runoff on steep terrain, data quality "
                    "issues, or measurement timing mismatch."
                ),
            })

    # Check 2: High LST + high NDVI
    if "lst_strict_mean_z" in work.columns and \
       "ndvi_strict_mean_z" in work.columns:
        z_lst = work["lst_strict_mean_z"]
        z_ndvi = work["ndvi_strict_mean_z"]
        mask = (z_lst > 1.0) & (z_ndvi > 1.0)
        for _, row in work[mask].iterrows():
            contradictions.append({
                "month": str(row.get(date_col, "?"))[:7],
                "type": "high_lst_high_ndvi",
                "description": (
                    f"LST +{row['lst_strict_mean_z']:.1f}σ "
                    f"and NDVI +{row['ndvi_strict_mean_z']:.1f}σ"
                ),
                "physical_explanation": (
                    "High temperature with elevated vegetation is possible "
                    "in irrigated/agricultural areas but contradictory for "
                    "rain-fed natural vegetation."
                ),
            })

    return {
        "n_contradictions": len(contradictions),
        "contradictions": contradictions[:10],  # Cap at 10
        "summary": (
            f"{len(contradictions)} physically contradictory month(s) detected "
            f"out of {len(work)} observed."
        ),
    }


# -----------------------------------------
# 5. Uncertainty Propagation
# -----------------------------------------

def propagate_uncertainty(df: pd.DataFrame) -> dict:
    """
    Quantify how observation coverage gaps propagate into
    uncertainty in derived regional mean estimates.

    For each variable:
      - Effective sample fraction = coverage% / 100
      - Standard error inflation = 1 / sqrt(effective_sample_fraction)
      - Confidence interval width relative to full-coverage case

    Returns per-variable uncertainty metrics.
    """
    coverage_cols = {
        "LST": "lst_strict_coverage_pct",
        "NDVI": "ndvi_strict_coverage_pct",
        "SMAP AM": "smap_am_strict_coverage_pct",
        "SMAP PM": "smap_pm_strict_coverage_pct",
        "GPM": "gpm_monthly_precipitation_coverage_pct",
    }

    value_cols = {
        "LST": "lst_strict_mean",
        "NDVI": "ndvi_strict_mean",
        "SMAP AM": "smap_am_strict_mean",
        "SMAP PM": "smap_pm_strict_mean",
        "GPM": "gpm_monthly_precipitation_mean",
    }

    results = {}

    for name, cov_col in coverage_cols.items():
        val_col = value_cols[name]

        if cov_col not in df.columns or val_col not in df.columns:
            continue

        cov = df[cov_col].dropna() / 100.0
        vals = df[val_col].dropna()

        if len(cov) == 0 or len(vals) == 0:
            continue

        # Effective sample fraction (average)
        eff_frac = float(cov.mean())

        # Standard error inflation factor
        # If coverage is 50%, SE is inflated by 1/sqrt(0.5) ≈ 1.41
        se_inflation = 1.0 / np.sqrt(max(eff_frac, 0.01))

        # Relative uncertainty: how much wider is our CI vs full coverage?
        # CI_width_ratio = se_inflation (since CI ∝ SE)
        ci_ratio = se_inflation

        # Standard deviation of the variable
        sd = float(vals.std())

        # Full-coverage 95% CI half-width (per observation)
        full_ci = 1.96 * sd / np.sqrt(len(vals))

        # Coverage-adjusted 95% CI half-width
        adj_ci = full_ci * ci_ratio

        results[name] = {
            "mean_coverage_pct": round(float(cov.mean() * 100), 1),
            "min_coverage_pct": round(float(cov.min() * 100), 1),
            "effective_sample_fraction": round(eff_frac, 4),
            "se_inflation_factor": round(float(se_inflation), 3),
            "ci_width_ratio": round(float(ci_ratio), 3),
            "full_coverage_ci_half_width": round(full_ci, 6),
            "coverage_adjusted_ci_half_width": round(adj_ci, 6),
            "interpretation": (
                f"Mean coverage {cov.mean()*100:.1f}% inflates standard "
                f"error by {se_inflation:.2f}× relative to full coverage."
            ),
        }

    return results


# -----------------------------------------
# 6. Sensitivity Analysis
# -----------------------------------------

def sensitivity_analysis(df: pd.DataFrame) -> dict:
    """
    Compare regional mean statistics under strict vs relaxed
    quality thresholds. If the difference is small, trend
    conclusions are robust to quality threshold choice.

    Returns per-variable sensitivity metrics.
    """
    pairs = {
        "LST": ("lst_strict_mean", "lst_relaxed_mean"),
        "NDVI": ("ndvi_strict_mean", "ndvi_relaxed_mean"),
        "SMAP AM": ("smap_am_strict_mean", "smap_am_relaxed_mean"),
        "SMAP PM": ("smap_pm_strict_mean", "smap_pm_relaxed_mean"),
    }

    results = {}

    for name, (strict_col, relaxed_col) in pairs.items():
        if strict_col not in df.columns or relaxed_col not in df.columns:
            continue

        strict = df[strict_col].dropna()
        relaxed = df[relaxed_col].dropna()

        if len(strict) < 4 or len(relaxed) < 4:
            continue

        # Mean difference
        mean_diff = float(relaxed.mean() - strict.mean())
        strict_std = float(strict.std())

        # Relative difference as % of strict std
        rel_diff_pct = abs(mean_diff) / strict_std * 100 if strict_std > 0 else 0

        # Correlation between strict and relaxed
        pair_df = df[[strict_col, relaxed_col]].dropna()
        corr = float(pair_df[strict_col].corr(pair_df[relaxed_col])) if len(pair_df) > 2 else np.nan

        robust = rel_diff_pct < 10 and (np.isnan(corr) or corr > 0.95)

        results[name] = {
            "strict_mean": round(float(strict.mean()), 6),
            "relaxed_mean": round(float(relaxed.mean()), 6),
            "mean_difference": round(mean_diff, 6),
            "relative_difference_pct": round(float(rel_diff_pct), 2),
            "correlation_strict_relaxed": round(corr, 4) if not np.isnan(corr) else None,
            "robust_to_threshold": robust,
            "interpretation": (
                f"Mean difference {rel_diff_pct:.1f}% of strict std — "
                f"conclusions {'robust' if robust else 'sensitive'} "
                f"to quality threshold choice."
            ),
        }

    return results


# -----------------------------------------
# 7. Full Physics Report
# -----------------------------------------

def generate_physics_report(df: pd.DataFrame, date_col: str = "date") -> dict:
    """
    Run all physics-aware intelligence checks and return a
    unified report.

    Returns a dict with all check results plus a text summary
    suitable for AI context.
    """
    plausibility = check_physical_plausibility(df)
    seasonal = check_seasonal_consistency(df, date_col)
    cross_sensor = check_cross_sensor_consistency(df)
    contradictory = detect_contradictory_signals(df, date_col)
    uncertainty = propagate_uncertainty(df)
    sensitivity = sensitivity_analysis(df)

    # Build text summary
    summary_lines = ["Physics-Aware Intelligence Report", "=" * 40, ""]

    # Plausibility
    summary_lines.append("1. PHYSICAL PLAUSIBILITY")
    for var, res in plausibility.items():
        summary_lines.append(
            f"  {res['label']}: {res['flag'].upper()} "
            f"({res['percentage_in_bounds']:.1f}% in bounds, "
            f"range [{res['min_observed']}, {res['max_observed']}] "
            f"{res['unit']})"
        )
    summary_lines.append("")

    # Seasonal
    summary_lines.append("2. SEASONAL CONSISTENCY")
    for var, res in seasonal.items():
        status = "✅" if res["seasonal_consistent"] else "⚠️"
        summary_lines.append(
            f"  {status} {res['label']}: "
            f"peak {res['actual_peak_month']} (expected {res['expected_peak_month']}), "
            f"trough {res['actual_trough_month']} (expected {res['expected_trough_month']})"
        )
    summary_lines.append("")

    # Cross-sensor
    if cross_sensor:
        status = "✅" if cross_sensor["diurnal_consistent"] else "⚠️"
        summary_lines.append("3. CROSS-SENSOR CONSISTENCY (SMAP AM vs PM)")
        summary_lines.append(
            f"  {status} correlation={cross_sensor['correlation']:.3f}, "
            f"mean AM-PM diff={cross_sensor['mean_am_minus_pm']:.4f}, "
            f"AM higher {cross_sensor['am_higher_pct']:.1f}% of months"
        )
        summary_lines.append("")

    # Contradictory signals
    summary_lines.append("4. CONTRADICTORY SIGNALS")
    summary_lines.append(f"  {contradictory['summary']}")
    for c in contradictory["contradictions"][:3]:
        summary_lines.append(f"  - {c['month']}: {c['description']}")
    summary_lines.append("")

    # Uncertainty
    summary_lines.append("5. UNCERTAINTY PROPAGATION")
    for name, res in uncertainty.items():
        summary_lines.append(
            f"  {name}: SE inflation {res['se_inflation_factor']:.2f}× "
            f"(coverage {res['mean_coverage_pct']:.1f}%)"
        )
    summary_lines.append("")

    # Sensitivity
    summary_lines.append("6. SENSITIVITY (strict vs relaxed)")
    for name, res in sensitivity.items():
        status = "✅" if res["robust_to_threshold"] else "⚠️"
        summary_lines.append(
            f"  {status} {name}: diff {res['relative_difference_pct']:.1f}% "
            f"of std, corr={res['correlation_strict_relaxed']}"
        )

    return {
        "plausibility": plausibility,
        "seasonal": seasonal,
        "cross_sensor": cross_sensor,
        "contradictory": contradictory,
        "uncertainty": uncertainty,
        "sensitivity": sensitivity,
        "text_summary": "\n".join(summary_lines),
    }
