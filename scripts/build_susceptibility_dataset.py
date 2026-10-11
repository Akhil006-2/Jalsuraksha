from pathlib import Path
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import requests

from scipy.ndimage import distance_transform_edt
from rasterio.features import rasterize
from rasterio.transform import xy
from shapely.geometry import LineString
from shapely.ops import unary_union
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path("data")
STACK = ROOT / "processed/training_prep/chennai_spatial_feature_stack_30m.tif"
FLOOD = ROOT / "processed/flood/chennai_nrsc_2015_observed_inundation.geojson"
OUT = ROOT / "processed/training_prep"
OUT.mkdir(parents=True, exist_ok=True)

CSV_OUT = OUT / "chennai_flood_susceptibility_presence_background.csv"
REPORT_OUT = OUT / "chennai_flood_susceptibility_dataset_report.json"

BUFFER_M = 300
BACKGROUND_RATIO = 1.0
RANDOM_SEED = 42

for p in (STACK, FLOOD):
    if not p.exists():
        raise FileNotFoundError(f"Missing required file: {p.resolve()}")

rng = np.random.default_rng(RANDOM_SEED)

# ---------------------------------------------------------
# 1. Read the aligned 30 m feature stack
# ---------------------------------------------------------
with rasterio.open(STACK) as ds:
    elevation = ds.read(1).astype("float32")
    slope = ds.read(2).astype("float32")
    lulc = ds.read(3).astype("float32")
    transform = ds.transform
    crs = ds.crs
    height, width = ds.height, ds.width
    nodata = ds.nodata
    profile = ds.profile.copy()

if crs is None:
    raise ValueError("Feature stack has no CRS.")

valid = (
    np.isfinite(elevation)
    & np.isfinite(slope)
    & np.isfinite(lulc)
    & (elevation != nodata)
    & (slope != nodata)
    & (lulc != nodata)
    & (lulc != 0)
)

# ---------------------------------------------------------
# 2. Rasterize the historical observed extent and its buffer
# ---------------------------------------------------------
flood = gpd.read_file(FLOOD).to_crs(crs)
flood = flood[
    flood.geometry.notna()
    & ~flood.geometry.is_empty
    & flood.geometry.is_valid
].copy()

if flood.empty:
    raise ValueError("No valid historical flood geometries.")

flood_union = unary_union(flood.geometry.tolist())

flood_mask = rasterize(
    [(flood_union, 1)],
    out_shape=(height, width),
    transform=transform,
    fill=0,
    all_touched=False,
    dtype="uint8"
).astype(bool)

buffer_geom = flood_union.buffer(BUFFER_M)
buffer_mask = rasterize(
    [(buffer_geom, 1)],
    out_shape=(height, width),
    transform=transform,
    fill=0,
    all_touched=False,
    dtype="uint8"
).astype(bool)

# ESA WorldCover class 80 denotes permanent water.
permanent_water = valid & (lulc == 80)

if not permanent_water.any():
    raise RuntimeError(
        "No permanent-water pixels found; cannot calculate water distance."
    )

pixel_y = abs(transform.e)
pixel_x = abs(transform.a)

distance_water = distance_transform_edt(
    ~permanent_water,
    sampling=(pixel_y, pixel_x)
).astype("float32")

# ---------------------------------------------------------
# 3. Attempt to retrieve mapped drainage from OpenStreetMap
# ---------------------------------------------------------
drainage_distance = None
drainage_status = "unavailable"

try:
    # AOI order: south, west, north, east.
    query = """
    [out:json][timeout:35];
    way["waterway"~"river|stream|canal|ditch|drain"]
      (12.900,80.170,12.995,80.270);
    out geom;
    """

    response = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=45
    )
    response.raise_for_status()
    osm_data = response.json()

    line_shapes = []
    for element in osm_data.get("elements", []):
        coords = [
            (p["lon"], p["lat"])
            for p in element.get("geometry", [])
            if "lon" in p and "lat" in p
        ]
        if len(coords) >= 2:
            line_shapes.append(
                (LineString(coords), 1)
            )

    if line_shapes:
        lines_gdf = gpd.GeoDataFrame(
            geometry=[g for g, _ in line_shapes],
            crs="EPSG:4326"
        ).to_crs(crs)

        drainage_raster = rasterize(
            [(geom, 1) for geom in lines_gdf.geometry],
            out_shape=(height, width),
            transform=transform,
            fill=0,
            all_touched=True,
            dtype="uint8"
        ).astype(bool)

        if drainage_raster.any():
            drainage_distance = distance_transform_edt(
                ~drainage_raster,
                sampling=(pixel_y, pixel_x)
            ).astype("float32")
            drainage_status = (
                f"OpenStreetMap waterway lines; "
                f"{len(lines_gdf)} features retrieved"
            )
        else:
            drainage_status = "OSM returned lines but none rasterized in grid"
    else:
        drainage_status = "No matching OSM waterway lines returned"

except Exception as exc:
    drainage_status = (
        "OSM download failed; drainage feature omitted: "
        f"{type(exc).__name__}: {str(exc)[:250]}"
    )

# ---------------------------------------------------------
# 4. Define presence and eligible background cells
# ---------------------------------------------------------
positive = valid & flood_mask

# Background is kept outside the exclusion buffer and excludes
# permanent-water pixels. It is NOT verified non-flood evidence.
eligible_background = (
    valid
    & ~buffer_mask
    & ~flood_mask
    & (lulc != 80)
)

positive_indices = np.flatnonzero(positive)
background_indices = np.flatnonzero(eligible_background)

if len(positive_indices) == 0:
    raise RuntimeError("No positive cells found inside the flood extent.")

if len(background_indices) == 0:
    raise RuntimeError("No eligible background cells remain.")

