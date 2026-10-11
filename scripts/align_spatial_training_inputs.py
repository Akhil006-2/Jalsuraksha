from pathlib import Path
import json
import numpy as np
import rasterio
import geopandas as gpd

from rasterio.warp import (
    calculate_default_transform,
    reproject,
    Resampling
)
from rasterio.features import rasterize
from rasterio.transform import array_bounds
from rasterio.crs import CRS

ROOT = Path("data")
DEM = ROOT / "processed/dem/chennai_aoi_dem.tif"
SLOPE = ROOT / "processed/terrain/chennai_aoi_slope_degrees.tif"
LULC = ROOT / "processed/lulc/chennai_aoi_worldcover_2021.tif"
FLOOD = ROOT / "processed/flood/chennai_nrsc_2015_observed_inundation.geojson"
AOI = ROOT / "aoi/study_area.geojson"

OUT = ROOT / "processed/training_prep"
OUT.mkdir(parents=True, exist_ok=True)

STACK = OUT / "chennai_spatial_feature_stack_30m.tif"
REPORT = OUT / "chennai_spatial_alignment_audit.json"

for path in [DEM, SLOPE, LULC, FLOOD, AOI]:
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path.resolve()}")

crs = CRS.from_epsg(32644)

# Define a consistent 30 m grid from the DEM footprint.
with rasterio.open(DEM) as src:
    transform, width, height = calculate_default_transform(
        src.crs, crs, src.width, src.height, *src.bounds,
        resolution=30
    )

grid = {
    "crs": crs,
    "transform": transform,
    "width": width,
    "height": height
}
shape = (height, width)

def warp_raster(path, resampling, dst_dtype="float32", dst_nodata=-9999):
    result = np.full(shape, dst_nodata, dtype=dst_dtype)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=result,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=crs,
            dst_nodata=dst_nodata,
            resampling=resampling
        )
    return result

dem = warp_raster(DEM, Resampling.bilinear)
slope = warp_raster(SLOPE, Resampling.bilinear)
lulc = warp_raster(LULC, Resampling.nearest, "uint8", 0)

aoi = gpd.read_file(AOI).to_crs(crs)
flood = gpd.read_file(FLOOD).to_crs(crs)

aoi_shapes = [(geom, 1) for geom in aoi.geometry if geom is not None]
aoi_mask = rasterize(
    aoi_shapes,
    out_shape=shape,
    transform=transform,
    fill=0,
    dtype="uint8",
    all_touched=False
).astype(bool)

flood_shapes = [
    (geom, 1) for geom in flood.geometry
    if geom is not None and not geom.is_empty
]
flood_mask = rasterize(
    flood_shapes,
    out_shape=shape,
    transform=transform,
    fill=0,
    dtype="uint8",
    all_touched=False
).astype(bool)

valid = (
    aoi_mask
    & np.isfinite(dem) & (dem != -9999)
    & np.isfinite(slope) & (slope != -9999)
    & (lulc != 0)
)

positive = valid & flood_mask
outside_extent = valid & ~flood_mask

# The outside-extent cells are deliberately NOT assigned negative labels.
stack = np.stack([dem, slope, lulc.astype("float32")])

profile = {
    "driver": "GTiff",
    "height": height,
    "width": width,
    "count": 3,
    "dtype": "float32",
    "crs": crs,
    "transform": transform,
    "nodata": -9999.0,
    "compress": "deflate"
}

with rasterio.open(STACK, "w", **profile) as dst:
    for idx, (arr, name) in enumerate(
        [(dem, "elevation_m"), (slope, "slope_degrees"),
         (lulc.astype("float32"), "worldcover_class")],
        start=1
    ):
        out_arr = arr.copy()
        out_arr[~aoi_mask] = -9999
        if idx == 3:
            out_arr[lulc == 0] = -9999
        dst.write(out_arr.astype("float32"), idx)
        dst.set_band_description(idx, name)

class_values, class_counts = np.unique(
    lulc[valid], return_counts=True
)

report = {
    "crs": crs.to_string(),
    "grid": {
        "width": width,
        "height": height,
        "resolution_m": [abs(transform.a), abs(transform.e)]
    },
    "cell_counts": {
        "grid_cells_inside_aoi": int(aoi_mask.sum()),
        "cells_with_valid_dem_slope_landcover": int(valid.sum()),
        "cells_inside_mapped_2015_extent": int(positive.sum()),
        "cells_outside_mapped_extent_unlabelled": int(outside_extent.sum())
    },
    "valid_predictor_summary": {
        "elevation_min_m": float(dem[valid].min()),
        "elevation_median_m": float(np.median(dem[valid])),
        "elevation_max_m": float(dem[valid].max()),
        "slope_min_degrees": float(slope[valid].min()),
        "slope_median_degrees": float(np.median(slope[valid])),
        "slope_max_degrees": float(slope[valid].max())
    },
    "landcover_class_counts": {
        str(k): int(v) for k, v in zip(class_values, class_counts)
    },
    "label_policy": {
        "positive": "Cell center lies inside published 2015 inundation extent",
        "negative": "None assigned",
        "pixelvalue_semantics_verified": False
    },
    "outputs": {
        "feature_stack": str(STACK),
        "audit_report": str(REPORT)
    }
}

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("=" * 70)
print("SPATIAL ALIGNMENT AUDIT COMPLETE")
print("=" * 70)
print("Grid:", width, "x", height, "at 30 m")
print("CRS:", crs)
print("Cells inside AOI:", int(aoi_mask.sum()))
print("Cells with valid predictors:", int(valid.sum()))
print("Cells inside mapped 2015 extent:", int(positive.sum()))
print("Cells outside extent (UNLABELLED):", int(outside_extent.sum()))
print("Land-cover classes:", report["landcover_class_counts"])
print("Feature stack:", STACK.resolve())
print("Audit report:", REPORT.resolve())
print("\nNo negative labels or training samples created.")
