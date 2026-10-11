import json
import rasterio
import numpy as np
from pathlib import Path


LULC_PATH = Path(
    "data/processed/lulc/chennai_aoi_worldcover_2021.tif"
)

CONFIG_PATH = Path(
    "config/lulc_classes.json"
)


print("=" * 70)
print("JALSURAKSHA - LULC FEATURE MAPPING")
print("=" * 70)


# ---------------------------------------------------------
# LOAD CONFIGURATION
# ---------------------------------------------------------

with open(CONFIG_PATH, "r") as f:
    classes = json.load(f)


# ---------------------------------------------------------
# READ RASTER
# ---------------------------------------------------------

with rasterio.open(LULC_PATH) as src:
    data = src.read(1)


total_pixels = data.size


# ---------------------------------------------------------
# CALCULATE FEATURE PERCENTAGES
# ---------------------------------------------------------

print("\nFEATURE GROUPS")
print("-" * 70)

for feature_name, class_values in classes.items():

    mask = np.isin(data, class_values)

    count = mask.sum()

    percentage = (
        count / total_pixels
    ) * 100

    print(
        f"{feature_name:<12} : "
        f"{percentage:6.2f}% "
        f"(classes: {class_values})"
    )


# ---------------------------------------------------------
# CHECK
# ---------------------------------------------------------

built_up = np.isin(
    data,
    classes["built_up"]
).sum()

vegetation = np.isin(
    data,
    classes["vegetation"]
).sum()

water = np.isin(
    data,
    classes["water"]
).sum()

other = np.isin(
    data,
    classes["other"]
).sum()

covered = (
    built_up +
    vegetation +
    water +
    other
)

print("\nCOVERAGE CHECK")
print("-" * 70)

print(
    f"Mapped pixels : {covered:,}"
)

print(
    f"Total pixels  : {total_pixels:,}"
)

print(
    f"Coverage      : "
    f"{100 * covered / total_pixels:.2f}%"
)

print("\n" + "=" * 70)
print("LULC FEATURE MAPPING COMPLETE")
print("=" * 70)