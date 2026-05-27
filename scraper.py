import requests
from bs4 import BeautifulSoup
import json
import time
import re
from statistics import median
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2
import random
from bs4.element import Script
import geopandas as gpd
from shapely.geometry import Point
import os

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
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_KEY:
    print("WARNING: GEMINI_API_KEY missing")

# =====================================
# AI CACHE
# =====================================

AI_CACHE_FILE = "ai_cache.json"

try:

    with open(
        AI_CACHE_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        ai_cache = json.load(f)

except:

    ai_cache = {}

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
    "penthouse": "penthouse",
    "apartmentcomplex": "apartment",
    "house": "villa"
}

VALID_LAYOUT_TYPES = [

    "standard",

    "terrace",

    "duplex",

    "penthouse",

    "luxury",

    "serviced",

    "loft",

    "ground_floor"
]


def normalize_area(area):

    if not area:
        return "Unknown"

    cleaned = area.strip().lower()

    return AREA_ALIASES.get(
        cleaned,
        area.strip().title()
    )

def haversine_distance(lat1, lng1, lat2, lng2):

    R = 6371

    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlng / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return R * c

def is_duplicate_property(

    lat,
    lng,
    price,
    sqft,
    bedrooms

):

    try:

        lat = float(lat)
        lng = float(lng)

        price = float(price)
        sqft = float(sqft)

    except:

        return False

    for existing in potential_duplicates:

        # =====================================
        # SAME BEDROOM COUNT
        # =====================================

        if existing["bedrooms"] != bedrooms:
            continue

        # =====================================
        # DISTANCE CHECK
        # =====================================

        distance = haversine_distance(

            lat,
            lng,

            existing["lat"],
            existing["lng"]
        )

        # 150 meters

        if distance > 0.15:
            continue

        # =====================================
        # PRICE CHECK
        # =====================================

        price_diff = abs(
            price - existing["price"]
        )

        if price_diff > 50000:
            continue

        # =====================================
        # SQFT CHECK
        # =====================================

        sqft_diff = abs(
            sqft - existing["sqft"]
        )

        if sqft_diff > 50:
            continue

        return True

    potential_duplicates.append({

        "lat": lat,
        "lng": lng,

        "price": price,
        "sqft": sqft,

        "bedrooms": bedrooms
    })

    return False


def get_canonical_area(lat, lng, raw_area=""):

    try:

        lat = float(lat)
        lng = float(lng)

    except:

        return normalize_area(raw_area)

    point = Point(lng, lat)

    matches = []

    for _, row in areas_gdf.iterrows():

        polygon = row.geometry

        try:

            if polygon.contains(point):

                matches.append({

                    "area": row["canonical_area"],

                    "polygon_area": polygon.area
                })

        except:
            continue


    # =====================================
    # DEBUG POLYGON FAILURES
    # =====================================

    if not matches:

        print(
            "NO POLYGON MATCH:",
            raw_area,
            lat,
            lng
        )

    # =====================================
    # SMALLEST POLYGON WINS
    # =====================================

    if matches:

        matches.sort(
            key=lambda x: x["polygon_area"]
        )

        return matches[0]["area"]

    # =====================================
    # FALLBACK
    # =====================================

    # =====================================
    # SEMANTIC FALLBACK
    # =====================================

    raw_lower = raw_area.lower()

    SEMANTIC_AREA_MATCHES = {

        "downtown": "Downtown Dubai",

        "business bay": "Business Bay",

        "difc": "DIFC",

        "city walk": "City Walk",

        "dubai marina": "Dubai Marina",

        "jumeirah lake towers": "Jumeirah Lake Towers",

        "jlt": "Jumeirah Lake Towers",

        "jumeirah village circle": "Jumeirah Village Circle",

        "jvc": "Jumeirah Village Circle",

        "dubai hills": "Dubai Hills Estate"
    }

    for keyword, canonical in SEMANTIC_AREA_MATCHES.items():

        if keyword in raw_lower:

            return canonical

    # =====================================
    # FINAL FALLBACK
    # =====================================

    return normalize_area(raw_area)


