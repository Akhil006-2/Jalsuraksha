from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

path = Path(
    r"data/raw/flood/chennai_2015_nrsc_candidate/"
    r"nrsc_flood_extent_2015.parquet"
)

west, south, east, north = 80.170, 12.900, 80.270, 12.995
aoi = box(west, south, east, north)

print("=" * 72)
print("CHENNAI 2015 FLOOD EXTENT - CANDIDATE INSPECTION")
print("=" * 72)
print("File exists:", path.exists())

if not path.exists():
    raise SystemExit("ERROR: Candidate file was not downloaded.")

print("File size:", path.stat().st_size, "bytes")

try:
    gdf = gpd.read_parquet(path)
except Exception as exc:
    raise SystemExit(f"ERROR reading Parquet: {type(exc).__name__}: {exc}")

print("\n--- STRUCTURE ---")
print("Feature count:", len(gdf))
print("CRS:", gdf.crs)
print("Columns:", list(gdf.columns))

if "geometry" not in gdf:
    raise SystemExit("STOP: No geometry column. This is not verified spatial data.")

print("\nGeometry types:")
print(gdf.geometry.geom_type.value_counts(dropna=False).to_string())

print("\n--- GEOGRAPHIC COVERAGE ---")
print("Native bounds:", gdf.total_bounds)

if gdf.crs is None:
    raise SystemExit("STOP: CRS is missing; cannot safely verify Chennai coverage.")

gdf_geo = gdf.to_crs("EPSG:4326")

print("Bounds in EPSG:4326:", gdf_geo.total_bounds)

nonempty = gdf_geo.geometry.notna() & ~gdf_geo.geometry.is_empty
valid = gdf_geo.geometry.is_valid

print("Non-empty geometries:", int(nonempty.sum()))
print("Null geometries:", int(gdf_geo.geometry.isna().sum()))
print("Invalid non-empty geometries:", int((nonempty & ~valid).sum()))

intersects = nonempty & gdf_geo.geometry.intersects(aoi)
print("Features intersecting Chennai AOI:", int(intersects.sum()))

if intersects.any():
    print("\n--- INTERSECTING FEATURE ATTRIBUTES ---")
    print(gdf_geo.loc[intersects].drop(columns="geometry").head(10).to_string())

print("\n--- SAMPLE ATTRIBUTES ---")
print(gdf_geo.drop(columns="geometry").head(5).to_string())

print("\nInspection only. No labels or training data were created.")
