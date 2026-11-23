"""Exploratory cross-variable lag model for the Predictive Intelligence page.

The model works on seasonally centred, standardised monthly regional means.
Its links are predictive lead-lag evidence, not proof of physical causation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import f as f_distribution


def prepare_anomaly_matrix(
    frame: pd.DataFrame,
    date_column: str,
    value_columns: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, float], dict[int, dict[str, float]]]:
    """Remove each signal's average calendar-month cycle and scale to SD units."""
    keys = [key for key, column in value_columns.items() if column in frame.columns]
    values = frame[[date_column] + [value_columns[key] for key in keys]].copy()
    values[date_column] = pd.to_datetime(values[date_column], errors="coerce")
    values = values.dropna(subset=[date_column]).sort_values(date_column).reset_index(drop=True)
    values = values.dropna(subset=[value_columns[key] for key in keys]).reset_index(drop=True)
    month_number = values[date_column].dt.month
    anomaly = pd.DataFrame(index=values.index)
    scales: dict[str, float] = {}
    monthly_means: dict[int, dict[str, float]] = {}

    for key in keys:
        column = value_columns[key]
        monthly_mean = values.groupby(month_number)[column].mean()
        centered = values[column] - month_number.map(monthly_mean)
        scale = float(centered.std(ddof=1))
        if not np.isfinite(scale) or scale <= 1e-12:
            continue
        anomaly[key] = centered / scale
        scales[key] = scale
        for month, mean in monthly_mean.items():
            monthly_means.setdefault(int(month), {})[key] = float(mean)

    anomaly = anomaly.dropna(axis=1).dropna().reset_index(drop=True)
    return anomaly, scales, monthly_means


def _lag_design(values: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    rows, targets = [], []
    for index in range(lags, len(values)):
        rows.append(np.concatenate([values[index - lag] for lag in range(1, lags + 1)]))
        targets.append(values[index])
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def fit_ridge_var(values: np.ndarray, lags: int = 3, alpha: float = 1.0) -> dict:
    """Fit an interpretable, ridge-regularised VAR(p) using NumPy."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or len(values) <= lags + values.shape[1] * lags + 5:
        raise ValueError("Not enough complete monthly rows for the selected lag model.")
    design, targets = _lag_design(values, lags)
    design = np.column_stack([np.ones(len(design)), design])
    penalty = np.eye(design.shape[1], dtype=float) * alpha
    penalty[0, 0] = 0.0  # do not shrink intercept
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ targets)
    return {"coefficients": coefficients, "lags": lags, "n_signals": values.shape[1]}


def forecast_var(
    model: dict,
    history: np.ndarray,
    steps: int,
    intervention: tuple[int, int, float] | None = None,
) -> np.ndarray:
    """Forecast all signals; optionally set (step, signal-index, z-value) once."""
    coefficients = model["coefficients"]
    lags = int(model["lags"])
    path = [row.copy() for row in np.asarray(history, dtype=float)[-lags:]]
    output = []
    for step in range(steps):
        lag_features = np.concatenate([path[-lag] for lag in range(1, lags + 1)])
        next_row = np.r_[1.0, lag_features] @ coefficients
        if intervention is not None and step == intervention[0]:
            next_row[intervention[1]] = intervention[2]
        output.append(next_row.copy())
        path.append(next_row)
    return np.asarray(output)


def granger_screen(values: np.ndarray, names: list[str], lags: int = 3) -> pd.DataFrame:
    """Conditional Granger screen: does source history add predictive value for target?"""
    values = np.asarray(values, dtype=float)
    n_rows, n_signals = values.shape
    if n_rows <= n_signals * lags + lags + 8:
        return pd.DataFrame(columns=["source", "target", "f_stat", "p_value", "q_value"])

    design, targets = _lag_design(values, lags)
    # Regressor metadata follows the exact [lag 1 all signals, lag 2 all signals, ...] layout.
    metadata = [(signal_index, lag) for lag in range(1, lags + 1) for signal_index in range(n_signals)]
    results = []
    n_obs = len(targets)

    for target_index, target_name in enumerate(names):
        for source_index, source_name in enumerate(names):
            if source_index == target_index:
                continue
            full_columns = np.arange(design.shape[1])
            keep = np.array([
                index for index, (signal_index, _lag) in enumerate(metadata)
                if signal_index != source_index
            ], dtype=int)
            y = targets[:, target_index]
            reduced_x = np.column_stack([np.ones(n_obs), design[:, keep]])
            full_x = np.column_stack([np.ones(n_obs), design])
            reduced_coef = np.linalg.lstsq(reduced_x, y, rcond=None)[0]
            full_coef = np.linalg.lstsq(full_x, y, rcond=None)[0]
            rss_reduced = float(np.sum((y - reduced_x @ reduced_coef) ** 2))
            rss_full = float(np.sum((y - full_x @ full_coef) ** 2))
            df_num = lags
            df_den = n_obs - full_x.shape[1]
            if df_den <= 0 or rss_full <= 1e-14:
                f_stat, p_value = 0.0, 1.0
            else:
                f_stat = max(0.0, ((rss_reduced - rss_full) / df_num) / (rss_full / df_den))
                p_value = float(f_distribution.sf(f_stat, df_num, df_den))
            results.append({
                "source": source_name,
                "target": target_name,
                "f_stat": f_stat,
                "p_value": p_value,
            })

    # Benjamini-Hochberg correction across all directed pairs.
    p_values = np.asarray([row["p_value"] for row in results], dtype=float)
    order = np.argsort(p_values)
    q_values = np.empty_like(p_values)
    running_min = 1.0
    total_tests = len(p_values)
    for rank_index in range(total_tests - 1, -1, -1):
        original_index = order[rank_index]
        adjusted = p_values[original_index] * total_tests / (rank_index + 1)
        running_min = min(running_min, adjusted)
        q_values[original_index] = min(1.0, running_min)
    for row, q_value in zip(results, q_values):
        row["q_value"] = float(q_value)
    return pd.DataFrame(results).sort_values("q_value").reset_index(drop=True)
