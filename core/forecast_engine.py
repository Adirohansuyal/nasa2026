"""
UG-ESI Contribution: Predictive Intelligence Engine
=====================================================
"What will happen NEXT?" — Answers NASA's implicit 5th question: SO WHAT?

Architecture:
  1. Rolling-origin validation selects lag depth, seasonal complexity, and Ridge strength.
  2. A seasonal autoregressive Ridge model learns from lagged observations,
     Fourier seasonality, and a continuing time trend.
  3. Residual bootstrap intervals are widened using held-out rolling-CV errors.
  5. Drought Risk Score → fuses LST forecast, NDVI forecast, SMAP forecast,
     and GPM forecast into a composite seasonal risk index (0–100)

Why this design instead of Prophet/LSTM?
  - Zero new pip installs (all deps already in requirements.txt)
  - Interpretable coefficients (not a black box)
  - Forecast performance and interval coverage are checked against held-out months.
  - Captures Uttarakhand's strong monsoon seasonality via explicit sin/cos
  - Robust to the autocorrelated residuals present in LST/NDVI (handles
    the same problem Modified Mann-Kendall was designed to solve)
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from typing import Optional


# ──────────────────────────────────────────────────────────────
# 1. Feature Engineering  (AR + Fourier seasonality)
# ──────────────────────────────────────────────────────────────

def _build_features(
    values: np.ndarray,
    months: np.ndarray,       # integer month-of-year 1..12
    lags: list[int] = (1, 2, 3, 6, 12),
    fourier_order: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build an AR-Fourier feature matrix from a 1-D value array.

    Features per sample:
      - AR lags (1, 2, 3, 6, 12 months back)
      - sin/cos Fourier harmonics of month-of-year (captures seasonality)
      - Linear time index (captures trend memory)

    Returns X (n_samples × n_features) and the valid y slice.
    max_lag rows are dropped from the head to avoid NaN lags.
    """
    max_lag = max(lags)
    n = len(values)

    rows = []
    targets = []

    for i in range(max_lag, n):
        row = []

        # AR lag features
        for lag in lags:
            row.append(values[i - lag])

        # Fourier seasonality features
        m = months[i]
        for k in range(1, fourier_order + 1):
            row.append(np.sin(2 * np.pi * k * m / 12))
            row.append(np.cos(2 * np.pi * k * m / 12))

        # Linear trend index (normalised)
        row.append(i / n)

        rows.append(row)
        targets.append(values[i])

    return np.array(rows), np.array(targets)


def _fourier_row(
    month_int: int,
    time_idx: float,
    last_lags: list,
    fourier_order: int = 3,
    lag_offsets: list[int] = (1, 2, 3, 6, 12),
) -> np.ndarray:
    """Build a single feature row for a future step (used in recursive forecast)."""
    row = list(last_lags)                                    # AR lags
    m = month_int
    for k in range(1, fourier_order + 1):
        row.append(np.sin(2 * np.pi * k * m / 12))
        row.append(np.cos(2 * np.pi * k * m / 12))
    row.append(time_idx)                                     # trend index
    return np.array(row).reshape(1, -1)


# ──────────────────────────────────────────────────────────────
# 2. Core Forecast Model
# ──────────────────────────────────────────────────────────────

