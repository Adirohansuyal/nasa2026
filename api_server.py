"""API proxy for OpenRouter explanations and local land-cover map overlays."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

load_dotenv()

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 12
_MAX_PROMPT_CHARS = 30_000
_request_times: dict[str, deque[float]] = defaultdict(deque)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "earthpulse-explainer"})



_EE_PROJECT = "gen-lang-client-0039569301"
_DYNAMIC_WORLD_ID = "GOOGLE/DYNAMICWORLD/V1"
_GAUL_DISTRICTS_ID = "FAO/GAUL/2025/level2"
_LANDCOVER_CLASSES = [
    ("Water", 0, "#005A9C"), ("Tree cover", 1, "#006B3C"),
    ("Grassland", 2, "#A6BF00"), ("Flooded vegetation", 3, "#8C4FA3"),
    ("Cropland", 4, "#D88700"), ("Shrubland", 5, "#88532D"),
    ("Built-up", 6, "#C13728"), ("Bare / sparse vegetation", 7, "#777777"),
    ("Snow / ice", 8, "#A4CFE3"),
]
_UTTARAKHAND_DISTRICTS = {
    "Almora", "Bageshwar", "Chamoli", "Champawat", "Dehradun", "Haridwar",
    "Nainital", "Pauri Garhwal", "Pithoragarh", "Rudraprayag", "Tehri Garhwal",
    "Udham Singh Nagar", "Uttarkashi",
}
_landcover_map_cache: dict[tuple[str, int], tuple[float, dict]] = {}


def _build_landcover_timeline(district_name: str, class_index: int) -> dict:
    import base64
    import json
    from io import BytesIO
    from pathlib import Path

    import numpy as np
    import rasterio
    from PIL import Image
    from rasterio.mask import mask
    from rasterio.warp import transform_bounds, transform_geom
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    map_dir = Path(__file__).resolve().parent / "research" / "data" / "dynamic_world_maps"
    boundary_file = map_dir / "districts.geojson"
    if not boundary_file.exists():
        raise FileNotFoundError("Offline map boundaries are missing from research/data/dynamic_world_maps.")
    features = json.loads(boundary_file.read_text())["features"]
    if district_name == "Uttarakhand":
        geometry = mapping(unary_union([shape(feature["geometry"]) for feature in features]))
    else:
        feature = next((item for item in features if item["properties"].get("GAUL2_NAME") == district_name), None)
        if feature is None:
            raise ValueError("The selected district is not available in the local boundaries.")
        geometry = feature["geometry"]

    class_color = _LANDCOVER_CLASSES[class_index][2]
    stable_color = (236, 0, 140)
    palette = [tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) for _, _, color in _LANDCOVER_CLASSES]
    palette.extend([stable_color, (0, 214, 107), (0, 207, 255)])
    years = list(range(2015, 2026))
    annual_labels = {}
    bounds = None
    projected_geometry = None
    for year in years:
        raster_path = map_dir / f"dynamic_world_label_{year}.tif"
        if not raster_path.exists():
            raise FileNotFoundError(f"Offline annual map for {year} is missing.")
        with rasterio.open(raster_path) as source:
            if projected_geometry is None:
                projected_geometry = transform_geom("EPSG:4326", source.crs, geometry)
            cropped, transform = mask(source, [projected_geometry], crop=True, filled=True, nodata=255)
            annual_labels[year] = cropped[0]
            if bounds is None:
                bounds = transform_bounds(source.crs, "EPSG:4326", *rasterio.transform.array_bounds(
                    cropped.shape[1], cropped.shape[2], transform
                ))

    maps = {}
    for index, year in enumerate(years):
        labels = annual_labels[year]
        display = np.where(labels < 9, labels, 255).astype(np.uint8)
        current = labels == class_index
        if index == 0:
            display[current] = 9
        else:
            previous = annual_labels[years[index - 1]]
            valid = (labels < 9) & (previous < 9)
            display[valid & current & (previous == class_index)] = 9
            display[valid & current & (previous != class_index)] = 10
            display[valid & ~current & (previous == class_index)] = 11
        rgba = np.zeros((*display.shape, 4), dtype=np.uint8)
        for code, color in enumerate(palette):
            rgba[display == code, :3] = color
            rgba[display == code, 3] = 255
        image = Image.fromarray(rgba, mode="RGBA")
        image.thumbnail((1200, 1200), Image.Resampling.NEAREST)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        maps[str(year)] = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    center = list(shape(geometry).centroid.coords[0])
    return {
        "district": district_name,
        "classIndex": class_index,
        "classColor": class_color,
        "stableColor": "#EC008C",
        "years": years,
        "maps": maps,
        "bounds": [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
        "outline": {"type": "Feature", "geometry": geometry, "properties": {"district": district_name}},
        "center": center,
    }


def _get_landcover_timeline(district_name: str, class_index: int) -> dict:
    key = (district_name, class_index)
    cached = _landcover_map_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < 1500:
        return cached[1]
    result = _build_landcover_timeline(district_name, class_index)
    _landcover_map_cache[key] = (now, result)
    return result


async def landcover_map_timeline(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Send a JSON object with district and classIndex."}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Send a JSON object with district and classIndex."}, status_code=400)
    district = payload.get("district")
    class_index = payload.get("classIndex")
    color = payload.get("classColor")
    if district not in _UTTARAKHAND_DISTRICTS | {"Uttarakhand"}:
        return JSONResponse({"error": "Choose a valid Uttarakhand district."}, status_code=400)
    if isinstance(class_index, bool) or not isinstance(class_index, int) or not 0 <= class_index < len(_LANDCOVER_CLASSES):
        return JSONResponse({"error": "Choose one of the nine Dynamic World classes."}, status_code=400)
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return JSONResponse({"error": "A valid class color is required."}, status_code=400)
    try:
        result = await run_in_threadpool(_get_landcover_timeline, district, class_index)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception:
        return JSONResponse({"error": "The local Dynamic World map files could not be read. Check research/data/dynamic_world_maps."}, status_code=503)
    return JSONResponse(result)

async def explain(request: Request) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = _request_times[client_ip]
    while recent and now - recent[0] > _WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= _MAX_REQUESTS_PER_WINDOW:
        return JSONResponse({"error": "Too many explanation requests. Please wait a minute."}, status_code=429)
    recent.append(now)

    if request.headers.get("content-length", "0").isdigit() and int(request.headers["content-length"]) > 32_000:
        return JSONResponse({"error": "The explanation context is too large."}, status_code=413)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Send a JSON object containing a prompt."}, status_code=400)
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > _MAX_PROMPT_CHARS:
        return JSONResponse({"error": "The explanation prompt is missing or too long."}, status_code=400)

    try:
        from core.openrouter_client import explain_text

        answer = await run_in_threadpool(
            explain_text,
            prompt.strip(),
            500,
            "You explain Earth observation statistics to the public. Use only supplied evidence. "
            "Never claim correlation proves causation, never invent measurements, and clearly state "
            "when evidence is weak, mixed, or insufficient. Write in clear, concise Hinglish when asked.",
        )
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY" in str(exc):
            return JSONResponse({"error": "OpenRouter is not configured on the server."}, status_code=503)
        return JSONResponse({"error": "The explanation service is not configured."}, status_code=503)
    except Exception as exc:
        # Preserve actionable provider status codes without returning raw provider
        # payloads or credentials to the browser.
        provider_response = getattr(exc, "response", None)
        provider_status = getattr(provider_response, "status_code", None)
        if provider_status == 402:
            return JSONResponse(
                {"error": "AI credits are temporarily unavailable. Please retry later."},
                status_code=402,
            )
        if provider_status == 429:
            return JSONResponse(
                {"error": "The AI service is busy. Please wait a moment and retry."},
                status_code=429,
            )
        return JSONResponse({"error": "OpenRouter could not generate an explanation right now."}, status_code=502)
    return JSONResponse({"answer": answer})


allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "EARTHPULSE_ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
]

app = Starlette(routes=[Route("/health", health, methods=["GET"]), Route("/api/explain", explain, methods=["POST"]), Route("/api/landcover/map-timeline", landcover_map_timeline, methods=["POST"])])
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
