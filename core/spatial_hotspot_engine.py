"""DBSCAN micro-hotspot clustering for coordinate-tagged satellite anomaly pixels."""

from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import transform, unary_union
from sklearn.cluster import DBSCAN


_TO_WGS84 = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)


def cluster_spatial_anomaly_points(
    events: pd.DataFrame,
    month: str | None,
    variable: str,
    direction: str,
    threshold_z: float = 3.5,
    eps_km: float = 13.0,
    min_samples: int = 3,
    min_recurrence_months: int = 2,
    boundaries: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Cluster thresholded monthly or recurring anomaly pixels using projected DBSCAN.

    Clustering happens per signal and anomaly direction, so unrelated signals
    cannot merge into one hotspot. If `month` is None, only pixels anomalous
    in at least `min_recurrence_months` unique months are retained. Coordinates
    are EPSG:6933 equal-area metres; the native pixel spacing is about 9 km.
    """
    z_column = f"{variable}_robust_z"
    required = {"month", "row", "column", "x_epsg6933", "y_epsg6933", z_column}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Spatial anomaly data is missing fields: {', '.join(sorted(missing))}")
    if direction not in {"POSITIVE", "NEGATIVE"}:
        raise ValueError("Direction must be POSITIVE or NEGATIVE.")

    if month is None:
        selected = events.copy()
    else:
        month_text = str(month)[:7]
        selected = events.loc[events["month"].astype(str).str[:7] == month_text].copy()
    selected[z_column] = pd.to_numeric(selected[z_column], errors="coerce")
    if direction == "POSITIVE":
        selected = selected.loc[selected[z_column] >= float(threshold_z)]
    else:
        selected = selected.loc[selected[z_column] <= -float(threshold_z)]
    selected = selected.dropna(subset=["x_epsg6933", "y_epsg6933", z_column])

    empty_columns = [
        "hotspot_id", "district", "pixel_count", "mean_robust_z",
        "mean_abs_robust_z", "max_abs_robust_z", "area_km2",
        "centroid_lon", "centroid_lat", "geometry",
    ]
    if selected.empty:
        return gpd.GeoDataFrame(columns=empty_columns, geometry="geometry", crs="EPSG:4326")

    # Each grid cell is one sample, even if a source export contains duplicates.
    aggregate = {
        "x_epsg6933": ("x_epsg6933", "mean"),
        "y_epsg6933": ("y_epsg6933", "mean"),
        "robust_z": (z_column, "mean"),
        "month_count": ("month", "nunique"),
    }
    if "if_anomaly_2pct" in selected.columns:
        aggregate["if_flagged"] = ("if_anomaly_2pct", "max")
    selected = selected.groupby(["row", "column"], as_index=False).agg(**aggregate)
    if month is None:
        selected = selected.loc[selected["month_count"] >= int(min_recurrence_months)]
    else:
        selected["month_count"] = 1
    if selected.empty:
        return gpd.GeoDataFrame(columns=empty_columns, geometry="geometry", crs="EPSG:4326")

    coordinates = selected[["x_epsg6933", "y_epsg6933"]].to_numpy(dtype=float)
    labels = DBSCAN(
        eps=float(eps_km) * 1000.0,
        min_samples=int(min_samples),
        metric="euclidean",
        algorithm="kd_tree",
    ).fit_predict(coordinates)
    selected["cluster"] = labels
    selected = selected.loc[selected["cluster"] >= 0]
    if selected.empty:
        return gpd.GeoDataFrame(columns=empty_columns, geometry="geometry", crs="EPSG:4326")

    # Derive square native-cell footprints from repeated projected grid centres.
    x_centres = np.sort(events["x_epsg6933"].dropna().unique().astype(float))
    y_centres = np.sort(events["y_epsg6933"].dropna().unique().astype(float))
    dx = float(np.median(np.diff(x_centres))) if len(x_centres) > 1 else 9008.05
    dy = float(np.median(np.diff(y_centres))) if len(y_centres) > 1 else 9008.05
    if not np.isfinite(dx) or dx <= 0:
        dx = 9008.05
    if not np.isfinite(dy) or dy <= 0:
        dy = 9008.05

    projected_boundaries = None
    if boundaries is not None and not boundaries.empty:
        projected_boundaries = boundaries.to_crs("EPSG:6933")

    records = []
    for component_id, pixels in selected.groupby("cluster", sort=True):
        cell_polygons = [
            box(x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2)
            for x, y in pixels[["x_epsg6933", "y_epsg6933"]].itertuples(index=False, name=None)
        ]
        projected_footprint = unary_union(cell_polygons)
        footprint = transform(
            _TO_WGS84.transform,
            projected_footprint.segmentize(max(dx, dy) / 4),
        )
        center_projected = projected_footprint.centroid
        center_lon, center_lat = _TO_WGS84.transform(center_projected.x, center_projected.y)
        district = "Outside mapped districts"
        if projected_boundaries is not None:
            point = Point(center_projected.x, center_projected.y)
            for _, boundary in projected_boundaries.iterrows():
                if boundary.geometry.covers(point):
                    district = str(boundary["district_name"])
                    break

        z_values = pixels["robust_z"].to_numpy(dtype=float)
        records.append({
            "component_id": int(component_id),
            "district": district,
            "pixel_count": int(len(pixels)),
            "anomaly_pixel_months": int(pixels["month_count"].sum()),
            "mean_months_flagged": float(pixels["month_count"].mean()),
            "mean_robust_z": float(np.mean(z_values)),
            "mean_abs_robust_z": float(np.mean(np.abs(z_values))),
            "max_abs_robust_z": float(np.max(np.abs(z_values))),
            "if_flagged_pct": (
                float(pixels["if_flagged"].mean() * 100)
                if "if_flagged" in pixels.columns else np.nan
            ),
            "area_km2": float(projected_footprint.area / 1_000_000),
            "centroid_lon": float(center_lon),
            "centroid_lat": float(center_lat),
            "geometry": footprint,
        })

    records.sort(key=lambda row: (row["pixel_count"], row["mean_abs_robust_z"]), reverse=True)
    for rank, row in enumerate(records, start=1):
        row["hotspot_id"] = f"H{rank:02d}"
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
