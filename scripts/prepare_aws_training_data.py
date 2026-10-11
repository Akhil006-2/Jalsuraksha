"""
JALSURAKSHA — FINAL PRE-TRAINING PREFLIGHT
Run from C:\Dev\Jalsuraksha:
    python .\scripts\prepare_aws_training_data.py

Creates AWS-ready train/validation CSVs from the audited frozen snapshot.
Only four approved predictors are included; coordinates, row/col, sample_type,
spatial_block and split are not model features.
This does not upload data or start paid AWS resources.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.cwd()
FROZEN_DIR = ROOT / "data/processed/training_prep/frozen"
OUTPUT_DIR = ROOT / "data/processed/training_prep/aws_ready"

FEATURES = [
    "elevation_m",
    "slope_degrees",
    "landcover_class",
    "distance_to_permanent_water_m",
]
TARGET = "label"
SPLIT = "split"
BLOCK = "spatial_block"
ALLOWED_SPLITS = {"train", "test"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stop(message: str, code: int = 1):
    print("\nPREFLIGHT FAILED:", message)
    print("No AWS-ready CSVs were created.")
    raise SystemExit(code)


def main():
    print("=" * 78)
    print("JALSURAKSHA — AWS TRAINING DATA PREFLIGHT")
    print("=" * 78)
    print("Project root:", ROOT)

    if not FROZEN_DIR.exists():
        stop(f"Frozen directory not found: {FROZEN_DIR}")

    frozen_files = sorted(FROZEN_DIR.glob("chennai_susceptibility_preliminary_*.csv"))
    if not frozen_files:
        stop("No preliminary frozen CSV found. Run audit_and_freeze_dataset.py first.")

    # Use latest timestamped snapshot, unless the user changes this script explicitly.
    source = frozen_files[-1]
    print("Frozen source:", source)

    df = pd.read_csv(source, low_memory=False)
    required = FEATURES + [TARGET, SPLIT, BLOCK]
    missing = [col for col in required if col not in df.columns]
    if missing:
        stop(f"Required columns missing: {missing}")

    print("\nSOURCE CHECKS")
    print("-" * 78)
    print("Rows:", len(df))
    print("Columns:", list(df.columns))
    print("Target counts:")
    print(df[TARGET].value_counts(dropna=False).sort_index().to_string())
    print("\nSplit counts:")
    print(df[SPLIT].value_counts(dropna=False).to_string())

    if df.empty:
        stop("Frozen dataset is empty.")

    if df[required].isna().any().any():
        missing_counts = df[required].isna().sum()
        stop("Missing values in required fields:\n" + missing_counts[missing_counts > 0].to_string())

    # Ensure features and target are numeric and finite.
    for col in FEATURES + [TARGET]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        values = df[col].to_numpy(dtype=float, na_value=np.nan)
        if not np.isfinite(values).all():
            stop(f"Column {col} contains non-numeric or non-finite values.")

    target_values = set(df[TARGET].unique().tolist())
    if target_values != {0, 1}:
        stop(f"Expected binary label values {{0, 1}}; found {sorted(target_values)}.")

    split_values = set(df[SPLIT].astype(str).str.lower().unique())
    if not split_values.issubset(ALLOWED_SPLITS) or split_values != ALLOWED_SPLITS:
        stop(f"Expected split values train and test; found {sorted(split_values)}.")

    df[SPLIT] = df[SPLIT].astype(str).str.lower()

    # Validate that spatial blocks do not cross train/test.
    block_split_counts = df.groupby(BLOCK, dropna=False)[SPLIT].nunique()
    shared_blocks = block_split_counts[block_split_counts > 1]
    if len(shared_blocks):
        stop(f"{len(shared_blocks)} spatial blocks cross train/test split.")

    # Check that both labels occur in both partitions.
    class_counts = {}
    for partition in ["train", "test"]:
        part = df[df[SPLIT] == partition]
        counts = part[TARGET].value_counts().to_dict()
        class_counts[partition] = {str(k): int(v) for k, v in counts.items()}
        if set(part[TARGET].unique()) != {0, 1}:
            stop(f"Partition '{partition}' does not contain both classes 0 and 1.")

    # Use only the approved predictors and target. Metadata is not model input.
    model_columns = FEATURES + [TARGET]
    train = df.loc[df[SPLIT] == "train", model_columns].copy()
    validation = df.loc[df[SPLIT] == "test", model_columns].copy()

    # Stable deterministic ordering; preserve source row order.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    train_path = OUTPUT_DIR / "train.csv"
    validation_path = OUTPUT_DIR / "validation.csv"
    train.to_csv(train_path, index=False, float_format="%.8g")
    validation.to_csv(validation_path, index=False, float_format="%.8g")

    # Verify written files can be read and have exactly the approved schema.
    train_check = pd.read_csv(train_path)
    val_check = pd.read_csv(validation_path)
    expected_columns = FEATURES + [TARGET]
    if list(train_check.columns) != expected_columns or list(val_check.columns) != expected_columns:
        stop("Written CSV schema differs from the approved feature schema.")
    if len(train_check) != len(train) or len(val_check) != len(validation):
        stop("Written CSV row counts do not match source partitions.")

    manifest = {
        "project": "JalSuraksha",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_REVIEW_BEFORE_S3_UPLOAD",
        "source_snapshot": str(source.relative_to(ROOT)),
        "source_sha256": sha256_file(source),
        "training_file": str(train_path.relative_to(ROOT)),
        "training_sha256": sha256_file(train_path),
        "training_rows": int(len(train)),
        "validation_file": str(validation_path.relative_to(ROOT)),
        "validation_sha256": sha256_file(validation_path),
        "validation_rows": int(len(validation)),
        "feature_columns": FEATURES,
        "target_column": TARGET,
        "target_values": [0, 1],
        "class_counts_by_partition": class_counts,
        "spatial_blocks_crossing_partitions": int(len(shared_blocks)),
        "excluded_metadata_columns": [
            c for c in df.columns if c not in model_columns
        ],
        "target_interpretation": (
            "2015 mapped inundation presence versus sampled background pseudoabsence; "
            "use only as a preliminary relative flood-susceptibility prototype"
        ),
        "known_limitations": [
            "Class 0 is pseudoabsence, not confirmed non-flood.",
            "Only one mapped flood event supplies target presence evidence.",
            "Do not join 2018-2025 rainfall or Sentinel-1 observations as contemporaneous features for the 2015 target.",
            "Model scores are not calibrated flood probabilities.",
            "This preparation step does not prove generalization to future flood events.",
        ],
        "aws_cost_note": "This script runs locally and does not create AWS resources.",
    }
    manifest_path = OUTPUT_DIR / "training_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\nPREFLIGHT PASSED")
    print("-" * 78)
    print("Train rows:", len(train))
    print("Validation rows:", len(validation))
    print("Feature columns:", FEATURES)
    print("Class counts by split:", json.dumps(class_counts))
    print("Spatial blocks shared across splits:", len(shared_blocks))
    print("\nCreated:")
    print("  Train      :", train_path)
    print("  Validation :", validation_path)
    print("  Manifest   :", manifest_path)
    print("\nIMPORTANT:")
    print("  These files are ready for review, not automatic approval of model validity.")
    print("  Target is 2015 presence vs pseudoabsence; call output relative susceptibility.")
    print("  No AWS resources were created and nothing was uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
