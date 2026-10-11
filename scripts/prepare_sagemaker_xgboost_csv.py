"""
JalSuraksha — prepare SageMaker built-in XGBoost CSV files.
Run from C:\\Dev\\Jalsuraksha:
    python .\\scripts\\prepare_sagemaker_xgboost_csv.py

Output CSVs have no header and label in the first column.
Source datasets remain unchanged.
"""
from __future__ import annotations
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path.cwd()
SOURCE_DIR = ROOT / "data" / "processed" / "training_prep" / "aws_ready"
OUTPUT_DIR = ROOT / "data" / "processed" / "training_prep" / "sagemaker_xgboost"
FEATURES = ["elevation_m", "slope_degrees", "landcover_class", "distance_to_permanent_water_m"]
TARGET = "label"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fail(message: str):
    print(f"\\nERROR: {message}")
    raise SystemExit(1)

def prepare_one(source: Path, destination: Path, expected_rows: int):
    if not source.exists():
        fail(f"Missing input file: {source}")
    df = pd.read_csv(source, low_memory=False)
    expected_columns = FEATURES + [TARGET]
    if list(df.columns) != expected_columns:
        fail(f"{source.name} schema mismatch. Expected {expected_columns}; found {list(df.columns)}")
    if len(df) != expected_rows:
        fail(f"{source.name} expected {expected_rows} rows, found {len(df)}")
    if df.isna().any().any():
        fail(f"{source.name} contains missing values")
    for col in expected_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if not np.isfinite(df[col].to_numpy(dtype=float, na_value=np.nan)).all():
            fail(f"{source.name}: {col} has non-numeric/non-finite values")
    if set(df[TARGET].unique().tolist()) != {0, 1}:
        fail(f"{source.name}: target must contain both binary labels 0 and 1")
    output = df[[TARGET] + FEATURES]
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(destination, index=False, header=False, float_format="%.8g")
    check = pd.read_csv(destination, header=None)
    if check.shape != (expected_rows, len(FEATURES) + 1):
        fail(f"Output verification failed for {destination.name}: shape {check.shape}")
    if set(check.iloc[:, 0].unique().tolist()) != {0, 1}:
        fail(f"First output column is not binary labels in {destination.name}")
    if not np.isfinite(check.to_numpy(dtype=float)).all():
        fail(f"Non-finite values found in {destination.name}")
    return {
        "source": str(source.relative_to(ROOT)),
        "output": str(destination.relative_to(ROOT)),
        "rows": int(len(check)),
        "columns": ["label"] + FEATURES,
        "header": False,
        "label_first": True,
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
        "label_counts": {str(int(k)): int(v) for k, v in check.iloc[:, 0].value_counts().sort_index().items()},
    }

def main():
    print("=" * 76)
    print("JALSURAKSHA — SAGEMAKER XGBOOST CSV PREPARATION")
    print("=" * 76)
    print("Source:", SOURCE_DIR)
    print("Output:", OUTPUT_DIR)
    train_info = prepare_one(SOURCE_DIR / "train.csv", OUTPUT_DIR / "train.csv", 24677)
    validation_info = prepare_one(SOURCE_DIR / "validation.csv", OUTPUT_DIR / "validation.csv", 8611)
    manifest = {
        "project": "JalSuraksha",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SAGEMAKER_XGBOOST_INPUTS_PREPARED",
        "algorithm": "Amazon SageMaker built-in XGBoost",
        "input_format": "CSV, no header, label in first column",
        "label_column": "label",
        "feature_order": FEATURES,
        "train": train_info,
        "validation": validation_info,
        "target_interpretation": "2015 mapped inundation presence versus background pseudoabsence; preliminary relative susceptibility only, not calibrated flood probability.",
        "limitations": [
            "Class 0 is background pseudoabsence, not verified non-flood.",
            "Only one mapped flood event provides positive labels.",
            "Do not interpret output as validated real-time flood prediction."
        ],
    }
    manifest_path = OUTPUT_DIR / "sagemaker_input_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("\\nSUCCESS — outputs verified")
    for item in (train_info, validation_info):
        print(f"\\n{Path(item['output']).name}: rows={item['rows']}, bytes={item['bytes']}")
        print("  label counts:", item["label_counts"])
        print("  SHA256:", item["sha256"])
    print("\\nManifest:", manifest_path)
    print("No AWS resources created; nothing uploaded.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
