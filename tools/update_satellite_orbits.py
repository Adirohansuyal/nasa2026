"""Refresh the offline satellite-elements snapshot from CelesTrak."""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SATELLITES = [
    ("TERRA", 25994, "#51d5ca"),
    ("AQUA", 27424, "#82adff"),
    ("SMAP", 40376, "#efbd72"),
]

records = []
for name, norad_id, color in SATELLITES:
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
    request = Request(url, headers={"User-Agent": "EARTHPULSE-X satellite tracker"})
    with urlopen(request, timeout=30) as response:
        lines = [line.strip() for line in response.read().decode("ascii").splitlines() if line.strip()]
    line1 = next(line for line in lines if line.startswith("1 "))
    line2 = next(line for line in lines if line.startswith("2 "))
    records.append({"name": name, "norad": norad_id, "color": color, "line1": line1, "line2": line2})

bundle = {"source": "CelesTrak GP data", "fetchedAt": datetime.now(timezone.utc).isoformat(), "satellites": records}
output = ROOT / "assets/satellite_orbits.js"
output.write_text("window.SAT_ORBIT_DATA=" + json.dumps(bundle, separators=(",", ":")) + ";\n")
print(f"Updated {output} with {len(records)} CelesTrak element sets.")
