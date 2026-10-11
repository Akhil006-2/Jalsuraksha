import requests
import re
import html
from urllib.parse import urljoin

PAGE_URL = (
    "https://bhuvan-app1.nrsc.gov.in/"
    "disaster/usrtasks/flood/flood.php?uname=empty"
)

print("=" * 80)
print("JALSURAKSHA - DISCOVER CHENNAI FLOOD ASSETS")
print("=" * 80)

print("\nDownloading official Bhuvan flood portal...")

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(
    PAGE_URL,
    headers=headers,
    timeout=60
)

response.raise_for_status()

source = response.text

print("Downloaded successfully.")
print("HTML size:", len(source), "characters")

# ------------------------------------------------------------
# SAVE RAW HTML
# ------------------------------------------------------------

output_file = "data/bhuvan_flood_portal.html"

with open(output_file, "w", encoding="utf-8") as f:
    f.write(source)

print("\nSaved raw page:")
print(output_file)

# ------------------------------------------------------------
# SEARCH TERMS
# ------------------------------------------------------------

terms = [
    "Chennai",
    "chennai",
    "Cumulative Inundation",
    "RISAT-1",
    "Tamil Nadu Heavy Rains 2021",
    "2021",
    "2015",
    "ChennaiCity",
    "inundation",
    "flood"
]

print("\n" + "=" * 80)
print("SEARCHING PAGE SOURCE")
print("=" * 80)

# ------------------------------------------------------------
# PRINT CONTEXT AROUND IMPORTANT TERMS
# ------------------------------------------------------------

for term in terms:

    positions = [
        m.start()
        for m in re.finditer(
            re.escape(term),
            source,
            flags=re.IGNORECASE
        )
    ]

    if not positions:
        continue

    print("\n")
    print("-" * 80)
    print(f"TERM: {term}")
    print(f"OCCURRENCES: {len(positions)}")
    print("-" * 80)

    # Only show first 5 occurrences
    for i, pos in enumerate(positions[:5], start=1):

        start = max(0, pos - 500)
        end = min(len(source), pos + 1000)

        snippet = source[start:end]

        # Make HTML easier to read
        snippet = html.unescape(snippet)

        print(f"\n--- occurrence {i} ---")
        print(snippet)

# ------------------------------------------------------------
# EXTRACT ALL URL-LIKE STRINGS
# ------------------------------------------------------------

print("\n" + "=" * 80)
print("POTENTIAL ASSET URLS")
print("=" * 80)

urls = set()

# Absolute URLs
for match in re.findall(
    r'https?://[^"\'<>\s]+',
    source,
    flags=re.IGNORECASE
):
    urls.add(html.unescape(match))

# Relative href/src URLs
for match in re.findall(
    r'(?:href|src)\s*=\s*["\']([^"\']+)["\']',
    source,
    flags=re.IGNORECASE
):
    urls.add(urljoin(PAGE_URL, html.unescape(match)))

# onclick URLs / quoted paths
for match in re.findall(
    r'["\']([^"\']+\.(?:jpg|jpeg|png|tif|tiff|pdf|kmz|kml|zip))["\']',
    source,
    flags=re.IGNORECASE
):
    urls.add(urljoin(PAGE_URL, html.unescape(match)))

# ------------------------------------------------------------
# FILTER CHENNAI / FLOOD RELATED URLS
# ------------------------------------------------------------

keywords = [
    "chennai",
    "flood",
    "floods",
    "inund",
    "risat",
    "2021",
    "2015",
    "cartosat",
    "tn_"
]

relevant_urls = []

for url in sorted(urls):

    lower = url.lower()

    if any(keyword in lower for keyword in keywords):
        relevant_urls.append(url)

print("\nFound", len(urls), "total URL-like strings.")

print(
    "Found",
    len(relevant_urls),
    "potential Chennai/flood-related URLs."
)

for url in relevant_urls:
    print("\n", url)

# ------------------------------------------------------------
# LOOK FOR IMAGE PATHS
# ------------------------------------------------------------

print("\n" + "=" * 80)
print("IMAGE / DOCUMENT PATHS")
print("=" * 80)

asset_pattern = re.compile(
    r'[^"\']+\.(?:jpg|jpeg|png|tif|tiff|pdf|kmz|kml)',
    flags=re.IGNORECASE
)

assets = set()

for match in asset_pattern.findall(source):

    cleaned = html.unescape(match)

    # Remove obvious HTML junk
    cleaned = cleaned.split()[0]
    cleaned = cleaned.rstrip(");,}")

    if len(cleaned) > 5:
        assets.add(cleaned)

for asset in sorted(assets):

    lower = asset.lower()

    if any(
        keyword in lower
        for keyword in [
            "chennai",
            "flood",
            "inund",
            "risat",
            "2021",
            "2015",
            "tn"
        ]
    ):
        print(asset)

# ------------------------------------------------------------
# FINAL
# ------------------------------------------------------------

print("\n" + "=" * 80)
print("DISCOVERY COMPLETE")
print("=" * 80)

print("\nIMPORTANT:")
print("Do NOT create target_flood yet.")
print("We first need the actual spatial flood asset.")
print("\nRaw HTML is available at:")
print(output_file)