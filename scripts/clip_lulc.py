import geopandas as gpd
import rasterio
from rasterio.mask import mask
from pathlib import Path


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

LULC_PATH = Path(
    "data/raw/lulc/"
    "ESA_WorldCover_10m_2021_v200_N12E078_Map.tif"
)

AOI_PATH = Path(
    "data/aoi/study_area.geojson"
)

OUTPUT_DIR = Path("data/processed/lulc")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = OUTPUT_DIR / "chennai_aoi_worldcover_2021.tif"


# ---------------------------------------------------------
# LOAD AOI
# ---------------------------------------------------------

print("=" * 70)
print("JALSURAKSHA - WORLDCOVER CLIPPING")
print("=" * 70)

print("\nLoading AOI...")

aoi = gpd.read_file(AOI_PATH)

print(f"AOI CRS      : {aoi.crs}")
print(f"AOI features : {len(aoi)}")


# ---------------------------------------------------------
# OPEN WORLDCOVER
# ---------------------------------------------------------

print("\nOpening WorldCover...")

with rasterio.open(LULC_PATH) as src:

    print(f"WorldCover CRS: {src.crs}")

    # Match AOI CRS to raster
    aoi = aoi.to_crs(src.crs)

    geometries = aoi.geometry.values

    # -----------------------------------------------------
    # CLIP
    # -----------------------------------------------------

    print("\nClipping WorldCover to AOI...")

    clipped, transform = mask(
        src,
        geometries,
        crop=True
    )

    # Copy metadata
    metadata = src.meta.copy()

    # Update metadata
    metadata.update(
        {
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": transform,
            "compress": "deflate"
        }
    )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    with rasterio.open(
        OUTPUT_PATH,
        "w",
        **metadata
    ) as dst:

        dst.write(clipped)


# ---------------------------------------------------------
# RESULT
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("WORLDCOVER CLIPPING COMPLETE")
print("=" * 70)

print(f"\nInput:")
print(f"  {LULC_PATH}")

print(f"\nOutput:")
print(f"  {OUTPUT_PATH}")

print("\nNext step:")
print("  Verify WorldCover classes and visualization.")

print("=" * 70)