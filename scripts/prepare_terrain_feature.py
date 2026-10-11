from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import array_bounds
from rasterio.crs import CRS
from rasterio.features import geometry_mask
import geopandas as gpd
from scipy.ndimage import sobel

root = Path("data")
dem_path = root / "processed/dem/chennai_aoi_dem.tif"
lulc_path = root / "processed/lulc/chennai_aoi_worldcover_2021.tif"
flood_path = root / "processed/flood/chennai_nrsc_2015_observed_inundation.geojson"
aoi_path = root / "aoi/study_area.geojson"

out_dir = root / "processed/terrain"
out_dir.mkdir(parents=True, exist_ok=True)

slope_path = out_dir / "chennai_aoi_slope_degrees.tif"
report_path = out_dir / "terrain_alignment_report.json"

for p in [dem_path, lulc_path, flood_path, aoi_path]:
    if not p.exists():
        raise FileNotFoundError(f"Missing input: {p.resolve()}")

with rasterio.open(dem_path) as ds:
    dem = ds.read(1).astype("float32")
    dem_profile = ds.profile.copy()
    dem_crs = ds.crs
    dem_transform = ds.transform
    dem_nodata = ds.nodata
    dem_bounds = ds.bounds

with rasterio.open(lulc_path) as ds:
    lulc_profile = ds.profile.copy()
    lulc_crs = ds.crs
    lulc_bounds = ds.bounds
    lulc_res = ds.res
    lulc_classes, lulc_counts = np.unique(ds.read(1), return_counts=True)

aoi = gpd.read_file(aoi_path).to_crs("EPSG:4326")
flood = gpd.read_file(flood_path).to_crs("EPSG:4326")

# UTM zone 44N covers this Chennai study area.
projected_crs = CRS.from_epsg(32644)

with rasterio.open(dem_path) as src:
    transform, width, height = calculate_default_transform(
        src.crs, projected_crs,
        src.width, src.height,
        *src.bounds,
        resolution=30
    )

    projected_dem = np.full((height, width), np.nan, dtype="float32")

    reproject(
        source=rasterio.band(src, 1),
        destination=projected_dem,
        src_transform=src.transform,
        src_crs=src.crs,
        src_nodata=src.nodata,
        dst_transform=transform,
        dst_crs=projected_crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear
    )

valid = np.isfinite(projected_dem)

if valid.sum() == 0:
    raise RuntimeError("No valid DEM pixels after reprojection.")

# Use actual projected pixel dimensions, in metres.
xres = abs(transform.a)
yres = abs(transform.e)

# Sobel derivatives are divided by 8 to give central-difference
# derivatives per pixel; divide again by pixel dimensions in metres.
filled = np.where(valid, projected_dem, np.nanmedian(projected_dem[valid]))
dz_dx = sobel(filled, axis=1, mode="nearest") / (8.0 * xres)
dz_dy = sobel(filled, axis=0, mode="nearest") / (8.0 * yres)

slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype("float32")
slope[~valid] = -9999.0

profile = {
    "driver": "GTiff",
    "height": height,
    "width": width,
    "count": 1,
    "dtype": "float32",
    "crs": projected_crs,
    "transform": transform,
    "nodata": -9999.0,
    "compress": "deflate"
}

with rasterio.open(slope_path, "w", **profile) as dst:
    dst.write(slope, 1)
    dst.set_band_description(1, "slope_degrees")

valid_slope = slope[valid]

report = {
    "dem_source": str(dem_path),
    "landcover_source": str(lulc_path),
    "flood_target_source": str(flood_path),
    "output_slope": str(slope_path),
    "projected_crs": projected_crs.to_string(),
    "slope_grid": {
        "width": int(width),
        "height": int(height),
        "resolution_metres": [xres, yres],
        "valid_pixels": int(valid.sum()),
        "slope_min_degrees": float(valid_slope.min()),
        "slope_median_degrees": float(np.median(valid_slope)),
        "slope_max_degrees": float(valid_slope.max())
    },
    "landcover": {
        "crs": str(lulc_crs),
        "bounds": list(lulc_bounds),
        "resolution_degrees": list(lulc_res),
        "class_counts_including_nodata": {
            str(k): int(v) for k, v in zip(lulc_classes, lulc_counts)
        }
    },
    "flood_target": {
        "features": int(len(flood)),
        "pixelvalue_counts": {
            str(k): int(v)
            for k, v in flood["pixelvalue"].value_counts().items()
        } if "pixelvalue" in flood.columns else {},
        "pixelvalue_semantics_verified": False
    },
    "note": (
        "Slope generated for inspection. No model labels, samples, "
        "or training table were created."
    )
}

report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("=" * 68)
print("TERRAIN FEATURE PREPARATION COMPLETE")
print("=" * 68)
print("Projected CRS:", projected_crs)
print("Slope grid:", width, "x", height)
print("Pixel resolution:", round(xres, 2), "x", round(yres, 2), "m")
print("Slope min/median/max:",
      round(float(valid_slope.min()), 4),
      round(float(np.median(valid_slope)), 4),
      round(float(valid_slope.max()), 4))
print("Slope raster:", slope_path.resolve())
print("Report:", report_path.resolve())
print("\nNo training samples or labels were created.")
