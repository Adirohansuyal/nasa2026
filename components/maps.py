"""
Premium Map Components for EARTHPULSE-X
========================================
- Satellite data rendered on geographic coordinates (lat/lon)
- Choropleth maps with district boundaries
- Side-by-side comparison maps
"""

import numpy as np
import pandas as pd
import xarray as xr
import plotly.graph_objects as go
import plotly.express as px
import pyproj
from functools import lru_cache

from config import BOUNDARIES_DIR

# EPSG:6933 → EPSG:4326 transformer (equal-area → lat/lon)
_TRANSFORMER = pyproj.Transformer.from_crs(
    "EPSG:6933", "EPSG:4326", always_xy=True
)

# ──────────────────────────────────────────────────────────────
# 1. Satellite Layer — render NetCDF data on geographic map
# ──────────────────────────────────────────────────────────────

# Color scales per variable type
VAR_COLORSCALES = {
    "lst": ("YlOrRd", "Land Surface Temperature (K)"),
    "ndvi": ("YlGn", "Vegetation Index (NDVI)"),
    "smap_am": ("YlGnBu", "Morning Soil Moisture (m³/m³)"),
    "smap_pm": ("YlGnBu", "Evening Soil Moisture (m³/m³)"),
    "gpm_monthly_precipitation": ("Cividis", "Monthly Precipitation (mm)"),
}

VAR_LABELS = {
    "lst": "🌡️ Land Surface Temperature",
    "ndvi": "🌿 Vegetation Index (NDVI)",
    "smap_am": "💧 Morning Soil Moisture",
    "smap_pm": "💧 Evening Soil Moisture",
    "gpm_monthly_precipitation": "🌧️ Precipitation",
}

VAR_UNITS = {
    "lst": "K",
    "ndvi": "",
    "smap_am": "m³/m³",
    "smap_pm": "m³/m³",
    "gpm_monthly_precipitation": "mm",
}


def satellite_layer(
    ds: xr.Dataset,
    variable: str,
    quality: str = "strict",
    show_valid_mask: bool = False,
    month_key: str = "",
) -> go.Figure:
    """
    Render a satellite data variable on a geographic map.

    Converts EPSG:6933 projected coordinates to lat/lon for
    proper geographic display with district boundary overlay.

    Parameters
    ----------
    ds : xarray Dataset with x, y coordinates (EPSG:6933)
    variable : base variable name (e.g. 'lst', 'ndvi', 'smap_am')
    quality : 'strict' or 'relaxed'
    show_valid_mask : if True, overlay valid/invalid pixel grid
    """
    var_name = f"{variable}_{quality}" if variable not in [
        "gpm_monthly_precipitation"
    ] else "gpm_monthly_precipitation"

    if var_name not in ds.data_vars:
        # Try without quality suffix for GPM
        if variable == "gpm_monthly_precipitation":
            var_name = "gpm_monthly_precipitation"
        else:
            var_name = variable

    data = ds[var_name].load()

    # Get coordinate arrays
    x_vals = ds["x"].values
    y_vals = ds["y"].values

    # Create meshgrid and transform to lat/lon
    X, Y = np.meshgrid(x_vals, y_vals)
    lon, lat = _TRANSFORMER.transform(X, Y)

    values = data.values

    # Valid mask
    valid_var = f"{var_name}_valid"
    if valid_var in ds.data_vars:
        mask = ds[valid_var].values
    else:
        mask = ~np.isnan(values)

    # Apply mask — set invalid pixels to NaN
    plot_values = np.where(mask == 1, values, np.nan)

    colorscale, title = VAR_COLORSCALES.get(
        variable, ("Viridis", var_name)
    )
    unit = VAR_UNITS.get(variable, "")
    label = VAR_LABELS.get(variable, variable)

    fig = go.Figure()

    # Main heatmap layer
    fig.add_trace(go.Heatmap(
        z=plot_values,
        x=lon[0, :],  # lon varies along x axis
        y=lat[:, 0],  # lat varies along y axis
        uid=f"satellite-raster-{variable}-{quality}",
        colorscale=colorscale,
        colorbar=dict(
            title=dict(text=f"{title}", font=dict(size=13)),
            thickness=12,
            len=0.7,
            x=1.02,
        ),
        hovertemplate=(
            f"<b>{label}</b><br>"
            f"Lon: %{{x:.3f}}<br>"
            f"Lat: %{{y:.3f}}<br>"
            f"Value: %{{z:.3f}} {unit}<br>"
            "<extra></extra>"
        ),
        zsmooth="best",
    ))

    # Optional: valid/invalid mask overlay
    if show_valid_mask:
        mask_for_scatter = np.where(mask == 0, 1, np.nan)
        fig.add_trace(go.Heatmap(
            z=mask_for_scatter,
            x=lon[0, :],
            y=lat[:, 0],
            colorscale=[[0, "rgba(239,100,97,0.3)"], [1, "rgba(239,100,97,0.3)"]],
            showscale=False,
            hovertemplate="No data<extra></extra>",
            zsmooth=False,
        ))

    # Try to overlay district boundaries
    _add_boundaries(fig)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,16,32,0.8)",
        font=dict(family="Urbanist, sans-serif", size=12, color="#AAB8CC"),
        height=580,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(
            title="Longitude",
            gridcolor="#1E2D4A",
            zeroline=False,
        ),
        yaxis=dict(
            title="Latitude",
            gridcolor="#1E2D4A",
            zeroline=False,
            scaleanchor="x",
            scaleratio=1,
        ),
        showlegend=False,
        uirevision=f"earth-observation-{variable}-{quality}-{month_key}",
        transition={"duration": 850, "easing": "cubic-in-out"},
    )

    return fig


