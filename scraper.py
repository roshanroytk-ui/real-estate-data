import requests
from bs4 import BeautifulSoup
import json

url = "https://www.bhomes.com/en/buy/apartment/uae/dubai"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)

print("Status:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

properties = []

# Find all JSON-LD scripts
scripts = soup.find_all("script", type="application/ld+json")

for script in scripts:
    try:
        data = json.loads(script.string)

        # Look for ItemList
        if isinstance(data, dict) and data.get("@type") == "ItemList":

            items = data.get("itemListElement", [])

            for item in items:

                listing = item.get("item", {})

                title = listing.get("name")
                url = listing.get("url")

                offers = listing.get("offers", {})
                price = offers.get("price")

                location = listing.get("location", {})
                area = location.get("name")

                properties.append({
                    "title": title,
                    "price": price,
                    "area": area,
                    "url": url
                })

    except Exception as e:
        print("Error parsing script:", e)

# Save JSON
with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")
