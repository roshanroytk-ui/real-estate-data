import requests
from bs4 import BeautifulSoup
import json
import time
from statistics import median

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
                                and (
                                    detail_data.get("@type") == "RealEstateListing"
                                    or (
                                        isinstance(detail_data.get("@type"), list)
                                        and "RealEstateListing" in detail_data.get("@type")
                                    )
                                )
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

                                try:
                                    bedrooms = int(bedrooms)
                                except:
                                    bedrooms = 0

                                bathrooms = detail_data.get("numberOfBathroomsTotal")

                                property_type = "other"

                                additional_properties = detail_data.get(
                                    "additionalProperty",
                                    []
                                )

                                for prop in additional_properties:

                                    if (
                                        isinstance(prop, dict)
                                        and prop.get("name") == "Property Type"
                                    ):

                                        property_type = (
                                            prop.get("value", "other")
                                            .lower()
                                            .strip()
                                        )

                                        break

                                location = detail_data.get("location", {})

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

        except Exception as e:
            print("Script Error:", e)
        
with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")

# =========================================
# PROFESSIONAL MARKET SEGMENT ENGINE
# =========================================

market_groups = {}

for property in properties:

    area = property["area"]
    property_type = property["property_type"]
    bedrooms = property["bedrooms"]
    price = property["price"]
    sqft = property["sqft"]

    if not sqft or sqft == 0:
        continue

    try:
        sqft = float(sqft)
    except:
        continue

    price_per_sqft = price / sqft

    # MICRO MARKET KEY
    market_key = (
        area,
        property_type,
        bedrooms
    )

    if market_key not in market_groups:

        market_groups[market_key] = {
            "prices": [],
            "listings": [],
            "lat": property["lat"],
            "lng": property["lng"]
        }

    market_groups[market_key]["prices"].append(
        price_per_sqft
    )

    market_groups[market_key]["listings"].append(
        property
    )

# =========================================
# BUILD HEATMAP
# =========================================

heatmap = []

for market_key, data in market_groups.items():

    area, property_type, bedrooms = market_key

    prices = data["prices"]

    # SKIP WEAK DATA
    if len(prices) < 2:
        continue

    market_median = median(prices)

    listing_count = len(prices)

    comparable_count = len(prices)

    if comparable_count < 10:
        confidence = "Low"

    elif comparable_count < 20:
        confidence = "Medium"

    else:
        confidence = "High"

    # MARKET TIER COLORING

    if market_median < 1500:
        color = "green"

    elif market_median < 3000:
        color = "yellow"

    else:
        color = "red"

    heatmap.append({

        "area": area,

        "property_type": property_type,

        "bedrooms": bedrooms,

        "median_price_per_sqft": round(
            market_median
        ),

        "listing_count": listing_count,

        "comparable_count": comparable_count,

        "confidence": confidence,

        "lat": data["lat"],
        "lng": data["lng"],

        "color": color
    })

# SORT
heatmap.sort(
    key=lambda x: x["median_price_per_sqft"]
)

# SAVE
with open(
    "heatmap.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        heatmap,
        f,
        indent=2,
        ensure_ascii=False
    )

print("Saved professional heatmap.json")

# =========================================
# INVESTMENT OPPORTUNITY ENGINE
# =========================================

opportunities = []

for market_key, data in market_groups.items():

    prices = data["prices"]

    # STRONGER DATA QUALITY
    if len(prices) < 5:
        continue

    market_median = median(prices)

    comparable_count = len(prices)

    if comparable_count < 10:
        confidence = "Low"

    elif comparable_count < 20:
        confidence = "Medium"

    else:
        confidence = "High"

    for listing in data["listings"]:

        try:
            sqft = float(listing["sqft"])
        except:
            continue

        listing_price_per_sqft = (
            listing["price"] / sqft
        )

        deviation = (
            listing_price_per_sqft - market_median
        ) / market_median

        # OPPORTUNITY COLORING
        if deviation < -0.15:
            color = "green"

        elif deviation > 0.15:
            color = "red"

        else:
            color = "yellow"

        opportunities.append({

            "title": listing["title"],

            "area": listing["area"],

            "property_type": listing["property_type"],

            "bedrooms": listing["bedrooms"],

            "price": round(listing["price"]),

            "sqft": round(sqft),

            "price_per_sqft": round(
                listing_price_per_sqft
            ),

            "market_median_price_per_sqft": round(
                market_median
            ),

            "comparable_count": comparable_count,

            "confidence": confidence,

            "deviation_score": round(
                deviation,
                2
            ),

            "lat": listing["lat"],
            "lng": listing["lng"],

            "url": listing["url"],

            "color": color
        })

# SORT BEST OPPORTUNITIES FIRST

opportunities.sort(
    key=lambda x: x["deviation_score"]
)

# SAVE

with open(
    "opportunities.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        opportunities,
        f,
        indent=2,
        ensure_ascii=False
    )

print("Saved opportunities.json")