@lru_cache(maxsize=1)
def _load_district_boundaries():
    """Read and project Uttarakhand district boundaries once per process."""
    try:
        import geopandas as gpd

        boundary_file = BOUNDARIES_DIR / "uttarakhand_13_districts.geojson"
        if not boundary_file.exists():
            return None

        gdf = gpd.read_file(boundary_file, engine="pyogrio")
        if gdf.crs and gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        return gdf
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_study_area_geometry():
    """Cache the merged study boundary used to mask pixels outside Uttarakhand."""
    boundaries = _load_district_boundaries()
    return boundaries.geometry.union_all() if boundaries is not None else None


def _add_boundaries(fig: go.Figure):
    """Overlay cached Uttarakhand district boundaries on a map."""
    gdf = _load_district_boundaries()
    if gdf is None:
        return

    trace_index = 0
    for _, row in gdf.iterrows():
        geom = row["geometry"]
        if geom.geom_type == "Polygon":
            polygons = [geom]
        elif geom.geom_type == "MultiPolygon":
            polygons = list(geom.geoms)
        else:
            continue

        for poly in polygons:
            x, y = poly.exterior.xy
            fig.add_trace(go.Scatter(
                x=list(x),
                y=list(y),
                mode="lines",
                uid=f"district-boundary-{trace_index}",
                line=dict(color="rgba(241,245,252,0.3)", width=1),
                hoverinfo="skip",
                showlegend=False,
            ))
            trace_index += 1