n_background = min(
    len(background_indices),
    int(round(len(positive_indices) * BACKGROUND_RATIO))
)

sampled_background = rng.choice(
    background_indices,
    size=n_background,
    replace=False
)

# Preserve all positive cells; sample background cells only.
selected_indices = np.concatenate(
    [positive_indices, sampled_background]
)

labels = np.concatenate([
    np.ones(len(positive_indices), dtype=np.uint8),
    np.zeros(len(sampled_background), dtype=np.uint8)
])

rows = selected_indices // width
cols = selected_indices % width

xs, ys = xy(transform, rows, cols, offset="center")

table = pd.DataFrame({
    "row": rows,
    "col": cols,
    "x_utm_m": np.asarray(xs),
    "y_utm_m": np.asarray(ys),
    "elevation_m": elevation.ravel()[selected_indices],
    "slope_degrees": slope.ravel()[selected_indices],
    "landcover_class": lulc.ravel()[selected_indices].astype(int),
    "distance_to_permanent_water_m":
        distance_water.ravel()[selected_indices],
    "label": labels,
    "sample_type": np.where(
        labels == 1,
        "observed_extent_presence",
        "background_pseudoabsence"
    )
})

if drainage_distance is not None:
    table["distance_to_osm_waterway_m"] = (
        drainage_distance.ravel()[selected_indices]
    )

# One-kilometre spatial groups to reduce train/test spatial leakage.
BLOCK_M = 1000
table["spatial_block"] = (
    (np.floor(table["x_utm_m"] / BLOCK_M).astype(int).astype(str))
    + "_"
    + (np.floor(table["y_utm_m"] / BLOCK_M).astype(int).astype(str))
)

# Shuffle row order without changing feature-label correspondence.
table = table.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

# ---------------------------------------------------------
# 5. Find a spatial holdout where both sets contain both labels
# ---------------------------------------------------------
split_found = False
groups = table["spatial_block"].to_numpy()
y = table["label"].to_numpy()

splitter = GroupShuffleSplit(
    n_splits=200,
    test_size=0.20,
    random_state=RANDOM_SEED
)

for train_idx, test_idx in splitter.split(table, y, groups):
    if (
        table.iloc[train_idx]["label"].nunique() == 2
        and table.iloc[test_idx]["label"].nunique() == 2
    ):
        # Also ensure the holdout has a meaningful size.
        if len(test_idx) >= 0.10 * len(table):
            table["split"] = "train"
            table.loc[test_idx, "split"] = "test"
            split_found = True
            break

if not split_found:
    table["split"] = "UNASSIGNED"

# ---------------------------------------------------------
# 6. Validate and save the dataset and report
# ---------------------------------------------------------
feature_cols = [
    "elevation_m",
    "slope_degrees",
    "landcover_class",
    "distance_to_permanent_water_m"
]
if drainage_distance is not None:
    feature_cols.append("distance_to_osm_waterway_m")

missing = table[feature_cols].isna().sum().to_dict()
infinite = {
    col: int((~np.isfinite(table[col].to_numpy(dtype=float))).sum())
    for col in feature_cols
}

report = {
    "objective": "Chennai flood susceptibility, presence-background",
    "grid_crs": crs.to_string(),
    "grid_resolution_m": [pixel_x, pixel_y],
    "source_flood_features": int(len(flood)),
    "valid_spatial_cells": int(valid.sum()),
    "positive_extent_cells_available": int(len(positive_indices)),
    "eligible_background_cells_before_sampling": int(len(background_indices)),
    "buffer_distance_m": BUFFER_M,
    "positive_samples": int((table["label"] == 1).sum()),
    "background_pseudoabsence_samples": int((table["label"] == 0).sum()),
    "feature_columns": feature_cols,
    "missing_values_by_feature": missing,
    "nonfinite_values_by_feature": infinite,
    "landcover_sample_counts": {
        str(k): int(v)
        for k, v in table["landcover_class"].value_counts().sort_index().items()
    },
    "osm_drainage_status": drainage_status,
    "split_status": "spatial holdout created" if split_found else
                    "UNASSIGNED: no valid spatial split found",
    "split_counts": {
        split: {
            "rows": int(len(part)),
            "labels": {
                str(k): int(v)
                for k, v in part["label"].value_counts().items()
            },
            "spatial_blocks": int(part["spatial_block"].nunique())
        }
        for split, part in table.groupby("split")
    },
    "label_semantics": {
        "1": "Cell center inside published 2015 NRSC inundation extent",
        "0": "Sampled background outside 300 m buffer and outside permanent-water class",
        "warning": "0 is a pseudoabsence/background label, not a confirmed non-flood observation"
    },
    "limitations": [
        "2015 flood target is not temporally aligned to 2018-2025 rainfall.",
        "Static susceptibility features do not support event-specific forecasts.",
        "Only one mapped historical event is currently represented.",
        "Spatial holdout from this one event does not establish generalization to other events.",
        "Scores from presence-background training are not calibrated flood probabilities."
    ]
}

table.to_csv(CSV_OUT, index=False)
REPORT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("=" * 72)
print("JALSURAKSHA PRESENCE-BACKGROUND DATASET AUDIT")
print("=" * 72)
print("CRS:", crs)
print("Grid:", width, "x", height)
print("Positive samples:", len(positive_indices))
print("Background pseudoabsence samples:", n_background)
print("Total rows:", len(table))
print("Features:", feature_cols)
print("OSM drainage:", drainage_status)
print("Missing values:", missing)
print("Non-finite values:", infinite)
print("Spatial split:", report["split_status"])
print("Split counts:", json.dumps(report["split_counts"], indent=2))
print("\nDataset:", CSV_OUT.resolve())
print("Report:", REPORT_OUT.resolve())
print("\nNo XGBoost model was trained.")
