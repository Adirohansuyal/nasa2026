"""API proxy for OpenRouter explanations and local land-cover map overlays."""

from __future__ import annotations

import os
import re
import time
import math
import statistics
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
from collections import defaultdict, deque

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

load_dotenv()

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 12
_MAX_PROMPT_CHARS = 30_000
# NASA FIRMS key for the local Uttarakhand globe proxy. Keep this server-side;
# the browser calls /api/firms/uttarakhand and never receives the key.
FIRMS_MAP_KEY = "90892aa833cf04bc64aee72e572fd93b"
_request_times: dict[str, deque[float]] = defaultdict(deque)
_global_forecast_cache: dict[str, object] = {"at": 0.0, "payload": None}

NASA_GEOSFP_GRID = "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/fcast/tavg3_2d_smp_Nx.latest.ascii"
NASA_GEOSCF_GRID = "https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/v2/fcst/aqc_tavg_1hr_glo_L1440x721_slv.latest.ascii"


def _nasa_ascii_grid(url: str) -> list[float]:
    """Read a bounded strided NASA OPeNDAP slice and return row-major values."""
    with urlopen(URLRequest(url, headers={"User-Agent": "EarthPulse-X/1.0 (NASA model viewer)"}), timeout=45) as response:
        body = response.read().decode("ascii", errors="replace")
    rows = re.findall(r"(?m)^\[\d+(?:\]\[\d+)*\],\s*([^\n]+)", body)
    values: list[float] = []
    for row in rows:
        for token in row.split(","):
            try:
                value = float(token.strip())
                values.append(value if math.isfinite(value) and abs(value) < 1e20 else math.nan)
            except ValueError:
                continue
    return values


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "earthpulse-explainer"})


async def forecast_point(request: Request) -> JSONResponse:
    """Fetch NASA GEOS-FP weather and GEOS-CF composition at a point."""

    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
        if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return JSONResponse({"error": "Valid latitude and longitude are required."}, status_code=400)

    try:
        lat_index = max(0, min(720, round((lat + 90) / .25)))
        lon_index = round(((lon + 180) % 360) / .3125)
        cf_lon_index = round(((lon + 180) % 360) / .25)
        geosfp = f"{NASA_GEOSFP_GRID}?prectot[1][{lat_index}][{lon_index}]"
        geoscf = f"{NASA_GEOSCF_GRID}?pm25_rh35[6][0][{lat_index}][{cf_lon_index}]"
        weather_values, air_values = await run_in_threadpool(_nasa_ascii_grid, geosfp), await run_in_threadpool(_nasa_ascii_grid, geoscf)
        rain_value = weather_values[0] * 10800 if weather_values and math.isfinite(weather_values[0]) else None
        pm_value = air_values[0] if air_values and math.isfinite(air_values[0]) else None
        return JSONResponse({"lat": lat, "lon": lon, "rainMm3h": rain_value,
                             "pm25": pm_value,
                             "fetchedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                             "sources": {"weather": "NASA GEOS-FP", "air": "NASA GEOS-CF"},
                             "kind": "NASA global model guidance; not a hazard warning"})
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError, IndexError) as exc:
        return JSONResponse({"error": "NASA forecast data unavailable: " + str(exc)}, status_code=502)


async def forecast_global(request: Request) -> JSONResponse:
    """Return global, strided NASA GEOS-FP and GEOS-CF forecast grids."""

    if request.query_params.get("refresh") != "1" and _global_forecast_cache["payload"] is not None and time.time() - float(_global_forecast_cache["at"]) < 900:
        return JSONResponse(_global_forecast_cache["payload"])
    try:
        # Both layers are sampled on a shared 10° × 15° global grid.
        rain = await run_in_threadpool(_nasa_ascii_grid, f"{NASA_GEOSFP_GRID}?prectot[1][40:40:680][0:48:1104]")
        # GEOS-CF: hourly global composition forecast, sampled at ~10° globally.
        pm25 = await run_in_threadpool(_nasa_ascii_grid, f"{NASA_GEOSCF_GRID}?pm25_rh35[6][0][40:40:680][0:60:1380]")
        points = []
        for i, lat_index in enumerate(range(40, 681, 40)):
            for j, lon_index in enumerate(range(0, 1105, 48)):
                k = i * 24 + j
                pk = i * 24 + j
                points.append({"lat": -90 + lat_index * .25, "lon": -180 + lon_index * .3125,
                               "rainMm3h": rain[k] * 10800 if k < len(rain) and math.isfinite(rain[k]) else None,
                               "pm25": pm25[pk] if pk < len(pm25) and math.isfinite(pm25[pk]) else None})
        payload = {"points": points, "sampleCount": len(points), "coverage": "Global NASA model grids, sampled 80°S–80°N",
                   "gridSpacingDegrees": {"latitude": 10, "longitude": 15},
                   "forecastDate": "GEOS-FP +3 h · GEOS-CF +6 h",
                   "fetchedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                   "source": "NASA GEOS-FP · precipitation | NASA GEOS-CF · PM₂.₅",
                   "kind": "Global forecast model output, not a hazard warning"}
        _global_forecast_cache["at"] = time.time()
        _global_forecast_cache["payload"] = payload
        return JSONResponse(payload)
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
        return JSONResponse({"error": "NASA global forecast unavailable: " + str(exc)}, status_code=502)