def spatial_hotspot_map(
    hotspots,
    month_label: str,
    variable_label: str,
    direction: str,
) -> go.Figure:
    """Render exact clustered pixel footprints, centroids, and district outlines."""
    fig = go.Figure()
    positive = str(direction).upper() == "POSITIVE"
    fill_color = "rgba(239,100,97,0.24)" if positive else "rgba(99,169,232,0.25)"
    outline_color = "#EF6461" if positive else "#63A9E8"

    for row in hotspots.itertuples(index=False):
        geometry = row.geometry
        polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        for polygon in polygons:
            lon, lat = polygon.exterior.xy
            fig.add_trace(go.Scatter(
                x=list(lon), y=list(lat), mode="lines", fill="toself",
                fillcolor=fill_color,
                line={"color": outline_color, "width": 1.2},
                name="Clustered anomalous pixels",
                legendgroup="hotspot-footprints",
                showlegend=False,
                hoverinfo="skip",
            ))

    _add_boundaries(fig)
    if not hotspots.empty:
        marker_size = np.clip(7 + np.sqrt(hotspots["pixel_count"].to_numpy(dtype=float)) * 1.7, 9, 25)
        fig.add_trace(go.Scatter(
            x=hotspots["centroid_lon"],
            y=hotspots["centroid_lat"],
            mode="markers+text",
            text=hotspots["hotspot_id"],
            textposition="top center",
            textfont={"family": "Urbanist, sans-serif", "size": 10, "color": "#F1F5FC"},
            marker={
                "size": marker_size,
                "color": hotspots["mean_abs_robust_z"],
                "colorscale": "YlOrRd" if positive else "Blues",
                "cmin": 3.5,
                "cmax": max(5.0, float(hotspots["mean_abs_robust_z"].max())),
                "showscale": True,
                "colorbar": {"title": "Mean |robust z|", "thickness": 13, "len": 0.68},
                "line": {"color": "#F1F5FC", "width": 1},
                "opacity": 0.96,
            },
            customdata=np.column_stack([
                hotspots["district"].astype(str),
                hotspots["pixel_count"].astype(str),
                hotspots["mean_robust_z"].map(lambda value: f"{value:+.2f}").to_numpy(),
                hotspots["max_abs_robust_z"].map(lambda value: f"{value:.2f}").to_numpy(),
                hotspots["area_km2"].map(lambda value: f"{value:.1f}").to_numpy(),
                hotspots["mean_months_flagged"].map(lambda value: f"{value:.1f}").to_numpy(),
            ]),
            hovertemplate=(
                "<b>%{text}</b> · %{customdata[0]}<br>"
                "Pixels in cluster: %{customdata[1]}<br>"
                "Mean anomaly: %{customdata[2]}σ<br>"
                "Strongest pixel: %{customdata[3]}σ<br>"
                "Approx. footprint: %{customdata[4]} km²<br>"
                "Average months flagged per cell: %{customdata[5]}<extra></extra>"
            ),
            name="Hotspot centre",
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,16,32,0.82)",
        font={"family": "Urbanist, sans-serif", "size": 12, "color": "#AAB8CC"},
        title={"text": f"{month_label} · {variable_label} · {direction.title()} anomalies", "x": 0.02},
        height=610,
        margin={"l": 55, "r": 90, "t": 55, "b": 48},
        xaxis={"title": "Longitude", "range": [77.25, 81.5], "gridcolor": "rgba(42,63,95,.45)"},
        yaxis={"title": "Latitude", "range": [28.65, 31.65], "scaleanchor": "x", "scaleratio": 1, "gridcolor": "rgba(42,63,95,.45)"},
        showlegend=False,
        uirevision=f"hotspots-{month_label}-{variable_label}-{direction}",
    )
    return fig


def comparison_layers(
    ds: xr.Dataset,
    var1: str,
    var2: str,
    quality: str = "strict",
) -> tuple:
    """
    Create two side-by-side satellite layer figures.
    Returns (fig1, fig2) for display in columns.
    """
    fig1 = satellite_layer(ds, var1, quality)
    fig2 = satellite_layer(ds, var2, quality)
    return fig1, fig2


# ──────────────────────────────────────────────────────────────
# 2. Choropleth Map — district-level data
# ──────────────────────────────────────────────────────────────

DISTRICT_COLORS = [
    [0.0, "#0A2540"],
    [0.15, "#123B52"],
    [0.35, "#167D91"],
    [0.55, "#35C9D0"],
    [0.70, "#E6B84C"],
    [0.85, "#F07835"],
    [1.0, "#E23D4D"],
]


