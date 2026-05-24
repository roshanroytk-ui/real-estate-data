import requests
from bs4 import BeautifulSoup
import json
import time

base_url = "https://www.bhomes.com/en/buy/apartment/uae/dubai"

headers = {
    "User-Agent": "Mozilla/5.0"
}

all_soups = []

for page in range(1, 11):

    if page == 1:
        url = base_url
    else:
        url = f"{base_url}?page={page}&sort=date_desc"

    print("Scraping:", url)

    response = requests.get(url, headers=headers)
    time.sleep(2)

    print("Status:", response.status_code)

    soup = BeautifulSoup(response.text, "html.parser")

    all_soups.append(soup)
# LOAD AREA COORDINATES
with open("areas.json", "r", encoding="utf-8") as f:
    area_coords = json.load(f)

# convert to quick lookup
coord_map = {
    item["area"]: {
        "lat": item["lat"],
        "lng": item["lng"]
    }
    for item in area_coords
}

properties = []
seen_urls = set()

for soup in all_soups:

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:

        try:
            data = json.loads(script.string)

            if isinstance(data, dict) and data.get("@type") == "ItemList":

                items = data.get("itemListElement", [])

                for item in items:

                    listing = item.get("item", {})

                    title = listing.get("name")
                    property_url = listing.get("url")

                    offers = listing.get("offers", {})
                    price = offers.get("price")

                    location = listing.get("location", {})
                    area = location.get("name")

                    coords = coord_map.get(area, {})

                    # SKIP DUPLICATES
                    if property_url in seen_urls:
                        continue

                    seen_urls.add(property_url)

                    properties.append({
                        "title": title,
                        "price": price,
                        "area": area,
                        "lat": coords.get("lat"),
                        "lng": coords.get("lng"),
                        "url": property_url
                    })

        except Exception as e:
            print("Error:", e)

with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")

# CREATE AREA AGGREGATION

area_data = {}

for property in properties:

    area = property["area"]
    price = property["price"]

    if area not in area_data:
        area_data[area] = {
            "total_price": 0,
            "count": 0,
            "lat": property["lat"],
            "lng": property["lng"]
        }

    area_data[area]["total_price"] += price
    area_data[area]["count"] += 1

# FINAL HEATMAP DATA
heatmap = []

for area, data in area_data.items():

    avg_price = data["total_price"] / data["count"]

    heatmap.append({
        "area": area,
        "avg_price": round(avg_price),
        "listing_count": data["count"],
        "lat": data["lat"],
        "lng": data["lng"]
    })

# SAVE HEATMAP DATA
with open("heatmap.json", "w", encoding="utf-8") as f:
    json.dump(heatmap, f, indent=2, ensure_ascii=False)

print("Saved heatmap.json")
