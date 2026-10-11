from pathlib import Path
import requests
from xml.etree import ElementTree as ET

BASE = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"
LAYER = "ChennaiDSS:gis_flood_inundation_nrsc_flood_extent_2015"
OUT = Path(r"data/raw/flood/chennai_2015_nrsc_candidate")
OUT.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "Jalsuraksha-research/1.0"

def local(tag):
    return tag.split("}")[-1]

def save_response(name, response):
    path = OUT / name
    path.write_bytes(response.content)
    print(f"Saved: {path} ({len(response.content)} bytes)")
    return path

print("=" * 72)
print("OFFICIAL NRSC 2015 LAYER METADATA")
print("=" * 72)

# 1. Feature schema
r = s.get(BASE, params={
    "service": "WFS",
    "version": "1.1.0",
    "request": "DescribeFeatureType",
    "typeName": LAYER,
}, timeout=60)
print("\nDescribeFeatureType HTTP:", r.status_code)
r.raise_for_status()
save_response("official_nrsc_2015_schema.xml", r)

root = ET.fromstring(r.content)
print("\n--- FIELD DEFINITIONS ---")
for el in root.iter():
    if local(el.tag) == "element":
        name = el.attrib.get("name")
        typ = el.attrib.get("type")
        if name:
            print(f"{name}: {typ}")

# 2. WMS layer title, abstract, styles, legend links
r = s.get(BASE, params={
    "service": "WMS",
    "version": "1.1.1",
    "request": "GetCapabilities",
}, timeout=60)
print("\nWMS GetCapabilities HTTP:", r.status_code)
r.raise_for_status()
save_response("official_nrsc_2015_wms_capabilities.xml", r)

root = ET.fromstring(r.content)
target = None

for el in root.iter():
    if local(el.tag) == "Layer":
        name = next(
            ((c.text or "").strip() for c in el
             if local(c.tag) == "Name"),
            None
        )
        if name == LAYER:
            target = el
            break

print("\n--- OFFICIAL LAYER METADATA ---")
if target is None:
    print("Layer not found in WMS capabilities.")
else:
    for child in target:
        tag = local(child.tag)
        if tag in ("Name", "Title", "Abstract", "SRS", "CRS"):
            print(f"{tag}: {(child.text or '').strip()}")

    print("\nStyles:")
    styles = [c for c in target if local(c.tag) == "Style"]
    for style in styles:
        for child in style:
            if local(child.tag) in ("Name", "Title"):
                print(f"  {local(child.tag)}: {(child.text or '').strip()}")
            if local(child.tag) == "LegendURL":
                for item in child:
                    if local(item.tag) == "OnlineResource":
                        href = next(
                            (v for k, v in item.attrib.items()
                             if k.endswith("href")),
                            None
                        )
                        if href:
                            print("  Legend URL:", href)

    if not styles:
        print("No explicit style advertised.")

# 3. Request the rendered legend for the first advertised style
if target is not None:
    styles = [c for c in target if local(c.tag) == "Style"]
    style_name = ""
    if styles:
        style_name = next(
            ((c.text or "").strip() for c in styles[0]
             if local(c.tag) == "Name"),
            ""
        )

    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetLegendGraphic",
        "format": "image/png",
        "layer": LAYER,
    }
    if style_name:
        params["style"] = style_name

    try:
        r = s.get(BASE, params=params, timeout=60)
        print("\nGetLegendGraphic HTTP:", r.status_code)
        print("Legend content type:", r.headers.get("Content-Type"))
        print("Legend response bytes:", len(r.content))
        if r.ok and "image" in r.headers.get("Content-Type", "").lower():
            save_response("official_nrsc_2015_legend.png", r)
        else:
            print("Legend response preview:", r.text[:600])
    except Exception as e:
        print("Legend request failed:", repr(e))

print("\nMetadata inspection complete.")
print("No labels or training data were created.")
