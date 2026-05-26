import requests
from bs4 import BeautifulSoup
import json
import time
from statistics import median
from datetime import datetime, timezone
import random

base_url = "https://www.bhomes.com/en/buy/apartment/uae/dubai"
bayut_base_url = "https://www.bayut.com/for-sale/apartments/dubai/"
propertyfinder_base_url = (
    "https://www.propertyfinder.ae/en/"
    "buy/dubai/apartments-for-sale.html"
)

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/"
}

session = requests.Session()
session.headers.update(headers)

AREA_ALIASES = {

    "dubai marina": "Dubai Marina",

    "jumeirah village circle": "Jumeirah Village Circle",

    "downtown dubai": "Downtown Dubai",

    "business bay": "Business Bay",

    "dubai south": "Dubai South"
}

PROPERTY_TYPE_MAP = {

    "apartment": "apartment",

    "flat": "apartment",

    "villa": "villa",

    "townhouse": "townhouse",

    "penthouse": "penthouse"
}


def normalize_area(area):

    if not area:
        return "Unknown"

    cleaned = area.strip().lower()

    return AREA_ALIASES.get(
        cleaned,
        area.strip().title()
    )


def normalize_property_type(property_type):

    if not property_type:
        return "other"

    cleaned = property_type.strip().lower()

    return PROPERTY_TYPE_MAP.get(
        cleaned,
        cleaned
    )

all_soups = []

# =========================================
# BHOMES
# =========================================

for page in range(1, 11):

    if page == 1:
        url = base_url
    else:
        url = f"{base_url}?page={page}&sort=date_desc"

    print("BHOMES:", url)

    try:

        response = session.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

    except Exception as e:

        print("Page Request Error:", e)

        continue

    time.sleep(2)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    all_soups.append({
        "source": "bhomes",
        "soup": soup
    })

"""
# =========================================
# BAYUT
# =========================================

for page in range(1, 11):

    if page == 1:
        url = bayut_base_url
    else:
        url = f"{bayut_base_url}page-{page}/"

    print("BAYUT:", url)

    try:

        response = session.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

    except Exception as e:

        print("Page Request Error:", e)

        continue

    time.sleep(random.uniform(2, 5))

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    all_soups.append({
        "source": "bayut",
        "soup": soup
    })
"""

# =========================================
# PROPERTY FINDER
# =========================================

for page in range(1, 11):

    if page == 1:

        url = propertyfinder_base_url

    else:

        url = (
            propertyfinder_base_url
            + f"?page={page}"
        )

    print("PROPERTYFINDER:", url)

    try:

        response = session.get(
            url,
            timeout=20
        )

        response.raise_for_status()

    except Exception as e:

        print(
            "PROPERTYFINDER Request Error:",
            e
        )

        continue

    time.sleep(2)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    all_soups.append({

        "source": "propertyfinder",

        "soup": soup
    })
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
seen_fingerprints = set()

# =========================================
# BHOMES PARSER
# =========================================

