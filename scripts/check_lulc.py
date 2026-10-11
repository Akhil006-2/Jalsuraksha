import rasterio
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


LULC_PATH = Path(
    "data/processed/lulc/chennai_aoi_worldcover_2021.tif"
)

OUTPUT_PATH = Path(
    "data/processed/lulc/chennai_aoi_worldcover_preview.png"
)


# ---------------------------------------------------------
# WORLDCOVER CLASS DEFINITIONS
# ---------------------------------------------------------

CLASS_NAMES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


# ---------------------------------------------------------
# OPEN RASTER
# ---------------------------------------------------------

print("=" * 70)
print("JALSURAKSHA - WORLDCOVER VERIFICATION")
print("=" * 70)

with rasterio.open(LULC_PATH) as src:

    data = src.read(1)

    print("\nRASTER INFORMATION")
    print(f"Width       : {src.width}")
    print(f"Height      : {src.height}")
    print(f"CRS         : {src.crs}")
    print(f"Resolution  : {src.res}")
    print(f"Dtype       : {src.dtypes[0]}")

    print("\nBOUNDS")
    print(f"Left        : {src.bounds.left}")
    print(f"Bottom      : {src.bounds.bottom}")
    print(f"Right       : {src.bounds.right}")
    print(f"Top         : {src.bounds.top}")


# ---------------------------------------------------------
# CLASS COUNTS
# ---------------------------------------------------------

print("\nWORLDCOVER CLASSES")
print("-" * 70)

unique, counts = np.unique(data, return_counts=True)

total_pixels = data.size

for class_value, count in zip(unique, counts):

    percentage = (count / total_pixels) * 100

    name = CLASS_NAMES.get(
        int(class_value),
        "Unknown class"
    )

    print(
        f"{int(class_value):3d} | "
        f"{name:<30} | "
        f"{count:10d} pixels | "
        f"{percentage:6.2f}%"
    )


# ---------------------------------------------------------
# VISUALIZATION
# ---------------------------------------------------------

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

plt.colorbar(
    label="WorldCover Class"
)

plt.title(
    "JalSuraksha - ESA WorldCover 2021"
)

plt.xlabel("Longitude")
plt.ylabel("Latitude")

plt.tight_layout()

plt.savefig(
    OUTPUT_PATH,
    dpi=200,
    bbox_inches="tight"
)

plt.show()


print("\n" + "=" * 70)
print("WORLDCOVER VERIFICATION COMPLETE")
print("=" * 70)

print(f"\nPreview saved to:")
print(OUTPUT_PATH)