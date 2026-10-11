import os
import requests
import pandas as pd


# ============================================================
# JALSURAKSHA - SENTINEL-1 DISCOVERY
# Copernicus Data Space OData
# ============================================================

WEST = 80.170
SOUTH = 12.900
EAST = 80.270
NORTH = 12.995

START_DATE = "2018-01-01T00:00:00.000Z"
END_DATE = "2025-12-31T23:59:59.999Z"

OUTPUT_DIR = "data/processed/sentinel1"

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "sentinel1_chennai_products.csv"
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# ============================================================
# AOI WKT
# ============================================================

AOI = (
    f"POLYGON(("
    f"{WEST} {SOUTH},"
    f"{EAST} {SOUTH},"
    f"{EAST} {NORTH},"
    f"{WEST} {NORTH},"
    f"{WEST} {SOUTH}"
    f"))"
)


# ============================================================
# CDSE ODATA ENDPOINT
# ============================================================

URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)


# ============================================================
# QUERY
# ============================================================

filter_query = (
    "Collection/Name eq 'SENTINEL-1' "
    f"and ContentDate/Start ge {START_DATE} "
    f"and ContentDate/Start le {END_DATE} "
    "and OData.CSC.Intersects("
    f"area=geography'SRID=4326;{AOI}'"
    ")"
)


params = {
    "$filter": filter_query,
    "$top": 1000,
    "$orderby": "ContentDate/Start asc"
}


print("=" * 70)
print("JALSURAKSHA - SENTINEL-1 SCENE DISCOVERY")
print("=" * 70)

print()
print("AOI:")
print(
    WEST,
    SOUTH,
    EAST,
    NORTH
)

print()
print(
    "Period:",
    START_DATE,
    "->",
    END_DATE
)

print()
print(
    "Querying Copernicus Sentinel-1 catalogue..."
)


# ============================================================
# PAGINATION
# ============================================================

records = []

request_url = URL
request_params = params


while request_url:

    response = requests.get(
        request_url,
        params=request_params,
        timeout=120
    )

    if response.status_code != 200:

        print()
        print(
            "HTTP ERROR:",
            response.status_code
        )

        print(
            response.text[:2000]
        )

        raise SystemExit(1)


    data = response.json()

    products = data.get(
        "value",
        []
    )


    for product in products:

        name = product.get(
            "Name",
            ""
        )

        # ----------------------------------------------
        # We only want GRD products
        # ----------------------------------------------

        if "_GRD" not in name:
            continue


        # ----------------------------------------------
        # Prefer IW mode
        # ----------------------------------------------

        if "_IW_" not in name:
            continue


        content_date = product.get(
            "ContentDate",
            {}
        )


        records.append({

            "product_id":
                product.get("Id"),

            "name":
                name,

            "datetime":
                content_date.get(
                    "Start"
                ),

            "end_datetime":
                content_date.get(
                    "End"
                ),

            "s3_path":
                product.get(
                    "S3Path"
                ),

            "footprint":
                product.get(
                    "Footprint"
                )
        })


    print(
        f"Received {len(products)} products "
        f"| GRD IW retained: {len(records)}"
    )


    # ----------------------------------------------
    # NEXT PAGE
    # ----------------------------------------------

    next_link = data.get(
        "@odata.nextLink"
    )


    if next_link:

        request_url = next_link

        # nextLink already contains query
        request_params = None

    else:

        request_url = None


# ============================================================
# DATAFRAME
# ============================================================

if not records:

    print()
    print(
        "No Sentinel-1 IW GRD products found."
    )

    raise SystemExit(1)


df = pd.DataFrame(
    records
)


# ============================================================
# DATE
# ============================================================

df["datetime"] = pd.to_datetime(
    df["datetime"],
    utc=True,
    errors="coerce"
)


# ============================================================
# PRODUCT INFORMATION FROM NAME
# ============================================================

df["satellite"] = (
    df["name"]
    .str.extract(
        r"^(S1[A-Z])"
    )
)


df["mode"] = (
    df["name"]
    .str.extract(
        r"^S1[A-Z]_([A-Z]{2})_"
    )
)


# Sentinel-1 product names generally contain
# polarization information such as DV / DH / SV / SH.

df["polarization_code"] = (
    df["name"]
    .str.extract(
        r"_1S([A-Z])([A-Z])_"
    )
    .apply(
        lambda x:
        "".join(
            x.dropna().astype(str)
        ),
        axis=1
    )
)


# ============================================================
# REMOVE DUPLICATES
# ============================================================

df = (
    df
    .drop_duplicates(
        subset=["name"]
    )
    .sort_values(
        "datetime"
    )
    .reset_index(
        drop=True
    )
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

print()
print("=" * 70)
print("DISCOVERY COMPLETE")
print("=" * 70)

print(
    "Total IW GRD scenes:",
    len(df)
)

print()

print("Satellites:")
print(
    df["satellite"]
    .value_counts()
)

print()

print("Polarization codes:")
print(
    df["polarization_code"]
    .value_counts()
)

print()

print("First acquisition:")
print(
    df["datetime"].min()
)

print()

print("Last acquisition:")
print(
    df["datetime"].max()
)

print()

print("Scenes by year:")

print(
    df["datetime"]
    .dt.year
    .value_counts()
    .sort_index()
)

print()

print(
    "Output:",
    OUTPUT_FILE
)

print("=" * 70)