
import re
import requests
from urllib.parse import urljoin

PAGE_URL = (
    "https://bhuvan-app1.nrsc.gov.in/"
    "disaster/usrtasks/flood/flood.php?uname=empty"
)

HEADERS = {"User-Agent": "Mozilla/5.0"}

TERMS = [
    "loadlayer",
    "removelayer",
    "tilecache2",
    "ch_exp_0306dec15",
    "loadmap",
    "OpenLayers",
    "tilecache",
]

session = requests.Session()
session.headers.update(HEADERS)

print("=" * 75)
print("JALSURAKSHA - TRACE CHENNAI MAP SERVICE")
print("=" * 75)

response = session.get(PAGE_URL, timeout=60)
response.raise_for_status()
html = response.text

print("\nPortal downloaded:", len(html), "characters")

# Save the complete page for inspection.
with open(
    "data/bhuvan_flood_portal.html",
    "w",
    encoding="utf-8"
) as f:
    f.write(html)

# Find external JavaScript files and iframe/frame URLs.
script_urls = set(
    urljoin(PAGE_URL, src)
    for src in re.findall(
        r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)',
        html,
        flags=re.I
    )
)

frame_urls = set(
    urljoin(PAGE_URL, src)
    for src in re.findall(
        r'<(?:iframe|frame)\b[^>]*\bsrc\s*=\s*["\']([^"\']+)',
        html,
        flags=re.I
    )
)

print("\nExternal JavaScript files:", len(script_urls))
print("Frames:", len(frame_urls))

def inspect_text(label, url, content):
    matches = []

    for term in TERMS:
        start = 0
        count = 0

        while True:
            pos = content.lower().find(term.lower(), start)

            if pos < 0:
                break

            count += 1
            matches.append((pos, term))
            start = pos + len(term)

            if count >= 10:
                break

    if not matches:
        return

    print("\n" + "-" * 75)
    print(label)
    print(url)
    print("-" * 75)

    # Print a limited number of distinct matching regions.
    shown = set()

    for pos, term in sorted(matches)[:15]:
        left = max(0, pos - 250)
        right = min(len(content), pos + 700)
        region = (left, right)

        if region in shown:
            continue

        shown.add(region)

        print(f"\n[MATCH: {term}]")
        print(content[left:right])

inspect_text("MAIN HTML", PAGE_URL, html)

for url in sorted(script_urls):
    try:
        r = session.get(url, timeout=30)
        print(f"\nFetched JS: {r.status_code} {url}")

        if r.ok:
            inspect_text("JAVASCRIPT MATCH", url, r.text)

    except requests.RequestException as exc:
        print("\nJS request failed:", url, exc)

for url in sorted(frame_urls):
    try:
        r = session.get(url, timeout=30)
        print(f"\nFetched FRAME: {r.status_code} {url}")

        if r.ok and "text/html" in r.headers.get(
            "Content-Type", ""
        ).lower():
            inspect_text("FRAME HTML", url, r.text)

            frame_scripts = re.findall(
                r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)',
                r.text,
                flags=re.I
            )

            for src in frame_scripts:
                js_url = urljoin(url, src)

                try:
                    js = session.get(js_url, timeout=30)
                    print(f"\nFetched FRAME JS: {js.status_code} {js_url}")

                    if js.ok:
                        inspect_text(
                            "FRAME JAVASCRIPT MATCH",
                            js_url,
                            js.text
                        )

                except requests.RequestException as exc:
                    print("Frame JS request failed:", js_url, exc)

    except requests.RequestException as exc:
        print("\nFrame request failed:", url, exc)

print("\n" + "=" * 75)
print("TRACE COMPLETE")
print("=" * 75)
print("Send the output containing loadlayer, tilecache2,")
print("ch_exp_0306dec15, or any map service URL.")