def choropleth_map(
    gdf,
    color_column: str,
    title: str = "",
    color_label: str = "",
    range_color=None,
    highlight_district: str = None,
) -> go.Figure:
    """
    Premium choropleth map from GeoDataFrame.

    Parameters
    ----------
    gdf : GeoDataFrame with district_name and geometry
    color_column : column to color by
    title : map title
    color_label : colorbar label
    range_color : (min, max) tuple for color scale
    highlight_district : district name to highlight with white border
    """
    fig = px.choropleth(
        gdf,
        geojson=gdf.geometry.__geo_interface__,
        locations=gdf.index,
        featureidkey="id",
        color=color_column,
        color_continuous_scale=DISTRICT_COLORS,
        range_color=range_color,
        hover_name="district_name",
    )

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        bgcolor="rgba(0,0,0,0)",
    )

    # District labels
    label_points = gdf.to_crs("EPSG:32644").copy()
    label_points["geometry"] = label_points.geometry.representative_point()
    label_points = label_points.to_crs("EPSG:4326")

    fig.add_scattergeo(
        lon=label_points.geometry.x,
        lat=label_points.geometry.y,
        text=label_points["district_name"],
        mode="text",
        textfont=dict(size=10, color="rgba(241,245,252,0.9)", family="Urbanist"),
        showlegend=False,
        hoverinfo="skip",
    )

    # Highlight selected district
    if highlight_district and highlight_district in gdf["district_name"].values:
        sel_geom = gdf.loc[
            gdf["district_name"] == highlight_district, "geometry"
        ].iloc[0]

        if sel_geom.geom_type == "Polygon":
            polys = [sel_geom]
        elif sel_geom.geom_type == "MultiPolygon":
            polys = list(sel_geom.geoms)
        else:
            polys = []

        for poly in polys:
            x, y = poly.exterior.xy
            fig.add_scattergeo(
                lon=list(x),
                lat=list(y),
                mode="lines",
                line=dict(color="#FFFFFF", width=3),
                showlegend=False,
                hoverinfo="skip",
            )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,16,32,0.5)",
        font=dict(family="Urbanist, sans-serif", size=12, color="#AAB8CC"),
        height=680,
        margin=dict(l=10, r=10, t=30, b=10),
        coloraxis_colorbar=dict(
            title=dict(text=color_label, font=dict(size=13)),
            thickness=12,
            len=0.6,
            x=1.02,
        ),
    )

    return fig


# ──────────────────────────────────────────────────────────────
# 3. Validity Grid — pixel-level observation coverage
# ──────────────────────────────────────────────────────────────

def validity_statistics(
    ds: xr.Dataset,
    variable: str,
    quality: str = "strict",
) -> tuple[int, int, float, np.ndarray]:
    """Return valid cells, study-area cells, coverage percentage, and in-area mask."""
    var_name = f"{variable}_{quality}_valid" if variable != "gpm_monthly_precipitation" else "gpm_monthly_precipitation_valid"
    if var_name not in ds.data_vars:
        var_name = f"{variable}_{quality}"
    mask = ds[var_name].load()
    x_vals = ds["x"].values
    y_vals = ds["y"].values
    X, Y = np.meshgrid(x_vals, y_vals)
    lon, lat = _TRANSFORMER.transform(X, Y)
    mask_values = mask.values
    region_mask = np.ones(mask_values.shape, dtype=bool)
    study_geometry = _load_study_area_geometry()
    if study_geometry is not None:
        try:
            from shapely import contains_xy

            region_mask = contains_xy(study_geometry, lon, lat)
        except Exception:
            pass
    total = int(np.count_nonzero(region_mask))
    valid = int(np.count_nonzero(region_mask & (mask_values == 1)))
    coverage = valid / total * 100 if total else 0.0
    return valid, total, coverage, region_mask


