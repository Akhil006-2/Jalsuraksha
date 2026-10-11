import rasterio
from rasterio.windows import from_bounds


# ============================================================
# CHIRPS v3.0 - Remote COG Test
# ============================================================

URL = (
    "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/"
    "daily/final/rnl/2023/"
    "chirps-v3.0.rnl.2023.01.01.tif"
)


# ============================================================
# Chennai Study AOI
# ============================================================

WEST = 80.170
SOUTH = 12.900
EAST = 80.270
NORTH = 12.995


# ============================================================
# Test
# ============================================================

print("=" * 70)
print("CHIRPS REMOTE COG TEST")
print("=" * 70)

print("\nOpening remote CHIRPS file...")
print("URL:", URL)

with rasterio.open(URL) as src:

    print("\nRemote file opened successfully!")

    print("CRS:", src.crs)
    print("Size:", src.width, "x", src.height)
    print("Resolution:", src.res)
    print("Bounds:", src.bounds)
    print("NoData:", src.nodata)

    # --------------------------------------------------------
    # Create AOI window
    # --------------------------------------------------------

    window = from_bounds(
        WEST,
        SOUTH,
        EAST,
        NORTH,
        transform=src.transform
    )

    # --------------------------------------------------------
    # Read only the Chennai AOI
    # --------------------------------------------------------

    data = src.read(1, window=window)

    print("\nAOI window:")
    print("Shape:", data.shape)

    # --------------------------------------------------------
    # Remove NoData values
    # --------------------------------------------------------

    if src.nodata is not None:
        valid_data = data[data != src.nodata]
    else:
        valid_data = data

    if valid_data.size == 0:
        print("No valid rainfall data found in AOI.")
    else:
        print("Min:", valid_data.min())
        print("Max:", valid_data.max())
        print("Mean:", valid_data.mean())


print("\n" + "=" * 70)
print("REMOTE COG TEST COMPLETE")
print("=" * 70)