class SeasonalARModel:
    """
    Seasonal AutoRegressive model with Ridge regularisation.

    This model:
      - Fits Ridge on lag + Fourier features
      - Recursively generates h-step-ahead point forecasts
      - Estimates uncertainty via Monte Carlo residual bootstrap
        (empirical, not parametric → valid for non-Gaussian residuals)
    """

    def __init__(
        self,
        lags: tuple = (1, 2, 3, 6, 12),
        fourier_order: int = 3,
        ridge_alpha: float = 1.0,
        n_bootstrap: int = 1000,
        seed: int = 42,
    ):
        self.lags = list(lags)
        self.fourier_order = fourier_order
        self.ridge_alpha = ridge_alpha
        self.n_bootstrap = n_bootstrap
        self.rng = np.random.default_rng(seed)

        self._model: Optional[Ridge] = None
        self._scaler = StandardScaler()
        self._fitted_values: Optional[np.ndarray] = None
        self._residuals: Optional[np.ndarray] = None
        self._train_values: Optional[np.ndarray] = None
        self._train_months: Optional[np.ndarray] = None
        self._n_train: int = 0

    def fit(self, values: np.ndarray, months: np.ndarray):
        """
        Fit the model.

        Parameters
        ----------
        values : 1-D float array, monthly time-series (e.g. LST means)
        months : 1-D int array, month-of-year (1..12), same length
        """
        self._train_values = values.copy()
        self._train_months = months.copy()
        self._n_train = len(values)

        X, y = _build_features(values, months, self.lags, self.fourier_order)

        X_scaled = self._scaler.fit_transform(X)
        self._model = Ridge(alpha=self.ridge_alpha, fit_intercept=True)
        self._model.fit(X_scaled, y)

        fitted = self._model.predict(X_scaled)
        self._residuals = y - fitted
        # Store fitted values aligned with the full length
        self._fitted_values = np.full(self._n_train, np.nan)
        self._fitted_values[max(self.lags):] = fitted

        return self

    def _single_forecast_path(
        self,
        h: int,
        residual_noise: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Recursively generate h point forecasts.
        If residual_noise is given, add it at each step (bootstrap simulation).
        """
        # Seed the buffer with the last max_lag real values
        max_lag = max(self.lags)
        buffer = list(self._train_values[-max_lag:])
        n_total = self._n_train
        forecasts = []

        # Last known month
        last_month_idx = int(self._train_months[-1])   # 1..12

        for step in range(h):
            month_idx = (last_month_idx + step) % 12 + 1   # roll over 12→1
            # Continue the same normalized time axis used during fitting.
            # Dividing by n_total + h compressed every forecast into [0, 1]
            # and effectively stopped the learned trend at the last observation.
            time_idx = (n_total + step) / n_total

            # Build lag vector from buffer (most recent = index -1)
            last_lags = [buffer[-lag] for lag in self.lags]

            x_row = _fourier_row(
                month_idx, time_idx, last_lags,
                self.fourier_order, self.lags,
            )
            x_scaled = self._scaler.transform(x_row)
            pred = float(self._model.predict(x_scaled)[0])

            if residual_noise is not None:
                pred += residual_noise[step]

            forecasts.append(pred)
            buffer.append(pred)
            if len(buffer) > max_lag + h:
                buffer.pop(0)

        return np.array(forecasts)

    def forecast(
        self,
        h: int = 6,
    ) -> dict:
        """
        Generate h-step-ahead forecasts with uncertainty bands.

        Returns
        -------
        dict with keys:
          point     : np.ndarray (h,) — median forecast
          lower_80  : np.ndarray (h,) — 10th percentile (80% PI lower)
          upper_80  : np.ndarray (h,) — 90th percentile (80% PI upper)
          lower_95  : np.ndarray (h,) — 2.5th percentile (95% PI lower)
          upper_95  : np.ndarray (h,) — 97.5th percentile (95% PI upper)
          in_sample_fitted : np.ndarray (n_train,) — fitted values
          residuals        : np.ndarray
        """
        if self._model is None:
            raise RuntimeError("Call .fit() first")

        # Point forecast (no noise)
        point = self._single_forecast_path(h, residual_noise=None)

        # Bootstrap uncertainty: resample residuals, add to each recursive path
        bootstrap_paths = np.zeros((self.n_bootstrap, h))
        resid = self._residuals

        for b in range(self.n_bootstrap):
            noise = self.rng.choice(resid, size=h, replace=True)
            bootstrap_paths[b] = self._single_forecast_path(h, residual_noise=noise)

        lower_80 = np.percentile(bootstrap_paths, 10, axis=0)
        upper_80 = np.percentile(bootstrap_paths, 90, axis=0)
        lower_95 = np.percentile(bootstrap_paths, 2.5, axis=0)
        upper_95 = np.percentile(bootstrap_paths, 97.5, axis=0)

        return {
            "point": point,
            "lower_80": lower_80,
            "upper_80": upper_80,
            "lower_95": lower_95,
            "upper_95": upper_95,
            "in_sample_fitted": self._fitted_values,
            "residuals": self._residuals,
        }


# ──────────────────────────────────────────────────────────────
# 3. Cross-Validation (Walk-Forward)
# ──────────────────────────────────────────────────────────────

_MODEL_CANDIDATES = (
    {"lags": (1, 2, 3, 6, 12), "fourier_order": 3, "ridge_alpha": 1.0},
    {"lags": (1, 2, 3, 12), "fourier_order": 1, "ridge_alpha": 1.0},
    {"lags": (1, 2, 3, 6, 12), "fourier_order": 1, "ridge_alpha": 10.0},
    {"lags": (1, 12), "fourier_order": 1, "ridge_alpha": 10.0},
)


def _conformal_radius(errors: list[float] | np.ndarray, coverage: float) -> float:
    """Finite-sample absolute-error quantile for a symmetric prediction band."""
    values = np.asarray(errors, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return float("nan")
    rank = int(np.ceil((len(values) + 1) * coverage))
    return float(np.sort(values)[min(max(rank, 1), len(values)) - 1])


def select_model_config(
    values: np.ndarray,
    months: np.ndarray,
    h: int = 3,
    min_train: int = 60,
    n_splits: int = 5,
) -> dict:
    """Choose model complexity using expanding-window, out-of-sample MAE."""
    values = np.asarray(values, dtype=float)
    months = np.asarray(months, dtype=int)
    target_horizon = min(max(1, int(h)), 6)
    last_origin = len(values) - target_horizon
    first_origin = max(int(min_train), 36)
    if last_origin < first_origin:
        return dict(_MODEL_CANDIDATES[0])

    origins = np.unique(np.linspace(
        first_origin, last_origin,
        num=min(int(n_splits), last_origin - first_origin + 1),
        dtype=int,
    ))
    candidate_errors: list[tuple[float, int]] = []
    for candidate_index, config in enumerate(_MODEL_CANDIDATES):
        errors = []
        for origin in origins:
            model = SeasonalARModel(**config, n_bootstrap=0)
            model.fit(values[:origin], months[:origin])
            prediction = model._single_forecast_path(target_horizon)
            actual = values[origin:origin + target_horizon]
            errors.extend(np.abs(prediction - actual).tolist())
        if errors:
            candidate_errors.append((float(np.mean(errors)), candidate_index))

    if not candidate_errors:
        return dict(_MODEL_CANDIDATES[0])
    _, selected_index = min(candidate_errors, key=lambda item: item[0])
    return dict(_MODEL_CANDIDATES[selected_index])

def walk_forward_cv(
    values: np.ndarray,
    months: np.ndarray,
    h: int = 3,
    min_train: int = 60,
    n_splits: int = 12,
) -> dict:
    """
    Walk-forward cross-validation to evaluate forecast skill.

    Uses the last n_splits folds, each training on an expanding window.

    Returns
    -------
    dict with 'mae', 'rmse', 'mape', 'coverage_80', 'coverage_95'
    """
    n = len(values)
    if n <= min_train + h:
        return {
            "mae": np.nan, "rmse": np.nan, "mape": np.nan,
            "coverage_80": np.nan, "coverage_95": np.nan,
            "baseline_mae": np.nan, "absolute_errors_by_lead": [], "n_folds": 0,
        }
    origins = np.unique(np.linspace(min_train, n - h, n_splits, dtype=int))

    maes, rmses, mapes, baseline_maes = [], [], [], []
    calibrated_cov80, calibrated_cov95 = [], []
    errors_by_lead: list[list[float]] = [[] for _ in range(h)]

    for split_end in origins:
        train_v = values[:split_end]
        train_m = months[:split_end]
        actual = values[split_end:split_end + h]

        try:
            config = select_model_config(
                train_v, train_m, h=h, min_train=min_train, n_splits=4
            )
            model = SeasonalARModel(**config, n_bootstrap=0)
            model.fit(train_v, train_m)
            pred = model._single_forecast_path(len(actual))

            err = np.abs(pred - actual)
            maes.append(float(np.mean(err)))
            rmses.append(float(np.sqrt(np.mean((pred - actual) ** 2))))
            naive_pred = np.asarray([train_v[-12 + i] for i in range(len(actual))])
            baseline_maes.append(float(np.mean(np.abs(naive_pred - actual))))

            nonzero = actual != 0
            if nonzero.any():
                mapes.append(float(np.mean(err[nonzero] / np.abs(actual[nonzero])) * 100))

            # Use only earlier out-of-fold errors to calibrate each evaluated fold.
            for lead, (prediction, observed) in enumerate(zip(pred, actual)):
                prior_errors = errors_by_lead[lead]
                if len(prior_errors) >= 4:
                    radius80 = _conformal_radius(prior_errors, 0.80)
                    radius95 = _conformal_radius(prior_errors, 0.95)
                    calibrated_cov80.append(float(abs(observed - prediction) <= radius80))
                    calibrated_cov95.append(float(abs(observed - prediction) <= radius95))
                prior_errors.append(float(abs(observed - prediction)))

        except Exception:
            continue

    return {
        "mae": float(np.mean(maes)) if maes else np.nan,
        "rmse": float(np.mean(rmses)) if rmses else np.nan,
        "mape": float(np.mean(mapes)) if mapes else np.nan,
        "coverage_80": float(np.mean(calibrated_cov80)) if calibrated_cov80 else np.nan,
        "coverage_95": float(np.mean(calibrated_cov95)) if calibrated_cov95 else np.nan,
        "baseline_mae": float(np.mean(baseline_maes)) if baseline_maes else np.nan,
        "absolute_errors_by_lead": errors_by_lead,
        "n_folds": len(maes),
    }


# ──────────────────────────────────────────────────────────────
# 4. Drought Risk Score  (composite multi-signal)
# ──────────────────────────────────────────────────────────────

def compute_drought_risk_score(
    lst_forecast: np.ndarray,
    lst_clim_mean: float,
    lst_clim_std: float,
    ndvi_forecast: np.ndarray,
    ndvi_clim_mean: float,
    ndvi_clim_std: float,
    smap_forecast: np.ndarray,
    smap_clim_mean: float,
    smap_clim_std: float,
    gpm_forecast: np.ndarray,
    gpm_clim_mean: float,
    gpm_clim_std: float,
    weights: dict = None,
) -> np.ndarray:
    """
    Compute a Drought Risk Score (0–100) for each forecast step.

    Logic:
      - Drought risk rises when:
          * LST > climatology    (hotter than normal → +risk)
          * NDVI < climatology   (less vegetation → +risk)
          * SMAP < climatology   (drier soils → +risk)
          * GPM < climatology    (less rain → +risk)

      - Each signal is standardised to a z-score relative to its
        monthly climatological mean ± std.
      - A positive z-score contribution = more drought-like.
      - Signals are weighted, summed, then logistically scaled to 0–100.

    Weights (default: PDSI-inspired, soil moisture most important):
      LST:  0.20
      NDVI: 0.25
      SMAP: 0.35
      GPM:  0.20

    Returns
    -------
    np.ndarray (h,) — drought risk score per forecast month (0=no risk, 100=extreme)
    """
    if weights is None:
        weights = {"lst": 0.20, "ndvi": 0.25, "smap": 0.35, "gpm": 0.20}

    def safe_z(arr, mean, std):
        if std == 0:
            return np.zeros_like(arr)
        return (arr - mean) / std

    # LST anomaly: above normal = drought signal (+)
    lst_z = safe_z(lst_forecast, lst_clim_mean, lst_clim_std)

    # NDVI anomaly: below normal = drought signal → invert sign
    ndvi_z = -safe_z(ndvi_forecast, ndvi_clim_mean, ndvi_clim_std)

    # SMAP anomaly: below normal = drought signal → invert sign
    smap_z = -safe_z(smap_forecast, smap_clim_mean, smap_clim_std)

    # GPM anomaly: below normal = drought signal → invert sign
    gpm_z = -safe_z(gpm_forecast, gpm_clim_mean, gpm_clim_std)

    # Weighted composite score (raw z-scale)
    composite = (
        weights["lst"] * lst_z
        + weights["ndvi"] * ndvi_z
        + weights["smap"] * smap_z
        + weights["gpm"] * gpm_z
    )

    # Logistic scaling → maps composite z to 0–100
    # centre = 0, scale = 1 → logistic sigmoid, then * 100
    score = 100.0 / (1.0 + np.exp(-composite))

    return score


def drought_risk_label(score: float) -> tuple[str, str]:
    """
    Map a drought risk score to a human-readable label and color.
    Returns (label, hex_color).
    """
    if score >= 75:
        return "🔴 Extreme", "#EF6461"
    elif score >= 60:
        return "🟠 High", "#E9A34B"
    elif score >= 45:
        return "🟡 Moderate", "#F5D842"
    elif score >= 30:
        return "🟢 Low", "#31C48D"
    else:
        return "🔵 Minimal", "#35C9D0"


# ──────────────────────────────────────────────────────────────
# 5. High-Level Forecast Runner
# ──────────────────────────────────────────────────────────────

def run_variable_forecast(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    h: int = 6,
    run_cv: bool = True,
) -> dict:
    """
    Convenience wrapper: fit SeasonalARModel on a single variable and
    return forecast output plus metadata.

    Parameters
    ----------
    df        : DataFrame with date_col and value_col
    date_col  : column with datetime values
    value_col : column with float values
    h         : forecast horizon (months)
    run_cv    : whether to include CV metrics in the result; rolling CV is always
                used to tune the model and calibrate forecast intervals.

    Returns
    -------
    dict with:
      'variable'      : str
      'unit'          : str
      'last_date'     : pd.Timestamp
      'forecast_dates': list of pd.Timestamps for h future months
      'point'         : np.ndarray (h,)
      'lower_80'      : np.ndarray (h,)
      'upper_80'      : np.ndarray (h,)
      'lower_95'      : np.ndarray (h,)
      'upper_95'      : np.ndarray (h,)
      'in_sample_fitted' : np.ndarray
      'historical_values': np.ndarray
      'historical_dates'  : list of pd.Timestamps
      'cv_metrics'    : dict (if run_cv=True)
      'model'         : SeasonalARModel (fitted, for inspection)
    """
    series = (
        df[[date_col, value_col]]
        .dropna()
        .sort_values(date_col)
        .reset_index(drop=True)
    )

    if len(series) < 24:
        raise ValueError(
            f"Need ≥ 24 months of data to forecast, got {len(series)}"
        )

    values = series[value_col].astype(float).values
    dates = pd.to_datetime(series[date_col])
    months = dates.dt.month.values.astype(int)

    model_config = select_model_config(values, months, h=h)
    model = SeasonalARModel(**model_config)
    model.fit(values, months)
    out = model.forecast(h=h)
    cv_metrics = walk_forward_cv(values, months, h=min(6, h))
    errors_by_lead = cv_metrics.get("absolute_errors_by_lead", [])
    for lead in range(min(h, len(errors_by_lead))):
        errors = errors_by_lead[lead]
        if not errors:
            continue
        radius80 = _conformal_radius(errors, 0.80)
        radius95 = _conformal_radius(errors, 0.95)
        bootstrap_radius80 = max(
            out["point"][lead] - out["lower_80"][lead],
            out["upper_80"][lead] - out["point"][lead],
        )
        bootstrap_radius95 = max(
            out["point"][lead] - out["lower_95"][lead],
            out["upper_95"][lead] - out["point"][lead],
        )
        radius80 = max(radius80, bootstrap_radius80)
        radius95 = max(radius95, bootstrap_radius95, radius80)
        out["lower_80"][lead] = out["point"][lead] - radius80
        out["upper_80"][lead] = out["point"][lead] + radius80
        out["lower_95"][lead] = out["point"][lead] - radius95
        out["upper_95"][lead] = out["point"][lead] + radius95

    # Generate future dates
    last_date = dates.iloc[-1]
    forecast_dates = [
        last_date + pd.DateOffset(months=i + 1) for i in range(h)
    ]

    result = {
        "variable": value_col,
        "last_date": last_date,
        "forecast_dates": forecast_dates,
        "historical_dates": list(dates),
        "historical_values": values,
        "model_config": model_config,
        **out,
        "model": model,
    }

    if run_cv:
        result["cv_metrics"] = cv_metrics

    return result


def run_all_forecasts(
    df: pd.DataFrame,
    date_col: str,
    var_config: dict,
    h: int = 6,
    run_cv: bool = False,
) -> dict[str, dict]:
    """
    Run forecast for every variable in var_config.

    Parameters
    ----------
    var_config : dict  {key: {"col": "col_name", "unit": "K", ...}}

    Returns
    -------
    dict {key: run_variable_forecast result}
    """
    results = {}
    for key, meta in var_config.items():
        col = meta.get("col", "")
        if col not in df.columns:
            continue
        try:
            results[key] = run_variable_forecast(
                df, date_col, col, h=h, run_cv=run_cv
            )
            results[key]["unit"] = meta.get("unit", "")
            results[key]["label"] = meta.get("label", key)
            results[key]["emoji"] = meta.get("emoji", "")
        except Exception as e:
            results[key] = {"error": str(e)}
    return results
