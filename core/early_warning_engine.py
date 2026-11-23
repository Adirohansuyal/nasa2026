"""
Early Warning System Engine  — Multi-Hazard Edition
=====================================================
Detects 6 distinct hazard types from 5 NASA satellite signals.
NOT just flood/precipitation — every variable combination matters.

Hazard taxonomy (signal-pattern based):
  FLOOD           GPM high  + SMAP high                     (saturated + rain)
  DROUGHT         GPM low   + SMAP low   + LST high         (dry + hot + no rain)
  HEAT_WAVE       LST high  alone (GPM/SMAP near normal)    (hot but not dry overall)
  VEGETATION_LOSS NDVI low  + LST high   + SMAP low         (vegetation stress)
  COLD_STRESS     LST abnormally low in warm months (Apr-Sep)(glacial/frost signal)
  COMPOUND        ≥ 3 variables simultaneously anomalous    (multi-sensor crisis)

Each hazard has:
  - A detection rule (which variables, which direction, thresholds)
  - A severity score (0-100)
  - A plain-English message template
  - A recommended action tag

Data sources used:
  1. earthpulse_x_monthly_seasonal_anomalies.csv  (126-month regional)
  2. earthpulse_x_spatial_isolation_forest_events.csv  (50,449 pixel-level)
"""

import numpy as np
import pandas as pd
from typing import Optional


# ──────────────────────────────────────────────────────────────
# Alert tier thresholds  (|z-score|)
# ──────────────────────────────────────────────────────────────

ALERT_THRESHOLDS = {
    "INFO":     2.0,
    "WARNING":  3.0,
    "CRITICAL": 4.0,
}

# ──────────────────────────────────────────────────────────────
# Hazard catalogue
# ──────────────────────────────────────────────────────────────

HAZARD_CATALOGUE = {
    "FLOOD": {
        "emoji":       "🌊",
        "color":       "#2D7DD2",
        "label":       "Flood / Excess Runoff",
        "description": "Extreme precipitation combined with saturated soils — "
                       "river overflow and flash flood risk.",
        "action":      "Activate flood early warning. Alert downstream communities.",
    },
    "DROUGHT": {
        "emoji":       "🏜️",
        "color":       "#E9A34B",
        "label":       "Drought / Water Stress",
        "description": "Below-normal rain, dry soils, and elevated land temperatures — "
                       "multi-variable water deficit.",
        "action":      "Trigger water-rationing protocols. Monitor crop stress.",
    },
    "HEAT_WAVE": {
        "emoji":       "🔥",
        "color":       "#EF6461",
        "label":       "Heat Wave / Thermal Stress",
        "description": "Land surface temperature anomalously high without matching "
                       "dry soil signal — heat stress event.",
        "action":      "Issue heat health advisory. Check glacier melt rates.",
    },
    "VEGETATION_LOSS": {
        "emoji":       "🍂",
        "color":       "#A78BFA",
        "label":       "Vegetation Loss / Forest Stress",
        "description": "NDVI significantly below normal with elevated temperature "
                       "and/or dry soils — deforestation or drought-induced die-off.",
        "action":      "Deploy forest fire watch. Investigate land-use change.",
    },
    "COLD_STRESS": {
        "emoji":       "❄️",
        "color":       "#35C9D0",
        "label":       "Cold Stress / Glacial Signal",
        "description": "Land surface temperature anomalously LOW in a warm season — "
                       "unusual cooling, snowfall, or glacial advance signal.",
        "action":      "Monitor high-altitude infrastructure. Check road closures.",
    },
    "COMPOUND": {
        "emoji":       "⚡",
        "color":       "#F472B6",
        "label":       "Compound Multi-Hazard Event",
        "description": "Three or more satellite signals simultaneously anomalous — "
                       "highest-uncertainty, highest-impact scenario.",
        "action":      "Convene multi-agency crisis review immediately.",
    },
}

# ──────────────────────────────────────────────────────────────
# Variable display metadata
# ──────────────────────────────────────────────────────────────

VAR_META = {
    "LST":     {"label": "Land Surface Temp",  "unit": "K",      "emoji": "🌡️"},
    "NDVI":    {"label": "Vegetation (NDVI)",   "unit": "index",  "emoji": "🌿"},
    "SMAP_AM": {"label": "Soil Moisture AM",    "unit": "m³/m³", "emoji": "💧"},
    "SMAP_PM": {"label": "Soil Moisture PM",    "unit": "m³/m³", "emoji": "💧"},
    "GPM":     {"label": "Precipitation",       "unit": "mm/mo", "emoji": "🌧️"},
}

Z_COLS = ["LST_robust_z", "NDVI_robust_z", "SMAP_AM_robust_z",
          "SMAP_PM_robust_z", "GPM_robust_z"]

DISTRICT_APPROX_BOUNDS = {
    "Chamoli":           (30.0, 31.0, 79.0, 80.5),
    "Rudraprayag":       (30.3, 30.9, 78.7, 79.3),
    "Uttarkashi":        (30.6, 31.3, 78.0, 79.3),
    "Pithoragarh":       (29.8, 30.6, 80.0, 81.1),
    "Almora":            (29.4, 30.0, 79.2, 80.0),
    "Bageshwar":         (29.7, 30.3, 79.6, 80.3),
    "Pauri Garhwal":     (29.7, 30.5, 78.4, 79.4),
    "Tehri Garhwal":     (30.1, 30.8, 78.1, 79.0),
    "Dehradun":          (30.0, 31.1, 77.5, 78.6),
    "Haridwar":          (29.7, 30.2, 77.7, 78.4),
    "Nainital":          (29.1, 29.7, 79.0, 79.8),
    "Champawat":         (29.1, 29.6, 80.0, 80.7),
    "Udham Singh Nagar": (28.8, 29.4, 79.1, 80.1),
}