async def firms_events(request: Request):
    """Proxy FIRMS area CSV while keeping the MAP_KEY server-side."""
    source = request.query_params.get("source", "VIIRS_NOAA20_NRT")
    region = request.query_params.get("region", "uttarakhand")
    if source not in {"VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_NRT", "MODIS_NRT"}:
        return JSONResponse({"error": "Unsupported FIRMS source."}, status_code=400)
    if region == "world":
        area = "world"
    elif region == "uttarakhand":
        area = "77.5,28.7,81.1,31.5"
    else:
        return JSONResponse({"error": "Choose world or uttarakhand."}, status_code=400)
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{source}/{area}/1"
    try:
        with urlopen(url, timeout=20) as response:
            return PlainTextResponse(response.read().decode("utf-8"), media_type="text/csv")
    except HTTPError as exc:
        return JSONResponse({"error": f"NASA FIRMS returned HTTP {exc.code}. Check the MAP_KEY and request limit."}, status_code=502)
    except (TimeoutError, URLError):
        return JSONResponse({"error": "NASA FIRMS could not be reached."}, status_code=502)


async def monitor_feed(request: Request):
    """Same-origin proxy for public monitor feeds that block browser CORS."""
    import json
    from datetime import date, timedelta
    from urllib.parse import urlencode

    source = request.path_params.get("source", "")
    today = date.today()
    start = today - timedelta(days=7)
    bbox = request.query_params.get("bbox")
    eonet_params = {"status": "open", "days": 7, "limit": 1000}
    if bbox == "uttarakhand":
        eonet_params["bbox"] = "77.5,28.7,81.1,31.5"
    hazard_codes = {
        "Earthquakes": "EQ", "Cyclones & severe storms": "TC", "Floods": "FL",
        "Volcanoes": "VO", "Droughts": "DR", "Wildfires": "WF",
    }
    hazard = request.query_params.get("hazard", "")
    event_types = hazard_codes.get(hazard, "EQ;TC;FL;VO;DR;WF")
    urls = {
        "eonet": "https://eonet.gsfc.nasa.gov/api/v3/events/geojson?" + urlencode(eonet_params),
        "usgs": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson",
    }
    if source == "power":
        end = today - timedelta(days=2)
        begin = end - timedelta(days=6)
        urls[source] = "https://power.larc.nasa.gov/api/temporal/daily/point?" + urlencode({
            "parameters": "PRECTOTCORR,RH2M,T2M", "community": "RE", "longitude": 78.0322,
            "latitude": 30.3165, "start": begin.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
            "format": "JSON", "time-standard": "UTC",
        })
    if source not in urls and source not in {"gdacs", "volcano", "openaq", "lhasa"}:
        return JSONResponse({"error": "Unsupported public monitor feed."}, status_code=400)
    openaq_key = os.getenv("OPENAQ_API_KEY", "").strip()
    if source == "openaq" and not openaq_key:
        return JSONResponse({"error": "OpenAQ API key not configured. Set OPENAQ_API_KEY in your private .env file."}, status_code=503)
    try:
        def get_feed():
            if source == "lhasa":
                from urllib.parse import urlencode
                try:
                    lat, lon = float(request.query_params["lat"]), float(request.query_params["lon"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("LHASA needs valid lat and lon coordinates.")
                if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 60 or abs(lon) > 180:
                    return json.dumps({"status": "outside_coverage", "error": "NASA LHASA global coverage is between 60°S and 60°N."})
                params = urlencode({"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": 4326,
                                    "returnGeometry": "false", "returnCatalogItems": "false", "returnPixelValues": "false", "f": "json"})
                def lhasa_value(day):
                    service = f"https://gis.earthdata.nasa.gov/portal/rest/services/Landslides/LHASA_Hazard_{day}/ImageServer"
                    with urlopen(URLRequest(service + "/identify?" + params, headers={"Accept": "application/json", "User-Agent": "EarthPulse-X/1.0"}), timeout=20) as response:
                        result = json.loads(response.read().decode("utf-8"))
                    if result.get("error"):
                        raise URLError("NASA LHASA identify service returned an error.")
                    raw = result.get("value")
                    try:
                        value = float(raw)
                        if not math.isfinite(value) or value < 0:
                            value = None
                    except (TypeError, ValueError):
                        value = None
                    return value
                today_value = lhasa_value("Today")
                try:
                    tomorrow_value = lhasa_value("Tomorrow")
                except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
                    tomorrow_value = None
                return json.dumps({"status": "available" if today_value is not None else "no_cell_data", "model": "NASA LHASA 2.1 · Hazard Today and Tomorrow", "lat": lat, "lon": lon,
                                   "cellValue": today_value, "tomorrowValue": tomorrow_value, "resolutionKm": 1,
                                   "fetchedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                                   "coverage": "60°S–60°N", "components": ["GPM IMERG rainfall", "SMAP soil moisture", "terrain susceptibility"],
                                   "message": "LHASA integrates rainfall, soil moisture and terrain susceptibility. This pixel value is a model output, not an official local warning."})
            if source == "openaq":
                from concurrent.futures import ThreadPoolExecutor
                from datetime import datetime, timezone, timedelta
                from urllib.parse import urlencode

                try:
                    lat, lon = float(request.query_params["lat"]), float(request.query_params["lon"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("OpenAQ needs valid lat and lon coordinates.")
                if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat) > 90 or abs(lon) > 180:
                    raise ValueError("OpenAQ coordinates are outside the valid range.")
                radius = min(100000, max(5000, int(request.query_params.get("radius", "25000"))))
                place = request.query_params.get("place", "Selected location")[:120]
                headers = {"X-API-Key": openaq_key, "Accept": "application/json", "User-Agent": "EarthPulse-X/1.0"}
                api = "https://api.openaq.org/v3"

                def fetch_json(url):
                    with urlopen(URLRequest(url, headers=headers), timeout=18) as response:
                        return json.loads(response.read().decode("utf-8"))

                query = urlencode({"coordinates": f"{lat},{lon}", "radius": radius, "limit": 100, "page": 1, "monitor": "true", "mobile": "false"})
                location_payload = fetch_json(api + "/locations?" + query)
                locations = location_payload.get("results") or []

                def distance_km(a, b, c, d):
                    p1, p2 = math.radians(a), math.radians(c)
                    dp, dl = p2-p1, math.radians(d-b)
                    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
                    return 6371 * 2 * math.asin(math.sqrt(min(1, h)))

                locations = [x for x in locations if (x.get("coordinates") or {}).get("latitude") is not None and x.get("sensors")]
                locations.sort(key=lambda x: distance_km(lat, lon, x["coordinates"]["latitude"], x["coordinates"]["longitude"]))
                locations = locations[:20]
                sensor_lookup = {}
                for location in locations:
                    for sensor in location.get("sensors", []):
                        parameter = (sensor.get("parameter") or {}).get("name", "")
                        norm = re.sub(r"[^a-z0-9]", "", parameter.lower())
                        aliases = {"pm25": "PM2.5", "pm2.5": "PM2.5", "pm10": "PM10", "no2": "NO₂", "so2": "SO₂", "co": "CO", "o3": "O₃"}
                        if norm in aliases:
                            sensor_lookup[int(sensor["id"])] = {"parameter": aliases[norm], "unit": (sensor.get("parameter") or {}).get("units", ""), "location": location}

                now = datetime.now(timezone.utc)
                def latest_for(location):
                    try:
                        data = fetch_json(api + f"/locations/{location['id']}/latest?limit=100")
                    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
                        return location, []
                    rows = []
                    for item in data.get("results", []):
                        sid = item.get("sensorsId")
                        meta = sensor_lookup.get(sid)
                        if not meta or meta["location"]["id"] != location["id"]:
                            continue
                        dt = item.get("datetime", {}).get("utc")
                        try:
                            stamp = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                            value = float(item.get("value"))
                        except (AttributeError, TypeError, ValueError):
                            continue
                        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=timezone.utc)
                        age = (now-stamp.astimezone(timezone.utc)).total_seconds()
                        if not math.isfinite(value) or value < 0 or age < -300 or age > 12*3600:
                            continue
                        rows.append({"parameter": meta["parameter"], "value": value, "unit": meta["unit"], "datetime": stamp.astimezone(timezone.utc).isoformat(), "sensorId": sid, "flagged": bool((item.get("flagInfo") or {}).get("hasFlags"))})
                    return location, rows

                with ThreadPoolExecutor(max_workers=8) as pool:
                    latest_results = list(pool.map(latest_for, locations))
                features, pm_sensors = [], []
                for location, measurements in latest_results:
                    coordinates = location["coordinates"]
                    distance = distance_km(lat, lon, coordinates["latitude"], coordinates["longitude"])
                    sensors = location.get("sensors", [])
                    for sensor in sensors:
                        meta = sensor_lookup.get(int(sensor.get("id", 0)))
                        if meta and meta["parameter"] == "PM2.5": pm_sensors.append((location, sensor, distance))
                    features.append({"type": "Feature", "id": str(location["id"]), "geometry": {"type": "Point", "coordinates": [coordinates["longitude"], coordinates["latitude"]]}, "properties": {"title": location.get("name") or "Air quality station", "locality": location.get("locality") or "", "country": (location.get("country") or {}).get("name", ""), "distanceKm": round(distance, 1), "measurements": measurements}})

                def hourly_for(item):
                    location, sensor, distance = item
                    start_hour = (now-timedelta(hours=6)).isoformat().replace("+00:00", "Z")
                    end_hour = now.isoformat().replace("+00:00", "Z")
                    params = urlencode({"datetime_from": start_hour, "datetime_to": end_hour, "limit": 12})
                    try:
                        data = fetch_json(api + f"/sensors/{sensor['id']}/hours?" + params)
                    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
                        return None
                    readings = []
                    for row in data.get("results", []):
                        if (row.get("flagInfo") or {}).get("hasFlags"): continue
                        try:
                            stamp = datetime.fromisoformat(row["period"]["datetimeFrom"]["utc"].replace("Z", "+00:00"))
                            value = float(row["value"])
                        except (KeyError, AttributeError, TypeError, ValueError): continue
                        age = (now-stamp.astimezone(timezone.utc)).total_seconds()/3600
                        if math.isfinite(value) and value >= 0 and -0.1 <= age <= 6.5:
                            readings.append((age, value))
                    recent = [v for age, v in readings if age <= 3]
                    prior = [v for age, v in readings if 3 < age <= 6]
                    if recent and prior:
                        return {"name": location.get("name") or location.get("locality") or "Nearby sensor", "distanceKm": round(distance, 1), "recentMean": statistics.mean(recent), "priorMean": statistics.mean(prior), "increase": statistics.mean(recent)-statistics.mean(prior)}
                    return None

                candidates = []
                pm_sensors.sort(key=lambda x: x[2])
                with ThreadPoolExecutor(max_workers=6) as pool:
                    for candidate in pool.map(hourly_for, pm_sensors[:12]):
                        if candidate and candidate["recentMean"] >= 35 and candidate["increase"] >= 10 and candidate["recentMean"] >= max(5, candidate["priorMean"])*1.5:
                            candidates.append(candidate)
                sites = sum(1 for feature in features if feature["properties"]["measurements"])
                status = "confirmed" if len(candidates) >= 2 else "possible" if candidates else "none" if pm_sensors else "insufficient_history"
                return json.dumps({"type": "FeatureCollection", "features": features, "properties": {"place": place, "radiusKm": round(radius/1000), "siteCount": sites, "measurementCount": sum(len(f["properties"]["measurements"]) for f in features), "spike": {"event": "POLLUTION_SPIKE", "status": status, "locations": candidates, "thresholds": {"recentMeanUgM3": 35, "absoluteIncreaseUgM3": 10, "relativeIncrease": 0.5, "crossCheck": "two nearby stations"}}, "latestAt": now.isoformat()}})
            if source == "volcano":
                import re
                import unicodedata
                import xml.etree.ElementTree as ET
                from datetime import datetime, timezone
                from email.utils import parsedate_to_datetime

                rss_request = URLRequest("https://volcano.si.edu/news/WeeklyVolcanoRSS.xml",
                    headers={"User-Agent": "EarthPulse-X/1.0 (volcano monitoring)", "Accept": "application/rss+xml, application/xml"})
                with urlopen(rss_request, timeout=30) as response:
                    rss = ET.fromstring(response.read())
                items = [node for node in rss.iter() if node.tag.rsplit("}", 1)[-1].lower() == "item"]

                def child_text(node, name):
                    child = next((x for x in node if x.tag.rsplit("}", 1)[-1].lower() == name), None)
                    return " ".join("".join(child.itertext()).split()) if child is not None else ""

                reports = []
                cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
                for item in items:
                    title = child_text(item, "title")
                    description = child_text(item, "description")
                    link = child_text(item, "link")
                    pub_date = child_text(item, "pubdate")
                    try:
                        published = parsedate_to_datetime(pub_date).astimezone(timezone.utc).timestamp()
                    except (TypeError, ValueError, OverflowError):
                        published = None
                    if published is not None and published < cutoff:
                        continue
                    match = re.search(r"(?:Report on\s+)?(.+?)\s*\(([^()]*)\)", title, re.I)
                    name = match.group(1).strip() if match else title.replace("Report on ", "").strip()
                    country = match.group(2).strip() if match else ""
                    reports.append({"title": title, "name": name, "country": country,
                                    "description": description, "link": link, "date": pub_date})

                # Join weekly activity reports to Smithsonian's volcano coordinates.
                point_by_name = {}
                reported_volcanoes = []
                def normalized_name(value):
                    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
                    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())
                if reports:
                    wfs_url = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?" + urlencode({
                        "service": "WFS", "version": "1.0.0", "request": "GetFeature",
                        "typeName": "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes",
                        "outputFormat": "application/json", "maxFeatures": 2500,
                    })
                    try:
                        wfs_request = URLRequest(wfs_url, headers={"User-Agent": "EarthPulse-X/1.0 (volcano monitoring)", "Accept": "application/json"})
                        with urlopen(wfs_request, timeout=30) as response:
                            volcanoes = json.loads(response.read().decode("utf-8"))
                        for feature in volcanoes.get("features", []):
                            props = feature.get("properties") or {}
                            coords = (feature.get("geometry") or {}).get("coordinates")
                            if not coords or len(coords) < 2:
                                continue
                            for value in props.values():
                                if isinstance(value, str):
                                    key = normalized_name(value)
                                    point_by_name[key] = coords
                    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
                        pass

                features = []
                for report in reports:
                    key = normalized_name(report["name"])
                    coords = point_by_name.get(key)
                    if not coords and key in {"ioto", "iwojima"}:
                        coords = [141.29, 24.75]
                    feature = {"type": "Feature", "id": report["name"], "properties": {
                        "title": report["name"], "country": report["country"],
                        "description": report["description"], "date": report["date"], "url": report["link"],
                    }}
                    if coords:
                        feature["geometry"] = {"type": "Point", "coordinates": coords}
                        reported_volcanoes.append({"name": report["name"], "country": report["country"], "coords": coords})
                    features.append(feature)

                # Add FIRMS thermal detections only when they fall close to a
                # volcano mentioned in the latest weekly activity report.
                thermal_errors = []
                thermal_count = 0
                if reported_volcanoes:
                    import csv
                    from concurrent.futures import ThreadPoolExecutor
                    firms_sources = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"]

                    def fetch_firms(sensor):
                        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{sensor}/world/1"
                        try:
                            with urlopen(url, timeout=20) as response:
                                return sensor, response.read().decode("utf-8"), None
                        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as exc:
                            return sensor, None, str(exc)

                    with ThreadPoolExecutor(max_workers=4) as pool:
                        firms_results = pool.map(fetch_firms, firms_sources)
                        thermal_bins = {}
                        for sensor, csv_text, fetch_error in firms_results:
                            if fetch_error:
                                thermal_errors.append(f"{sensor}: {fetch_error}")
                                continue
                            try:
                                rows = csv.DictReader(csv_text.splitlines())
                                for row in rows:
                                    try:
                                        lat, lon = float(row["latitude"]), float(row["longitude"])
                                    except (KeyError, TypeError, ValueError):
                                        continue
                                    closest, closest_km = None, 20.0
                                    for volcano in reported_volcanoes:
                                        vlon, vlat = float(volcano["coords"][0]), float(volcano["coords"][1])
                                        dy = (lat - vlat) * 111.32
                                        dx = (lon - vlon) * 111.32 * math.cos(math.radians((lat + vlat) / 2))
                                        distance = math.hypot(dx, dy)
                                        if distance < closest_km:
                                            closest, closest_km = volcano, distance
                                    if closest is None:
                                        continue
                                    cell = (closest["name"], round(lat, 2), round(lon, 2))
                                    item = thermal_bins.setdefault(cell, {"name": closest["name"], "country": closest["country"], "lat": [], "lon": [], "sensors": set(), "count": 0, "distance": closest_km})
                                    item["lat"].append(lat)
                                    item["lon"].append(lon)
                                    item["sensors"].add(sensor)
                                    item["count"] += 1
                                    item["distance"] = min(item["distance"], closest_km)
                            except (UnicodeDecodeError, csv.Error) as exc:
                                thermal_errors.append(f"{sensor}: invalid CSV ({exc})")
                    for item in thermal_bins.values():
                        sensors = sorted(item["sensors"])
                        features.append({"type": "Feature", "id": "firms-" + item["name"] + "-" + str(thermal_count),
                            "properties": {"kind": "thermal", "title": "Thermal anomaly near " + item["name"],
                                "country": item["country"], "sensors": sensors, "detections": item["count"],
                                "distanceKm": round(item["distance"], 1),
                                "description": "NASA FIRMS thermal detections from the last 24 hours. A thermal anomaly near a volcano is not confirmation of an eruption."},
                            "geometry": {"type": "Point", "coordinates": [sum(item["lon"])/len(item["lon"]), sum(item["lat"])/len(item["lat"])]}})
                        thermal_count += 1
                elif reports:
                    thermal_errors.append("Could not match recent volcano reports to Smithsonian volcano coordinates.")
                else:
                    thermal_errors.append("No recent volcano reports with coordinates were available for thermal matching.")
                thermal_status = f"NASA FIRMS: {thermal_count} nearby thermal clusters"
                if thermal_errors:
                    thermal_status += " · partial feed issues: " + "; ".join(thermal_errors)
                return json.dumps({"type": "FeatureCollection", "features": features,
                                   "properties": {"thermalStatus": thermal_status}})
            if source == "gdacs":
                # GDACS returns at most 100 records per page. Walk every page for
                # the requested hazard and stop only at the final/duplicate page.
                base = "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/SEARCH"
                collected, seen = [], set()
                page = 1
                while True:
                    params = urlencode({
                        "eventlist": event_types, "fromdate": start.isoformat(), "todate": today.isoformat(),
                        "alertlevel": "red;orange;green", "pagesize": 100, "pagenumber": page,
                    })
                    with urlopen(base + "?" + params, timeout=45) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    features = payload.get("features") or payload.get("results") or []
                    new_features = []
                    for index, feature in enumerate(features):
                        props = feature.get("properties") or {}
                        key = str(feature.get("id") or props.get("eventid") or props.get("eventId") or (page, index))
                        if key not in seen:
                            seen.add(key)
                            new_features.append(feature)
                    collected.extend(new_features)
                    if len(features) < 100 or not new_features:
                        return json.dumps({"type": "FeatureCollection", "features": collected})
                    page += 1
            with urlopen(urls[source], timeout=45) as response:
                return response.read().decode("utf-8")
        body = await run_in_threadpool(get_feed)
        # Validate JSON here so the UI gets a useful source error, not a blank panel.
        json.loads(body)
        return JSONResponse(json.loads(body))
    except HTTPError as exc:
        if source == "openaq" and exc.code in {401, 403}:
            return JSONResponse({"error": "OpenAQ rejected the API key. Check OPENAQ_API_KEY in your private .env file."}, status_code=502)
        if source == "openaq" and exc.code == 429:
            return JSONResponse({"error": "OpenAQ rate limit reached. Try again shortly."}, status_code=502)
        return JSONResponse({"error": f"{source.upper()} returned HTTP {exc.code}."}, status_code=502)
    except (TimeoutError, URLError) as exc:
        return JSONResponse({"error": f"{source.upper()} could not be reached: {exc.reason if isinstance(exc, URLError) else 'request timed out'}."}, status_code=502)
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"error": f"{source.upper()} returned invalid JSON."}, status_code=502)



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

app = Starlette(routes=[Route("/health", health, methods=["GET"]), Route("/api/explain", explain, methods=["POST"]), Route("/api/forecast/point", forecast_point, methods=["GET"]), Route("/api/forecast/global", forecast_global, methods=["GET"]), Route("/api/firms/events", firms_events, methods=["GET"]), Route("/api/monitor/{source}", monitor_feed, methods=["GET"]), Route("/api/landcover/map-timeline", landcover_map_timeline, methods=["POST"])])
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
