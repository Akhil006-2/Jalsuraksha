import rasterio
import numpy as np
from pathlib import Path

DEM_PATH = Path(
    "data/raw/dem/N12E080/"
    "Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif"
)

print("=" * 70)
print("JALSURAKSHA - DEM VERIFICATION")
print("=" * 70)

if not DEM_PATH.exists():
    raise FileNotFoundError(f"DEM not found: {DEM_PATH}")

with rasterio.open(DEM_PATH) as src:

    print("\nFILE")
    print(f"Path       : {DEM_PATH}")
    print(f"Width      : {src.width}")
    print(f"Height     : {src.height}")
    print(f"Band count : {src.count}")

    print("\nSPATIAL INFORMATION")
    print(f"CRS        : {src.crs}")
    print(f"Bounds     : {src.bounds}")
    print(f"Resolution : {src.res}")

    print("\nDATA TYPE")
    print(f"Dtype      : {src.dtypes[0]}")
    print(f"NoData     : {src.nodata}")

    data = src.read(1, masked=True)

    print("\nELEVATION STATISTICS")
    print(f"Minimum    : {data.min():.2f} m")
    print(f"Maximum    : {data.max():.2f} m")
    print(f"Mean       : {data.mean():.2f} m")
    print(f"Median     : {np.ma.median(data):.2f} m")

    print("\nVALID PIXELS")
    print(f"Valid      : {data.count()}")
    print(f"Total      : {data.size}")
    print(f"Valid %    : {100 * data.count() / data.size:.2f}%")

print("\n" + "=" * 70)
print("DEM VERIFICATION COMPLETE")
print("=" * 70)