# ──────────────────────────────────────────────────────────────
# 1. Helpers
# ──────────────────────────────────────────────────────────────

def alert_color(level: str) -> str:
    return {"CRITICAL": "#EF6461", "WARNING": "#E9A34B",
            "INFO": "#F5D842", "NORMAL": "#31C48D"}.get(level, "#6B7B91")

def alert_emoji(level: str) -> str:
    return {"CRITICAL": "🔴", "WARNING": "🟠",
            "INFO": "🟡", "NORMAL": "🟢"}.get(level, "⚪")

def _tier(az: float, ti: float, tw: float, tc: float) -> str:
    if az >= tc:   return "CRITICAL"
    if az >= tw:   return "WARNING"
    if az >= ti:   return "INFO"
    return "NORMAL"


# ──────────────────────────────────────────────────────────────
# 2. Hazard detection rules
# ──────────────────────────────────────────────────────────────

def detect_hazards(
    lst_z: float,
    ndvi_z: float,
    smap_am_z: float,
    smap_pm_z: float,
    gpm_z: float,
    month_number: int,
    threshold: float = 1.5,
) -> list[dict]:
    """
    Apply rule-based multi-hazard detection to a single month's z-scores.

    Returns list of triggered hazards (may be empty or multiple).
    Each entry: {hazard_type, severity_score, evidence, message}
    """
    triggered = []
    smap_z = (smap_am_z + smap_pm_z) / 2  # average AM+PM

    def _ev(name, z, direction):
        sign = "+" if z > 0 else ""
        return f"{VAR_META[name]['emoji']} {VAR_META[name]['label']} {sign}{z:.2f}σ ({direction})"

    # ── FLOOD: GPM high AND SMAP high
    if gpm_z >= threshold and smap_z >= threshold:
        sev = min(100, (gpm_z + smap_z) / 2 * 20)
        triggered.append({
            "hazard_type":    "FLOOD",
            "severity_score": round(sev, 1),
            "evidence": [_ev("GPM", gpm_z, "excess rain"),
                         _ev("SMAP_AM", smap_am_z, "saturated soil")],
            "message": (f"🌊 Flood risk: GPM +{gpm_z:.1f}σ rain with "
                        f"SMAP +{smap_z:.1f}σ saturated soils"),
        })

    # ── DROUGHT: GPM low AND SMAP low AND LST high
    drought_signals = sum([gpm_z <= -threshold, smap_z <= -threshold, lst_z >= threshold])
    if drought_signals >= 2 and (gpm_z < 0 or smap_z < 0):
        sev = min(100, (abs(gpm_z) + abs(smap_z) + max(lst_z, 0)) / 3 * 20)
        evidence = []
        if gpm_z <= -threshold:
            evidence.append(_ev("GPM", gpm_z, "rain deficit"))
        if smap_z <= -threshold:
            evidence.append(_ev("SMAP_AM", smap_am_z, "dry soil"))
        if lst_z >= threshold:
            evidence.append(_ev("LST", lst_z, "hot surface"))
        triggered.append({
            "hazard_type":    "DROUGHT",
            "severity_score": round(sev, 1),
            "evidence":       evidence,
            "message": (f"🏜️ Drought: GPM {gpm_z:.1f}σ, SMAP {smap_z:.1f}σ"
                        + (f", LST +{lst_z:.1f}σ" if lst_z >= threshold else "")),
        })

    # ── HEAT WAVE: LST high, but NOT a drought (smap roughly normal)
    if lst_z >= threshold and smap_z > -threshold and not any(
        h["hazard_type"] == "DROUGHT" for h in triggered
    ):
        sev = min(100, lst_z * 18)
        triggered.append({
            "hazard_type":    "HEAT_WAVE",
            "severity_score": round(sev, 1),
            "evidence": [_ev("LST", lst_z, "thermal anomaly")],
            "message": f"🔥 Heat wave: LST +{lst_z:.1f}σ above normal",
        })

    # ── VEGETATION LOSS: NDVI low AND (LST high OR SMAP low)
    if ndvi_z <= -threshold and (lst_z >= threshold or smap_z <= -threshold):
        sev = min(100, (abs(ndvi_z) + max(lst_z, 0) + max(-smap_z, 0)) / 3 * 20)
        evidence = [_ev("NDVI", ndvi_z, "vegetation loss")]
        if lst_z >= threshold:
            evidence.append(_ev("LST", lst_z, "heat stress"))
        if smap_z <= -threshold:
            evidence.append(_ev("SMAP_AM", smap_am_z, "dry soil"))
        triggered.append({
            "hazard_type":    "VEGETATION_LOSS",
            "severity_score": round(sev, 1),
            "evidence":       evidence,
            "message": (f"🍂 Vegetation stress: NDVI {ndvi_z:.1f}σ"
                        + (f" + LST +{lst_z:.1f}σ" if lst_z >= threshold else "")
                        + (f" + SMAP {smap_z:.1f}σ" if smap_z <= -threshold else "")),
        })

    # ── COLD STRESS: LST anomalously low in warm months (Apr–Sep)
    if lst_z <= -threshold and month_number in range(4, 10):
        sev = min(100, abs(lst_z) * 18)
        triggered.append({
            "hazard_type":    "COLD_STRESS",
            "severity_score": round(sev, 1),
            "evidence": [_ev("LST", lst_z, "anomalous cooling")],
            "message": f"❄️ Cold/glacial stress: LST {lst_z:.1f}σ below normal in warm season",
        })

    # ── COMPOUND: ≥ 3 variables anomalous simultaneously
    anomalous_vars = sum([
        abs(lst_z) >= threshold,
        abs(ndvi_z) >= threshold,
        abs(smap_am_z) >= threshold,
        abs(gpm_z) >= threshold,
    ])
    if anomalous_vars >= 3 and not any(
        h["hazard_type"] == "COMPOUND" for h in triggered
    ):
        sev = min(100, anomalous_vars * 22)
        all_z = {"LST": lst_z, "NDVI": ndvi_z, "SMAP_AM": smap_am_z, "GPM": gpm_z}
        evidence = [
            _ev(k, v, "above" if v > 0 else "below")
            for k, v in all_z.items() if abs(v) >= threshold
        ]
        triggered.append({
            "hazard_type":    "COMPOUND",
            "severity_score": round(sev, 1),
            "evidence":       evidence,
            "message": f"⚡ Compound event: {anomalous_vars} sensors simultaneously anomalous",
        })

    return triggered


