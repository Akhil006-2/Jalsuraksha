from pathlib import Path
import geopandas as gpd
import pandas as pd

candidate = Path(
    r"data/raw/flood/chennai_2015_nrsc_candidate/"
    r"nrsc_flood_extent_2015.parquet"
)
official = Path(
    r"data/raw/flood/chennai_2015_nrsc_candidate/"
    r"official_geoserver_nrsc_2015_check.geojson"
)

print("=" * 72)
print("OFFICIAL LAYER vs DOWNLOADED CANDIDATE")
print("=" * 72)

if not candidate.exists() or not official.exists():
    raise SystemExit("Missing one or both files. No changes made.")

a = gpd.read_parquet(candidate)
b = gpd.read_file(official)

print("Candidate rows:", len(a))
print("Official rows:", len(b))
print("Candidate CRS:", a.crs)
print("Official CRS:", b.crs)

required = {"id", "area", "perimeter", "pixelvalue", "geometry"}
if not required.issubset(a.columns) or not required.issubset(b.columns):
    raise SystemExit("Column mismatch: inspect columns before proceeding.")

# Compare attributes by feature ID.
a = a.sort_values("id").reset_index(drop=True)
b = b.sort_values("id").reset_index(drop=True)

print("\n--- ATTRIBUTE COMPARISON ---")
print("Same ID sequence:", a["id"].equals(b["id"]))
print("Same pixelvalue sequence:", a["pixelvalue"].equals(b["pixelvalue"]))
print("Same area sequence:", a["area"].equals(b["area"]))
print("Same perimeter sequence:", a["perimeter"].equals(b["perimeter"]))

print("\nCandidate pixelvalue counts:")
print(a["pixelvalue"].value_counts(dropna=False).to_string())

print("\nOfficial pixelvalue counts:")
print(b["pixelvalue"].value_counts(dropna=False).to_string())

# Compare geometry after transforming both to a common CRS.
a = a.to_crs("EPSG:4326")
b = b.to_crs("EPSG:4326")

same_geometry = []
for ga, gb in zip(a.geometry, b.geometry):
    if ga is None or gb is None:
        same_geometry.append(False)
    else:
        same_geometry.append(ga.equals(gb))

print("\n--- GEOMETRY COMPARISON ---")
print("Exactly equal feature geometries:", sum(same_geometry), "/", len(same_geometry))
print("Same total bounds:", a.total_bounds.tolist() == b.total_bounds.tolist())

print("\n--- STUDY AREA COVERAGE ---")
print("Candidate bounds:", a.total_bounds)
print("Official bounds:", b.total_bounds)

print("\nConclusion:")
if (
    len(a) == len(b)
    and a["id"].equals(b["id"])
    and a["pixelvalue"].equals(b["pixelvalue"])
    and all(same_geometry)
):
    print("Candidate matches the official service for IDs, classes and geometry.")
    print("The source layer is named NRSC flood extent 2015.")
    print("Class meaning and event-specific interpretation still require documentation.")
else:
    print("Differences found. Do not treat the files as identical yet.")

print("\nRead-only validation. No labels or training data were created.")
