"""
JALSURAKSHA — AUDIT AND FREEZE TRAINING DATASET
Run from: C:\Dev\Jalsuraksha
Command:  python .\scripts\audit_and_freeze_dataset.py

This script:
- audits the current presence-background CSV and its report
- checks feature columns, target values, missing/non-finite values and duplicates
- checks the supplied spatial train/test split if one is available
- checks spatial-stack dimensions/CRS if rasterio is installed
- writes audit artifacts
- creates a frozen snapshot ONLY when blocking checks pass
- does NOT train a model or claim pseudoabsence labels are confirmed negatives
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.cwd()

DATASET = ROOT / "data/processed/training_prep/chennai_flood_susceptibility_presence_background.csv"
DATASET_REPORT = ROOT / "data/processed/training_prep/chennai_flood_susceptibility_dataset_report.json"
STACK = ROOT / "data/processed/training_prep/chennai_spatial_feature_stack_30m.tif"
ALIGNMENT_AUDIT = ROOT / "data/processed/training_prep/chennai_spatial_alignment_audit.json"
FLOOD_GEOJSON = ROOT / "data/processed/flood/chennai_nrsc_2015_observed_inundation.geojson"
OUTPUT_DIR = ROOT / "data/processed/training_prep/audit"
FREEZE_DIR = ROOT / "data/processed/training_prep/frozen"

EXPECTED_FEATURES = [
    "elevation_m",
    "slope_degrees",
    "landcover_class",
    "distance_to_permanent_water_m",
]
TARGET_CANDIDATES = ["target_flood", "target", "label", "class", "flood"]
SPLIT_CANDIDATES = ["split", "dataset_split", "partition", "set"]
BLOCK_CANDIDATES = ["spatial_block", "block_id", "block", "spatial_group"]

# Broad plausibility checks are diagnostic; they do not automatically remove rows.
PLAUSIBILITY = {
    "elevation_m": (-100.0, 5000.0),
    "slope_degrees": (0.0, 90.0),
    "landcover_class": (0.0, 100.0),
    "distance_to_permanent_water_m": (0.0, 1_000_000.0),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc)}


def find_column(df: pd.DataFrame, candidates: list[str]):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def finite_count(series: pd.Series) -> int:
    numeric = pd.to_numeric(series, errors="coerce")
    return int(np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).sum())


def main():
    print("=" * 78)
    print("JALSURAKSHA — TRAINING DATA AUDIT AND FREEZE")
    print("=" * 78)
    print("Project root:", ROOT)

    if not DATASET.exists():
        print("\nBLOCKED: training CSV not found:")
        print(DATASET)
        print("\nRun this script from C:\\Dev\\Jalsuraksha and confirm the dataset path.")
        return 2

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET, low_memory=False)
    dataset_report = load_json(DATASET_REPORT)
    alignment_report = load_json(ALIGNMENT_AUDIT)

    issues = []
    warnings = []
    checks = {}

    print("\n[1/8] BASIC DATASET")
    print("-" * 78)
    print("Rows:", len(df))
    print("Columns:", len(df.columns))
    print("Column names:", list(df.columns))

    if len(df) == 0:
        issues.append("Dataset has zero rows.")

    if df.columns.duplicated().any():
        issues.append("Duplicate column names detected.")

    target_col = find_column(df, TARGET_CANDIDATES)
    split_col = find_column(df, SPLIT_CANDIDATES)
    block_col = find_column(df, BLOCK_CANDIDATES)

    feature_cols = [c for c in EXPECTED_FEATURES if c in df.columns]
    missing_features = [c for c in EXPECTED_FEATURES if c not in df.columns]

    if missing_features:
        issues.append(f"Missing expected feature columns: {missing_features}")
    if target_col is None:
        issues.append(
            "Could not identify target column. Expected one of: "
            + ", ".join(TARGET_CANDIDATES)
        )

    checks["rows"] = int(len(df))
    checks["columns"] = list(map(str, df.columns))
    checks["target_column"] = str(target_col) if target_col is not None else None
    checks["split_column"] = str(split_col) if split_col is not None else None
    checks["spatial_block_column"] = str(block_col) if block_col is not None else None
    checks["expected_features_found"] = feature_cols
    checks["missing_expected_features"] = missing_features

    print("\n[2/8] FEATURES AND NUMERIC VALIDITY")
    print("-" * 78)
    feature_stats = {}
    for col in feature_cols:
        numeric = pd.to_numeric(df[col], errors="coerce")
        arr = numeric.to_numpy(dtype=float, na_value=np.nan)
        finite = np.isfinite(arr)
        lo, hi = PLAUSIBILITY[col]
        out_of_range = finite & ((arr < lo) | (arr > hi))
        feature_stats[col] = {
            "dtype_in_csv": str(df[col].dtype),
            "missing_or_non_numeric": int((~np.isfinite(arr)).sum()),
            "finite_count": int(finite.sum()),
            "min": float(np.min(arr[finite])) if finite.any() else None,
            "median": float(np.median(arr[finite])) if finite.any() else None,
            "max": float(np.max(arr[finite])) if finite.any() else None,
            "plausibility_range_used_for_flagging_only": [lo, hi],
            "outside_broad_plausibility_range": int(out_of_range.sum()),
        }
        print(
            f"{col}: missing/non-finite={feature_stats[col]['missing_or_non_numeric']}, "
            f"min={feature_stats[col]['min']}, median={feature_stats[col]['median']}, "
            f"max={feature_stats[col]['max']}, range_flags={feature_stats[col]['outside_broad_plausibility_range']}"
        )
        if feature_stats[col]["missing_or_non_numeric"] > 0:
            issues.append(f"{col} has missing, non-numeric, or non-finite values.")
        if out_of_range.any():
            warnings.append(
                f"{col} has {int(out_of_range.sum())} value(s) outside broad plausibility bounds; inspect, do not auto-delete."
            )

    checks["feature_statistics"] = feature_stats

    print("\n[3/8] TARGET / LABEL AUDIT")
    print("-" * 78)
    label_summary = {}
    if target_col is not None:
        target = pd.to_numeric(df[target_col], errors="coerce")
        target_vals = sorted(target.dropna().unique().tolist())
        label_counts = target.value_counts(dropna=False).to_dict()
        label_summary = {
            "unique_values": [v.item() if hasattr(v, "item") else v for v in target_vals],
            "counts": {str(k): int(v) for k, v in label_counts.items()},
            "missing": int(target.isna().sum()),
        }
        print("Target column:", target_col)
        print("Unique values:", target_vals)
        print("Counts:", label_summary["counts"])
        print("Missing target rows:", label_summary["missing"])

        if target.isna().any():
            issues.append("Target has missing or non-numeric values.")
        if set(target_vals) != {0, 1}:
            issues.append(f"Target must contain exactly 0 and 1 for this binary workflow; found {target_vals}.")
        if target.nunique(dropna=True) < 2:
            issues.append("Target has fewer than two classes.")

        if set(target_vals) == {0, 1}:
            zeros = int((target == 0).sum())
            ones = int((target == 1).sum())
            print(f"Class 0 rows: {zeros}; class 1 rows: {ones}")
            warnings.append(
                "Class 0 is documented as background pseudoabsence, not confirmed non-flood. "
                "Model output must be called relative susceptibility, not calibrated flood probability."
            )
    checks["label_summary"] = label_summary

    print("\n[4/8] DUPLICATES AND ROW INTEGRITY")
    print("-" * 78)
    exact_duplicates = int(df.duplicated().sum())
    feature_target_cols = feature_cols + ([target_col] if target_col else [])
    feature_target_duplicates = (
        int(df.duplicated(subset=feature_target_cols).sum())
        if feature_target_cols else None
    )
    print("Exact duplicate rows:", exact_duplicates)
    print("Duplicate feature+target signatures:", feature_target_duplicates)
    checks["exact_duplicate_rows"] = exact_duplicates
    checks["duplicate_feature_target_signatures"] = feature_target_duplicates
    if exact_duplicates:
        warnings.append(
            f"{exact_duplicates} exact duplicate rows found. Review source sampling before training."
        )

    print("\n[5/8] SPATIAL SPLIT / LEAKAGE AUDIT")
    print("-" * 78)
    split_summary = {}
    if split_col:
        print("Split column:", split_col)
        print(df[split_col].value_counts(dropna=False).to_string())
        split_summary["counts"] = {
            str(k): int(v) for k, v in df[split_col].value_counts(dropna=False).items()
        }
        if df[split_col].isna().any():
            issues.append("Split column contains missing values.")
        if df[split_col].nunique(dropna=True) < 2:
            issues.append("Split column contains fewer than two partitions.")
    else:
        warnings.append(
            "No split column in the CSV. Confirm whether train/test membership is stored in a separate file/report before freezing."
        )

    if block_col and split_col:
        block_split_counts = df.groupby(block_col, dropna=False)[split_col].nunique(dropna=False)
        cross_split_blocks = int((block_split_counts > 1).sum())
        split_summary["block_column"] = block_col
        split_summary["blocks_appearing_in_multiple_splits"] = cross_split_blocks
        print("Blocks appearing in multiple splits:", cross_split_blocks)
        if cross_split_blocks:
            issues.append(
                f"{cross_split_blocks} spatial blocks occur in multiple splits; possible spatial leakage."
            )
    else:
        warnings.append(
            "Spatial block identifiers are not available as columns in this CSV; split isolation cannot be independently verified from this file."
        )
    checks["split_summary"] = split_summary

    print("\n[6/8] SPATIAL ARTIFACTS")
    print("-" * 78)
    if STACK.exists():
        try:
            import rasterio
            with rasterio.open(STACK) as src:
                stack_info = {
                    "path": str(STACK.relative_to(ROOT)),
                    "width": int(src.width),
                    "height": int(src.height),
                    "count": int(src.count),
                    "crs": str(src.crs),
                    "bounds": [float(x) for x in src.bounds],
                    "transform": list(src.transform)[:6],
                    "nodata": src.nodata,
                }
                print("Stack:", stack_info)
                checks["spatial_stack"] = stack_info
                if src.crs is None:
                    issues.append("Spatial feature stack has no CRS.")
                if src.width <= 0 or src.height <= 0:
                    issues.append("Spatial feature stack has invalid dimensions.")
        except ImportError:
            warnings.append("rasterio not installed; spatial stack could not be inspected.")
        except Exception as exc:
            warnings.append(f"Could not inspect spatial stack: {exc}")
    else:
        warnings.append("Spatial feature stack TIFF not found at expected path.")

    checks["alignment_audit_available"] = ALIGNMENT_AUDIT.exists()
    checks["dataset_report_available"] = DATASET_REPORT.exists()
    checks["flood_geojson_available"] = FLOOD_GEOJSON.exists()
    if alignment_report is not None:
        checks["alignment_audit_summary"] = alignment_report
    if dataset_report is not None:
        checks["dataset_report_summary"] = dataset_report

    print("\n[7/8] TEMPORAL / LABEL SEMANTICS")
    print("-" * 78)
    warnings.append(
        "Training target represents the 2015 NRSC inundation event; 2018–2025 rainfall/Sentinel-1 features are not contemporaneous with that target and must not be joined as if they were 2015 observations."
    )
    warnings.append(
        "Only one mapped flood event is represented. Generalization to other flood events has not been established."
    )
    warnings.append(
        "WorldCover class 80 is a permanent-water proxy, not a complete drainage network."
    )
    warnings.append(
        "Review coastal DEM values and steep-slope outliers in the context of this low-relief urban AOI."
    )

    print("2015 target + 2018–2025 rainfall/SAR: temporal mismatch flagged.")
    print("Background samples: pseudoabsence, not confirmed non-flood.")
    print("Drainage-distance feature: absent in the current feature table.")

    print("\n[8/8] AUDIT RESULT")
    print("-" * 78)
    blocking_failures = len(issues)
    # Dataset can be frozen as a clearly qualified preliminary dataset if
    # structural checks pass; scientific limitations remain warnings.
    audit = {
        "project": "JalSuraksha",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(DATASET.relative_to(ROOT)),
        "dataset_sha256": sha256_file(DATASET),
        "dataset_bytes": DATASET.stat().st_size,
        "dataset_rows": int(len(df)),
        "dataset_columns": list(map(str, df.columns)),
        "status": "BLOCKED" if blocking_failures else "PRELIMINARY_DATASET_QA_PASSED_WITH_LIMITATIONS",
        "is_final_validated_flood_dataset": False,
        "approved_target_interpretation": "2015 mapped inundation presence versus background pseudoabsence; relative susceptibility only",
        "blockers": issues,
        "warnings": warnings,
        "checks": checks,
    }

    report_path = OUTPUT_DIR / "training_dataset_audit.json"
    report_path.write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")

    summary_path = OUTPUT_DIR / "training_dataset_audit_summary.txt"
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("JALSURAKSHA TRAINING DATASET AUDIT\n")
        f.write("=" * 60 + "\n")
        f.write(f"Status: {audit['status']}\n")
        f.write(f"Rows: {len(df)}\n")
        f.write(f"SHA256: {audit['dataset_sha256']}\n")
        f.write("\nBLOCKERS\n")
        for item in issues:
            f.write(f"- {item}\n")
        f.write("\nWARNINGS / LIMITATIONS\n")
        for item in warnings:
            f.write(f"- {item}\n")
        f.write("\nThis is not a validated observed flood/non-flood dataset.\n")

    print("Status:", audit["status"])
    print("Blockers:", len(issues))
    for issue in issues:
        print("  BLOCKER:", issue)
    print("Warnings:", len(warnings))
    for warning in warnings:
        print("  WARNING:", warning)
    print("\nAudit JSON:", report_path)
    print("Audit summary:", summary_path)

    if issues:
        print("\nFREEZE NOT CREATED: resolve blockers and rerun this script.")
        return 1

    # Freeze a versioned, immutable-by-convention snapshot only after
    # structural blockers pass. The file is explicitly named preliminary.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    frozen_csv = FREEZE_DIR / f"chennai_susceptibility_preliminary_{timestamp}.csv"
    frozen_meta = FREEZE_DIR / f"chennai_susceptibility_preliminary_{timestamp}.json"

    shutil.copy2(DATASET, frozen_csv)
    metadata = {
        "dataset_snapshot": str(frozen_csv.relative_to(ROOT)),
        "source_dataset": str(DATASET.relative_to(ROOT)),
        "sha256": sha256_file(frozen_csv),
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "audit_report": str(report_path.relative_to(ROOT)),
        "status": "PRELIMINARY — NOT A VALIDATED FLOOD/NON-FLOOD DATASET",
        "target_semantics": audit["approved_target_interpretation"],
        "warnings": warnings,
    }
    frozen_meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("\nPRELIMINARY SNAPSHOT CREATED")
    print("CSV:", frozen_csv)
    print("Metadata:", frozen_meta)
    print("SHA256:", metadata["sha256"])
    print("\nDo not upload/train until you have reviewed the audit JSON and accepted the limitations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
