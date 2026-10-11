
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
import osmnx as ox
from rasterio.plot import plotting_extent
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]

RASTER_PATH = ROOT / "data" / "processed" / "susceptibility" / "chennai_flood_susceptibility_v1.tif"
GRAPH_PATH = ROOT / "data" / "processed" / "roads" / "chennai.graphml"
OUTPUT_PATH = ROOT / "runs" / "jalsuraksha_map.png"

# Test locations
ORIGIN = (12.947, 80.220)       # latitude, longitude
DESTINATION = (12.976, 80.221)  # latitude, longitude

if not RASTER_PATH.exists():
    raise FileNotFoundError(f"Raster not found: {RASTER_PATH}")

if not GRAPH_PATH.exists():
    raise FileNotFoundError(f"Road graph not found: {GRAPH_PATH}")

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Load raster
with rasterio.open(RASTER_PATH) as src:
    raster = src.read(1).astype("float32")
    raster_crs = src.crs
    bounds = src.bounds
    nodata = src.nodata
    extent = plotting_extent(src)

    if nodata is not None:
        raster[raster == nodata] = np.nan

    raster[~np.isfinite(raster)] = np.nan

# Load road graph
print("Loading road graph...")
G = ox.load_graphml(GRAPH_PATH)

print(f"Graph: {len(G.nodes):,} nodes, {len(G.edges):,} edges")

# Project roads into the raster's coordinate system
G_projected = ox.project_graph(G, to_crs=raster_crs)

# Restrict plotting to the raster footprint plus a small margin
margin = 600
view_bounds = box(
    bounds.left - margin,
    bounds.bottom - margin,
    bounds.right + margin,
    bounds.top + margin,
)

nodes, edges = ox.graph_to_gdfs(
    G_projected, nodes=True, edges=True, fill_edge_geometry=True
)

edges_view = edges[edges.intersects(view_bounds)]

# Create figure
fig, ax = plt.subplots(figsize=(13, 10))

image = ax.imshow(
    raster,
    extent=extent,
    origin="upper",
    cmap="YlOrRd",
    vmin=0,
    vmax=1,
    alpha=0.72,
    interpolation="nearest",
)

# Draw road edges overlapping the study area
if not edges_view.empty:
    edges_view.plot(
        ax=ax,
        color="#263238",
        linewidth=0.45,
        alpha=0.85,
        zorder=3,
    )
else:
    print("Warning: No roads intersect the raster viewing area.")

# Convert latitude/longitude to raster CRS for marker placement
from pyproj import Transformer

transformer = Transformer.from_crs(
    "EPSG:4326", raster_crs, always_xy=True
)

ox_x, ox_y = transformer.transform(ORIGIN[1], ORIGIN[0])
dx, dy = transformer.transform(DESTINATION[1], DESTINATION[0])

ax.scatter(
    ox_x, ox_y, s=130, marker="o",
    color="#00A86B", edgecolors="white",
    linewidths=1.5, label="Origin", zorder=5,
)

ax.scatter(
    dx, dy, s=150, marker="*", 
    color="#1565C0", edgecolors="white",
    linewidths=1.2, label="Destination", zorder=5,
)

colorbar = fig.colorbar(image, ax=ax, shrink=0.75)
colorbar.set_label("Relative flood susceptibility score")

ax.set_xlim(bounds.left - margin, bounds.right + margin)
ax.set_ylim(bounds.bottom - margin, bounds.top + margin)
ax.set_aspect("equal")
ax.set_xlabel(f"Easting ({raster_crs})")
ax.set_ylabel("Northing")
ax.set_title(
    "JalSuraksha — Chennai Road Network & Flood Susceptibility\n"
    "Susceptibility is a static model output, not live flood status"
)
ax.legend(loc="upper right")
ax.grid(alpha=0.15)

plt.tight_layout()
plt.savefig(OUTPUT_PATH, dpi=180, bbox_inches="tight")
print(f"Map saved to: {OUTPUT_PATH}")

plt.show()
