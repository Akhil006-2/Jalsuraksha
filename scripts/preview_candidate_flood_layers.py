
from pathlib import Path
import requests

BASE_URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"

# Chennai AOI: west, south, east, north
WEST, SOUTH, EAST, NORTH = 80.170, 12.900, 80.270, 12.995

OUTPUT = Path("data/processed/flood/candidate_previews")
OUTPUT.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    "Flood",
    "ap_011112_flood",
    "ap_021112_flood",
    "ap_051112_flood",
    "ap_061112_flood",
    "ap_241013_flood",
    "ap_271013_flood",
    "ap_271013e_flood",
    "ap_281013_flood",
]

for layer_name in CANDIDATES:
    print(f"\nTesting: {layer_name}")

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer_name,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{WEST},{SOUTH},{EAST},{NORTH}",
        "WIDTH": "800",
        "HEIGHT": "700",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=60)
        content_type = response.headers.get("Content-Type", "")
        print("HTTP:", response.status_code)
        print("Content type:", content_type)
        print("Bytes:", len(response.content))

        response.raise_for_status()

        if "image/png" in content_type.lower() or response.content.startswith(b"\x89PNG"):
            path = OUTPUT / f"{layer_name}.png"
            path.write_bytes(response.content)
            print("Saved:", path)
        else:
            print("Not a PNG. Response preview:")
            print(response.text[:500])

    except requests.RequestException as exc:
        print("Request failed:", exc)

print("\nFinished. These are visual previews, not training labels.")
print("Output folder:", OUTPUT)
