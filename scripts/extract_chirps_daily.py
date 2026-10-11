import os
import csv
import re
from datetime import date, timedelta
from urllib.parse import urljoin

import numpy as np
import requests
import rasterio
from rasterio.windows import from_bounds


# ============================================================
# JALSURAKSHA - CHIRPS DAILY RAINFALL EXTRACTION
# ============================================================

START_DATE = date(2018, 1, 1)
END_DATE = date(2025, 12, 31)

# CHIRPS v3 daily RNL directory
BASE_URL = (
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/"
    "daily/final/rnl/"
)

# Chennai AOI
WEST = 80.170
SOUTH = 12.900
EAST = 80.270
NORTH = 12.995

OUTPUT_DIR = "data/processed/rainfall"

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "chennai_daily_rainfall_2018_2025.csv"
)


# ============================================================
# SETUP
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)

SESSION = requests.Session()

HEADERS = {
    "User-Agent": "Jalsuraksha/1.0"
}


# ============================================================
# DATE RANGE
# ============================================================

def date_range(start, end):
    current = start

    while current <= end:
        yield current
        current += timedelta(days=1)


# ============================================================
# GET YEAR DIRECTORY
# ============================================================

def get_year_listing(year):

    url = f"{BASE_URL}{year}/"

    response = SESSION.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


# ============================================================
# FIND CHIRPS FILE
# ============================================================

def find_file_for_date(year, month, day):

    html = get_year_listing(year)

    target_date = f"{year}.{month:02d}.{day:02d}"

    # Extract all href values
    links = re.findall(
        r'href=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE
    )

    candidates = []

    for link in links:

        filename = link.split("/")[-1]

        if target_date in filename.lower():

            if filename.lower().endswith(
                (".tif", ".tiff", ".cog")
            ):
                candidates.append(link)

    if not candidates:
        return None

    # Prefer COG / TIFF
    candidates.sort(
        key=lambda x: (
            0 if ".tif" in x.lower() else 1,
            len(x)
        )
    )

    return urljoin(
        f"{BASE_URL}{year}/",
        candidates[0]
    )


# ============================================================
# CACHE YEAR FILE LISTINGS
# ============================================================

YEAR_LISTINGS = {}


def get_file_for_date(d):

    year = d.year

    if year not in YEAR_LISTINGS:

        print(f"\nLoading CHIRPS directory: {year}")

        html = get_year_listing(year)

        links = re.findall(
            r'href=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE
        )

        YEAR_LISTINGS[year] = links

        print(
            f"Found {len(links)} files/entries for {year}"
        )

    target_date = f"{d.year}.{d.month:02d}.{d.day:02d}"

    candidates = []

    for link in YEAR_LISTINGS[year]:

        filename = link.split("/")[-1]

        if target_date in filename:

            if filename.lower().endswith(
                (".tif", ".tiff", ".cog")
            ):
                candidates.append(filename)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            0 if ".tif" in x.lower() else 1,
            len(x)
        )
    )

    return (
        f"{BASE_URL}{year}/{candidates[0]}"
    )


# ============================================================
# EXTRACT ONE DAY
# ============================================================

def extract_daily_rainfall(d):

    try:

        url = get_file_for_date(d)

        if url is None:

            print(
                f"NO FILE {d}: "
                f"CHIRPS file not found"
            )

            return None

        with rasterio.open(url) as src:

            window = from_bounds(
                WEST,
                SOUTH,
                EAST,
                NORTH,
                transform=src.transform
            )

            data = src.read(
                1,
                window=window
            )

            data = data.astype(
                np.float32
            )

            # Handle nodata correctly
            if src.nodata is not None:

                valid = (
                    np.isfinite(data)
                    & (data != src.nodata)
                )

            else:

                valid = np.isfinite(data)

            if not np.any(valid):

                return None

            rainfall_mean = float(
                np.mean(data[valid])
            )

            rainfall_max = float(
                np.max(data[valid])
            )

            return (
                rainfall_mean,
                rainfall_max
            )

    except Exception as e:

        print(
            f"ERROR {d}: {e}"
        )

        return None


# ============================================================
# MAIN
# ============================================================

print("=" * 70)
print("JALSURAKSHA - CHIRPS DAILY RAINFALL EXTRACTION")
print("=" * 70)

print(
    f"Period : {START_DATE} -> {END_DATE}"
)

print(
    f"AOI    : "
    f"{WEST}, {SOUTH}, {EAST}, {NORTH}"
)

print()

print(
    "Reading remote CHIRPS files."
)

print(
    "No global rainfall TIFFs will be downloaded."
)

print()


# ============================================================
# TOTAL DAYS
# ============================================================

total_days = (
    END_DATE - START_DATE
).days + 1

processed = 0
failed = 0


# ============================================================
# CSV
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "date",
        "rainfall_mean_mm",
        "rainfall_max_mm"
    ])

    # --------------------------------------------------------
    # PROCESS EACH DAY
    # --------------------------------------------------------

    for index, d in enumerate(
        date_range(
            START_DATE,
            END_DATE
        ),
        start=1
    ):

        result = extract_daily_rainfall(d)

        if result is None:

            failed += 1

            writer.writerow([
                d.isoformat(),
                "",
                ""
            ])

        else:

            mean_rain, max_rain = result

            writer.writerow([
                d.isoformat(),
                f"{mean_rain:.6f}",
                f"{max_rain:.6f}"
            ])

            processed += 1

        # Progress every 25 days
        if index % 25 == 0 or index == total_days:

            print(
                f"Progress: {index}/{total_days} "
                f"| successful={processed} "
                f"| failed={failed}"
            )


# ============================================================
# COMPLETE
# ============================================================

print()

print("=" * 70)
print("EXTRACTION COMPLETE")
print("=" * 70)

print(
    f"Successful days : {processed}"
)

print(
    f"Failed days     : {failed}"
)

print(
    f"Output          : {OUTPUT_FILE}"
)

print("=" * 70)