# ──────────────────────────────────────────────────────────────
# 3. Monthly regional alerts with multi-hazard typing
# ──────────────────────────────────────────────────────────────

def compute_monthly_alerts(
    anomalies_df: pd.DataFrame,
    threshold_info: float = 2.0,
    threshold_warning: float = 3.0,
    threshold_critical: float = 4.0,
) -> pd.DataFrame:
    """
    Compute per-month z-scores, alert tiers, AND hazard types
    for all 5 NASA satellite variables.

    Returns DataFrame (one row per month) with:
      - {VAR}_z, {VAR}_alert  for each variable
      - active_alerts (count elevated)
      - max_alert_level
      - hazards (list of hazard dicts from detect_hazards)
      - primary_hazard (highest-severity hazard type or "NONE")
      - alert_message
    """
    anom_col_map = {
        "lst_anomaly":     "LST",
        "ndvi_anomaly":    "NDVI",
        "smap_am_anomaly": "SMAP_AM",
        "smap_pm_anomaly": "SMAP_PM",
        "gpm_anomaly":     "GPM",
    }

    result = anomalies_df[["month", "year", "month_number"]].copy()

    # ── Z-score each variable
    for anom_col, var_key in anom_col_map.items():
        if anom_col not in anomalies_df.columns:
            result[f"{var_key}_z"]     = 0.0
            result[f"{var_key}_alert"] = "NORMAL"
            continue
        series = anomalies_df[anom_col].astype(float)
        std = series.std()
        z = (series - series.mean()) / std if std > 0 else series * 0.0
        result[f"{var_key}_z"] = z.round(3)
        result[f"{var_key}_alert"] = z.abs().apply(
            lambda az: _tier(az, threshold_info, threshold_warning, threshold_critical)
        )

    # ── Per-row alert summary
    level_rank = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
    alert_cols = [f"{k}_alert" for k in anom_col_map.values()]

    result["active_alerts"] = result[alert_cols].apply(
        lambda row: sum(1 for v in row if v != "NORMAL"), axis=1
    )
    result["max_alert_level"] = result[alert_cols].apply(
        lambda row: max(row, key=lambda v: level_rank.get(v, 0)), axis=1
    )

    # ── Multi-hazard detection per month
    # Use a LOWER threshold than INFO for hazard pattern matching —
    # hazards are defined by combinations, so individual signals can be
    # sub-threshold while the combination is still meaningful.
    hazard_threshold = max(1.0, threshold_info * 0.65)

    all_hazards = []
    primary_hazards = []
    messages = []

    for _, row in result.iterrows():
        lst_z    = float(row.get("LST_z",     0.0))
        ndvi_z   = float(row.get("NDVI_z",    0.0))
        smap_z   = float(row.get("SMAP_AM_z", 0.0))
        smap_pm  = float(row.get("SMAP_PM_z", 0.0))
        gpm_z    = float(row.get("GPM_z",     0.0))
        month_no = int(row.get("month_number", 6))

        hazards = detect_hazards(
            lst_z, ndvi_z, smap_z, smap_pm, gpm_z,
            month_no, threshold=hazard_threshold,
        )
        all_hazards.append(hazards)

        if hazards:
            top = max(hazards, key=lambda h: h["severity_score"])
            primary_hazards.append(top["hazard_type"])
            messages.append(top["message"])
        else:
            primary_hazards.append("NONE")
            # Fallback: if active alerts but no hazard pattern matched,
            # still build a message from raw z-scores
            var_labels = {
                "LST": "🌡️ LST", "NDVI": "🌿 NDVI",
                "SMAP_AM": "💧 SMAP AM", "SMAP_PM": "💧 SMAP PM", "GPM": "🌧️ GPM",
            }
            parts = []
            for vk in anom_col_map.values():
                lvl = row.get(f"{vk}_alert", "NORMAL")
                zv  = row.get(f"{vk}_z", 0.0)
                if lvl != "NORMAL":
                    direction = "above" if zv > 0 else "below"
                    parts.append(f"{var_labels[vk]} {abs(zv):.1f}σ {direction} normal")
            messages.append("; ".join(parts) if parts else "All within normal range")

    result["hazards"]        = all_hazards
    result["primary_hazard"] = primary_hazards
    result["alert_message"]  = messages
    result["month"]          = pd.to_datetime(result["month"])
    return result


# ──────────────────────────────────────────────────────────────
# 4. District-level multi-hazard risk from spatial pixels
# ──────────────────────────────────────────────────────────────