def normalize_property_type(
    property_type,
    title="",
    description=""
):

    combined_text = f"{title} {description}".lower()

    # =====================================
    # DETECT STUDIO APARTMENTS
    # =====================================

    studio_patterns = [

        "studio apartment",
        "studio flat",
        "studio unit",
        "spacious studio",
        "studio layout",
        "well-designed studio",
        "studio"
    ]

    for pattern in studio_patterns:

        if pattern in combined_text:

            return "studio apartment"

    # =====================================
    # NORMAL NORMALIZATION
    # =====================================

    if not property_type:
        return "other"

    cleaned = property_type.strip().lower()

    return PROPERTY_TYPE_MAP.get(
        cleaned,
        cleaned
    )

def detect_layout_type_with_gemini(listing):

    try:

        title = listing.get("title", "")
        sqft = listing.get("sqft", 0)
        bedrooms = listing.get("bedrooms", 0)
        area = listing.get("area", "")
        price_per_sqft = listing.get("price_per_sqft", 0)
        description = listing.get("description", "")

        prompt = f"""
You are a Dubai real estate classification engine.

Your task:
Classify this property into ONE layout type only.

Allowed layout types:

- standard
- terrace
- duplex
- penthouse
- luxury
- serviced
- loft
- ground_floor

Rules:
- Return ONLY valid JSON
- Do NOT explain
- Do NOT add markdown

Property:

Title: {title}

Area: {area}

Bedrooms: {bedrooms}

Sqft: {sqft}

Price Per Sqft: {price_per_sqft}

Description:
{description}

Output format:

{{
  "layout_type": "standard"
}}
"""
        time.sleep(2)

        response = requests.post(

            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}",

            json={

                "contents": [

                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            },

            timeout=30
        )

        data = response.json()
        
        # =====================================
        # DEBUG GEMINI FAILURES
        # =====================================
        
        if "candidates" not in data:
        
            print("GEMINI BAD RESPONSE:")
            print(json.dumps(data, indent=2))
        
            return "standard"
        
        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        text = text.strip()

        if text.startswith("```json"):
            text = text.replace("```json", "")
            text = text.replace("```", "")

        parsed = json.loads(text)

        layout_type = parsed.get(
            "layout_type",
            "standard"
        )

        if layout_type not in VALID_LAYOUT_TYPES:
            return "standard"

        return layout_type

    except Exception as e:

        print("Gemini Layout Error:", e)

        return "standard"

def generate_ai_analysis(listing, market_median):

    try:

        prompt = f"""
You are a Dubai real estate investment analyst.

Analyze this property compared to its market.

Return ONLY valid JSON.

Property:

Title: {listing.get("title")}

Area: {listing.get("area")}

Bedrooms: {listing.get("bedrooms")}

Sqft: {listing.get("sqft")}

Price Per Sqft: {listing.get("price_per_sqft")}

Market Median: {market_median}

Description:
{listing.get("description", "")}

Return format:

{{
  "quality_context": "...",
  "risk_flags": [
    "..."
  ],
  "investment_summary": "..."
}}
"""
        time.sleep(2)

        response = requests.post(

            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}",

            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            },

            timeout=30
        )

        data = response.json()
        
        # =====================================
        # DEBUG GEMINI FAILURES
        # =====================================
        
        if "candidates" not in data:
        
            print("GEMINI ANALYSIS BAD RESPONSE:")
            print(json.dumps(data, indent=2))
        
            return None
        
        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        text = text.strip()

        if text.startswith("```json"):
            text = text.replace("```json", "")
            text = text.replace("```", "")

        return json.loads(text)

    except Exception as e:

        print("AI ANALYSIS ERROR:", e)

        return None

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

