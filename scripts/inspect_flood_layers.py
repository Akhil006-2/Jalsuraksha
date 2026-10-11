
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"

print("=" * 75)
print("JALSURAKSHA - OFFICIAL FLOOD LAYER INSPECTOR")
print("=" * 75)

params = {
    "SERVICE": "WMS",
    "REQUEST": "GetCapabilities",
    "VERSION": "1.1.1",
}

try:
    response = requests.get(URL, params=params, timeout=60)
    print("\nHTTP status:", response.status_code)
    print("Response URL:", response.url)
    print("Content type:", response.headers.get("Content-Type"))
    response.raise_for_status()

    content = response.content
    if b"<WMS_Capabilities" not in content and b"<WMT_MS_Capabilities" not in content:
        print("\nThe response does not look like standard WMS capabilities.")
        print(content[:1500].decode("utf-8", errors="replace"))
        raise SystemExit(1)

    output = Path("data/processed/flood")
    output.mkdir(parents=True, exist_ok=True)

    xml_path = output / "bhuvan_flood_capabilities.xml"
    xml_path.write_bytes(content)
    print("Saved capabilities:", xml_path)

    root = ET.fromstring(content)

    def local_name(tag):
        return tag.split("}")[-1]

    def child_text(element, wanted):
        for child in element:
            if local_name(child.tag) == wanted and child.text:
                return child.text.strip()
        return ""

    layers = []

    def walk(element):
        if local_name(element.tag) == "Layer":
            name = child_text(element, "Name")
            title = child_text(element, "Title")
            abstract = child_text(element, "Abstract")

            if name:
                layers.append({
                    "name": name,
                    "title": title,
                    "abstract": abstract,
                })

        for child in element:
            walk(child)

    walk(root)

    print(f"\nTotal named layers found: {len(layers)}")
    print("\n--- Layers relevant to Tamil Nadu / Chennai / flood events ---")

    keywords = (
        "tamil", "chennai", "tn_", "2021", "2020", "2015",
        "flood", "inund", "cumulative"
    )

    matches = [
        layer for layer in layers
        if any(
            word in (
                layer["name"] + " " +
                layer["title"] + " " +
                layer["abstract"]
            ).lower()
            for word in keywords
        )
    ]

    for layer in matches:
        print("\nLayer name:", layer["name"])
        print("Title:", layer["title"])
        if layer["abstract"]:
            print("Abstract:", layer["abstract"][:400])

    names_path = output / "bhuvan_flood_layer_names.txt"
    with names_path.open("w", encoding="utf-8") as file:
        for layer in layers:
            file.write(
                f'{layer["name"]}\t{layer["title"]}\t'
                f'{layer["abstract"]}\n'
            )

    print("\nAll layer names saved to:", names_path)
    print("\nInspection finished. No flood labels were created.")

except requests.RequestException as error:
    print("\nNetwork/request error:", error)
except ET.ParseError as error:
    print("\nCould not parse capabilities XML:", error)
