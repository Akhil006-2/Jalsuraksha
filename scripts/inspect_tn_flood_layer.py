from owslib.wms import WebMapService

URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"

print("=" * 75)
print("JALSURAKSHA - INSPECT TAMIL NADU FLOOD LAYER")
print("=" * 75)

print("\nConnecting to Bhuvan WMS...")
wms = WebMapService(
    URL,
    version="1.1.1",
    timeout=60
)

print("Connection successful!")

# ------------------------------------------------------------
# TARGET LAYER
# ------------------------------------------------------------

layer_id = "tn_011112_flood"

if layer_id not in wms.contents:
    print(f"\nERROR: Layer '{layer_id}' not found.")
    raise SystemExit(1)

layer = wms.contents[layer_id]

print("\n" + "=" * 75)
print("LAYER INFORMATION")
print("=" * 75)

print("\nLayer ID:")
print(layer_id)

print("\nTitle:")
print(layer.title)

print("\nAbstract:")
print(layer.abstract)

print("\nCRS options:")
print(layer.crsOptions)

print("\nBounding boxes:")
for bbox in layer.boundingBox:
    print(bbox)

print("\nGeographic bounding box:")
print(layer.boundingBoxWGS84)

print("\nStyles:")
for style_name, style_info in layer.styles.items():
    print(" ", style_name)
    print("    ", style_info)

# ------------------------------------------------------------
# SERVICE INFORMATION
# ------------------------------------------------------------

print("\n" + "=" * 75)
print("WMS SERVICE INFORMATION")
print("=" * 75)

print("\nSupported GetMap formats:")

try:
    formats = wms.getOperationByName("GetMap").formatOptions

    for fmt in formats:
        print(" ", fmt)

except Exception as e:
    print("Could not read GetMap formats:", e)

# ------------------------------------------------------------
# CHENNAI AOI
# ------------------------------------------------------------

WEST = 80.170
SOUTH = 12.900
EAST = 80.270
NORTH = 12.995

print("\n" + "=" * 75)
print("OUR CHENNAI AOI")
print("=" * 75)

print(f"WEST  : {WEST}")
print(f"SOUTH : {SOUTH}")
print(f"EAST  : {EAST}")
print(f"NORTH : {NORTH}")

# ------------------------------------------------------------
# CHECK OVERLAP
# ------------------------------------------------------------

bbox = layer.boundingBoxWGS84

layer_west = bbox[0]
layer_south = bbox[1]
layer_east = bbox[2]
layer_north = bbox[3]

overlap = not (
    EAST < layer_west or
    WEST > layer_east or
    NORTH < layer_south or
    SOUTH > layer_north
)

print("\n" + "=" * 75)
print("AOI COVERAGE CHECK")
print("=" * 75)

print("Layer extent:")
print(
    f"({layer_west}, {layer_south}) -> "
    f"({layer_east}, {layer_north})"
)

if overlap:
    print("\n✓ SUCCESS: Chennai AOI overlaps the flood layer.")
else:
    print("\n✗ PROBLEM: Chennai AOI does NOT overlap this layer.")

print("\n" + "=" * 75)
print("INSPECTION COMPLETE")
print("=" * 75)