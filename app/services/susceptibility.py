from functools import lru_cache
import math
import rasterio
from rasterio.warp import transform
from app.config import settings

@lru_cache(maxsize=1)
def _raster():
    path = settings().raster_path
    return rasterio.open(path) if path.exists() else None

@lru_cache(maxsize=1)
def _raster_data():
    src = _raster()
    if src is None:
        return None
    from rasterio.warp import transform_bounds
    data = src.read(1)
    w_bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    return {
        "data": data,
        "nodata": src.nodata,
        "crs": src.crs,
        "width": src.width,
        "height": src.height,
        "transform": src.transform,
        "bounds": src.bounds,
        "wgs84_bounds": w_bounds,
        "res": src.res,
    }

def status():
    src = _raster()
    if src is None:
        return {"available": False, "path": str(settings().raster_path)}
    return {"available": True, "crs": str(src.crs), "width": src.width, "height": src.height,
            "resolution": list(src.res), "bounds": list(src.bounds), "nodata": src.nodata}

def sample(lat, lon):
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    rd = _raster_data()
    if rd is None:
        return None
    wb = rd["wgs84_bounds"]
    if lon < wb[0] or lon > wb[2] or lat < wb[1] or lat > wb[3]:
        return None
    try:
        from rasterio.transform import rowcol
        xs, ys = transform("EPSG:4326", rd["crs"], [lon], [lat])
        row, col = rowcol(rd["transform"], xs[0], ys[0])
        if row < 0 or col < 0 or row >= rd["height"] or col >= rd["width"]:
            return None
        value = float(rd["data"][row, col])
        if (rd["nodata"] is not None and value == rd["nodata"]) or not math.isfinite(value) or not 0 <= value <= 1:
            return None
        return value
    except Exception:
        return None


@lru_cache(maxsize=1)
def overlay_bounds():
    """Return Leaflet ImageOverlay bounds without rendering the PNG."""
    src = _raster()
    if src is None:
        return None
    from rasterio.warp import calculate_default_transform
    transform_wgs84, width, height = calculate_default_transform(
        src.crs, "EPSG:4326", src.width, src.height, *src.bounds
    )
    west = transform_wgs84.c
    north = transform_wgs84.f
    east = west + width * transform_wgs84.a
    south = north + height * transform_wgs84.e
    return {
        "bounds": [[south, west], [north, east]],
        "crs": "EPSG:4326",
        "width": width,
        "height": height,
    }

@lru_cache(maxsize=1)
def overlay_data():
    src = _raster()
    if src is None:
        return None
    import io
    import numpy as np
    import matplotlib.pyplot as plt
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from PIL import Image

    dst_crs = "EPSG:4326"
    xform, width, height = calculate_default_transform(
        src.crs, dst_crs, src.width, src.height, *src.bounds
    )
    destination = np.empty((height, width), dtype=np.float32)
    reproject(
        source=rasterio.band(src, 1),
        destination=destination,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=xform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        dst_nodata=-9999.0
    )
    minx = xform.c
    maxy = xform.f
    maxx = minx + width * xform.a
    miny = maxy + height * xform.e
    bounds = [[miny, minx], [maxy, maxx]]

    valid_mask = (destination != -9999.0) & np.isfinite(destination)
    cmap = plt.get_cmap("YlOrRd")
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    norm_vals = np.clip(destination[valid_mask], 0.0, 1.0)
    colors = cmap(norm_vals)
    rgba[valid_mask, :3] = (colors[:, :3] * 255).astype(np.uint8)
    # 75% opacity for valid pixels so base map streets are visible underneath
    rgba[valid_mask, 3] = 185

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return {
        "png_bytes": buf.getvalue(),
        "bounds": bounds,
        "width": width,
        "height": height,
        "crs": "EPSG:4326"
    }
