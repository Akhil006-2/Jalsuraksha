"""Static 100-year return-period flood-hazard polygons supplied by OpenCity/GCC.

These polygons describe mapped design hazard, not live flood conditions. Locations
outside the polygons are unclassified, not confirmed flood-free.
"""
from functools import lru_cache
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, MultiPolygon, Point, mapping
from shapely.strtree import STRtree

from app.config import settings

NS = {"k": "http://www.opengis.net/kml/2.2"}
CATEGORY_RISK = {"LOW": 0.20, "MODERATE": 0.65, "HIGH": 1.0}

def _ring(text):
    if not text:
        return []
    coords = []
    for token in text.split():
        bits = token.split(",")
        if len(bits) >= 2:
            try:
                coords.append((float(bits[0]), float(bits[1])))
            except ValueError:
                continue
    return coords

def _polygon(element):
    outer_el = element.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", NS)
    outer = _ring(outer_el.text if outer_el is not None else None)
    if len(outer) < 4:
        return None
    holes = []
    for el in element.findall("./k:innerBoundaryIs/k:LinearRing/k:coordinates", NS):
        ring = _ring(el.text)
        if len(ring) >= 4:
            holes.append(ring)
    try:
        geom = Polygon(outer, holes)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom if not geom.is_empty else None
    except Exception:
        return None

@lru_cache(maxsize=1)
def features():
    path = settings().flood_hazard_kml
    if not path.exists():
        return []
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    result = []
    for i, pm in enumerate(root.findall(".//k:Placemark", NS)):
        props = {el.attrib.get("name"): (el.text or "").strip()
                 for el in pm.findall(".//k:SimpleData", NS)}
        category = props.get("CATEGORY", "").upper()
        if category not in CATEGORY_RISK:
            continue
        polygons = [_polygon(el) for el in pm.findall(".//k:Polygon", NS)]
        polygons = [p for p in polygons if p is not None]
        if not polygons:
            continue
        geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        result.append({"id": str(props.get("OBJECTID", i)), "category": category,
                       "geometry": geom, "risk": CATEGORY_RISK[category]})
    return result

@lru_cache(maxsize=1)
def _spatial_index():
    rows = features()
    if not rows:
        return None, []
    geoms = [row["geometry"] for row in rows]
    return STRtree(geoms), rows

def classify(lat, lon):
    """Return mapped category for a point, preferring the highest overlapping hazard."""
    rows = features()
    if not rows:
        return {"category": "UNAVAILABLE", "risk": None, "mapped": False}
    point = Point(float(lon), float(lat))
    tree, indexed_rows = _spatial_index()
    candidate_indices = tree.query(point) if tree is not None else []
    matched = [indexed_rows[int(i)] for i in candidate_indices
               if indexed_rows[int(i)]["geometry"].covers(point)]
    if not matched:
        return {"category": "UNCLASSIFIED", "risk": None, "mapped": False}
    selected = max(matched, key=lambda row: row["risk"])
    return {"category": selected["category"], "risk": selected["risk"], "mapped": True}

def geojson():
    rows = features()
    if not rows:
        return {"type": "FeatureCollection", "features": [], "metadata": {
            "available": False, "message": "Flood-hazard KML is unavailable or invalid."}}
    out = []
    for row in rows:
        out.append({"type": "Feature", "id": row["id"],
                    "properties": {"category": row["category"], "risk": row["risk"],
                                   "source": "OpenCity / Greater Chennai Corporation",
                                   "return_period_years": 100},
                    "geometry": mapping(row["geometry"])})
    minx = min(r["geometry"].bounds[0] for r in rows)
    miny = min(r["geometry"].bounds[1] for r in rows)
    maxx = max(r["geometry"].bounds[2] for r in rows)
    maxy = max(r["geometry"].bounds[3] for r in rows)
    counts = {key: sum(1 for row in rows if row["category"] == key)
              for key in ("HIGH", "MODERATE", "LOW")}
    return {"type": "FeatureCollection", "features": out,
            "metadata": {"available": True, "source": "OpenCity / Greater Chennai Corporation",
                         "title": "Chennai Flows 100 Years Return Period",
                         "return_period_years": 100, "feature_count": len(rows),
                         "category_counts": counts, "bounds": [minx, miny, maxx, maxy],
                         "coverage_note": "Coverage is limited to the source polygons. Outside areas are unclassified, not flood-free.",
                         "time_note": "Static design-hazard dataset; not a live flood observation."}}

def status():
    rows = features()
    return {"available": bool(rows), "path": str(settings().flood_hazard_kml),
            "feature_count": len(rows),
            "source": "OpenCity / Greater Chennai Corporation",
            "return_period_years": 100,
            "coverage_note": "Outside mapped polygons means unclassified, not flood-free."}


def classify_segment(lat1, lon1, lat2, lon2):
    """Classify a road segment by polygon intersection, not just its midpoint."""
    from shapely.geometry import LineString
    rows = features()
    if not rows:
        return {"category": "UNAVAILABLE", "risk": None, "mapped": False}
    line = LineString([(float(lon1), float(lat1)), (float(lon2), float(lat2))])
    tree, indexed_rows = _spatial_index()
    candidates = tree.query(line) if tree is not None else []
    matched = [indexed_rows[int(i)] for i in candidates
               if indexed_rows[int(i)]["geometry"].intersects(line)]
    if not matched:
        return {"category": "UNCLASSIFIED", "risk": None, "mapped": False}
    selected = max(matched, key=lambda row: row["risk"])
    return {"category": selected["category"], "risk": selected["risk"], "mapped": True}


def classify_segments(segments):
    """Vectorized STRtree classification of road segments by polygon intersection."""
    from shapely.geometry import LineString
    rows = features()
    if not rows:
        return ["UNAVAILABLE"] * len(segments)
    tree, indexed_rows = _spatial_index()
    categories = ["UNCLASSIFIED"] * len(segments)
    if not segments or tree is None:
        return categories
    lines = [LineString([(float(lon1), float(lat1)), (float(lon2), float(lat2))])
             for lat1, lon1, lat2, lon2 in segments]
    pairs = tree.query(lines, predicate="intersects")
    best = [0.0] * len(lines)
    for line_index, polygon_index in zip(pairs[0], pairs[1]):
        row = indexed_rows[int(polygon_index)]
        i = int(line_index)
        if row["risk"] > best[i]:
            best[i] = row["risk"]
            categories[i] = row["category"]
    return categories
