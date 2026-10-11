from pathlib import Path
import json
import pandas as pd
import rasterio
import geopandas as gpd

root = Path("data")

rasters = [
    root / "processed/dem/chennai_aoi_dem.tif",
    root / "processed/lulc/chennai_aoi_worldcover_2021.tif",
]

tables = [
    root / "processed/rainfall/chennai_daily_rainfall_2018_2025.csv",
    root / "processed/rainfall/chennai_rainfall_features_2018_2025.csv",
    root / "processed/sentinel1/sentinel1_chennai_products_clean.csv",
]

vectors = [
    root / "aoi/study_area.geojson",
    root / "processed/flood/chennai_nrsc_2015_observed_inundation.geojson",
]

print("=" * 76)
print("JALSURAKSHA — PRE-TRAINING DATA AUDIT")
print("=" * 76)

print("\n1. RASTER METADATA")
for path in rasters:
    print(f"\n--- {path} ---")
    if not path.exists():
        print("MISSING")
        continue

    with rasterio.open(path) as ds:
        print("CRS:", ds.crs)
        print("Width x height:", ds.width, "x", ds.height)
        print("Bands:", ds.count)
        print("Resolution:", ds.res)
        print("Bounds:", ds.bounds)
        print("NoData:", ds.nodata)
        print("Dtype:", ds.dtypes)
        print("Pixel size:", abs(ds.res[0]), abs(ds.res[1]))

        band = ds.read(1, masked=True)
        if band.count():
            print("Valid pixel count:", int(band.count()))
            print("Min:", float(band.min()))
            print("Max:", float(band.max()))

print("\n\n2. CSV SCHEMAS AND DATE COVERAGE")
for path in tables:
    print(f"\n--- {path} ---")
    if not path.exists():
        print("MISSING")
        continue

    df = pd.read_csv(path)
    print("Rows:", len(df))
    print("Columns:", df.columns.tolist())
    print("Missing values by column:")
    print(df.isna().sum().to_dict())

    for col in df.columns:
        if "date" in col.lower() or col.lower() in ("time", "datetime"):
            dates = pd.to_datetime(df[col], errors="coerce")
            if dates.notna().any():
                print(
                    f"Date column {col}:",
                    dates.min(), "to", dates.max()
                )

    if "pixelvalue" in df.columns:
        print("Pixelvalue counts:", df["pixelvalue"].value_counts().to_dict())

print("\n\n3. VECTOR METADATA")
for path in vectors:
    print(f"\n--- {path} ---")
    if not path.exists():
        print("MISSING")
        continue

    gdf = gpd.read_file(path)
    print("Features:", len(gdf))
    print("CRS:", gdf.crs)
    print("Geometry types:", gdf.geometry.geom_type.value_counts().to_dict())
    print("Bounds:", gdf.total_bounds.tolist())
    print("Columns:", gdf.columns.tolist())
    print("Invalid geometries:", int((~gdf.geometry.is_valid).sum()))
    print("Empty geometries:", int(gdf.geometry.is_empty.sum()))

    if "pixelvalue" in gdf.columns:
        print("Pixelvalue counts:", gdf["pixelvalue"].value_counts().to_dict())

print("\n\n4. SENTINEL-1 CATALOGUE SAMPLE")
path = root / "processed/sentinel1/sentinel1_chennai_products_clean.csv"
if path.exists():
    df = pd.read_csv(path)
    print(df.head(5).to_string(index=False, max_cols=12))
    print("\nUnique values in likely date columns:")
    for col in df.columns:
        if any(word in col.lower() for word in ("date", "time", "polar", "orbit", "mode")):
            print(f"{col}: {df[col].nunique(dropna=True)} unique values")

print("\n\nAudit finished. No files modified and no model trained.")