def compute_district_risk_from_spatial(
    spatial_df: pd.DataFrame,
    month_filter: Optional[str] = None,
    boundaries_gdf=None,
    threshold: float = 3.0,
) -> pd.DataFrame:
    """
    Aggregate pixel-level spatial anomaly events to district-level
    multi-hazard risk metrics.

    Returns one row per district with per-variable z-stats,
    composite risk score, risk level, and primary hazard type.
    """
    df = spatial_df.copy()
    if month_filter:
        df = df[df["month"].astype(str).str.startswith(month_filter[:7])]
    if df.empty:
        return pd.DataFrame()

    # Coordinate transform EPSG:6933 → WGS84
    try:
        import pyproj
        _t = pyproj.Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
        df["lon"], df["lat"] = _t.transform(
            df["x_epsg6933"].values, df["y_epsg6933"].values
        )
        has_coords = True
    except Exception:
        has_coords = False

    # Assign districts
    if has_coords and boundaries_gdf is not None:
        try:
            import geopandas as gpd
            from shapely.geometry import Point
            gdf_pts = gpd.GeoDataFrame(
                df,
                geometry=[Point(x, y) for x, y in zip(df["lon"], df["lat"])],
                crs="EPSG:4326",
            )
            bnd = boundaries_gdf.to_crs("EPSG:4326")
            joined = gpd.sjoin(gdf_pts, bnd[["district_name", "geometry"]],
                               how="left", predicate="within")
            df["district_name"] = joined["district_name"].fillna("Unknown")
        except Exception:
            df["district_name"] = _bbox_assign(df)
    elif has_coords:
        df["district_name"] = _bbox_assign(df)
    else:
        df["district_name"] = "Unknown"

    df = df[df["district_name"] != "Unknown"]
    if df.empty:
        return pd.DataFrame()

    # Max absolute z across all variables per pixel
    z_cols_here = [c for c in Z_COLS if c in df.columns]
    df["max_abs_z"] = df[z_cols_here].abs().max(axis=1) if z_cols_here else 0.0
    df["is_alert"]  = df["max_abs_z"] >= threshold

    rows = []
    for district, grp in df.groupby("district_name"):
        total     = len(grp)
        alert_px  = int(grp["is_alert"].sum())
        alert_pct = alert_px / total * 100 if total else 0.0
        if_px     = int(grp["if_anomaly_2pct"].sum()) if "if_anomaly_2pct" in grp.columns else 0
        if_pct    = if_px / total * 100 if total else 0.0

        def _ms(col, fn):
            s = grp[col].dropna() if col in grp.columns else pd.Series(dtype=float)
            return float(fn(s)) if len(s) > 0 else 0.0

        mean_lst   = _ms("LST_robust_z",    np.mean)
        max_lst    = _ms("LST_robust_z",     np.max)
        mean_ndvi  = _ms("NDVI_robust_z",   np.mean)
        min_ndvi   = _ms("NDVI_robust_z",    np.min)
        mean_smap  = _ms("SMAP_AM_robust_z", np.mean)
        mean_smap_pm = _ms("SMAP_PM_robust_z", np.mean)
        mean_gpm   = _ms("GPM_robust_z",    np.mean)
        max_gpm    = _ms("GPM_robust_z",     np.max)
        max_z      = float(grp["max_abs_z"].max()) if total > 0 else 0.0

        # Composite risk (multi-hazard aware)
        risk_raw = (
            0.35 * min(alert_pct / 100, 1.0)
            + 0.25 * min(if_pct / 100, 1.0)
            + 0.25 * min(max_z / 6.0, 1.0)
            + 0.15 * min(abs(mean_ndvi) / 3.0, 1.0)   # vegetation signal bonus
        )
        risk_score = round(risk_raw * 100, 1)

        if risk_score >= 60:   risk_level = "CRITICAL"
        elif risk_score >= 40: risk_level = "WARNING"
        elif risk_score >= 20: risk_level = "INFO"
        else:                  risk_level = "NORMAL"

        # Detect primary hazard for this district
        hazards = detect_hazards(
            mean_lst, mean_ndvi, mean_smap, mean_smap_pm, mean_gpm,
            month_number=6,           # neutral month (aggregated)
            threshold=1.0,            # lower threshold for district aggregates
        )
        primary_hazard = (
            max(hazards, key=lambda h: h["severity_score"])["hazard_type"]
            if hazards else "NONE"
        )

        rows.append({
            "district_name":     district,
            "risk_level":        risk_level,
            "risk_score":        risk_score,
            "primary_hazard":    primary_hazard,
            "alert_pct":         round(alert_pct, 1),
            "if_anomaly_pct":    round(if_pct, 1),
            "mean_lst_z":        round(mean_lst, 3),
            "max_lst_z":         round(max_lst, 3),
            "mean_ndvi_z":       round(mean_ndvi, 3),
            "min_ndvi_z":        round(min_ndvi, 3),
            "mean_smap_z":       round(mean_smap, 3),
            "mean_gpm_z":        round(mean_gpm, 3),
            "max_gpm_z":         round(max_gpm, 3),
            "total_pixels":      total,
            "alert_pixels":      alert_px,
        })

    return pd.DataFrame(rows).sort_values("risk_score", ascending=False).reset_index(drop=True)


def _bbox_assign(df: pd.DataFrame) -> pd.Series:
    names = []
    for _, row in df.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        assigned = "Unknown"
        if lat is not None and lon is not None:
            for dist, (lat_min, lat_max, lon_min, lon_max) in DISTRICT_APPROX_BOUNDS.items():
                if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                    assigned = dist
                    break
        names.append(assigned)
    return pd.Series(names, index=df.index)


# ──────────────────────────────────────────────────────────────
# 5. Alert feed generator
# ──────────────────────────────────────────────────────────────

