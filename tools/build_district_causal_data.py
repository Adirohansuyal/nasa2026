"""Build a small browser dataset of monthly satellite anomaly means by district.

Input records are the existing pixel-level robust-z anomaly grid, spatially
assigned to Uttarakhand district polygons. Values are anomaly z-scores, not
raw millimetres, degrees, or soil-moisture measurements.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep


ROOT = Path(__file__).resolve().parents[1]
VARIABLES = {
    "GPM": "GPM_robust_z",
    "SMAP_AM": "SMAP_AM_robust_z",
    "NDVI": "NDVI_robust_z",
    "LST": "LST_robust_z",
}


def read_js_json(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    return json.loads(source[source.index("=") + 1 : source.rfind(";")])


def main() -> None:
    predictive = read_js_json(ROOT / "assets/predictive_data.js")
    anomaly = read_js_json(ROOT / "assets/anomaly_data.js")
    events = predictive["districts"]["events"]
    features = anomaly["districtGeo"]["features"]
    polygons = []
    for feature in features:
        geom = shape(feature["geometry"])
        polygons.append((feature["properties"]["district_name"], prep(geom), geom.bounds))

    months = sorted({event["month"] for event in events})
    # sums[ district ][ month ][ variable ] = [sum, count]
    sums: dict[str, dict[str, dict[str, list[float]]]] = {
        name: {month: {key: [0.0, 0] for key in VARIABLES} for month in months}
        for name, _, _ in polygons
    }
    assigned = 0
    for event in events:
        point = Point(event["lon"], event["lat"])
        for name, polygon, bounds in polygons:
            if bounds[0] <= point.x <= bounds[2] and bounds[1] <= point.y <= bounds[3] and polygon.covers(point):
                for key, source_key in VARIABLES.items():
                    value = event.get(source_key)
                    if value is not None:
                        sums[name][event["month"]][key][0] += float(value)
                        sums[name][event["month"]][key][1] += 1
                assigned += 1
                break

    districts = {}
    for name, monthly in sums.items():
        districts[name] = {
            key: [
                round(total / count, 4) if count else None
                for month in months
                for total, count in [monthly[month][key]]
            ]
            for key in VARIABLES
        }
        districts[name]["pixelCounts"] = [
            monthly[month]["GPM"][1] for month in months
        ]

    payload = {
        "source": "Monthly means of existing pixel-level satellite robust-z anomalies, spatially grouped by district",
        "months": months,
        "variables": VARIABLES,
        "districts": districts,
        "assignedPixelMonths": assigned,
    }
    target = ROOT / "assets/district_causal_data.js"
    target.write_text(
        "window.DISTRICT_CAUSAL_DATA=" + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {target.relative_to(ROOT)}: {len(months)} months, {len(districts)} districts, {assigned:,} pixel-month records")


if __name__ == "__main__":
    main()
