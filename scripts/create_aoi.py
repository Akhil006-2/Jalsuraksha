import geopandas as gpd
from shapely.geometry import box
from pathlib import Path


# ============================================================
# JALSURAKSHA
# Chennai / Velachery-Pallikaranai Study AOI
# ============================================================

# Bounding box
WEST = 80.170
SOUTH = 12.900
EAST = 80.270
NORTH = 12.995

# Create rectangular polygon
aoi_geometry = box(WEST, SOUTH, EAST, NORTH)

# Create GeoDataFrame
aoi = gpd.GeoDataFrame(
    {
        "aoi_id": ["CHENNAI_VELACHERY_PALLIKARANAI"],
        "name": ["Velachery-Pallikaranai Study Area"],
    },
    geometry=[aoi_geometry],
    crs="EPSG:4326"
)

# Output directory
output_dir = Path("data/aoi")
output_dir.mkdir(parents=True, exist_ok=True)

# Save
output_file = output_dir / "study_area.geojson"

aoi.to_file(output_file, driver="GeoJSON")

print("=" * 60)
print("JALSURAKSHA AOI CREATED")
print("=" * 60)

print(f"Output: {output_file}")
print(f"CRS: {aoi.crs}")
print()
print("Bounds:")
print(f"West : {WEST}")
print(f"South: {SOUTH}")
print(f"East : {EAST}")
print(f"North: {NORTH}")
print()
projected = aoi.to_crs("EPSG:32644")

print(
    "Area (km²):",
    projected.geometry.area.iloc[0] / 1_000_000
)
print("AOI created successfully.")