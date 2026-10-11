import os
import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = (
    "data/processed/rainfall/"
    "chennai_daily_rainfall_2018_2025.csv"
)

OUTPUT_FILE = (
    "data/processed/rainfall/"
    "chennai_rainfall_features_2018_2025.csv"
)


EXPECTED_START = "2018-01-01"
EXPECTED_END = "2025-12-31"


# ============================================================
# LOAD
# ============================================================

print("=" * 70)
print("JALSURAKSHA - CHIRPS PREPROCESSING")
print("=" * 70)

df = pd.read_csv(INPUT_FILE)

print("\nLoaded rows:", len(df))
print("Columns:", list(df.columns))


# ============================================================
# DATE
# ============================================================

df["date"] = pd.to_datetime(df["date"])

df = df.sort_values("date").reset_index(drop=True)


# ============================================================
# DATE VALIDATION
# ============================================================

expected_dates = pd.date_range(
    EXPECTED_START,
    EXPECTED_END,
    freq="D"
)

actual_dates = df["date"]

missing_dates = expected_dates.difference(
    actual_dates
)

duplicate_dates = (
    df["date"]
    .duplicated()
    .sum()
)

print("\nDATE VALIDATION")
print("-" * 70)

print("Expected days :", len(expected_dates))
print("Actual rows   :", len(df))
print("Missing dates :", len(missing_dates))
print("Duplicate dates:", duplicate_dates)


# ============================================================
# RAINFALL CLEANING
# ============================================================

rain_cols = [
    "rainfall_mean_mm",
    "rainfall_max_mm"
]

for col in rain_cols:

    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )

    # Negative rainfall is physically invalid
    df.loc[
        df[col] < 0,
        col
    ] = np.nan


# ============================================================
# MISSING VALUES
# ============================================================

print("\nMISSING VALUES")
print("-" * 70)

for col in rain_cols:

    print(
        f"{col}:",
        df[col].isna().sum()
    )


# ============================================================
# BASIC STATISTICS
# ============================================================

print("\nRAINFALL STATISTICS")
print("-" * 70)

print(
    df[rain_cols].describe()
)


# ============================================================
# RAINFALL FEATURES
# ============================================================

# Daily rainfall intensity
df["rainfall"] = df[
    "rainfall_mean_mm"
]


# Rainy day
df["is_rainy_day"] = (
    df["rainfall"] >= 1.0
).astype(int)


# Heavy rainfall
df["is_heavy_rain"] = (
    df["rainfall"] >= 20.0
).astype(int)


# Very heavy rainfall
df["is_very_heavy_rain"] = (
    df["rainfall"] >= 50.0
).astype(int)


# Extreme rainfall
df["is_extreme_rain"] = (
    df["rainfall"] >= 100.0
).astype(int)


# ============================================================
# ROLLING FEATURES
# ============================================================

df["rainfall_3day"] = (
    df["rainfall"]
    .rolling(3, min_periods=1)
    .sum()
)

df["rainfall_7day"] = (
    df["rainfall"]
    .rolling(7, min_periods=1)
    .sum()
)

df["rainfall_30day"] = (
    df["rainfall"]
    .rolling(30, min_periods=1)
    .sum()
)


# ============================================================
# TEMPORAL FEATURES
# ============================================================

df["year"] = df["date"].dt.year

df["month"] = df["date"].dt.month

df["day_of_year"] = (
    df["date"].dt.dayofyear
)


# ============================================================
# SEASON
# ============================================================

def get_season(month):

    if month in [12, 1, 2]:
        return "winter"

    if month in [3, 4, 5]:
        return "pre_monsoon"

    if month in [6, 7, 8, 9]:
        return "southwest_monsoon"

    return "northeast_monsoon"


df["season"] = df["month"].apply(
    get_season
)


# ============================================================
# SAVE
# ============================================================

df.to_csv(
    OUTPUT_FILE,
    index=False
)


# ============================================================
# SUMMARY
# ============================================================

print("\nFEATURE SUMMARY")
print("-" * 70)

print(
    "Rainy days:",
    df["is_rainy_day"].sum()
)

print(
    "Heavy rain days:",
    df["is_heavy_rain"].sum()
)

print(
    "Very heavy rain days:",
    df["is_very_heavy_rain"].sum()
)

print(
    "Extreme rain days:",
    df["is_extreme_rain"].sum()
)

print(
    "Maximum rainfall:",
    df["rainfall"].max()
)

print(
    "Mean rainfall:",
    df["rainfall"].mean()
)


print("\nSaved:")
print(OUTPUT_FILE)

print("=" * 70)
print("CHIRPS PREPROCESSING COMPLETE")
print("=" * 70)