def generate_alert_strings(
    monthly_alerts: pd.DataFrame,
    top_n: int = 10,
    min_level: str = "WARNING",
) -> list[dict]:
    """
    Convert monthly alerts to structured, multi-hazard alert dicts.
    """
    level_rank = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
    min_rank   = level_rank.get(min_level, 1)

    filtered = monthly_alerts[
        monthly_alerts["max_alert_level"].map(level_rank) >= min_rank
    ].sort_values(
        ["max_alert_level", "active_alerts"],
        key=lambda col: col.map(level_rank) if col.name == "max_alert_level" else col,
        ascending=False,
    ).head(top_n * 3)

    alerts = []
    for _, row in filtered.iterrows():
        month_str = pd.to_datetime(row["month"]).strftime("%B %Y")
        level     = row["max_alert_level"]
        hazards   = row.get("hazards", [])
        primary   = row.get("primary_hazard", "NONE")
        msg       = row.get("alert_message", "")

        # Per-variable detail
        details = []
        for var in ["LST", "NDVI", "SMAP_AM", "SMAP_PM", "GPM"]:
            lvl = row.get(f"{var}_alert", "NORMAL")
            zv  = row.get(f"{var}_z", 0.0)
            if lvl == "NORMAL" or (isinstance(zv, float) and np.isnan(zv)):
                continue
            direction = "above" if float(zv) > 0 else "below"
            details.append({
                "var":       f"{VAR_META[var]['emoji']} {VAR_META[var]['label']}",
                "z":         round(abs(float(zv)), 2),
                "direction": direction,
                "level":     lvl,
                "color":     alert_color(lvl),
            })

        if not details and not hazards:
            continue

        hazard_meta = HAZARD_CATALOGUE.get(primary, {})

        alerts.append({
            "month_str":    month_str,
            "month_dt":     pd.to_datetime(row["month"]),
            "alert_level":  level,
            "color":        alert_color(level),
            "emoji":        alert_emoji(level),
            "primary_hazard": primary,
            "hazard_emoji": hazard_meta.get("emoji", "⚠️"),
            "hazard_label": hazard_meta.get("label", primary),
            "hazard_color": hazard_meta.get("color", alert_color(level)),
            "hazard_action":hazard_meta.get("action", ""),
            "all_hazards":  hazards,
            "message":      msg,
            "details":      details,
            "active_count": int(row["active_alerts"]),
        })
        if len(alerts) >= top_n:
            break

    return alerts


# ──────────────────────────────────────────────────────────────
# 6. Hazard frequency summary over full period
# ──────────────────────────────────────────────────────────────

def hazard_frequency_summary(monthly_alerts: pd.DataFrame) -> pd.DataFrame:
    """
    Count how many months each hazard type was primary.
    Returns DataFrame sorted by count desc.
    """
    rows = []
    hazard_counts: dict[str, int] = {}

    for _, row in monthly_alerts.iterrows():
        hazards = row.get("hazards", [])
        seen = set()
        for h in hazards:
            ht = h["hazard_type"]
            if ht not in seen:
                hazard_counts[ht] = hazard_counts.get(ht, 0) + 1
                seen.add(ht)

    for ht, cnt in sorted(hazard_counts.items(), key=lambda x: -x[1]):
        meta = HAZARD_CATALOGUE.get(ht, {})
        rows.append({
            "hazard_type":  ht,
            "label":        meta.get("label", ht),
            "emoji":        meta.get("emoji", "⚠️"),
            "color":        meta.get("color", "#6B7B91"),
            "months_triggered": cnt,
            "description":  meta.get("description", ""),
            "action":       meta.get("action", ""),
        })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────
# 7. Chamoli 2021 historical validation
# ──────────────────────────────────────────────────────────────

