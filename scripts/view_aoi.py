import geopandas as gpd
import matplotlib.pyplot as plt

aoi = gpd.read_file("data/aoi/study_area.geojson")

fig, ax = plt.subplots(figsize=(10, 10))

aoi.boundary.plot(
    ax=ax,
    linewidth=2
)

aoi.plot(
    ax=ax,
    alpha=0.2
)

ax.set_title(
    "JalSuraksha - Chennai Velachery-Pallikaranai Study AOI"
)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

plt.tight_layout()

plt.savefig(
    "data/aoi/study_area_preview.png",
    dpi=200
)

plt.show()