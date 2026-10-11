
import os
import re
import pandas as pd

INPUT_FILE = "data/processed/sentinel1/sentinel1_chennai_products.csv"
OUTPUT_DIR = "data/processed/sentinel1"
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "sentinel1_chennai_products_clean.csv"
)

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("JALSURAKSHA - SENTINEL-1 CATALOGUE CLEANUP")
print("=" * 70)

df = pd.read_csv(INPUT_FILE)

print("Input products:", len(df))

# Extract acquisition identity from the Sentinel-1 product name.
# Example: S1A_IW_GRDH_1SDV_20180112T003140_...
df["acquisition_key"] = df["name"].str.extract(
    r"^(S1[A-Z]_IW_GRDH_[^_]+_[^_]+_[0-9]{8}T[0-9]{6})"
)

missing_keys = df["acquisition_key"].isna().sum()

if missing_keys:
    raise ValueError(
        f"{missing_keys} products have unrecognized names. "
        "Inspect these before deduplication."
    )

# Prefer Cloud Optimized GeoTIFF products when both versions exist.
df["is_cog"] = df["name"].str.contains(
    "_COG.SAFE",
    case=False,
    regex=False
)

# Prefer COG, then use the product name for deterministic tie-breaking.
df = df.sort_values(
    ["is_cog", "name"],
    ascending=[False, True]
)

clean = df.drop_duplicates(
    subset=["acquisition_key"],
    keep="first"
).copy()

clean = clean.sort_values("datetime").reset_index(drop=True)

clean = clean.drop(
    columns=["acquisition_key", "is_cog"]
)

clean.to_csv(OUTPUT_FILE, index=False)

print("\nCLEANUP SUMMARY")
print("-" * 70)
print("Original products :", len(df))
print("Unique acquisitions:", len(clean))
print("Removed duplicates:", len(df) - len(clean))
print("\nAcquisitions by year:")
print(
    pd.to_datetime(clean["datetime"], utc=True)
    .dt.year.value_counts()
    .sort_index()
)

print("\nSaved:", OUTPUT_FILE)
print("=" * 70)