for source_data in all_soups:

    if source_data["source"] != "bhomes":
        continue

    soup = source_data["soup"]

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            if not script.string:
                continue

            data = json.loads(script.string)

            if (
                not isinstance(data, dict)
                or data.get("@type") != "ItemList"
            ):
                continue

            items = data.get("itemListElement", [])

            for item in items:

                listing = item.get("item", {})

                title = listing.get("name")

                property_url = listing.get("url")

                if not property_url:
                    continue

                if property_url in seen_urls:
                    continue

                seen_urls.add(property_url)

                try:

                    detail_response = session.get(
                        property_url,
                        headers=headers,
                        timeout=20
                    )

                    time.sleep(1)

                except Exception as e:

                    print("BHOMES Request Error:", e)

                    continue

                detail_soup = BeautifulSoup(
                    detail_response.text,
                    "html.parser"
                )

                detail_scripts = detail_soup.find_all(
                    "script",
                    type="application/ld+json"
                )

                for detail_script in detail_scripts:

                    try:

                        if not detail_script.string:
                            continue

                        detail_data = json.loads(
                            detail_script.string
                        )

                        if isinstance(detail_data, list):

                            for item_data in detail_data:

                                if (
                                    isinstance(item_data, dict)
                                    and item_data.get("@type") == "RealEstateListing"
                                ):

                                    detail_data = item_data

                        if (
                            not isinstance(detail_data, dict)
                            or (
                                detail_data.get("@type") != "RealEstateListing"
                                and not (
                                    isinstance(
                                        detail_data.get("@type"),
                                        list
                                    )
                                    and "RealEstateListing"
                                    in detail_data.get("@type")
                                )
                            )
                        ):
                            continue

                        offers = detail_data.get(
                            "offers",
                            {}
                        )

                        try:
                            price = float(
                                offers.get("price")
                            )
                        except:
                            continue

                        currency = offers.get(
                            "priceCurrency"
                        )

                        geo = detail_data.get(
                            "geo",
                            {}
                        )

                        lat = geo.get("latitude")
                        lng = geo.get("longitude")

                        floor_size = detail_data.get(
                            "floorSize",
                            {}
                        )

                        sqft = floor_size.get("value")

                        try:
                            sqft = str(sqft).replace(",", "")
                            sqft = float(sqft)
                        except:
                            continue

                        bedrooms = detail_data.get(
                            "numberOfRooms"
                        )

                        try:
                            bedrooms = int(bedrooms)
                        except:
                            bedrooms = 0

                        bathrooms = detail_data.get(
                            "numberOfBathroomsTotal"
                        )

                        property_type = "other"

                        additional_properties = (
                            detail_data.get(
                                "additionalProperty",
                                []
                            )
                        )

                        for prop in additional_properties:

                            if (
                                isinstance(prop, dict)
                                and prop.get("name") == "Property Type"
                            ):

                                property_type = (
                                    normalize_property_type(
                                        prop.get(
                                            "value",
                                            "other"
                                        )
                                    )
                                )

                                break

                        location = detail_data.get(
                            "location",
                            {}
                        )

                        area = normalize_area(
                            location.get("name")
                        )

                        if (
                            (not lat or not lng)
                            and area in coord_map
                        ):

                            lat = coord_map[area]["lat"]
                            lng = coord_map[area]["lng"]

                        fingerprint = (
                            area,
                            property_type,
                            bedrooms,
                            round(price, -4),
                            round(sqft, -1)
                        )

                        if fingerprint in seen_fingerprints:
                            continue

                        seen_fingerprints.add(
                            fingerprint
                        )

                        properties.append({

                            "source": "bhomes",

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

                        print("BHOMES Detail Error:", e)

        except Exception as e:

            print("BHOMES Script Error:", e)
"""
# =========================================
# BAYUT PARSER
# =========================================

for source_data in all_soups:

    if source_data["source"] != "bayut":
        continue

    soup = source_data["soup"]

    print(soup.prettify()[:5000])
    break

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            if not script.string:
                continue

            data = json.loads(script.string)

            print(json.dumps(data)[:3000])
            break

            if not isinstance(data, dict):
                continue

            graph = data.get("@graph", [])

            for item in graph:

                main_entity = item.get("mainEntity")

                if not main_entity:
                    continue

                item_list = main_entity.get(
                    "itemListElement",
                    []
                )

                for listing_item in item_list:

                    listing = listing_item.get(
                        "item",
                        {}
                    )

                    if (
                        listing.get("@type")
                        != "RealEstateListing"
                    ):
                        continue

                    property_url = listing.get("url")

                    if not property_url:
                        continue

                    if property_url in seen_urls:
                        continue

                    seen_urls.add(property_url)

                    main = listing.get(
                        "mainEntity",
                        {}
                    )

                    title = main.get(
                        "description",
                        "Unknown"
                    )

                    price = main.get("price")

                    try:
                        price = float(price)
                    except:
                        continue

                    currency = main.get(
                        "priceCurrency",
                        "AED"
                    )

                    geo = main.get(
                        "geo",
                        {}
                    )

                    lat = geo.get("latitude")
                    lng = geo.get("longitude")

                    address = main.get(
                        "address",
                        {}
                    )

                    area = normalize_area(
                        address.get(
                            "addressLocality",
                            "Unknown"
                        )
                    )

                    floor_size = main.get(
                        "floorSize",
                        {}
                    )

                    sqft = floor_size.get("value")

                    try:
                        sqft = (
                            str(sqft)
                            .replace(",", "")
                        )

                        sqft = float(sqft)

                    except:
                        continue

                    bedrooms = main.get(
                        "numberOfBedrooms",
                        0
                    )

                    try:
                        bedrooms = int(bedrooms)
                    except:
                        bedrooms = 0

                    bathrooms = main.get(
                        "numberOfBathroomsTotal"
                    )

                    property_type = normalize_property_type(
                        main.get(
                            "accommodationCategory",
                            "other"
                        )
                    )

                    if (
                        (not lat or not lng)
                        and area in coord_map
                    ):

                        lat = coord_map[area]["lat"]
                        lng = coord_map[area]["lng"]

                    fingerprint = (
                        area,
                        property_type,
                        bedrooms,
                        round(price, -4),
                        round(sqft, -1)
                    )

                    if fingerprint in seen_fingerprints:
                        continue

                    seen_fingerprints.add(
                        fingerprint
                    )

                    properties.append({

                        "source": "bayut",

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

        except Exception as e:

            print("BAYUT Script Error:", e)

"""

# =========================================
# PROPERTY FINDER PARSER
# =========================================

for source_data in all_soups:

    if source_data["source"] != "propertyfinder":
        continue

    soup = source_data["soup"]

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        try:

            if not script.string:
                continue

            data = json.loads(
                script.string
            )

            if not isinstance(data, dict):
                continue

            item_list = data.get(
                "accessModeSufficient",
                {}
            )

            if item_list.get("@type") != "ItemList":
                continue

            items = item_list.get(
                "itemListElement",
                []
            )

            for listing_item in items:

                listing = listing_item.get(
                    "mainEntity",
                    {}
                )

                property_url = listing.get(
                    "url"
                )

                if not property_url:
                    continue

                if property_url in seen_urls:
                    continue

                seen_urls.add(
                    property_url
                )

                title = listing.get(
                    "name",
                    "Unknown"
                )

                offers = listing.get(
                    "offers",
                    []
                )

                try:

                    offer = offers[0]

                    price_spec = offer.get(
                        "priceSpecification",
                        {}
                    )

                    price = float(
                        price_spec.get("price")
                    )

                except:
                    continue

                currency = price_spec.get(
                    "priceCurrency",
                    "AED"
                )

                geo = listing.get(
                    "geo",
                    {}
                )

                lat = geo.get(
                    "latitude"
                )

                lng = geo.get(
                    "longitude"
                )

                address = listing.get(
                    "address",
                    {}
                )

                area = normalize_area(
                    address.get(
                        "addressLocality",
                        "Unknown"
                    )
                )

                floor_size = listing.get(
                    "floorSize",
                    {}
                )

                sqft = floor_size.get(
                    "value"
                )

                try:

                    sqft = (
                        str(sqft)
                        .replace(",", "")
                    )

                    sqft = float(sqft)

                except:
                    continue

                bedrooms = listing.get(
                    "numberOfRooms",
                    0
                )

                try:

                    bedrooms = int(
                        bedrooms
                    )

                except:

                    bedrooms = 0

                bathrooms = listing.get(
                    "numberOfBathroomsTotal"
                )

                property_type = (
                    normalize_property_type(
                        listing.get(
                            "@type",
                            "other"
                        )
                    )
                )

                if (
                    (not lat or not lng)
                    and area in coord_map
                ):

                    lat = coord_map[area]["lat"]

                    lng = coord_map[area]["lng"]

                fingerprint = (

                    area,

                    property_type,

                    bedrooms,

                    round(price, -4),

                    round(sqft, -1)
                )

                if (
                    fingerprint
                    in seen_fingerprints
                ):
                    continue

                seen_fingerprints.add(
                    fingerprint
                )

                properties.append({

                    "source":
                    "propertyfinder",

                    "title":
                    title,

                    "price":
                    price,

                    "currency":
                    currency,

                    "area":
                    area,

                    "lat":
                    lat,

                    "lng":
                    lng,

                    "sqft":
                    sqft,

                    "bedrooms":
                    bedrooms,

                    "bathrooms":
                    bathrooms,

                    "property_type":
                    property_type,

                    "url":
                    property_url
                })

        except Exception as e:

            print(
                "PROPERTYFINDER Script Error:",
                e
            )
            
with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")


last_updated = datetime.now(timezone.utc).isoformat()

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
    if len(prices) < 5:
        continue

    market_median = median(prices)

    listing_count = len(prices)

    comparable_count = len(prices)

    if comparable_count < 5:
        confidence = "Low"

    elif comparable_count < 8:
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

        "sources": list(set(
            listing["source"]
            for listing in data["listings"]
        )),

        "area": area,

        "property_type": property_type,

        "bedrooms": bedrooms,

        "median_price_per_sqft": round(
            market_median
        ),

        "listing_count": listing_count,

        "comparable_count": comparable_count,

        "confidence": confidence,

        "last_updated": last_updated,

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

    if comparable_count < 5:
        confidence = "Low"

    elif comparable_count < 8:
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

            "source": listing["source"],

            "title": listing["title"],

            "area": listing["area"],

            "property_type": listing["property_type"],

            "bedrooms": listing["bedrooms"],

            "bathrooms": listing["bathrooms"],

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

            "last_updated": last_updated,

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