areas_gdf = gpd.read_file(
    "dubai_areas.geojson"
)

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
potential_duplicates = []

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

                                description = detail_data.get(
                                    "description",
                                    ""
                                )
                                
                                property_type = normalize_property_type(
                                
                                    prop.get(
                                        "value",
                                        "other"
                                    ),
                                
                                    title=title,
                                
                                    description=description
                                )
    
                                break

                        location = detail_data.get(
                            "location",
                            {}
                        )

                        raw_area = location.get("name")

                        area = get_canonical_area(
                            lat,
                            lng,
                            raw_area
                        )

                        if (
                            (not lat or not lng)
                            and area in coord_map
                        ):

                            lat = coord_map[area]["lat"]
                            lng = coord_map[area]["lng"]

                        if is_duplicate_property(
                        
                            lat,
                            lng,
                            price,
                            sqft,
                            bedrooms
                        ):
                            continue

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

                            "url": property_url,

                            "description": description,

                            "layout_type": "standard",
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

                    if is_duplicate_property(
                    
                        lat,
                        lng,
                        price,
                        sqft,
                        bedrooms
                    ):
                        continue


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

                        "url": property_url,

                        "layout_type": "standard",
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

    try:

        # =====================================
        # GET __NEXT_DATA__
        # =====================================

        next_data_script = soup.find(
            "script",
            id="__NEXT_DATA__"
        )

        if (
            not next_data_script
            or not next_data_script.string
        ):
            continue

        data = json.loads(
            next_data_script.string
        )

        # =====================================
        # GET LISTINGS
        # =====================================

        listings = (
            data
            .get("props", {})
            .get("pageProps", {})
            .get("searchResult", {})
            .get("listings", [])
        )

        # =====================================
        # LOOP LISTINGS
        # =====================================

        for listing_wrapper in listings:

            try:

                # =====================================
                # ACTUAL PROPERTY OBJECT
                # =====================================

                property_data = listing_wrapper.get(
                    "property",
                    {}
                )

                if not property_data:
                    continue

                # =====================================
                # URL
                # =====================================

                property_url = property_data.get(
                    "share_url"
                )

                if not property_url:
                    continue

                if property_url in seen_urls:
                    continue

                seen_urls.add(property_url)

                # =====================================
                # TITLE
                # =====================================

                title = property_data.get(
                    "title",
                    "Unknown"
                )

                # =====================================
                # PRICE
                # =====================================

                price_data = property_data.get(
                    "price",
                    {}
                )

                price = price_data.get("value")

                if not price:
                    continue

                try:
                    price = float(price)
                except:
                    continue

                currency = price_data.get(
                    "currency",
                    "AED"
                )

                # =====================================
                # LOCATION
                # =====================================

                location = property_data.get(
                    "location",
                    {}
                )

                coordinates = location.get(
                    "coordinates",
                    {}
                )

                lat = coordinates.get("lat")
                lng = coordinates.get("lon")

                # =====================================
                # AREA
                # =====================================

                raw_area = (
                    location.get("full_name")
                    or location.get("name")
                    or "Unknown"
                )

                area = get_canonical_area(
                    lat,
                    lng,
                    raw_area
                )

                # =====================================
                # SQFT
                # =====================================

                size_data = property_data.get(
                    "size",
                    {}
                )

                sqft = size_data.get("value")

                try:

                    sqft = float(
                        str(sqft)
                        .replace(",", "")
                    )

                except:
                    continue

                # =====================================
                # BEDROOMS
                # =====================================

                bedrooms = property_data.get(
                    "bedrooms_value"
                )

                if bedrooms is None:

                    bedrooms = property_data.get(
                        "bedrooms",
                        0
                    )

                try:
                    bedrooms = int(bedrooms)
                except:
                    bedrooms = 0

                # =====================================
                # BATHROOMS
                # =====================================

                bathrooms = property_data.get(
                    "bathrooms_value"
                )

                if bathrooms is None:

                    bathrooms = property_data.get(
                        "bathrooms"
                    )

                try:
                    bathrooms = int(bathrooms)
                except:
                    bathrooms = None

                description = property_data.get(
                    "description",
                    ""
                )

                # =====================================
                # PROPERTY TYPE
                # =====================================

                property_type = normalize_property_type(

                    property_data.get(
                        "property_type",
                        "other"
                    ),

                    title=title,

                    description=property_data.get(
                        "description",
                        ""
                    )
                )

                # =====================================
                # COORD FALLBACK
                # =====================================

                if (
                    (not lat or not lng)
                    and area in coord_map
                ):

                    lat = coord_map[
                        area
                    ]["lat"]

                    lng = coord_map[
                        area
                    ]["lng"]

                # =====================================
                # DUPLICATE CHECK
                # =====================================

                if is_duplicate_property(

                    lat,
                    lng,
                    price,
                    sqft,
                    bedrooms
                ):
                    continue

                # =====================================
                # SAVE PROPERTY
                # =====================================

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

                    "raw_area":
                    raw_area,

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
                    property_url,

                    "description": description,

                    "layout_type": "standard",
                })

            except Exception as e:

                print(
                    "PROPERTYFINDER Listing Error:",
                    e
                )

    except Exception as e:

        print(
            "PROPERTYFINDER NEXT_DATA Error:",
            e
        )
            
