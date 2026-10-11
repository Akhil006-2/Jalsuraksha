from pathlib import Path
import requests
import xml.etree.ElementTree as ET
import json
import re

ROOT = Path(r"C:\Dev\Jalsuraksha")
OUT = ROOT / "data" / "raw" / "flood" / "chennai_2015_nrsc_candidate"
OUT.mkdir(parents=True, exist_ok=True)

RESOURCE_ID = "2056abd6-26d7-413b-9dfa-e63cbbf41ee7"
API_URLS = [
    "https://data.opencity.in/api/3/action/resource_show",
    "https://data.opencity.in/api/action/resource_show",
]

session = requests.Session()
session.headers["User-Agent"] = "Jalsuraksha-research/1.0"

print("=" * 72)
print("OPENCITY NRSC FLOOD KML CROSS-CHECK")
print("=" * 72)

metadata = None

# Try the CKAN resource API to discover the actual download URL.
for api in API_URLS:
    try:
        response = session.get(
            api,
            params={"id": RESOURCE_ID},
            timeout=30,
        )
        print("\nAPI:", api)
        print("HTTP:", response.status_code)

        if not response.ok:
            print("Response preview:", response.text[:300])
            continue

        payload = response.json()
        if payload.get("success") and isinstance(payload.get("result"), dict):
            metadata = payload["result"]
            break

        print("API did not return a resource record.")
    except Exception as exc:
        print("Request error:", repr(exc))

if metadata is None:
    raise SystemExit(
        "\nCould not discover the KML download URL automatically. "
        "No labels were created. Open the resource page manually:\n"
        "https://data.opencity.in/dataset/chennai-floods-2015-data/"
        "resource/2056abd6-26d7-413b-9dfa-e63cbbf41ee7"
    )

print("\n--- RESOURCE METADATA ---")
for key in ("name", "format", "mimetype", "size", "source", "url"):
    print(f"{key}: {metadata.get(key)}")

download_url = metadata.get("url")
if not download_url:
    raise SystemExit("Resource metadata has no download URL.")

# Download the KML as a separate raw source.
kml_path = OUT / "opencity_nrsc_chennai_2015_inundation.kml"

try:
    response = session.get(download_url, timeout=120)
    print("\nDownload HTTP:", response.status_code)
    print("Content type:", response.headers.get("Content-Type"))
    print("Downloaded bytes:", len(response.content))
    response.raise_for_status()
except Exception as exc:
    raise SystemExit(f"Download failed: {exc}")

if not response.content.lstrip().startswith(b"<?xml") and b"<kml" not in response.content[:2000].lower():
    print("Response preview:", response.text[:500])
    raise SystemExit("STOP: Download response does not look like KML/XML.")

kml_path.write_bytes(response.content)
print("Saved KML:", kml_path)

# Parse the KML without converting it into training labels.
try:
    root = ET.fromstring(response.content)
except ET.ParseError as exc:
    raise SystemExit(f"KML XML parse failed: {exc}")

def local_name(tag):
    return tag.split("}")[-1]

placemarks = [
    element for element in root.iter()
    if local_name(element.tag) == "Placemark"
]

print("\n--- KML CONTENT ---")
print("Placemark count:", len(placemarks))

for index, placemark in enumerate(placemarks[:10], start=1):
    values = {}
    for element in placemark.iter():
        tag = local_name(element.tag)
        if tag in ("name", "description", "value", "SimpleData"):
            text = (element.text or "").strip()
            if text:
                values.setdefault(tag, []).append(text[:250])

    print(f"\nPlacemark {index}:")
    for key, value in values.items():
        print(f"  {key}: {value[:5]}")

# Calculate rough bounds from all KML coordinate tuples.
coordinates = []
for element in root.iter():
    if local_name(element.tag) == "coordinates" and element.text:
        for item in element.text.split():
            parts = item.split(",")
            if len(parts) >= 2:
                try:
                    coordinates.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    pass

if coordinates:
    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]
    print("\n--- KML GEOGRAPHIC BOUNDS ---")
    print("West:", min(longitudes))
    print("South:", min(latitudes))
    print("East:", max(longitudes))
    print("North:", max(latitudes))
else:
    print("\nNo standard KML coordinate tuples found.")

# Search the KML text for class/legend clues.
text = response.content.decode("utf-8", errors="replace")
for term in ("pixelvalue", "permanent water", "inundated", "flood", "legend"):
    print(f"Contains {term!r}:", term.lower() in text.lower())

print("\nKML inspection complete.")
print("No flood labels or model training data were created.")
