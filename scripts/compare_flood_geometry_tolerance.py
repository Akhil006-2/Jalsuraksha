from pathlib import Path
import geopandas as gpd
import pandas as pd
import numpy as np

base = Path(r"data/raw/flood/chennai_2015_nrsc_candidate")
candidate_path = base / "nrsc_flood_extent_2015.parquet"
official_path = base / "official_geoserver_nrsc_2015_check.geojson"

candidate = gpd.read_parquet(candidate_path)
official = gpd.read_file(official_path)

candidate = candidate.to_crs("EPSG:32644").sort_values("id").reset_index(drop=True)
official = official.to_crs("EPSG:32644").sort_values("id").reset_index(drop=True)

if not candidate["id"].equals(official["id"]):
    raise SystemExit("STOP: Feature IDs differ; comparison is not aligned.")

rows = []
for (_, a), (_, b) in zip(candidate.iterrows(), official.iterrows()):
    ga, gb = a.geometry, b.geometry

    if ga is None or gb is None or ga.is_empty or gb.is_empty:
        rows.append({"id": a["id"], "exact": False, "hausdorff_m": np.nan,
                     "relative_area_difference": np.nan})
        continue

    area_a = ga.area
    area_b = gb.area
    relative_area = abs(area_a - area_b) / max(area_a, area_b, 1e-12)

    rows.append({
        "id": a["id"],
        "exact": ga.equals(gb),
        "hausdorff_m": ga.hausdorff_distance(gb),
        "relative_area_difference": relative_area,
    })

df = pd.DataFrame(rows)

print("=" * 72)
print("GEOMETRY COMPARISON IN EPSG:32644")
print("=" * 72)
print("Features compared:", len(df))
print("Exactly equal:", int(df["exact"].sum()))
print("Hausdorff distance (metres):")
print(df["hausdorff_m"].describe(percentiles=[0.5, 0.9, 0.95, 0.99]).to_string())
print("\nRelative area difference:")
print(df["relative_area_difference"].describe(
    percentiles=[0.5, 0.9, 0.95, 0.99]
).to_string())

for tolerance in [0.01, 0.1, 1.0, 5.0]:
    count = int((df["hausdorff_m"] <= tolerance).sum())
    print(f"Features with Hausdorff distance <= {tolerance} m: {count}")

print("\nLargest differences:")
print(
    df.sort_values("hausdorff_m", ascending=False)
      .head(10).to_string(index=False)
)

report = base / "geometry_comparison_report.csv"
df.to_csv(report, index=False)
print("\nReport saved:", report)
print("No labels or training data were created.")
