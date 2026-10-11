import json
from pathlib import Path
import requests
import geopandas as gpd
from shapely.geometry import box
from xml.etree import ElementTree as ET

BASE = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"
OUT = Path("data/raw/flood/chennai_2015_nrsc_candidate")
OUT.mkdir(parents=True, exist_ok=True)

AOI = box(80.170, 12.900, 80.270, 12.995)
TARGET = "gis_flood_inundation_nrsc_flood_extent_2015"

session = requests.Session()
session.headers.update({"User-Agent": "Jalsuraksha-research/1.0"})

print("=" * 72)
print("OFFICIAL CHENNAI FLOOD GEOSERVER AUDIT")
print("=" * 72)

# 1. Read the server's WFS catalogue.
try:
    r = session.get(
        BASE,
        params={"service": "WFS", "request": "GetCapabilities"},
        timeout=60
    )
    print("Capabilities HTTP:", r.status_code)
    r.raise_for_status()
except Exception as e:
    raise SystemExit(f"Could not access WFS capabilities: {e}")

root = ET.fromstring(r.content)

def local_name(tag):
    return tag.split("}")[-1]

layers = []
for element in root.iter():
    if local_name(element.tag) == "FeatureType":
        info = {}
        for child in element:
            key = local_name(child.tag)
            if key in ("Name", "Title", "Abstract"):
                info[key] = (child.text or "").strip()
        if info.get("Name"):
            layers.append(info)

print("Advertised WFS feature types:", len(layers))

matches = [
    item for item in layers
    if TARGET.lower() in item.get("Name", "").lower()
    or TARGET.lower() in item.get("Title", "").lower()
]

print("\nMatching layers:")
if not matches:
    print("Exact target not found. Related flood extent layers:")
    for item in layers:
        combined = (item.get("Name", "") + " " + item.get("Title", "")).lower()
        if "flood" in combined and ("extent" in combined or "inundation" in combined):
            print(item)
    raise SystemExit("STOP: No matching feature type found; no data downloaded.")

for item in matches:
    print(item)

# Prefer the exact matching layer name.
exact = [
    item for item in matches
    if TARGET.lower() in item.get("Name", "").lower()
]
chosen = exact[0] if exact else matches[0]
typename = chosen["Name"]

print("\nSelected type:", typename)
print("Requesting features as GeoJSON; this is a data inspection only.")

# 2. Download the feature layer into a separate raw-data file.
try:
    r = session.get(
        BASE,
        params={
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": typename,
            "outputFormat": "application/json",
            "maxFeatures": "10000"
        },
        timeout=120
    )
    print("GetFeature HTTP:", r.status_code)
    print("Content type:", r.headers.get("Content-Type"))
    print("Response bytes:", len(r.content))
    r.raise_for_status()
except Exception as e:
    raise SystemExit(f"GetFeature request failed: {e}")

# Do not save an XML/HTML error page under a GeoJSON filename.
try:
    payload = r.json()
except Exception:
    print("Response preview:", r.text[:1200])
    raise SystemExit("STOP: Response is not JSON; no GeoJSON saved.")

if not isinstance(payload, dict) or "features" not in payload:
    print(json.dumps(payload, indent=2)[:2000])
    raise SystemExit("STOP: JSON does not contain a GeoJSON features array.")

geojson_path = OUT / "official_geoserver_nrsc_2015_check.geojson"
geojson_path.write_text(json.dumps(payload), encoding="utf-8")
print("Saved raw service response:", geojson_path)
print("Returned feature count:", len(payload["features"]))

if not payload["features"]:
    raise SystemExit("STOP: Service returned no features.")

# 3. Inspect geometry, properties, and study-area overlap.
try:
    gdf = gpd.read_file(geojson_path)
except Exception as e:
    raise SystemExit(f"GeoJSON geometry inspection failed: {e}")

print("\n--- RETURNED DATA ---")
print("Rows:", len(gdf))
print("CRS:", gdf.crs)
print("Columns:", list(gdf.columns))
print("Geometry types:")
print(gdf.geometry.geom_type.value_counts(dropna=False).to_string())
print("Bounds:", gdf.total_bounds)

if gdf.crs is None:
    raise SystemExit("STOP: CRS missing; spatial overlap cannot be verified.")

gdf = gdf.to_crs("EPSG:4326")
valid_nonempty = (
    gdf.geometry.notna()
    & ~gdf.geometry.is_empty
    & gdf.geometry.is_valid
)
print("Valid non-empty geometries:", int(valid_nonempty.sum()))

overlap = valid_nonempty & gdf.geometry.intersects(AOI)
print("Features intersecting Chennai AOI:", int(overlap.sum()))

print("\nSample attributes:")
print(gdf.drop(columns="geometry").head(10).to_string())

print("\nInspection only. No flood labels or training data were created.")