def validity_grid(
    ds: xr.Dataset,
    variable: str,
    quality: str = "strict",
    month_label: str | None = None,
) -> go.Figure:
    """
    Render binary validity mask on geographic coordinates.
    Teal = valid data, red = no data within the study boundary.
    """
    var_name = f"{variable}_{quality}_valid" if variable != "gpm_monthly_precipitation" else "gpm_monthly_precipitation_valid"
    if var_name not in ds.data_vars:
        var_name = f"{variable}_{quality}"
    mask = ds[var_name].load()
    x_vals = ds["x"].values
    y_vals = ds["y"].values
    X, Y = np.meshgrid(x_vals, y_vals)
    lon, lat = _TRANSFORMER.transform(X, Y)
    mask_values = mask.values

    # Pixels outside the district boundary are outside the study area, not data gaps.
    region_mask = np.ones(mask_values.shape, dtype=bool)
    study_geometry = _load_study_area_geometry()
    if study_geometry is not None:
        try:
            from shapely import contains_xy

            region_mask = contains_xy(study_geometry, lon, lat)
        except Exception:
            pass

    fig = go.Figure()

    # Missing pixels inside the study area (red)
    fig.add_trace(go.Heatmap(
        z=np.where(region_mask & (mask_values != 1), 0.5, np.nan),
        x=lon[0, :],
        y=lat[:, 0],
        uid="validity-missing-pixels",
        colorscale=[[0, "rgba(239,100,97,0.25)"], [1, "rgba(239,100,97,0.25)"]],
        showscale=False,
        zsmooth=False,
        hoverinfo="skip",
    ))

    # Valid pixels inside the study area (teal)
    fig.add_trace(go.Heatmap(
        z=np.where(region_mask & (mask_values == 1), 0.5, np.nan),
        x=lon[0, :],
        y=lat[:, 0],
        uid="validity-valid-pixels",
        colorscale=[[0, "rgba(53,201,208,0.15)"], [1, "rgba(53,201,208,0.15)"]],
        showscale=False,
        zsmooth=False,
        hoverinfo="skip",
    ))

    # Grid lines for pixel boundaries
    for i in range(0, len(y_vals), 2):
        lon_row = np.where(region_mask[i, :], lon[i, :], np.nan)
        lat_row = np.where(region_mask[i, :], lat[i, 0], np.nan)
        fig.add_trace(go.Scatter(
            x=lon_row, y=lat_row,
            mode="lines",
            uid=f"validity-grid-row-{i}",
            line=dict(color="rgba(30,45,74,0.3)", width=0.5),
            hoverinfo="skip",
            showlegend=False,
        ))

    _add_boundaries(fig)

    total = int(np.count_nonzero(region_mask))
    valid = int(np.count_nonzero(region_mask & (mask_values == 1)))
    coverage = valid / total * 100 if total else 0.0

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(10,16,32,0.8)",
        font=dict(family="Urbanist, sans-serif", size=12, color="#AAB8CC"),
        height=520,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="Longitude", gridcolor="#1E2D4A"),
        yaxis=dict(title="Latitude", gridcolor="#1E2D4A", scaleanchor="x", scaleratio=1),
        showlegend=False,
        uirevision=f"validity-{variable}-{quality}-{month_label or ''}",
        transition={"duration": 850, "easing": "cubic-in-out"},
        annotations=[
            dict(
                x=0.02, y=0.98,
                xref="paper", yref="paper",
                text=(
                    f"📅 {month_label}  ·  " if month_label else ""
                ) + f"✅ Valid in Uttarakhand: {valid} ({coverage:.1f}%)  ·  ❌ Missing: {total - valid}",
                showarrow=False,
                font=dict(size=13, color="#AAB8CC", family="Urbanist"),
                bgcolor="rgba(15,26,46,0.8)",
                bordercolor="#1E2D4A",
                borderwidth=1,
                borderpad=8,
            )
        ],
    )

    return fig
