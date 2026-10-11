from pathlib import Path
import requests
from PIL import Image
from io import BytesIO

url = "https://chennaifloodmonitor.tn.gov.in/geohorr/ChennaiDSS/ows"

params = {
    "service": "WMS",
    "version": "1.1.1",
    "request": "GetLegendGraphic",
    "format": "image/png",
    "layer": "gis_flood_inundation_nrsc_flood_extent_2015",
    "style": "gisfloodinun",
    "width": 30,
    "height": 20,
}

outdir = Path(r"data/raw/flood/chennai_2015_nrsc_candidate")
outdir.mkdir(parents=True, exist_ok=True)

r = requests.get(url, params=params, timeout=60)
print("HTTP:", r.status_code)
print("Content type:", r.headers.get("Content-Type"))
print("Response bytes:", len(r.content))

if r.ok and "image/png" in r.headers.get("Content-Type", "").lower():
    path = outdir / "official_nrsc_2015_legend.png"
    path.write_bytes(r.content)
    im = Image.open(BytesIO(r.content))
    print("Legend saved:", path)
    print("Legend dimensions:", im.size)
    print("Open this image to inspect the advertised style.")
else:
    print("Response preview:")
    print(r.text[:1000])
