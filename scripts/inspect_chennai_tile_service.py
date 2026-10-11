
import requests
from urllib.parse import urljoin

BASE = "https://bhuvan-app1.nrsc.gov.in/disaster/usrtasks/flood/"
JS_URL = urljoin(BASE, "js/v16.js")

print("=" * 70)
print("JALSURAKSHA - CHENNAI FLOOD SERVICE INSPECTION")
print("=" * 70)

response = requests.get(JS_URL, timeout=60)
response.raise_for_status()

source = response.text
print("JavaScript downloaded:", len(source), "characters")

terms = [
    "tilecache2",
    "function loadlayer",
    "loadlayer =",
    "tilecache"
]

for term in terms:
    print("\n" + "-" * 70)
    print("SEARCH:", term)
    print("-" * 70)

    start = 0
    found = 0

    while True:
        pos = source.lower().find(term.lower(), start)

        if pos == -1:
            break

        found += 1
        left = max(0, pos - 700)
        right = min(len(source), pos + 1800)

        print(source[left:right])
        print("\n[END MATCH]\n")

        start = pos + len(term)

        if found >= 5:
            print("Stopped after 5 matches.")
            break

    if found == 0:
        print("No matches found in this JavaScript file.")

print("\nInspection complete.")