def chamoli_2021_validation(
    monthly_alerts: pd.DataFrame,
    spatial_df: pd.DataFrame,
) -> dict:
    """
    Check whether the EWS flagged the Feb 7, 2021 Chamoli GLOF.
    Returns verdict dict with evidence and scientific explanation.
    """
    target_month = "2021-02"

    ma_copy = monthly_alerts.copy()
    ma_copy["month_str"] = pd.to_datetime(ma_copy["month"]).dt.strftime("%Y-%m")
    feb21 = ma_copy[ma_copy["month_str"] == target_month]

    regional_row        = feb21.iloc[0] if not feb21.empty else None
    regional_alert_level = regional_row.get("max_alert_level", "NORMAL") if regional_row is not None else "NORMAL"
    regional_hazards    = regional_row.get("hazards", []) if regional_row is not None else []
    found_regional      = regional_alert_level in ("WARNING", "CRITICAL", "INFO")

    # Pixel-level check
    sp = spatial_df.copy()
    sp["month_str"] = pd.to_datetime(sp["month"]).dt.strftime("%Y-%m")
    feb21_px = sp[sp["month_str"] == target_month]
    pixel_stats = {}
    found_pixel = False

    if not feb21_px.empty:
        n_total = len(feb21_px)
        n_if    = int(feb21_px["if_anomaly_2pct"].sum()) if "if_anomaly_2pct" in feb21_px.columns else 0
        high_gpm = int((feb21_px["GPM_robust_z"].abs() >= 2.5).sum()) if "GPM_robust_z" in feb21_px.columns else 0
        high_lst = int((feb21_px["LST_robust_z"].abs() >= 2.5).sum()) if "LST_robust_z" in feb21_px.columns else 0
        high_ndvi= int((feb21_px["NDVI_robust_z"].abs() >= 2.5).sum()) if "NDVI_robust_z" in feb21_px.columns else 0

        pixel_stats = {
            "total_pixels":       n_total,
            "if_anomaly_pixels":  n_if,
            "if_anomaly_pct":     round(n_if / n_total * 100, 1),
            "high_gpm_z_pixels":  high_gpm,
            "high_lst_z_pixels":  high_lst,
            "high_ndvi_z_pixels": high_ndvi,
            "mean_gpm_z":  round(float(feb21_px["GPM_robust_z"].mean()), 3) if "GPM_robust_z" in feb21_px.columns else 0.0,
            "mean_lst_z":  round(float(feb21_px["LST_robust_z"].mean()), 3) if "LST_robust_z" in feb21_px.columns else 0.0,
            "mean_ndvi_z": round(float(feb21_px["NDVI_robust_z"].mean()), 3) if "NDVI_robust_z" in feb21_px.columns else 0.0,
        }
        found_pixel = n_if > 0 or high_gpm > 0 or high_lst > 0

    if found_regional and found_pixel:
        verdict = "✅ CONFIRMED"
        detail  = (
            f"EWS flagged February 2021 at regional level ({regional_alert_level}) AND "
            f"detected pixel-level anomalies ({pixel_stats.get('if_anomaly_pct', 0):.1f}% "
            f"IF-flagged; LST mean z={pixel_stats.get('mean_lst_z', 0):.2f}σ). "
            f"Consistent with the Chamoli glacier burst (7 Feb 2021)."
        )
    elif found_regional or found_pixel:
        verdict = "⚠️ PARTIAL SIGNAL"
        detail  = (
            f"Partial signal: {'regional alert (' + regional_alert_level + ')' if found_regional else 'no regional alert'}. "
            f"{'Pixel-level anomalies present' if found_pixel else 'No pixel signal'}. "
            "The Chamoli GLOF was a sub-daily event — monthly aggregates may dilute the signal."
        )
    else:
        verdict = "❌ NOT DETECTED"
        detail  = (
            "February 2021 shows no significant anomaly in the monthly time-series. "
            "The Chamoli event was a glacial lake outburst flood (GLOF) — a single-day "
            "ice dam failure, not a multi-day precipitation anomaly. "
            "Monthly 1km² data cannot resolve sub-daily events. "
            "This is scientifically honest: the system is designed for accumulated "
            "hydro-meteorological stress, not sudden geophysical events."
        )

    return {
        "target_month":          target_month,
        "found_regional_signal": found_regional,
        "found_pixel_signal":    found_pixel,
        "regional_alert_level":  regional_alert_level,
        "regional_hazards":      regional_hazards,
        "regional_row":          regional_row,
        "pixel_stats":           pixel_stats,
        "validation_verdict":    verdict,
        "validation_detail":     detail,
    }


# ──────────────────────────────────────────────────────────────
# 8. Top anomalous months
# ──────────────────────────────────────────────────────────────

