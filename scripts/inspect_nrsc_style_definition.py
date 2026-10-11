from pathlib import Path
import requests

base = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"
outdir = Path(r"data/raw/flood/chennai_2015_nrsc_candidate")
outdir.mkdir(parents=True, exist_ok=True)

params = {
    "service": "WMS",
    "version": "1.1.1",
    "request": "GetStyles",
    "layers": "gis_flood_inundation_nrsc_flood_extent_2015",
}

print("=" * 72)
print("NRSC FLOOD 2015 STYLE DEFINITION")
print("=" * 72)

try:
    r = requests.get(base, params=params, timeout=60)
    print("HTTP:", r.status_code)
    print("Content type:", r.headers.get("Content-Type"))
    print("Response bytes:", len(r.content))

    print("\nResponse preview:")
    print(r.text[:2500])

    if r.ok and (
        "xml" in r.headers.get("Content-Type", "").lower()
        or "<StyledLayerDescriptor" in r.text
    ):
        path = outdir / "official_nrsc_2015_style.xml"
        path.write_bytes(r.content)
        print("\nSaved style response:", path)

        for term in ("pixelvalue", "1", "13", "RasterSymbolizer",
                     "ColorMap", "Rule", "ogc:Filter"):
            print(f"Contains {term!r}:", term.lower() in r.text.lower())
    else:
        print("\nThe service did not return a recognised style document.")
except Exception as e:
    print("Request failed:", repr(e))

print("\nNo labels or training data were created.")
