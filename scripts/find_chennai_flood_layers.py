
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"

# Your current Chennai study area
WEST, SOUTH, EAST, NORTH = 80.170, 12.900, 80.270, 12.995


def tag_name(tag):
    return tag.split("}")[-1]


def direct_child(element, name):
    for child in element:
        if tag_name(child.tag) == name:
            return child
    return None


def read_bbox(element):
    # Prefer the geographic bounding box.
    node = direct_child(element, "LatLonBoundingBox")

    if node is not None:
        attrs = node.attrib
        return (
            float(attrs["minx"]),
            float(attrs["miny"]),
            float(attrs["maxx"]),
            float(attrs["maxy"]),
            "LatLonBoundingBox",
        )

    # Otherwise accept an EPSG:4326 bounding box.
    for child in element:
        if tag_name(child.tag) != "BoundingBox":
            continue

        attrs = child.attrib
        crs = attrs.get("SRS", attrs.get("CRS", ""))

        if crs.upper() in ("EPSG:4326", "CRS:84"):
            return (
                float(attrs["minx"]),
                float(attrs["miny"]),
                float(attrs["maxx"]),
                float(attrs["maxy"]),
                crs,
            )

    return None


def overlaps(a, b):
    minx, miny, maxx, maxy = a
    west, south, east, north = b

    return (
        maxx >= west
        and minx <= east
        and maxy >= south
        and miny <= north
    )


def main():
    print("=" * 75)
    print("JALSURAKSHA - SEARCH ALL WMS LAYERS FOR CHENNAI")
    print("=" * 75)

    response = requests.get(
        URL,
        params={
            "SERVICE": "WMS",
            "REQUEST": "GetCapabilities",
            "VERSION": "1.1.1",
        },
        timeout=60,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)

    results = []

    def walk(element):
        if tag_name(element.tag) == "Layer":
            name_node = direct_child(element, "Name")
            title_node = direct_child(element, "Title")

            name = (
                name_node.text.strip()
                if name_node is not None and name_node.text
                else ""
            )
            title = (
                title_node.text.strip()
                if title_node is not None and title_node.text
                else ""
            )

            bbox = read_bbox(element)

            if name and bbox:
                minx, miny, maxx, maxy, source = bbox
                bounds = (minx, miny, maxx, maxy)

                if overlaps(bounds, (WEST, SOUTH, EAST, NORTH)):
                    results.append((name, title, bounds, source))

        for child in element:
            walk(child)

    walk(root)

    output = Path("data/processed/flood")
    output.mkdir(parents=True, exist_ok=True)
    report = output / "chennai_overlapping_wms_layers.txt"

    print(f"\nLayers overlapping Chennai AOI: {len(results)}")

    with report.open("w", encoding="utf-8") as file:
        for name, title, bounds, source in results:
            line = (
                f"NAME: {name}\n"
                f"TITLE: {title}\n"
                f"BOUNDS: {bounds}\n"
                f"BOUND SOURCE: {source}\n"
            )
            print("\n" + line)
            file.write(line + "\n")

    if not results:
        print(
            "\nNo overlapping layers were found using the geographic "
            "bounds published in the service."
        )

    print("\nReport saved to:", report)
    print("No labels or training data were created.")


if __name__ == "__main__":
    main()
