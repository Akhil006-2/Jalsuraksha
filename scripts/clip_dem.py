import geopandas as gpd
import rasterio
from rasterio.mask import mask
from pathlib import Path


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

DEM_PATH = Path(
    "data/raw/dem/N12E080/"
    "Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif"
)

AOI_PATH = Path(
    "data/aoi/study_area.geojson"
)

OUTPUT_DIR = Path("data/processed/dem")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = OUTPUT_DIR / "chennai_aoi_dem.tif"


# ---------------------------------------------------------
# LOAD AOI
# ---------------------------------------------------------

print("=" * 70)
print("JALSURAKSHA - DEM CLIPPING")
print("=" * 70)

print("\nLoading AOI...")

aoi = gpd.read_file(AOI_PATH)

print(f"AOI CRS: {aoi.crs}")
print(f"AOI features: {len(aoi)}")


# ---------------------------------------------------------
# OPEN DEM
# ---------------------------------------------------------

print("\nOpening DEM...")

with rasterio.open(DEM_PATH) as src:

    print(f"DEM CRS: {src.crs}")

    # Make sure AOI uses the same CRS as DEM
    aoi = aoi.to_crs(src.crs)

    geometries = aoi.geometry.values

    # -----------------------------------------------------
    # CLIP
    # -----------------------------------------------------

    print("\nClipping DEM to AOI...")

    clipped, transform = mask(
        src,
        geometries,
        crop=True
    )

    # Copy original metadata
    metadata = src.meta.copy()

    # Update metadata for clipped raster
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
print("DEM CLIPPING COMPLETE")
print("=" * 70)

print(f"\nInput DEM:")
print(f"  {DEM_PATH}")

print(f"\nAOI:")
print(f"  {AOI_PATH}")

print(f"\nOutput DEM:")
print(f"  {OUTPUT_PATH}")

print("\nNext step:")
print("  Verify the clipped DEM.")
print("=" * 70)