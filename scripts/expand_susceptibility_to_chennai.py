"""Experimental expansion of susceptibility raster to a broader Chennai region.

This uses the existing four-feature XGBoost model and raw DEM/ESA WorldCover inputs.
The model was trained on a much smaller AOI; expanded-area output is EXTRAPOLATION
and must be reviewed before public use. It is not a new validated citywide model.
"""
from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt
import joblib

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data/processed/susceptibility/jalsuraksha_xgboost.joblib"
DEM = ROOT / "data/raw/dem/N12E080/Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif"
LULC = ROOT / "data/raw/lulc/ESA_WorldCover_10m_2021_v200_N12E078_Map.tif"
OUT = ROOT / "data/processed/susceptibility/chennai_flood_susceptibility_expanded_experimental.tif"
META = OUT.with_suffix(".metadata.json")
# Approximate metropolitan bounding box; replace with authoritative CMDA boundary for release.
WGS84_BOUNDS = (79.90, 12.65, 80.55, 13.40)
TARGET_CRS = "EPSG:32644"
RESOLUTION_M = 30.0
NODATA = -9999.0

def warp(src_path, dst_crs, transform, width, height, resampling, src_band=1):
    out = np.full((height, width), np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        reproject(source=rasterio.band(src, src_band), destination=out,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=transform, dst_crs=dst_crs,
            resampling=resampling, src_nodata=src.nodata, dst_nodata=np.nan)
    return out

def main():
    for f in (MODEL, DEM, LULC):
        if not f.exists():
            raise FileNotFoundError(f"Required input missing: {f}")
    left, bottom, right, top = transform_bounds("EPSG:4326", TARGET_CRS, *WGS84_BOUNDS, densify_pts=21)
    width = int(np.ceil((right-left)/RESOLUTION_M))
    height = int(np.ceil((top-bottom)/RESOLUTION_M))
    transform = from_origin(left, top, RESOLUTION_M, RESOLUTION_M)
    print(f"Preparing experimental grid: {width} x {height} ({width*height:,} cells)")
    with rasterio.open(DEM) as src:
        source_bounds = src.bounds
        if source_bounds.left > WGS84_BOUNDS[0] or source_bounds.bottom > WGS84_BOUNDS[1] or source_bounds.right < WGS84_BOUNDS[2] or source_bounds.top < WGS84_BOUNDS[3]:
            raise RuntimeError(
                f"DEM coverage {source_bounds} does not cover the requested Chennai bounds {WGS84_BOUNDS}. "
                "Download and mosaic adjacent Copernicus DEM tiles before generating a citywide layer; "
                "this script deliberately refuses to publish a partial heatmap."
            )
    dem = warp(DEM, TARGET_CRS, transform, width, height, Resampling.bilinear)
    lulc = warp(LULC, TARGET_CRS, transform, width, height, Resampling.nearest)
    valid = np.isfinite(dem) & np.isfinite(lulc) & (lulc > 0)
    # Slope derived from the resampled elevation surface; edge values are approximate.
    safe_dem = np.where(valid, dem, np.nanmedian(dem[valid]) if valid.any() else 0).astype(np.float32)
    gy, gx = np.gradient(safe_dem, RESOLUTION_M, RESOLUTION_M)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    water = valid & (lulc == 80)
    if not water.any():
        raise RuntimeError("No ESA WorldCover class 80 water cells found.")
    dist = distance_transform_edt(~water, sampling=(RESOLUTION_M, RESOLUTION_M)).astype(np.float32)
    model = joblib.load(MODEL)
    prediction = np.full((height, width), NODATA, dtype=np.float32)
    # Bounded batches reduce peak RAM for the expanded region.
    indices = np.flatnonzero(valid)
    flat = prediction.ravel()
    batch = 100_000
    for start in range(0, len(indices), batch):
        idx = indices[start:start+batch]
        rows = np.column_stack([dem.ravel()[idx], slope.ravel()[idx], lulc.ravel()[idx], dist.ravel()[idx]]).astype(np.float32)
        flat[idx] = model.predict_proba(rows)[:, 1]
    profile = {"driver":"GTiff","height":height,"width":width,"count":1,"dtype":"float32",
        "crs":TARGET_CRS,"transform":transform,"nodata":NODATA,"compress":"DEFLATE",
        "predictor":3,"tiled":True,"blockxsize":256,"blockysize":256}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(prediction, 1)
        dst.update_tags(
            model_type="relative_susceptibility_experimental_extrapolation",
            training_aoi="Chennai inner AOI only",
            warning="Expanded-area inference is out-of-training-domain extrapolation; not validated citywide and not a live flood probability.",
            feature_order="elevation_m,slope_degrees,landcover_class,distance_to_permanent_water_m",
            source_model=str(MODEL.relative_to(ROOT)))
    metadata = {
        "status":"EXPERIMENTAL_NOT_VALIDATED_FOR_PUBLIC_SAFETY",
        "output":str(OUT.relative_to(ROOT)), "crs":TARGET_CRS,
        "resolution_m":RESOLUTION_M, "shape":[height,width],
        "approximate_wgs84_bounds":list(WGS84_BOUNDS),
        "model_training_extent":"Original narrow Chennai AOI",
        "limitations":[
            "This is spatial extrapolation beyond the model's training area.",
            "Distance to water uses ESA WorldCover class 80 as a proxy, not a complete drainage network.",
            "Slope is derived from a resampled DEM and may smooth local terrain.",
            "Do not describe scores as calibrated probabilities or current flood conditions.",
            "Use an authoritative CMDA boundary and independent event-based validation before production."
        ]}
    META.write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Wrote {META}")
    print("WARNING: output is experimental extrapolation; validate before enabling for users.")

if __name__ == "__main__":
    main()
