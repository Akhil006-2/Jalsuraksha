
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

BASE_URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"
LAYER = "tn_011112_flood"

# Chennai study-area bounds
WEST, SOUTH, EAST, NORTH = 80.170, 12.900, 80.270, 12.995

OUT = Path("data/processed/flood")
OUT.mkdir(parents=True, exist_ok=True)


def local_name(tag):
    return tag.split("}")[-1]


def find_layer(element, wanted):
    if local_name(element.tag) == "Layer":
        name = ""
        for child in element:
            if local_name(child.tag) == "Name" and child.text:
                name = child.text.strip()
                break

        if name == wanted:
            return element

    for child in element:
        result = find_layer(child, wanted)
        if result is not None:
            return result

    return None


print("=" * 70)
print("TESTING TAMIL NADU FLOOD LAYER")
print("=" * 70)

try:
    response = requests.get(
        BASE_URL,
        params={
            "SERVICE": "WMS",
            "REQUEST": "GetCapabilities",
            "VERSION": "1.1.1",
        },
        timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)

    layer = find_layer(root, LAYER)

    if layer is None:
        print(f"Layer not found: {LAYER}")
        raise SystemExit(1)

    print("\nLayer:", LAYER)

    for child in layer:
        tag = local_name(child.tag)
        if tag in ("Title", "Abstract", "SRS", "CRS", "LatLonBoundingBox", "BoundingBox"):
            print(tag, child.attrib if child.attrib else (child.text or "").strip())

    # WMS 1.1.1 uses x/y order for EPSG:4326 BBOX.
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": LAYER,
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{WEST},{SOUTH},{EAST},{NORTH}",
        "WIDTH": "800",
        "HEIGHT": "700",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
    }

    print("\nRequesting map for Chennai AOI...")
    result = requests.get(BASE_URL, params=params, timeout=60)

    print("HTTP status:", result.status_code)
    print("Content type:", result.headers.get("Content-Type"))
    print("Response size:", len(result.content), "bytes")

    result.raise_for_status()

    content_type = result.headers.get("Content-Type", "").lower()

    if "image/png" in content_type or result.content.startswith(b"\x89PNG"):
        output_file = OUT / "tn_011112_flood_chennai_test.png"
        output_file.write_bytes(result.content)
        print("Map image saved:", output_file)
        print("Open the image and check whether the Chennai area has mapped features.")
    else:
        print("The server did not return a PNG map.")
        print(result.text[:1500])

    print("\nTest complete. This image is only a visual service test,")
    print("not a verified historical flood-label raster.")

except requests.RequestException as error:
    print("\nRequest failed:", error)
except ET.ParseError as error:
    print("\nCould not parse capabilities:", error)
