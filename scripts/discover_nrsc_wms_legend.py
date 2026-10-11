from pathlib import Path
import requests
from xml.etree import ElementTree as ET

base = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"
target = "ChennaiDSS:gis_flood_inundation_nrsc_flood_extent_2015"
out = Path(r"data/raw/flood/chennai_2015_nrsc_candidate")

def local(tag):
    return tag.split("}")[-1]

print("=" * 72)
print("WMS LAYER AND LEGEND DISCOVERY")
print("=" * 72)

# Read the saved WMS capabilities first.
capfile = out / "official_nrsc_2015_wms_capabilities.xml"
root = ET.parse(capfile).getroot()

layers = []
for layer in root.iter():
    if local(layer.tag) != "Layer":
        continue

    direct = {}
    styles = []
    for child in layer:
        tag = local(child.tag)
        if tag in ("Name", "Title", "Abstract"):
            direct[tag] = (child.text or "").strip()
        elif tag == "Style":
            style = {}
            for item in child:
                key = local(item.tag)
                if key in ("Name", "Title"):
                    style[key] = (item.text or "").strip()
                elif key == "LegendURL":
                    for sub in item:
                        if local(sub.tag) == "OnlineResource":
                            style["LegendURL"] = next(
                                (v for k, v in sub.attrib.items()
                                 if k.endswith("href")), ""
                            )
            styles.append(style)

    if direct.get("Name") or direct.get("Title"):
        layers.append((direct, styles))

print("Total named/title WMS layer nodes:", len(layers))

keywords = ("nrsc", "2015", "inundation", "flood", "extent")
matches = []
for info, styles in layers:
    text = " ".join(info.values()).lower()
    if any(word in text for word in keywords):
        matches.append((info, styles))

print("\n--- RELEVANT WMS LAYERS ---")
for info, styles in matches:
    print("\nName:", info.get("Name", "(none)"))
    print("Title:", info.get("Title", "(none)"))
    print("Abstract:", info.get("Abstract", "(none)")[:300])
    print("Styles:", styles if styles else "(none advertised)")

print("\n--- EXACT TARGET CHECK ---")
exact = [(info, styles) for info, styles in layers
         if info.get("Name", "").lower() == target.lower()]
print("Exact target in saved WMS catalogue:", bool(exact))

# Also query WFS schema to check if the layer exposes any field annotations.
print("\n--- WFS SCHEMA ANNOTATIONS ---")
schema = out / "official_nrsc_2015_schema.xml"
schema_root = ET.parse(schema).getroot()
annotations = []
for el in schema_root.iter():
    if local(el.tag) in ("documentation", "appinfo"):
        text = " ".join("".join(el.itertext()).split())
        if text:
            annotations.append(text)

if annotations:
    for annotation in annotations:
        print(annotation)
else:
    print("No explanatory documentation/appinfo annotations found in schema.")

print("\nNo labels created.")