def top_anomalous_months(monthly_alerts: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    level_rank = {"NORMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
    z_cols     = [c for c in monthly_alerts.columns if c.endswith("_z")]
    df = monthly_alerts.copy()
    df["_lr"]  = df["max_alert_level"].map(level_rank).fillna(0)
    df["_tz"]  = df[z_cols].abs().sum(axis=1) if z_cols else 0
    return (
        df.sort_values(["_lr", "active_alerts", "_tz"], ascending=False)
          .head(n)
          .drop(columns=["_lr", "_tz"], errors="ignore")
          .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────
# 9. Per-Hazard District Intelligence
# ──────────────────────────────────────────────────────────────

# Approximate mean elevation (m) per district — used to weight cold stress scores
# Higher elevation → more climatologically relevant for cold/glacial signals
DISTRICT_ELEVATION_M = {
    "Uttarkashi":        3200,
    "Chamoli":           3100,
    "Pithoragarh":       2800,
    "Rudraprayag":       2400,
    "Bageshwar":         2200,
    "Tehri Garhwal":     1900,
    "Pauri Garhwal":     1600,
    "Almora":            1500,
    "Champawat":         1400,
    "Nainital":          1200,
    "Dehradun":           700,
    "Haridwar":           290,
    "Udham Singh Nagar":  244,
}

# Which z-score columns to use for each hazard's "intensity" signal
HAZARD_SIGNAL_COLS = {
    "FLOOD":           {"primary": "GPM_z",     "secondary": "SMAP_AM_z", "dir": +1},
    "DROUGHT":         {"primary": "GPM_z",      "secondary": "LST_z",    "dir": -1},
    "HEAT_WAVE":       {"primary": "LST_z",      "secondary": None,       "dir": +1},
    "VEGETATION_LOSS": {"primary": "NDVI_z",     "secondary": "LST_z",    "dir": -1},
    "COLD_STRESS":     {"primary": "LST_z",      "secondary": None,       "dir": -1},
    "COMPOUND":        {"primary": None,          "secondary": None,       "dir": +1},
}


def district_hazard_breakdown(
    monthly_alerts: pd.DataFrame,
    spatial_df: pd.DataFrame,
    boundaries_gdf=None,
    hazard_threshold: float = 1.3,
) -> dict[str, pd.DataFrame]:
    """
    For each of the 6 hazard types, compute a per-district summary
    showing:
      - How many months that hazard was triggered in that district's
        regional signal (from monthly_alerts)
      - Mean intensity z-score for the hazard's primary sensor
      - Worst month (highest severity)
      - List of triggered months

    Uses the monthly_alerts z-scores (regional) to score all 13
    districts equally (regional signal is Uttarakhand-wide), then
    overlays pixel-level spatial data per district for the
    primary signal intensity.

    Returns
    -------
    dict mapping hazard_type → DataFrame with columns:
        district_name, months_triggered, mean_intensity_z,
        max_intensity_z, worst_month, triggered_months (list),
        risk_score (0–100), risk_level
    """
    # ── Step 1: identify months each hazard was active (regional)
    hazard_months: dict[str, list] = {ht: [] for ht in HAZARD_CATALOGUE}
    hazard_severity: dict[str, list] = {ht: [] for ht in HAZARD_CATALOGUE}

    for _, row in monthly_alerts.iterrows():
        hazards = row.get("hazards", [])
        month_dt = pd.to_datetime(row["month"])
        for h in hazards:
            ht = h["hazard_type"]
            if ht in hazard_months:
                hazard_months[ht].append(month_dt.strftime("%Y-%m"))
                hazard_severity[ht].append(h["severity_score"])

    # ── Step 2: for each hazard, compute district-level pixel stats
    #           for the months that hazard was active
    results: dict[str, pd.DataFrame] = {}

    # Prep spatial data with coords
    sp = spatial_df.copy()
    try:
        import pyproj
        _t = pyproj.Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
        sp["lon"], sp["lat"] = _t.transform(
            sp["x_epsg6933"].values, sp["y_epsg6933"].values
        )
        has_coords = True
    except Exception:
        has_coords = False

    # Assign districts to pixels once (expensive — do it once)
    if has_coords and boundaries_gdf is not None:
        try:
            import geopandas as gpd
            from shapely.geometry import Point
            gdf_pts = gpd.GeoDataFrame(
                sp,
                geometry=[Point(x, y) for x, y in zip(sp["lon"], sp["lat"])],
                crs="EPSG:4326",
            )
            bnd = boundaries_gdf.to_crs("EPSG:4326")
            joined = gpd.sjoin(
                gdf_pts, bnd[["district_name", "geometry"]],
                how="left", predicate="within",
            )
            sp["district_name"] = joined["district_name"].fillna("Unknown")
        except Exception:
            sp["district_name"] = _bbox_assign(sp) if has_coords else "Unknown"
    elif has_coords:
        sp["district_name"] = _bbox_assign(sp)
    else:
        sp["district_name"] = "Unknown"

    sp = sp[sp["district_name"] != "Unknown"]
    sp["month_str"] = pd.to_datetime(sp["month"]).dt.strftime("%Y-%m")

    all_districts = sorted(sp["district_name"].unique()) if not sp.empty else []

    for ht in HAZARD_CATALOGUE:
        active_months = hazard_months.get(ht, [])
        sig_meta = HAZARD_SIGNAL_COLS.get(ht, {})
        primary_z_col = sig_meta.get("primary")    # e.g. "GPM_z" in monthly_alerts
        direction     = sig_meta.get("dir", +1)

        # Map monthly_alerts col name → spatial df col name
        _z_col_map = {
            "GPM_z":     "GPM_robust_z",
            "LST_z":     "LST_robust_z",
            "NDVI_z":    "NDVI_robust_z",
            "SMAP_AM_z": "SMAP_AM_robust_z",
        }
        spatial_z_col = _z_col_map.get(primary_z_col or "", None)

        rows = []
        for district in all_districts:
            dist_sp = sp[sp["district_name"] == district]

            if not active_months or dist_sp.empty:
                # No hazard months or no pixels → zero exposure
                rows.append({
                    "district_name":    district,
                    "months_triggered": 0,
                    "mean_intensity_z": 0.0,
                    "max_intensity_z":  0.0,
                    "worst_month":      "—",
                    "triggered_months": [],
                    "frequency_score": 0.0,
                    "intensity_score": 0.0,
                    "geo_weight": 1.0,
                    "raw_risk_score": 0.0,
                    "risk_score":       0.0,
                    "risk_level":       "NORMAL",
                })
                continue

            # Filter pixels to only months when hazard was active
            dist_active = dist_sp[dist_sp["month_str"].isin(active_months)]

            months_triggered = len(set(dist_active["month_str"].tolist()))

            # Intensity z-scores
            if spatial_z_col and spatial_z_col in dist_active.columns and len(dist_active) > 0:
                z_vals = dist_active[spatial_z_col].dropna()
                mean_z = float(z_vals.mean()) if len(z_vals) > 0 else 0.0
                if direction == +1:
                    max_z = float(z_vals.max()) if len(z_vals) > 0 else 0.0
                else:
                    # For negative-direction hazards (drought, cold), worst = most negative
                    max_z = float(z_vals.min()) if len(z_vals) > 0 else 0.0
            elif ht == "COMPOUND" and len(dist_active) > 0:
                # Compound: no single primary sensor — use max abs z across all sensors
                z_cols_all = ["LST_robust_z", "NDVI_robust_z",
                              "SMAP_AM_robust_z", "GPM_robust_z"]
                available = [c for c in z_cols_all if c in dist_active.columns]
                if available:
                    max_abs_series = dist_active[available].abs().max(axis=1)
                    mean_z = float(max_abs_series.mean())
                    max_z  = float(max_abs_series.max())
                else:
                    mean_z = 0.0
                    max_z  = 0.0
            else:
                mean_z = 0.0
                max_z  = 0.0

            # Worst month: the active month with highest absolute mean z in this district
            worst_month = "—"
            if len(dist_active) > 0 and months_triggered > 0:
                if spatial_z_col and spatial_z_col in dist_active.columns:
                    month_means = (
                        dist_active.groupby("month_str")[spatial_z_col]
                        .mean()
                        .apply(lambda v: v * direction)
                        .sort_values(ascending=False)
                    )
                elif ht == "COMPOUND":
                    z_cols_all = ["LST_robust_z", "NDVI_robust_z",
                                  "SMAP_AM_robust_z", "GPM_robust_z"]
                    available = [c for c in z_cols_all if c in dist_active.columns]
                    if available:
                        month_means = (
                            dist_active.groupby("month_str")[available]
                            .apply(lambda g: g.abs().max(axis=1).mean())
                            .sort_values(ascending=False)
                        )
                    else:
                        month_means = pd.Series(dtype=float)
                else:
                    month_means = pd.Series(dtype=float)
                if not month_means.empty:
                    worst_month = month_means.index[0]

            # ── Geography-aware risk score ────────────────────────────────
            # Raw scores (0-1 each):
            freq_score      = min(months_triggered / max(len(active_months), 1), 1.0)
            intensity_score = min(abs(mean_z) / 3.0, 1.0)

            elev  = DISTRICT_ELEVATION_M.get(district, 1000)
            max_e = max(DISTRICT_ELEVATION_M.values())   # 3200 m
            min_e = min(DISTRICT_ELEVATION_M.values())   # 244 m
            # Normalised 0→1: 0 = lowest district (USN 244m), 1 = highest (Uttarkashi 3200m)
            elev_norm = (elev - min_e) / (max_e - min_e)
            geo_weight = 1.0

            if ht == "COLD_STRESS":
                # High-altitude districts ARE the cold-stress zone.
                # Elevation weight: 0.54 (plains) → 1.0 (high Himalayas)
                geo_weight = 0.5 + 0.5 * elev_norm
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * geo_weight * 100, 1)

            elif ht == "HEAT_WAVE":
                # Plains (Haridwar, Dehradun, USN) are genuinely hotter.
                # Inverse elevation weight: low elevation → higher heat risk weight.
                geo_weight = 1.0 - 0.4 * elev_norm    # 1.0 (USN/plains) → 0.6 (Uttarkashi)
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * geo_weight * 100, 1)

            elif ht == "FLOOD":
                # Flash floods hit mid-elevation river valleys hardest
                # (Chamoli, Rudraprayag, Tehri, Uttarkashi — Ganga/Alaknanda tributaries).
                # Very low plains (USN, Haridwar) get riverine flooding too.
                # Peaks at mid-elevation, tapers at both extremes.
                # mid_weight peaks at ~1500m (Almora/Pauri range)
                mid_norm   = 1.0 - abs(elev_norm - 0.42) / 0.58   # peaks ~mid
                geo_weight = 0.6 + 0.4 * mid_norm
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * geo_weight * 100, 1)

            elif ht == "DROUGHT":
                # Drought hits rain-shadow mid-hills and drier valleys most.
                # Pauri/Tehri/Dehradun are known drought-prone; high Himalayas get glacier melt.
                # Slight mid-elevation preference, no strong correction needed.
                # Keep flat weights but boost mid-range districts slightly.
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * 100, 1)

            elif ht == "VEGETATION_LOSS":
                # Forests are predominantly in mid-to-high hills.
                # Plains (USN/Haridwar) are agricultural — less forest to lose.
                # Boost mid-high elevation districts slightly.
                geo_weight = 0.65 + 0.35 * elev_norm
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * geo_weight * 100, 1)

            elif ht == "COMPOUND":
                # For compound events primary_z_col is None → mean_z = 0 for all.
                # Use multi-sensor max_abs_z from spatial data instead.
                z_cols_all = ["LST_robust_z", "NDVI_robust_z",
                              "SMAP_AM_robust_z", "GPM_robust_z"]
                available = [c for c in z_cols_all if c in dist_active.columns]
                if available and len(dist_active) > 0:
                    compound_z = dist_active[available].abs().max(axis=1).mean()
                    intensity_score = min(compound_z / 4.0, 1.0)
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * 100, 1)

            else:
                risk_score = round((0.50 * freq_score + 0.50 * intensity_score) * 100, 1)

            if risk_score >= 60:   risk_level = "CRITICAL"
            elif risk_score >= 40: risk_level = "WARNING"
            elif risk_score >= 15: risk_level = "INFO"
            else:                  risk_level = "NORMAL"

            rows.append({
                "district_name":    district,
                "months_triggered": months_triggered,
                "mean_intensity_z": round(mean_z, 3),
                "max_intensity_z":  round(max_z, 3),
                "worst_month":      worst_month,
                "triggered_months": sorted(set(dist_active["month_str"].tolist())),
                "frequency_score": round(freq_score, 4),
                "intensity_score": round(intensity_score, 4),
                "geo_weight": round(geo_weight, 4),
                "raw_risk_score": round(risk_score, 1),
                "risk_score":       risk_score,
                "risk_level":       risk_level,
            })

        df_out = pd.DataFrame(rows).sort_values("risk_score", ascending=False).reset_index(drop=True)

        # ── Re-normalise risk_score so the RANGE spans the actual spread
        #    (avoids all districts collapsing to 100 when freq_score ≈ 1 everywhere)
        raw_scores = df_out["raw_risk_score"].copy()
        s_min, s_max = raw_scores.min(), raw_scores.max()
        spread = s_max - s_min

        if spread > 1.0:
            # Stretch to 0-100
            df_out["risk_score"] = ((raw_scores - s_min) / spread * 100).round(1)
        else:
            # Truly flat → keep as-is (all districts same exposure)
            pass

        # Recompute risk_level from normalised scores
        def _level(s):
            if s >= 60:   return "CRITICAL"
            if s >= 40:   return "WARNING"
            if s >= 15:   return "INFO"
            return "NORMAL"

        df_out["risk_level"] = df_out["risk_score"].apply(_level)

        results[ht] = df_out

    return results
