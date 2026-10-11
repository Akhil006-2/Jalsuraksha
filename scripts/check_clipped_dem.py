import rasterio
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


DEM_PATH = Path(
    "data/processed/dem/chennai_aoi_dem.tif"
)

print("=" * 70)
print("JALSURAKSHA - CLIPPED DEM VERIFICATION")
print("=" * 70)

with rasterio.open(DEM_PATH) as src:

    data = src.read(1, masked=True)

    print("\nRASTER INFORMATION")
    print(f"Width       : {src.width}")
    print(f"Height      : {src.height}")
    print(f"CRS         : {src.crs}")
    print(f"Resolution  : {src.res}")

    print("\nBOUNDS")
    print(f"Left        : {src.bounds.left}")
    print(f"Bottom      : {src.bounds.bottom}")
    print(f"Right       : {src.bounds.right}")
    print(f"Top         : {src.bounds.top}")

    print("\nELEVATION")
    print(f"Minimum     : {data.min():.2f} m")
    print(f"Maximum     : {data.max():.2f} m")
    print(f"Mean        : {data.mean():.2f} m")
    print(f"Median      : {np.ma.median(data):.2f} m")

    print("\nVALID PIXELS")
    print(f"Valid       : {data.count()}")
    print(f"Total       : {data.size}")
    print(f"Valid %     : {100 * data.count() / data.size:.2f}%")

    # -----------------------------------------------------
    # VISUALIZATION
    # -----------------------------------------------------

    plt.figure(figsize=(10, 8))

    plt.imshow(
        data,
        extent=[
            src.bounds.left,
            src.bounds.right,
            src.bounds.bottom,
            src.bounds.top
        ],
        origin="upper"
    )

    plt.colorbar(label="Elevation (m)")

    plt.title(
        "JalSuraksha - Chennai Study Area DEM"
    )

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")

    plt.tight_layout()

    output_path = Path(
        "data/processed/dem/chennai_aoi_dem_preview.png"
    )

    plt.savefig(
        output_path,
        dpi=200,
        bbox_inches="tight"
    )

    plt.show()

print("\n" + "=" * 70)
print("CLIPPED DEM VERIFICATION COMPLETE")
print("=" * 70)

print(f"\nPreview saved to:")
print("data/processed/dem/chennai_aoi_dem_preview.png")