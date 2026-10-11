from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

PAGE = "https://sentinel-asia.org/EO/2015/article20151201IN.html"

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            if attrs.get("href"):
                self.links.append((attrs.get("title", ""), attrs["href"]))

request = Request(PAGE, headers={"User-Agent": "Mozilla/5.0"})

with urlopen(request, timeout=30) as response:
    html = response.read().decode("utf-8", errors="replace")

parser = LinkParser()
parser.feed(html)

extensions = (
    ".shp", ".tif", ".tiff", ".gpkg", ".geojson",
    ".kml", ".kmz", ".zip", ".gml", ".nc", ".hdf", ".img"
)

print("=" * 70)
print("SENTINEL ASIA CHENNAI FLOOD DATA AUDIT")
print("=" * 70)
print("Links found:", len(parser.links))

matches = []
for title, href in parser.links:
    url = urljoin(PAGE, href)
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in extensions):
        matches.append((title, url))

print("\nPotential GIS/data downloads:")
if matches:
    for title, url in matches:
        print(f"\nTitle: {title or '(untitled)'}")
        print("URL:", url)
else:
    print("No direct links to common GIS/data formats found.")

print("\nImage links:")
for title, href in parser.links:
    url = urljoin(PAGE, href)
    if urlparse(url).path.lower().endswith((".jpg", ".jpeg", ".png")):
        print(url)
