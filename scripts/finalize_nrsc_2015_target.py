from pathlib import Path
import json
import geopandas as gpd
from shapely.geometry import box

ROOT = Path(".")
SOURCE = ROOT / "data/raw/flood/chennai_2015_nrsc_candidate/official_geoserver_nrsc_2015_check.geojson"
OUT_DIR = ROOT / "data/processed/flood"
OUT_FILE = OUT_DIR / "chennai_nrsc_2015_observed_inundation.geojson"
META_FILE = OUT_DIR / "chennai_nrsc_2015_target_metadata.json"

# The existing Jalsuraksha AOI
WEST, SOUTH, EAST, NORTH = 80.170, 12.900, 80.270, 12.995

if not SOURCE.exists():
    raise FileNotFoundError(
        f"Official GeoServer export not found: {SOURCE.resolve()}"
    )

OUT_DIR.mkdir(parents=True, exist_ok=True)

gdf = gpd.read_file(SOURCE)

if gdf.crs is None:
    raise ValueError("Source CRS is missing; refusing to guess coordinates.")

# Reproject to longitude/latitude before applying the AOI.
gdf = gdf.to_crs("EPSG:4326")
gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

aoi = box(WEST, SOUTH, EAST, NORTH)
intersecting = gdf[gdf.geometry.intersects(aoi)].copy()

if intersecting.empty:
    raise RuntimeError("No official flood polygons intersect the specified AOI.")

# Clip polygons to the AOI. Keep only valid, nonempty polygonal results.
intersecting["geometry"] = intersecting.geometry.intersection(aoi)
intersecting = intersecting[
    intersecting.geometry.notna() & ~intersecting.geometry.is_empty
].copy()
intersecting = intersecting[
    intersecting.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
].copy()

if intersecting.empty:
    raise RuntimeError("No polygon geometry remains after clipping.")

# These labels mean "inside the published historical inundation extent",
# NOT that pixelvalue meanings have been decoded.
intersecting["label"] = 1
intersecting["label_type"] = "observed_inundation_extent"
intersecting["event_year"] = 2015
intersecting["source_name"] = "Chennai Flood Monitoring DSS / NRSC layer"
intersecting["pixelvalue_semantics"] = "unverified_do_not_use_as_class"

intersecting.to_file(OUT_FILE, driver="GeoJSON")

metadata = {
    "dataset": "Jalsuraksha Chennai historical inundation target",
    "source_layer": "ChennaiDSS:gis_flood_inundation_nrsc_flood_extent_2015",
    "source_url": "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows",
    "mirror": "OpenCity Chennai 2015 Floods Inundation Zone KML",
    "event_year": 2015,
    "output_crs": "EPSG:4326",
    "aoi_west_south_east_north": [WEST, SOUTH, EAST, NORTH],
    "source_feature_count": int(len(gdf)),
    "features_intersecting_aoi_before_clip": int(
        gdf.geometry.intersects(aoi).sum()
    ),
    "output_polygon_count": int(len(intersecting)),
    "label_definition": (
        "1 means geometry falls within the published NRSC 2015 "
        "inundation-extent polygons."
    ),
    "negative_labels_created": 0,
    "pixelvalue_counts_in_output": {
        str(k): int(v)
        for k, v in intersecting["pixelvalue"].value_counts(dropna=False).items()
    } if "pixelvalue" in intersecting.columns else {},
    "pixelvalue_semantics": (
        "Unknown. Values 0, 1 and 13 have not been assigned class meanings."
    ),
    "limitations": [
        "Areas outside the mapped extent are not confirmed non-flood observations.",
        "The target represents the 2015 event, not the 2018-2025 rainfall period.",
        "This is an observed-extent target, not a complete supervised training dataset."
    ]
}

META_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

print("=" * 72)
print("NRSC 2015 TARGET PREPARATION COMPLETE")
print("=" * 72)
print(f"Official source features: {len(gdf)}")
print(f"AOI output polygons:      {len(intersecting)}")
print("Positive extent labels:   1 = inside mapped inundation extent")
print("Negative labels created:  0")
print("pixelvalue decoded:       NO")
print(f"\nGeoJSON:  {OUT_FILE.resolve()}")
print(f"Metadata: {META_FILE.resolve()}")
print("\nDo not train a binary flood classifier from this file alone.")
