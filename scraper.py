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

                
                    # SKIP DUPLICATES
                    if property_url in seen_urls:
                        continue

                    seen_urls.add(property_url)

                    # VISIT PROPERTY DETAIL PAGE
                    detail_response = requests.get(property_url, headers=headers)

                    time.sleep(1)

                    detail_soup = BeautifulSoup(detail_response.text, "html.parser")

                    detail_scripts = detail_soup.find_all(
                        "script",
                        type="application/ld+json"
                    )

                    for detail_script in detail_scripts:

                        try:
                            if not detail_script.string:
                                continue

                            detail_data = json.loads(detail_script.string)

                            # SOME JSON-LD BLOCKS ARE LISTS
                            if isinstance(detail_data, list):

                                for item_data in detail_data:

                                    if (
                                        isinstance(item_data, dict)
                                        and item_data.get("@type") == "RealEstateListing"
                                    ):

                                        detail_data = item_data

                            if (
                                isinstance(detail_data, dict)
                                and detail_data.get("@type") == "RealEstateListing"
                            ):

                                offers = detail_data.get("offers", {})

                                price = offers.get("price")

                                try:
                                    price = float(price)
                                except:
                                    continue
                                currency = offers.get("priceCurrency")

                                geo = detail_data.get("geo", {})

                                lat = geo.get("latitude")
                                lng = geo.get("longitude")

                                floor_size = detail_data.get("floorSize", {})

                                sqft = floor_size.get("value")

                                bedrooms = detail_data.get("numberOfRooms")

                                bathrooms = detail_data.get("numberOfBathroomsTotal")

                                property_type = detail_data.get("additionalType")

                                location = detail_data.get("contentLocation", {})

                                area = location.get("name")

                                properties.append({
                                    "title": title,
                                    "price": price,
                                    "currency": currency,
                                    "area": area,
                                    "lat": lat,
                                    "lng": lng,
                                    "sqft": sqft,
                                    "bedrooms": bedrooms,
                                    "bathrooms": bathrooms,
                                    "property_type": property_type,
                                    "url": property_url
                                })
                                break

                        except Exception as e:
                            print("Detail Error:", e)
        
with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")

# CREATE AREA AGGREGATION

area_data = {}

for property in properties:

    area = property["area"]
    price = property["price"]

    sqft = property["sqft"]

    # SKIP BAD DATA
    if not sqft or sqft == 0:
        continue

    try:
        sqft = float(sqft)
    except:
        continue

    price_per_sqft = price / sqft

    if area not in area_data:
        area_data[area] = {
            "total_price_per_sqft": 0,
            "count": 0,
            "lat": property["lat"],
            "lng": property["lng"]
        }

    area_data[area]["total_price_per_sqft"] += price_per_sqft
    area_data[area]["count"] += 1

# FINAL HEATMAP DATA
heatmap = []

for area, data in area_data.items():

    avg_price_per_sqft = (
        data["total_price_per_sqft"] / data["count"]
    )

    heatmap.append({
        "area": area,
        "avg_price_per_sqft": round(avg_price_per_sqft),
        "listing_count": data["count"],
        "lat": data["lat"],
        "lng": data["lng"]
    })

# SAVE HEATMAP DATA
with open("heatmap.json", "w", encoding="utf-8") as f:
    json.dump(heatmap, f, indent=2, ensure_ascii=False)

print("Saved heatmap.json")