with open("properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, indent=2, ensure_ascii=False)

print(f"Saved {len(properties)} properties.")

# =========================================
# AI LAYOUT AUDIT
# =========================================

for property in properties:

    try:

        sqft = float(property["sqft"])

        if sqft <= 0:
            continue

        property["price_per_sqft"] = (

            property["price"] / sqft
        )

    except:
        continue

# =====================================
# INITIAL MARKET MEDIANS
# =====================================

initial_groups = {}

for property in properties:

    key = (

        property["area"],

        property["property_type"],

        property["bedrooms"]
    )

    if key not in initial_groups:

        initial_groups[key] = []

    initial_groups[key].append(
        property["price_per_sqft"]
    )

initial_medians = {

    key: median(values)

    for key, values in initial_groups.items()

    if len(values) >= 5
}

# =====================================
# EXTREME DEVIATION AI AUDIT
# =====================================

for property in properties:

    key = (

        property["area"],

        property["property_type"],

        property["bedrooms"]
    )

    market_median = initial_medians.get(key)

    if not market_median:
        continue

    deviation = (

        property["price_per_sqft"]
        - market_median

    ) / market_median

    if abs(deviation) >= 0.40:

        title_lower = property["title"].lower()

        # =====================================
        # FREE RULE ENGINE
        # =====================================
        
        if "terrace" in title_lower:
        
            property["layout_type"] = "terrace"
            continue
        
        if "duplex" in title_lower:
        
            property["layout_type"] = "duplex"
            continue
        
        if "penthouse" in title_lower:
        
            property["layout_type"] = "penthouse"
            continue
        
        if "loft" in title_lower:
        
            property["layout_type"] = "loft"
            continue
        
        if "ground floor" in title_lower:
        
            property["layout_type"] = "ground_floor"
            continue

        print(
            "AI AUDIT:",
            property["title"]
        )

        cache_key = property["url"]
        
        if cache_key in ai_cache:
        
            layout_type = ai_cache[
                cache_key
            ].get(
                "layout_type",
                "standard"
            )
        
            print(
                "CACHE HIT:",
                layout_type
            )
        
        else:
        
            layout_type = (
                detect_layout_type_with_gemini(
                    property
                )
            )
        
            ai_cache[cache_key] = {
        
                "layout_type": layout_type
            }
        
            print(
                "NEW AI ANALYSIS:",
                layout_type
            )
        
        property["layout_type"] = layout_type



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
    layout_type = property.get(
        "layout_type",
        "standard"
    )
    
    market_key = (
        area,
        property_type,
        bedrooms,
        layout_type
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

    area, property_type, bedrooms, layout_type = market_key

    prices = data["prices"]

    # SKIP WEAK DATA
    if layout_type != "standard":

        if len(prices) < 2:
            continue
    
    else:
    
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

        "layout_type": layout_type,

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

    area, property_type, bedrooms, layout_type = market_key

    # STRONGER DATA QUALITY
    if layout_type != "standard":
    
        if len(prices) < 2:
            continue
    
    else:
    
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

            "layout_type": listing.get(
                "layout_type",
                "standard"
            ),

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


# =====================================
# AI INVESTMENT ANALYSIS
# =====================================

for opportunity in opportunities:

    deviation = opportunity["deviation_score"]

    # ONLY HIGH SIGNAL DEALS

    if deviation > -0.30:
        continue

    print(
        "AI INVESTMENT ANALYSIS:",
        opportunity["title"]
    )

    cache_key = (
        opportunity["url"]
        + "_investment_analysis"
    )
    
    if cache_key in ai_cache:
    
        analysis = ai_cache[
            cache_key
        ]
    
        print(
            "CACHE HIT: investment analysis"
        )
    
    else:
    
        analysis = generate_ai_analysis(
    
            opportunity,
    
            opportunity[
                "market_median_price_per_sqft"
            ]
        )
    
        if analysis:
    
            ai_cache[cache_key] = analysis
    
            print(
                "NEW INVESTMENT ANALYSIS"
            )
    
    if analysis:
    
        opportunity["ai_analysis"] = analysis
        
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

# =====================================
# SAVE AI CACHE
# =====================================

with open(
    AI_CACHE_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        ai_cache,
        f,
        indent=2,
        ensure_ascii=False
    )

print("Saved ai_cache.json")
