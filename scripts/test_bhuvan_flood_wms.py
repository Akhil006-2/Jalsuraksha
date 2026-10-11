from owslib.wms import WebMapService


URL = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"


print("=" * 70)
print("JALSURAKSHA - BHUVAN FLOOD WMS TEST")
print("=" * 70)

print("\nConnecting to:")
print(URL)

wms = WebMapService(
    URL,
    version="1.1.1",
    timeout=60
)

print("\nConnection successful!")

print("\nAvailable layers:")
print("-" * 70)

for layer_id, layer in wms.contents.items():

    print(
        layer_id,
        "->",
        layer.title
    )

print("\nTotal layers:", len(wms.contents))

print("=" * 70)