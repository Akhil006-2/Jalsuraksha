
from pathlib import Path
import json
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from shapely.geometry import box

# ============================================================
# JALSURAKSHA - OFFICIAL CHENNAI FLOOD EXTENT AUDIT
# Read-only audit: does NOT create training labels.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "flood" / "chennai_2015_nrsc_candidate"
OFFICIAL_FILE = DATA_DIR / "official_geoserver_nrsc_2015_check.geojson"
CANDIDATE_FILE = DATA_DIR / "nrsc_flood_extent_2015.parquet"
STYLE_FILE = DATA_DIR / "official_nrsc_2015_style.xml"

LAYER_NAME = "ChennaiDSS:gis_flood_inundation_nrsc_flood_extent_2015"
WFS_URL = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"

# Existing project AOI, EPSG:4326
WEST, SOUTH, EAST, NORTH = 80.170, 12.900, 80.270, 12.995
AOI = box(WEST, SOUTH, EAST, NORTH)

DATA_DIR.mkdir(parents=True, exist_ok=True)


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def download_official_geojson():
    """Download the official WFS layer if the saved response is absent."""
    if OFFICIAL_FILE.exists():
        print("Using saved official response:", OFFICIAL_FILE)
        return

    print("Saved official response not found; requesting WFS...")
    response = requests.get(
        WFS_URL,
        params={
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": LAYER_NAME,
            "outputFormat": "application/json",
            "maxFeatures": 10000,
        },
        headers={"User-Agent": "Jalsuraksha-research/1.0"},
        timeout=120,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(
            "WFS response was not JSON. First 1000 characters:\n"
            + response.text[:1000]
        )

    if not isinstance(payload, dict) or "features" not in payload:
        raise RuntimeError("WFS response does not contain GeoJSON features.")

    OFFICIAL_FILE.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    print("Downloaded official response:", OFFICIAL_FILE)


def inspect_schema(gdf):
    section("1. DATA STRUCTURE")
    print("Official layer:", LAYER_NAME)
    print("Feature count:", len(gdf))
    print("CRS:", gdf.crs)
    print("Columns:", list(gdf.columns))
    print("\nGeometry types:")
    print(gdf.geometry.geom_type.value_counts(dropna=False).to_string())

    required = {"id", "area", "perimeter", "pixelvalue", "geometry"}
    missing = required - set(gdf.columns)
    if missing:
        raise RuntimeError(f"Required fields missing: {sorted(missing)}")

    if gdf.crs is None:
        raise RuntimeError("CRS is missing; cannot verify geographic coverage.")


def inspect_classes(gdf):
    section("2. PIXELVALUE CLASS COUNTS")
    counts = (
        gdf["pixelvalue"]
        .value_counts(dropna=False)
        .sort_index()
        .rename_axis("pixelvalue")
        .reset_index(name="feature_count")
    )
    print(counts.to_string(index=False))

    csv_path = DATA_DIR / "pixelvalue_class_counts.csv"
    counts.to_csv(csv_path, index=False)
    print("Class-count report saved:", csv_path)

    print(
        "\nWARNING: These are numeric class values only. "
        "Their meanings are not established by the SLD."
    )


def inspect_geometry(gdf):
    section("3. GEOMETRY QUALITY")
    geom = gdf.geometry

    nonempty = geom.notna() & ~geom.is_empty
    valid = geom.is_valid

    print("Null geometries:", int(geom.isna().sum()))
    print("Non-empty geometries:", int(nonempty.sum()))
    print("Invalid non-empty geometries:", int((nonempty & ~valid).sum()))

    # Transform to WGS84 for geographic reporting and AOI intersection.
    geo = gdf.to_crs("EPSG:4326")

    print("Bounds (longitude/latitude):", geo.total_bounds.tolist())
    intersecting = (
        geo.geometry.notna()
        & ~geo.geometry.is_empty
        & geo.geometry.intersects(AOI)
    )
    print("Features intersecting project AOI:", int(intersecting.sum()))

    return geo, intersecting


def inspect_candidate_comparison(official):
    section("4. DOWNLOADED CANDIDATE COMPARISON")

    if not CANDIDATE_FILE.exists():
        print("Candidate Parquet file not found; skipping comparison.")
        return

    candidate = gpd.read_parquet(CANDIDATE_FILE)

    print("Candidate rows:", len(candidate))
    print("Official rows:", len(official))
    print("Candidate CRS:", candidate.crs)
    print("Official CRS:", official.crs)

    if len(candidate) != len(official):
        print("WARNING: Feature counts differ.")
        return

    a = candidate.sort_values("id").reset_index(drop=True)
    b = official.sort_values("id").reset_index(drop=True)

    for column in ("id", "pixelvalue", "area", "perimeter"):
        same = a[column].equals(b[column])
        print(f"Same {column} values in ID order:", same)

    # Exact coordinate equality is not required after CRS transformation.
    a = a.to_crs("EPSG:32644").sort_values("id").reset_index(drop=True)
    b = b.to_crs("EPSG:32644").sort_values("id").reset_index(drop=True)

    if not a["id"].equals(b["id"]):
        print("WARNING: IDs differ after sorting; skipping geometry comparison.")
        return

    distances = []
    for ga, gb in zip(a.geometry, b.geometry):
        if ga is None or gb is None or ga.is_empty or gb.is_empty:
            distances.append(float("nan"))
        else:
            distances.append(ga.hausdorff_distance(gb))

    valid_distances = pd.Series(distances).dropna()

    if valid_distances.empty:
        print("No comparable geometries.")
    else:
        print("Comparable geometries:", len(valid_distances))
        print("Maximum Hausdorff distance (m):", valid_distances.max())
        print("All distances <= 0.01 m:",
              bool((valid_distances <= 0.01).all()))


def create_class_preview(geo, intersecting):
    section("5. CLASS DISTRIBUTION MAP")

    # This is a diagnostic map only. Colors are arbitrary visual aids.
    subset = geo.loc[intersecting].copy()

    if subset.empty:
        print("No features intersect the AOI; map not generated.")
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    for value in sorted(subset["pixelvalue"].dropna().unique()):
        group = subset[subset["pixelvalue"] == value]
        group.plot(
            ax=ax,
            label=f"pixelvalue = {value}",
            alpha=0.65,
            linewidth=0.4,
        )

    gpd.GeoSeries([AOI], crs="EPSG:4326").boundary.plot(
        ax=ax,
        color="black",
        linewidth=1.5,
        label="Study AOI",
    )

    ax.set_title(
        "Chennai 2015 NRSC Flood Extent Layer\n"
        "Pixel-value classes (display colors do not indicate class meaning)"
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend()
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()

    output = DATA_DIR / "nrsc_2015_pixelvalue_preview.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)

    print("Preview saved:", output)


def main():
    section("JALSURAKSHA - NRSC FLOOD EXTENT AUDIT")

    download_official_geojson()

    official = gpd.read_file(OFFICIAL_FILE)
    inspect_schema(official)
    inspect_classes(official)
    geo, intersecting = inspect_geometry(official)
    inspect_candidate_comparison(official)
    create_class_preview(geo, intersecting)

    section("AUDIT RESULT")
    print("Official WFS layer retrieved:", OFFICIAL_FILE.exists())
    print("Official style file exists:", STYLE_FILE.exists())
    print("Class meanings verified: NO")
    print("Training labels created: NO")
    print("XGBoost training performed: NO")
    print(
        "\nNext requirement: obtain authoritative documentation "
        "for pixelvalue classes 0, 1, and 13."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nAUDIT FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
