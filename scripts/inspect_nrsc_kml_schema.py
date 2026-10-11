from pathlib import Path
from collections import Counter
import xml.etree.ElementTree as ET
import re

path = Path(
    "data/raw/flood/chennai_2015_nrsc_candidate/"
    "opencity_nrsc_chennai_2015_inundation.kml"
)

print("=" * 72)
print("NRSC 2015 KML — FIELD AND CLASS SEMANTICS AUDIT")
print("=" * 72)

if not path.exists():
    raise FileNotFoundError(f"KML not found: {path.resolve()}")

root = ET.parse(path).getroot()

def local_name(tag):
    return tag.rsplit("}", 1)[-1]

# 1. Print KML schema and field definitions.
print("\n--- SCHEMA DEFINITIONS ---")
schemas_found = 0

for elem in root.iter():
    if local_name(elem.tag) == "Schema":
        schemas_found += 1
        print(f"\nSchema id={elem.get('id')} name={elem.get('name')}")
        for child in elem:
            if local_name(child.tag) in ("SimpleField", "field"):
                print(
                    f"  name={child.get('name')!r}, "
                    f"type={child.get('type')!r}, "
                    f"displayName={child.get('displayName')!r}"
                )

if schemas_found == 0:
    print("No KML Schema elements found.")

# 2. Collect field names and values from every Placemark.
placemarks = [
    elem for elem in root.iter()
    if local_name(elem.tag) == "Placemark"
]

print(f"\n--- PLACEMARKS: {len(placemarks)} ---")
field_counts = {}
value_counts = {}

for pm in placemarks:
    for elem in pm.iter():
        if local_name(elem.tag) == "SimpleData":
            name = elem.get("name", "<unnamed>")
            value = (elem.text or "").strip()
            field_counts[name] = field_counts.get(name, 0) + 1
            value_counts.setdefault(name, Counter())[value] += 1

print("\n--- FIELD NAMES ---")
for name, count in field_counts.items():
    print(f"{name}: present in {count}/{len(placemarks)} placemarks")

print("\n--- UNIQUE VALUES PER FIELD ---")
for name, counts in value_counts.items():
    print(f"\n{name}:")
    for value, count in counts.most_common(30):
        print(f"  {value!r}: {count}")

# 3. Inspect styles and any text that might explain the legend.
print("\n--- STYLE DEFINITIONS ---")
styles = [
    elem for elem in root.iter()
    if local_name(elem.tag) in ("Style", "StyleMap")
]
print(f"Style / StyleMap elements: {len(styles)}")

for elem in styles[:20]:
    print(
        f"  {local_name(elem.tag)} id={elem.get('id')!r}"
    )
    for child in elem.iter():
        if local_name(child.tag) in (
            "color", "colorMode", "fill", "outline",
            "PolyStyle", "LineStyle", "IconStyle"
        ):
            text = (child.text or "").strip()
            if text:
                print(f"    {local_name(child.tag)}: {text}")

# 4. Search descriptive text for documented class meanings.
print("\n--- LEGEND / CLASS DOCUMENTATION TEXT ---")
texts = []

for elem in root.iter():
    if local_name(elem.tag) in (
        "name", "description", "displayName", "value"
    ):
        value = (elem.text or "").strip()
        if value:
            texts.append(value)

patterns = re.compile(
    r"pixelvalue|inundat|flood|water|class|legend|raster|"
    r"permanent|temporary|13|\\b0\\b",
    re.IGNORECASE
)

matches = []
for value in texts:
    if patterns.search(value):
        matches.append(value)

for value in matches[:80]:
    print(" ", value[:500])

if not matches:
    print("No potentially relevant legend text found.")

print("\nAudit complete. No labels or training data were created.")
