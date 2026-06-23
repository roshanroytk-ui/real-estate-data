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
import pandas as pd
from shapely.geometry import Point
from collections import Counter
import os
import time

TIMERS = {}

def timer_start(name):
    TIMERS[name] = time.time()

def timer_end(name):
    elapsed = time.time() - TIMERS[name]
    print(f"\n[TIMER] {name}: {elapsed:.1f} seconds")

base_url = "https://www.bhomes.com/en/buy/apartment/uae/dubai"
propertyfinder_base_url = (
    "https://www.propertyfinder.ae/en/"
    "buy/dubai/apartments-for-sale.html"
)
ninetynineacres_base_url = (
    "https://www.99acres.com/property-in-dubai-ffid"
)

REA_GRAPHQL_URL = (
    "https://www.rea.global/international/graphql"
)

HOUSING_GRAPHQL_URL = (
    "https://mightyzeus-mum.housing.com/api/gql"
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

SCRAPE_MODES = [
    "sale",
    "rent"
]
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

def extract_developer_name(description):

    if not description:
        return None

    developer_patterns = [

        r"developed by ([A-Z][A-Za-z&\- ]+)",

        r"by ([A-Z][A-Za-z&\- ]+)",

        r"from ([A-Z][A-Za-z&\- ]+)",

        r"project by ([A-Z][A-Za-z&\- ]+)"
    ]

    blacklist = {

        "betterhomes",
        "dubai marina",
        "downtown dubai"
    }

    for pattern in developer_patterns:

        match = re.search(
            pattern,
            description,
            re.IGNORECASE
        )

        if match:

            developer = (
                match.group(1)
                .strip()
            )

            developer_lower = developer.lower()

            if developer_lower not in blacklist:

                return developer

    return None

def detect_completion_status(description):

    if not description:
        return "ready"

    text = description.lower()

    offplan_keywords = [

        "off-plan",
        "off plan",
        "handover",
        "completion expected",
        "under construction",
        "q1 2026",
        "q2 2026",
        "q3 2026",
        "q4 2026"
    ]

    for keyword in offplan_keywords:

        if keyword in text:

            return "off_plan"

    return "ready"

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

VALID_QUALITY_TIERS = [

    "standard",

    "premium",

    "ultra_luxury"
]

def detect_quality_tier(property):

    score = 0

    description_raw = property.get("description", "")
    title_raw = property.get("title", "")

    description = str(description_raw).lower()
    title = str(title_raw).lower()

    amenities = property.get(
        "amenities",
        []
    )

    completion_status = property.get(
        "completion_status",
        ""
    )

    sqft = property.get(
        "sqft",
        0
    )

    developer = str(
        property.get(
            "developer_name",
            ""
        )
    ).lower()

    try:
        property_age = int(
            property.get(
                "property_age",
                0
            )
        )
    except:
        property_age = 0

    try:
        sqft = float(sqft)
    except:
        sqft = 0

    # =====================================
    # ULTRA LUXURY KEYWORDS
    # =====================================

    ultra_keywords = [

        "ultra luxury",
        "branded residence",
        "dorchester",
        "omniyat",
        "foster + partners",
        "private beach",
        "private pool",
        "sky palace",
        "full floor",
        "penthouse",
        "serviced by",
        "waterfront luxury",
        "exclusive residence",
        "iconic address"
    ]

    # =====================================
    # PREMIUM KEYWORDS
    # =====================================

    premium_keywords = [

        "beach access",
        "sea view",
        "high floor",
        "luxury living",
        "modern finishes",
        "upgraded",
        "infinity pool",
        "concierge",
        "waterfront",
        "premium",
        "resort-style"
    ]

    # =====================================
    # SCORE ULTRA
    # =====================================

    for keyword in ultra_keywords:

        if keyword in description or keyword in title:
            score += 3

    # =====================================
    # SCORE PREMIUM
    # =====================================

    for keyword in premium_keywords:

        if keyword in description or keyword in title:
            score += 1

    # =====================================
    # AMENITY SCORING
    # =====================================

    ultra_amenities = [

        "Private Beach",
        "Private Pool",
        "Infinity Pool",
        "Spa",
        "Valet Service"
    ]

    premium_amenities = [

        "Shared Pool",
        "Shared Gym",
        "View of Water",
        "Concierge Service",
        "Balcony"
    ]

    for amenity in amenities:

        if amenity in ultra_amenities:
            score += 2

        elif amenity in premium_amenities:
            score += 1


    premium_developers = [    
        "emaar",
        "aldar",
        "damac",
        "binghatti",
        "sobha",
        "meraas",
        "imtiaz",
        "nakheel",
        "ellington",
        "select group"
    ]
    
    ultra_developers = [ 
        "omniyat"
    ]
    
    for dev in premium_developers:
    
        if dev in developer:
            score += 1
    
    for dev in ultra_developers:
    
        if dev in developer:
            score += 3

    

    title_upper = title.upper()

    if "ULTRA LUXURY" in title_upper:
        score += 6
    
    if "BRANDED" in title_upper:
        score += 3
    
    if "EXCLUSIVE" in title_upper:
        score += 2
    
    if "WATERFRONT" in title_upper:
        score += 2

    # =====================================
    # OFF PLAN LUXURY BOOST
    # =====================================

    if completion_status == "off_plan":
        score += 2

    # =====================================
    # HUGE LAYOUT BOOST
    # =====================================

    if sqft >= 5000:
        score += 4

    elif sqft >= 2500:
        score += 2

    # =====================================
    # AGE PENALTY
    # =====================================
    
    if property_age >= 20:
        score -= 3
    
    elif property_age >= 15:
        score -= 2
    
    elif property_age >= 10:
        score -= 1


    # =====================================
    # FINAL CLASSIFICATION
    # =====================================

    if score >= 8:
        return "ultra_luxury"

    elif score >= 4:
        return "premium"

    return "standard"

# =====================================
# MINIMUM COMPARABLES
# =====================================

MIN_LAYOUT_COMPS = {

    "standard": 5,

    "terrace": 3,

    "duplex": 3,

    "penthouse": 3,

    "luxury": 3,

    "serviced": 3,

    "loft": 3,

    "ground_floor": 3
}

MIN_QUALITY_COMPS = {

    "standard": 5,

    "premium": 3,

    "ultra_luxury": 2
}

AED_TO_INR = 22.7

def normalize_price_to_aed(price, currency):

    if not price:
        return None

    if currency == "AED":
        return float(price)

    if currency == "INR":
        return float(price) / AED_TO_INR

    return float(price)

def parse_housing_price(price_text):

    price_text = str(price_text)

    if "Cr" in price_text:

        return (

            float(

                price_text
                .replace("₹", "")
                .replace("Cr", "")
                .strip()

            )

            * 10000000
        )

    if "L" in price_text:

        return (

            float(

                price_text
                .replace("₹", "")
                .replace("L", "")
                .strip()

            )

            * 100000
        )

    return float(

        re.sub(
            r"[^\d.]",
            "",
            price_text
        )
    )


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

def nearest_poi(
    lat,
    lng,
    poi_type
):

    try:

        lat = float(lat)
        lng = float(lng)

    except:

        return (
            None,
            None
        )

    subset = poi_gdf[
        poi_gdf["poi_type"] == poi_type
    ]

    if len(subset) == 0:

        return (
            None,
            None
        )

    nearest_distance = None

    nearest_name = None

    for _, row in subset.iterrows():

        distance = haversine_distance(

            lat,
            lng,

            row["lat"],
            row["lng"]
        )

        if (
            nearest_distance is None
            or
            distance < nearest_distance
        ):

            nearest_distance = distance

            nearest_name = row["name"]

    return (
        nearest_name,
        round(nearest_distance, 2)
    )

def calculate_location_score(
    metro_km,
    mall_km,
    beach_km,
    school_km,
    university_km,
    hospital_km
):

    score = 0

    if metro_km is not None:

        score += max(
            0,
            10 - metro_km * 2
        ) * 0.30

    if mall_km is not None:

        score += max(
            0,
            10 - mall_km
        ) * 0.15

    if beach_km is not None:

        score += max(
            0,
            10 - beach_km
        ) * 0.15

    if school_km is not None:

        score += max(
            0,
            10 - school_km
        ) * 0.20

    if university_km is not None:

        score += max(
            0,
            10 - university_km
        ) * 0.10

    if hospital_km is not None:

        score += max(
            0,
            10 - hospital_km
        ) * 0.10

    return round(score, 1)

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
    


def get_area_assignment(lat, lng, raw_area=""):

    global polygon_time

    try:
        polygon_time += 1
    except:
        polygon_time = 1

    try:

        lat = float(lat)
        lng = float(lng)
    
    except:
    
        fallback = normalize_area(raw_area)
    
        return {
            "comparable_area": fallback,
            "heatmap_area": fallback
        }
    
    # =====================================
    # REA GENERIC DUBAI FALLBACK LOCATION
    # =====================================
    
    if lat is None or lng is None:
    
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
    
                return {
                    "comparable_area": canonical,
                    "heatmap_area": canonical
                }
    
        fallback = normalize_area(raw_area)
    
        return {
            "comparable_area": fallback,
            "heatmap_area": fallback
        }
    
    point = Point(lng, lat)


    matches = []
    debug_matches = []

    for _, row in areas_gdf.iterrows():

        polygon = row.geometry
    
        try:
    
            b = polygon.bounds
    
    
        except:
            continue

        try:

            contains = polygon.contains(point)
            covers = polygon.covers(point)
            intersects = polygon.intersects(point)
            
            distance = polygon.distance(point)
            
            if distance < 0.001:

                runtime_debug.append({
            
                    "type": "close_polygon",
            
                    "area": row["name"],
            
                    "distance": distance
                })
            
            if contains or covers or intersects:

                area_name = row["name"]

                if pd.isna(area_name) or str(area_name).strip() == "":
                    continue
            
                polygon_bounds = polygon.bounds

                centroid = polygon.centroid
            
                match_info = {
            
                    "area": row["name"],

                    "osm_name": row.get("osm_name"),
            
                    "polygon_area": polygon.area,

                    "polygon_centroid_lat": centroid.y,
                    
                    "polygon_centroid_lng": centroid.x,
            
                    "bounds": {
            
                        "min_lng": polygon_bounds[0],
            
                        "min_lat": polygon_bounds[1],
            
                        "max_lng": polygon_bounds[2],
            
                        "max_lat": polygon_bounds[3]
                    }
                }
            
                matches.append(match_info)
            
                debug_matches.append(match_info)
                runtime_debug.append({

                    "type": "polygon_match",
                
                    "area": row["name"]
                })
        except:
            continue


    # =====================================
    # DEBUG POLYGON FAILURES
    # =====================================

    closest_distance = 999999
    closest_area = None
    
    for _, row in areas_gdf.iterrows():
    
        polygon = row.geometry
    
        try:
    
            distance = polygon.distance(point)
    
            if distance < closest_distance:
                closest_distance = distance
                closest_area = row["name"]
    
        except:
            pass

    if not matches:

        polygon_debug.append({
    
            "raw_area": raw_area,
    
            "lat": lat,
    
            "lng": lng,
    
            "matched_polygons": [],
    
            "selected_area": None
        })
    
        runtime_debug.append({

            "type": "polygon_miss",
        
            "raw_area": raw_area,
        
            "lat": lat,
        
            "lng": lng,
        
            "nearest_area": closest_area,
        
            "distance": closest_distance
        })

    # =====================================
    # SMALLEST POLYGON WINS
    # =====================================

    if matches:

        matches.sort(
            key=lambda x: x["polygon_area"]
        )
    
        polygon_debug.append({
    
            "raw_area": raw_area,
    
            "lat": lat,
    
            "lng": lng,
    
            "matched_polygons": matches,
    
            "selected_area": matches[0]["area"],
    
            "selected_polygon_area": matches[0]["polygon_area"]
        })

    if matches:

        matches.sort(
            key=lambda x: x["polygon_area"]
        )
    
        comparable_area = matches[0]["area"]
    
        heatmap_area = matches[-1]["area"]

        runtime_debug.append({

            "type": "polygon_selection",
        
            "comparable_area": comparable_area,
        
            "heatmap_area": heatmap_area,
        
            "match_count": len(matches)
        })
    
        return {
            "comparable_area": comparable_area,
            "heatmap_area": heatmap_area
        }

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

            return {
                "comparable_area": canonical,
                "heatmap_area": canonical
            }

    # =====================================
    # FINAL FALLBACK
    # =====================================

    fallback = normalize_area(raw_area)

    return {
        "comparable_area": fallback,
        "heatmap_area": fallback
    }

# =====================================
# BHOMES AMENITY EXTRACTION
# =====================================

def extract_amenities(amenity_features):

    amenities = []

    if not amenity_features:
        return amenities

    for item in amenity_features:

        try:

            name = item.get("name")
            value = item.get("value")

            # =====================================
            # HANDLE BOTH SCHEMA FORMATS
            # =====================================

            is_enabled = (
                value is True
                or value == True
                or value == "true"
                or value == "True"
                or value == "http://schema.org/True"
            )

            if name and is_enabled:

                amenities.append(name)

        except:
            continue

    return amenities

def normalize_amenities(amenities):

    if not amenities:
        return []

    # =====================================
    # REMOVE DUPLICATES
    # =====================================

    amenities = list(
        dict.fromkeys(amenities)
    )

    ALIASES = {

        "Private Beach Access": "Private Beach",
    
        "Beach Access": "Private Beach",
    
        "Sea View": "View of Water",
    
        "Infinity Swimming Pool": "Infinity Pool",
    
        "Gymnasium": "Shared Gym"
    }
    
    normalized = []
    
    for amenity in amenities:
    
        normalized.append(
            ALIASES.get(
                amenity,
                amenity
            )
        )
    
    amenities = normalized

    # =====================================
    # PRIORITY SYSTEM
    # =====================================

    PRIORITY_AMENITIES = [

        # ULTRA PREMIUM
        "Private Beach",
        "Beach Access",
        "Sea View",
        "View of Water",
        "Waterfront",
        "Infinity Pool",
        "Private Pool",
        "Shared Pool",

        # WELLNESS
        "Gym",
        "Shared Gym",
        "Private Gym",
        "Spa",
        "Shared Spa",
        "Sauna",

        # LIFESTYLE
        "Rooftop",
        "Sky Lounge",
        "Concierge Service",
        "Valet Service",
        "Children's Play Area",
        "Children's Pool",

        # PROPERTY FEATURES
        "Balcony",
        "Walk-in Closet",
        "Built-In Wardrobes",

        # SAFETY
        "Security",
        "Covered Parking"
    ]

    # =====================================
    # SORT BY PRIORITY
    # =====================================

    def amenity_score(name):

        try:
            return PRIORITY_AMENITIES.index(name)
        except:
            return 999

    amenities.sort(
        key=amenity_score
    )

    # =====================================
    # LIMIT TO TOP 3
    # =====================================

    return amenities


def normalize_property_type(
    property_type,
    title="",
    description=""
):

    combined_text = f"{title} {description}".lower()

    if property_type:

        pt = property_type.lower()
    
        if "studio" in pt:
            return "studio apartment"

    # =====================================
    # DETECT STUDIO APARTMENTS
    # =====================================

    studio_patterns = [

        "studio apartment",
        "studio flat",
        "studio unit",
        "spacious studio",
        "studio layout",
        "well-designed studio"
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

def property_type_display(property_type):

    if not property_type:
        return None

    return (
        property_type
        .replace("_", " ")
        .title()
    )

def batch_detect_layout_types(listings):

    start = time.time()

    try:

        simplified = []

        for listing in listings:

            simplified.append({

                "url": listing["url"],

                "title": listing.get(
                    "title",
                    ""
                ),

                "area": listing.get(
                    "area",
                    ""
                ),

                "bedrooms": listing.get(
                    "bedrooms",
                    0
                ),

                "sqft": listing.get(
                    "sqft",
                    0
                ),

                "price_per_sqft": round(
                    listing.get(
                        "price_per_sqft",
                        0
                    )
                ),

                "description": listing.get(
                    "description",
                    ""
                ),
                "amenities": listing.get(
                    "amenities",
                    []
                ),
                
                "completion_status": listing.get(
                    "completion_status",
                    ""
                ),
                
                "tower_name": listing.get(
                    "tower_name",
                    ""
                ),
                
                "quality_tier": listing.get(
                    "quality_tier",
                    "standard"
                ),
            })

        prompt = f"""
You are a Dubai real estate classification engine.

For EACH property:

Classify into ONE layout type only.

Allowed values:

- standard
- terrace
- duplex
- penthouse
- luxury
- serviced
- loft
- ground_floor


Allowed quality_tier values:

ultra_luxury:
- branded residences
- waterfront trophy assets
- ultra-premium developers
- private beach/pool
- penthouse-scale layouts
- iconic architecture

premium:
- luxury towers
- beachfront
- modern high-end finishes
- strong amenities

standard:
- regular apartments
- older stock
- non-branded

Return ONLY valid JSON array.

Example:

[
  {{
    "url": "...",
    "layout_type": "standard",
    "quality_tier": "standard"
  }}
]

Properties:

{json.dumps(simplified, indent=2)}
"""

        time.sleep(2)

        response = requests.post(

            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}",

            json={

                "generationConfig": {
                    "temperature": 0
                },

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

            timeout=60
        )

        data = response.json()

        if "candidates" not in data:

            print("BATCH GEMINI ERROR:")
            print(json.dumps(data, indent=2))

            return {}

        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        text = text.strip()

        if text.startswith("```json"):
            text = text.replace(
                "```json",
                ""
            )

            text = text.replace(
                "```",
                ""
            )

        parsed = json.loads(text)

        results = {}

        for item in parsed:

            url = item.get("url")

            layout_type = item.get(
                "layout_type",
                "standard"
            )

            quality_tier = item.get(

                "quality_tier",
            
                "standard"
            )

            if (
                layout_type
                not in VALID_LAYOUT_TYPES
            ):

                layout_type = "standard"

            if (
                quality_tier
                not in VALID_QUALITY_TIERS
            ):
            
                quality_tier = "standard"

            results[url] = {

                "layout_type": layout_type,
            
                "quality_tier": quality_tier
            }

        print(
            "BATCH LAYOUT TIME:",
            round(time.time() - start, 1)
        )

        return results

    except Exception as e:

        print("BATCH LAYOUT ERROR:", e)

        return {}

def generate_ai_analysis(listing, market_median):

    start = time.time()

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

                "generationConfig": {
                    "temperature": 0
                },
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
        
        if "error" in data:

            error_code = data["error"].get("code")
        
            if error_code == 429:
        
                raise RuntimeError(
                    "GEMINI_QUOTA_EXCEEDED"
                )
        
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

        print(
            "AI ANALYSIS TIME:",
            round(time.time() - start, 1)
        )

    except RuntimeError:

        raise

    except Exception as e:

        print("AI ANALYSIS ERROR:", e)

        return None

all_soups = []

# =========================================
# DUBIZZLE ALGOLIA
# =========================================

APP_ID = "WD0PTZ13ZS"
API_KEY = "cef139620248f1bc328a00fddc7107a6"

RAK_API_KEY = "cdd839b4fdac840289e88633779e8634"

ALGOLIA_URL = (
    f"https://{APP_ID}-dsn.algolia.net/1/indexes/*/queries"
)

ALGOLIA_HEADERS = {
    "X-Algolia-Application-Id": APP_ID,
    "X-Algolia-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def get_dubizzle_index():

    if SCRAPE_MODE == "rent":

        return (
            "by_verification_feature_asc_"
            "property-for-rent-residential.com"
        )

    return (
        "by_verification_feature_asc_"
        "property-for-sale-residential.com"
    )

# =========================================
# DUBIZZLE SCRAPER
# =========================================

def fetch_dubizzle_algolia():

    listings = []

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                f"query=&page={page}&hitsPerPage=1000"
            }
            for page in range(5)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=ALGOLIA_HEADERS,
            json=payload,
            timeout=60
        )
        
        response.raise_for_status()
        
        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"ALGOLIA PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("DUBIZZLE ERROR:", e)

    print(
        "TOTAL DUBIZZLE LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_rak():

    listings = []

    rak_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=11)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=rak_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"RAK PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("RAK ERROR:", e)

    print(
        "TOTAL RAK LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_abudhabi():

    listings = []

    abu_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=3)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=abu_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"ABU DHABI PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("ABU DHABI ERROR:", e)

    print(
        "TOTAL ABU DHABI LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_alain():

    listings = []

    alain_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=39)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=alain_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"AL AIN PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("AL AIN ERROR:", e)

    print(
        "TOTAL AL AIN LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_fujairah():

    listings = []

    fujairah_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=13)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=fujairah_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"FUJAIRAH PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("FUJAIRAH ERROR:", e)

    print(
        "TOTAL FUJAIRAH LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_uaq():

    listings = []

    uaq_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=15)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=uaq_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"UAQ PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("UAQ ERROR:", e)

    print(
        "TOTAL UAQ LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_sharjah():

    listings = []

    sharjah_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=12)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=sharjah_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"SHARJAH PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("SHARJAH ERROR:", e)

    print(
        "TOTAL SHARJAH LISTINGS:",
        len(listings)
    )

    return listings

def fetch_dubizzle_ajman():

    listings = []

    sharjah_headers = {
        "X-Algolia-Application-Id": APP_ID,
        "X-Algolia-API-Key": RAK_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "requests": [
            {
                "indexName":
                get_dubizzle_index(),

                "params":
                (
                    f"query="
                    f"&page={page}"
                    f"&hitsPerPage=1000"
                    f"&filters=(city.id=14)"
                )
            }
            for page in range(2)
        ]
    }

    try:

        response = requests.post(
            ALGOLIA_URL,
            headers=sharjah_headers,
            json=payload,
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        for result in data["results"]:

            hits = result.get("hits", [])

            listings.extend(hits)

            print(
                f"AJMAN PAGE {result.get('page')} "
                f"({len(hits)} listings)"
            )

    except Exception as e:

        print("AJMAN ERROR:", e)

    print(
        "TOTAL AJMAN LISTINGS:",
        len(listings)
    )

    return listings

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

# 99ACRES

for page in range(1,11):

    url = (
        ninetynineacres_base_url
        + f"?page={page}"
    )

    response = session.get(
        url,
        timeout=20
    )

    if "verifycaptcha" in response.url:

        print(
            "99ACRES CAPTCHA HIT:",
            page
        )
    
        break

    sleep_time = random.uniform(2, 6)

    print(
        f"99ACRES WAITING {sleep_time:.1f}s"
    )
    
    time.sleep(sleep_time)

    print("99ACRES STATUS:", response.status_code)
    print("99ACRES URL:", response.url)
    print("99ACRES TITLE CHECK:")
    
    tmp_soup = BeautifulSoup(response.text, "html.parser")
    
    if tmp_soup.title:
        print(tmp_soup.title.text)


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    all_soups.append({
        "source": "99acres",
        "soup": soup
    })

polygon_debug = []
runtime_debug = []

ai_cache_hits = 0
ai_audits_queued = 0

# LOAD AREA COORDINATES
with open("areas.json", "r", encoding="utf-8") as f:
    area_coords = json.load(f)

areas_gdf = gpd.read_file(
    "polygon_cache.geojson"
)

poi_gdf = gpd.read_file(
    "poi_cache.geojson"
)

areas_gdf = areas_gdf[
    areas_gdf["name"].notna()
]

print("ORIGINAL CRS:", areas_gdf.crs)

# force WGS84 lat/lng
if areas_gdf.crs is not None:
    areas_gdf = areas_gdf.to_crs("EPSG:4326")

print("AFTER CONVERSION:", areas_gdf.crs)

print(
    "TOTAL BOUNDS:",
    areas_gdf.total_bounds
)

print(
    "AREA COUNT:",
    len(areas_gdf)
)

print(areas_gdf.columns.tolist())

# convert to quick lookup
coord_map = {
    item["area"]: {
        "lat": item["lat"],
        "lng": item["lng"]
    }
    for item in area_coords
}

# =========================================
# REA GRAPHQL
# =========================================

def fetch_rea_listings():

    all_listings = []

    page = 1
    page_size = 5000

    query = """
    query searchListViewQuery(
      $country:String!,
      $channel:String!,
      $page:Int!,
      $pageSize:Int!,
      $language:String!,
      $currencyCode:String,
      $where:String,
      $searchtypes:[String],
      $includesurrounding:Boolean,
      $distanceUnit:String
    ){
      searchListListings(
        listingSearchInput:{
          country:$country
          channel:$channel
          currencyCode:$currencyCode
          where:$where
          searchtypes:$searchtypes
          includesurrounding:$includesurrounding
          distanceUnit:$distanceUnit
          language:$language
        }
        pageReq:{
          pageNo:$page,
          pageSize:$pageSize
        }
      ){
        listings{
          id
          displayAddress
          description

          bedrooms
          bathrooms
          parkingSpaces

          completionDate

          propertyTypes(language:$language)

          buildingSize(
            language:$language,
            unit:SQUARE_METERS
          )

          detailPageUrl(language:$language)

          geoLocation{
            latitude
            longitude
          }

          price(
            language:$language,
            currency:$currencyCode
          ){
            displayConsumerPrice
          }
        }
      }
    }
    """

    while True:

        variables = {
            "country": "ae",
            "channel": "buy",
            "searchtypes": ["apartment"],
            "where": "united arab emirates",
            "language": "en",
            "currencyCode": "AED",
            "page": page,
            "pageSize": page_size,
            "includesurrounding": True,
            "distanceUnit": "Miles"
        }

        response = requests.post(
            REA_GRAPHQL_URL,
            json={
                "operationName": "searchListViewQuery",
                "variables": variables,
                "query": query
            },
            timeout=60
        )

        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            print("REA GRAPHQL ERRORS:")
            print(json.dumps(data["errors"], indent=2))
        
        print("REA STATUS:", response.status_code)
        
        if data.get("data") is None:
            print("REA DATA IS NULL")
            print(json.dumps(data, indent=2)[:5000])

        listings = (
            ((data.get("data") or {})
              .get("searchListListings") or {})
              .get("listings", [])
        )

        if not listings:
            break

        print(
            f"REA PAGE {page}: {len(listings)} listings"
        )

        all_listings.extend(listings)

        page += 1

    print(
        "REA TOTAL LISTINGS:",
        len(all_listings)
    )

    return all_listings

def fetch_housing_listings():

    listings = []

    query = """
    query(
      $pageInfo: PageInfoInput
      $city: CityInput
      $hash: String!
      $service: String!
      $category: String!
    ) {
      searchResults(
        hash: $hash
        service: $service
        category: $category
        city: $city
        pageInfo: $pageInfo
      ) {
        properties {

          listingId

          title

          propertyType

          coords

          displayPrice {
            displayValue
          }

          propertyInformation

          description {
            overviewDescription
          } 

          details {

            overviewPoints {
                label
                description
            }
        
            amenities {
                type
                data
            }
          }
        }
      }
    }
    """

    page = 1
    MAX_HOUSING_PAGES = 10
    
    seen_housing_ids = set()
    
    while page <= MAX_HOUSING_PAGES:

        print("HOUSING PAGE:", page)

        response = requests.post(

            HOUSING_GRAPHQL_URL,

            json={

                "query": query,

                "variables": {

                    "hash": "P54p7jy36ukewjpga",

                    "service": "buy",

                    "category": "residential",

                    "city": {

                        "name": "Dubai",

                        "id": "d53c5c7632ac07b8cf84",

                        "cityId": "b8cc6e243a6a58a45f9a"
                    },

                    "pageInfo": {

                        "page": page,

                        "size": 30
                    }
                }
            },

            timeout=60
        )

        print("STATUS:", response.status_code)
        
        response.raise_for_status()
        
        data = response.json()

        properties = (

            data["data"]
            ["searchResults"]
            ["properties"]
        )

        print(
            f"HOUSING PAGE {page}: "
            f"{len(properties)} properties"
        )

        listing_ids = {
            p.get("listingId")
            for p in properties
        }
        
        print(
            f"UNIQUE IDS THIS PAGE: "
            f"{len(listing_ids)}"
        )
        
        new_ids = (
            listing_ids
            - seen_housing_ids
        )
        
        print(
            f"NEW IDS THIS PAGE: "
            f"{len(new_ids)}"
        )
        
        # STOP IF PAGE IS A DUPLICATE
        if page > 1 and len(new_ids) == 0:
        
            print(
                "HOUSING STOPPED: duplicate pages detected"
            )
        
            break
        
        seen_housing_ids.update(
            listing_ids
        )

        print(
            "HOUSING LISTINGS:",
            len(properties)
        )

        if not properties:
            break

        listings.extend(properties)

        if len(properties) < 30:
            break

        page += 1

        time.sleep(1)

        if page > MAX_HOUSING_PAGES:
            print(
                f"HOUSING STOPPED: reached MAX_HOUSING_PAGES={MAX_HOUSING_PAGES}"
            )

    return listings

properties = []
rent_properties = []

for SCRAPE_MODE in SCRAPE_MODES:

    print(
        f"RUNNING MODE: {SCRAPE_MODE}"
    )

    seen_urls = set()
    potential_duplicates = []

    timer_start("DUBIZZLE")

    dubizzle_hits = fetch_dubizzle_algolia()

    timer_end("DUBIZZLE")

    timer_start("REA")

    rak_hits = fetch_dubizzle_rak()

    timer_end("REA")

    timer_start("ABU DHABI DUBIZZLE")

    abu_hits = fetch_dubizzle_abudhabi()
    
    timer_end("ABU DHABI DUBIZZLE")

    timer_start("ALAIN")

    alain_hits = fetch_dubizzle_alain()

    timer_end("ALAIN")

    timer_start("FUJAIRAH")

    fujairah_hits = fetch_dubizzle_fujairah()

    timer_end("FUJAIRAH")

    timer_start("UAQ DUBIZZLE")

    uaq_hits = fetch_dubizzle_uaq()

    timer_end("UAQ DUBIZZLE")

    timer_start("SHARJAH DUBIZZLE")

    sharjah_hits = fetch_dubizzle_sharjah()

    timer_end("SHARJAH DUBIZZLE")

    timer_start("AJMAN")

    ajman_hits = fetch_dubizzle_ajman()

    timer_end("AJMAN")

    print("RAW DUBIZZLE HITS:", len(dubizzle_hits))
    print("RAW RAK HITS:", len(rak_hits))
    print("RAW ABU DHABI HITS:", len(abu_hits))
    print("RAW AL AIN HITS:", len(alain_hits))
    print("RAW FUJAIRAH HITS:", len(fujairah_hits))
    print("RAW UAQ HITS:", len(uaq_hits))
    print("RAW SHARJAH HITS:", len(sharjah_hits))
    print("RAW AJMAN HITS:", len(ajman_hits))

    dubizzle_hits.extend(rak_hits)
    dubizzle_hits.extend(abu_hits)
    dubizzle_hits.extend(alain_hits)
    dubizzle_hits.extend(fujairah_hits)
    dubizzle_hits.extend(uaq_hits)
    dubizzle_hits.extend(sharjah_hits)
    dubizzle_hits.extend(ajman_hits)

    if SCRAPE_MODE == "sale":

        rea_hits = fetch_rea_listings()

        housing_hits = fetch_housing_listings()

    else:

        rea_hits = []
        housing_hits = []

    print(
        "TOTAL HOUSING LISTINGS:",
        len(housing_hits)
    )
    
    print(
        "TOTAL DUBIZZLE LISTINGS:",
        len(dubizzle_hits)
    )



    # =========================================
    # DUBIZZLE PARSER
    # =========================================
    
    for hit in dubizzle_hits:
    
        try:
    
            price = hit.get("price")
    
            sqft = hit.get("size")
    
            if not price or not sqft:
                continue
    
            bedrooms = hit.get(
                "bedrooms",
                0
            )
    
            bathrooms = hit.get(
                "bathrooms"
            )
    
            geo = hit.get(
                "_geoloc",
                {}
            )
    
            lat = geo.get("lng")
            lng = geo.get("lat")
    
            city = hit.get("city", {})
            city_id = city.get("id")
            
            EMIRATE_MAP = {
                3: "Abu Dhabi",
                11: "Ras Al Khaimah",
                12: "Sharjah",
                13: "Fujairah",
                14: "Ajman",
                15: "Umm Al Quwain",
                39: "Al Ain"
            }
            
            emirate = EMIRATE_MAP.get(
                city_id,
                "Dubai"
            )
    
    
            title = (
                hit.get("name", {})
                .get("en", "")
            )
    
    
            property_url = (
                hit.get(
                    "absolute_url",
                    {}
                )
                .get("en")
            )
    
            if not property_url:
                continue
    
            if property_url in seen_urls:
                continue
    
            seen_urls.add(property_url)
    
            raw_area = ""
    
            neighborhoods = hit.get(
                "neighborhoods",
                {}
            )
    
            names = neighborhoods.get(
                "name",
                {}
            )
    
            if names.get("en"):
    
                raw_area = names["en"][0]
    
    
            area_info = get_area_assignment(
                lat,
                lng,
                raw_area
            )
    
            area = (
                area_info[
                    "comparable_area"
                ]
            )
    
            heatmap_area = (
                area_info[
                    "heatmap_area"
                ]
            )
    
            if is_duplicate_property(
                lat,
                lng,
                price,
                sqft,
                bedrooms
            ):
                continue
    
            building = hit.get(
                "building"
            )
    
            tower_name = "Unknown"
    
            if building:
    
                tower_name = (
                    building.get(
                        "name",
                        {}
                    )
                    .get("en", "Unknown")
                )
    
            developer_name = (
                hit.get("project_developer_name", {}).get("en")
                if isinstance(
                    hit.get("project_developer_name"),
                    dict
                )
                else hit.get("project_developer_name")
            )
    
            property_type = "apartment"
            property_age = 0
            
            for item in hit.get("property_info", []):
            
                if not isinstance(item, dict):
                    continue
            
                item_id = item.get("id")
            
                # PROPERTY TYPE
                if item_id == "property_type":
            
                    value = item.get("value")
            
                    if isinstance(value, dict):
            
                        property_type = normalize_property_type(
                            value.get("en", "apartment")
                        )
            
                # PROPERTY AGE
                elif item_id == "property_age":
            
                    value = item.get("value", {})
            
                    if isinstance(value, dict):
            
                        age_text = value.get("en", "")
            
                        match = re.search(r"(\d+)", age_text)
            
                        if match:
                            property_age = int(match.group(1))
            
            url_lower = property_url.lower()
            title_lower = title.lower()
            
            if property_type == "apartment":
            
                if "villa" in url_lower or "villa" in title_lower:
                    property_type = "villa"
            
                elif "townhouse" in url_lower or "townhouse" in title_lower:
                    property_type = "townhouse"
            
                elif "penthouse" in url_lower or "penthouse" in title_lower:
                    property_type = "penthouse"
    
            record = {
    
                "source": "dubizzle",
    
                "emirate": emirate,
    
                "title": title,
    
                "price": float(price),
    
                "currency": "AED",
    
                "developer_name": developer_name,
    
                "property_age": property_age,
    
                "area": area,
    
                "heatmap_area":
                heatmap_area,
    
                "raw_area":
                raw_area,
    
                "lat": lat,
    
                "lng": lng,
    
                "sqft": float(sqft),
    
                "bedrooms": bedrooms,
    
                "bathrooms": bathrooms,
    
                "property_type":
                property_type,

                "property_type_display": property_type_display(property_type),
    
                "url":
                property_url,
    
                "description":
                hit.get(
                    "description",
                    {}
                ).get(
                    "en",
                    ""
                ),
    
                "tower_name":
                tower_name,
    
                "amenities": normalize_amenities([
                    amenity.get("en")
                    for amenity in hit.get("amenities_v2", [])
                    if amenity.get("en")
                ]),
    
                "completion_status":
                hit.get(
                    "completion_status",
                    "unknown"
                ),
    
                "furnished_status":
                str(
                    hit.get(
                        "furnished",
                        ""
                    )
                ),
    
                "is_verified":
                hit.get(
                    "is_verified",
                    False
                ),
    
                "layout_type":
                "standard",
    
                "quality_tier":
                "standard"
            }
    
            if SCRAPE_MODE == "rent":
        
                rent_properties.append(record)
            
            else:
            
                properties.append(record)
    
        except Exception as e:
    
            print(
                "DUBIZZLE PARSE ERROR:",
                e
            )
    
    # =========================================
    # REA PARSER
    # =========================================
    
    for listing in rea_hits:
    
        try:
    
            bedrooms = listing.get(
                "bedrooms",
                0
            )
    
            bathrooms = listing.get(
                "bathrooms"
            )
    
            description = listing.get(
                "description",
                ""
            )
    
            raw_area = listing.get(
                "displayAddress",
                "Unknown"
            )
    
            geo = listing.get(
                "geoLocation"
            ) or {}
    
            lat = geo.get("latitude")
            lng = geo.get("longitude")
    
            # Remove REA generic Dubai coordinates completely
            if (
                lat is not None
                and lng is not None
                and abs(float(lat) - 25.204849) < 0.0001
                and abs(float(lng) - 55.270783) < 0.0001
            ):
                continue
    
            area_info = get_area_assignment(
                lat,
                lng,
                raw_area
            )
    
            area = area_info[
                "comparable_area"
            ]
    
            heatmap_area = area_info[
                "heatmap_area"
            ]
    
            price_obj = listing.get(
                "price"
            ) or {}
    
            display_price = (
                price_obj.get(
                    "displayConsumerPrice",
                    ""
                )
            )
    
            digits = re.sub(
                r"[^\d.]",
                "",
                display_price
            )
    
            if not digits:
                continue
    
            price = float(digits)
    
            sqm = listing.get(
                "buildingSize"
            )
    
            try:
                sqm = float(sqm)
                sqft = sqm * 10.7639
            except:
                continue
    
            property_url = (
                "https://www.rea.global"
                + listing.get(
                    "detailPageUrl",
                    ""
                )
            )
    
            if property_url in seen_urls:
                continue
    
            seen_urls.add(property_url)
    
            property_types = listing.get(
                "propertyTypes",
                []
            )
    
            property_type = "apartment"
    
            if property_types:
    
                property_type = normalize_property_type(
                    property_types[0]
                )
    
            if is_duplicate_property(
                lat,
                lng,
                price,
                sqft,
                bedrooms
            ):
                continue
    
            properties.append({
    
                "source": "rea",
    
                "emirate": "Dubai",
    
                "title": raw_area,
    
                "price": price,
    
                "currency": "AED",
    
                "area": area,
    
                "heatmap_area": heatmap_area,
    
                "raw_area": raw_area,
    
                "lat": lat,
    
                "lng": lng,
    
                "sqft": sqft,
    
                "bedrooms": bedrooms,
    
                "bathrooms": bathrooms,
    
                "property_type": property_type,

                "property_type_display": property_type_display(property_type),
    
                "url": property_url,
    
                "description": description,
    
                "tower_name": None,
    
                "amenities": [],
    
                "completion_status": (
                    "off_plan"
                    if listing.get(
                        "completionDate"
                    )
                    else "ready"
                ),
    
                "furnished_status": "UNKNOWN",
    
                "is_verified": False,
    
                "layout_type": "standard",
    
                "quality_tier": "standard"
            })
    
        except Exception as e:
    
            print(
                "REA PARSE ERROR:",
                e
            )
    
    # =========================================
    # HOUSING PARSER
    # =========================================
    
    for listing in housing_hits:
    
        try:
    
            info = listing.get(
                "propertyInformation",
                {}
            )
    
            title = listing.get(
                "title",
                "Unknown"
            )
    
            bedrooms = info.get(
                "bedrooms",
                0
            )
    
            bathrooms = info.get(
                "bathrooms"
            )
    
            area_text = info.get(
                "area",
                ""
            )
    
            sqft_match = re.search(
                r"([\d,.]+)",
                area_text
            )
    
            if not sqft_match:
                continue
    
            sqft = float(
    
                sqft_match.group(1)
                .replace(",", "")
            )
    
            price_text = info.get(
                "price"
            )
    
            if not price_text:
                continue
    
            price = normalize_price_to_aed(
    
                parse_housing_price(
                    price_text
                ),
    
                "INR"
            )
    
            coords = listing.get(
                "coords",
                []
            )
    
            lat = None
            lng = None
    
            if len(coords) == 2:
    
                lat = float(coords[0])
    
                lng = float(coords[1])
    
            description = (
    
                listing.get(
                    "description",
                    {}
                )
                .get(
                    "overviewDescription",
                    ""
                )
            )
    
            raw_area = ""
    
            overview_points = (
                listing.get(
                    "details",
                    {}
                )
                .get(
                    "overviewPoints"
                )
                or []
            )
            
            for point in overview_points:
            
                label = str(
                    point.get(
                        "label",
                        ""
                    )
                ).lower()
            
                value = str(
                    point.get(
                        "description",
                        ""
                    )
                ).strip()
            
                if (
                    "locality" in label
                    or "location" in label
                    or "area" in label
                    or "community" in label
                ):
            
                    raw_area = value
                    break
    
            if not raw_area:
    
                known_areas = [
            
                    "Dubai Marina",
                    "Business Bay",
                    "Downtown Dubai",
                    "Jumeirah Village Circle",
                    "JVC",
                    "Dubai Hills",
                    "DIFC",
                    "City Walk",
                    "Jumeirah Lake Towers",
                    "JLT",
                    "Palm Jumeirah"
                ]
            
                title_lower = title.lower()
            
                for area_name in known_areas:
            
                    if area_name.lower() in title_lower:
            
                        raw_area = area_name
                        break
            
            
            if not raw_area:
            
                raw_area = "Dubai"
    
            amenities = []
    
            for group in (
                listing.get(
                    "details",
                    {}
                )
                .get(
                    "amenities",
                    []
                )
            ):
    
                amenities.extend(
    
                    group.get(
                        "data",
                        []
                    )
                )
    
            area_info = get_area_assignment(
    
                lat,
                lng,
                raw_area
            )
    
            area = area_info[
                "comparable_area"
            ]
    
            heatmap_area = area_info[
                "heatmap_area"
            ]
    
            property_type = normalize_property_type(
    
                "apartment",
    
                title=title,
    
                description=description
            )
    
            if is_duplicate_property(
    
                lat,
                lng,
                price,
                sqft,
                bedrooms
            ):
                continue
    
            properties.append({
    
                "source": "housing",
    
                "emirate": "Dubai",
    
                "title": title,
    
                "price": price,
    
                "currency": "AED",
    
                "original_price": (
                    parse_housing_price(
                        price_text
                    )
                ),
    
                "original_currency": "INR",
    
                "area": area,
    
                "heatmap_area": heatmap_area,
    
                "raw_area": raw_area,
    
                "lat": lat,
    
                "lng": lng,
    
                "sqft": sqft,
    
                "bedrooms": bedrooms,
    
                "bathrooms": bathrooms,
    
                "property_type": property_type,

                "property_type_display": property_type_display(property_type),
    
                "url": (
                    "https://housing.com/in/buy/resale/page/"
                    + str(
                        listing["listingId"]
                    )
                ),
    
                "description": description,
    
                "tower_name": None,
    
                "amenities": normalize_amenities(
                    amenities
                ),
    
                "completion_status": "ready",
    
                "furnished_status": "UNKNOWN",
    
                "is_verified": False,
    
                "layout_type": "standard",
    
                "quality_tier": "standard"
            })
    
        except Exception as e:
    
            import traceback
        
            print(
                "HOUSING PARSE ERROR:",
                e
            )
        
            print(
                "FAILED LISTING ID:",
                listing.get("listingId")
            )
        
            traceback.print_exc()

    if SCRAPE_MODE == "sale":
        
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
        
                        amenities = []
        
                        for detail_script in detail_scripts:
        
                            try:
        
                                if not detail_script.string:
                                    continue
        
                                detail_data = json.loads(
                                    detail_script.string
                                )
                                
                                # =====================================
                                # HANDLE mainEntity
                                # =====================================
                                
                                if (
                                    isinstance(detail_data, dict)
                                    and "mainEntity" in detail_data
                                ):
                                
                                    detail_data = detail_data["mainEntity"]
                                
                                # =====================================
                                # HANDLE ARRAY JSON-LD
                                # =====================================
                                
                                if isinstance(detail_data, list):
                                
                                    for item_data in detail_data:
                                
                                        item_type = item_data.get("@type")
                                
                                        if isinstance(item_type, list):
                                
                                            if "RealEstateListing" in item_type:
                                
                                                detail_data = item_data
                                                break
                                
                                        elif item_type == "RealEstateListing":
                                
                                            detail_data = item_data
                                            break
        
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
        
                                # NEW FIX
                                if not detail_data.get("additionalProperty"):
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
                                # =====================================
                                # AMENITIES
                                # =====================================
                                
                                features = detail_data.get(
                                    "amenityFeature",
                                    []
                                )
                                
                                amenities = normalize_amenities(
        
                                    extract_amenities(features)
                                )
                                property_type = "other"
        
                                description = detail_data.get(
                                    "description",
                                    ""
                                )
        
                                developer_name = None
        
                                if "damac maison" in description.lower():
                                    developer_name = "DAMAC"
                                
                                elif "emaar" in description.lower():
                                    developer_name = "EMAAR"
                                
                                else:
                                    developer_name = extract_developer_name(
                                        description
                                    )
        
        
                                completion_status = detect_completion_status(
                                    description
                                )
        
                                additional_properties = detail_data.get(
                                    "additionalProperty",
                                    []
                                )
                                
                                # normalize into list
                                if isinstance(additional_properties, dict):
                                    additional_properties = [additional_properties]
                                
                                for prop in additional_properties:
                                
                                    if not isinstance(prop, dict):
                                        continue
                                
                                    # CASE 1
                                    if prop.get("name") == "Property Type":
                                
                                        property_type = normalize_property_type(
                                            prop.get("value", "other"),
                                            title=title,
                                            description=description
                                        )
                                
                                        break
                                
                                    # CASE 2 (bhomes weird schema)
                                    elif (
                                        prop.get("@type") == "PropertyValue"
                                        and prop.get("name")
                                    ):
                                
                                        property_type = normalize_property_type(
                                            prop.get("name"),
                                            title=title,
                                            description=description
                                        )
        
        
                                location = detail_data.get(
                                    "location",
                                    {}
                                )
        
                                raw_area = location.get("name")
                                address = location.get(
                                    "address",
                                    {}
                                )
        
                                street_address = (
                                    address.get("streetAddress")
                                    or address.get("addressRegion")
                                    or address.get("addressLocality")
                                    or ""
                                )
                                
                                addressRegion = address.get(
                                    "addressRegion",
                                    ""
                                )
                                
                                tower_name = "Unknown"
        
                                # 1. Best source
                                if street_address:
                                
                                    tower_name = (
                                        street_address
                                        .split(",")[0]
                                        .strip()
                                    )
                                
                                # 2. Fallback
                                elif location.get("name"):
                                
                                    tower_name = (
                                        location.get("name")
                                        .strip()
                                    )
                                
                                # 3. Last fallback: description
                                else:
                                
                                    tower_patterns = [
                                
                                        r"located in ([A-Z][A-Za-z0-9&\-\(\) ]+)",
                                
                                        r"in ([A-Z][A-Za-z0-9&\-\(\) ]+)",
                                
                                        r"at ([A-Z][A-Za-z0-9&\-\(\) ]+)"
                                    ]
                                
                                    for pattern in tower_patterns:
                                
                                        match = re.search(
                                            pattern,
                                            description
                                        )
                                
                                        if match:
                                
                                            tower_name = (
                                                match.group(1)
                                                .strip()
                                            )
                                
                                            break
        
                                area_info = get_area_assignment(
                                    lat,
                                    lng,
                                    raw_area
                                )
                                
                                area = area_info["comparable_area"]
                                
                                heatmap_area = area_info["heatmap_area"]
        
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
        
                                is_verified = True
        
        
                                seen_urls.add(property_url)
        
                                desc_lower = description.lower()
                                    
                                if "unfurnished" in desc_lower:
                                    furnished_status = "NO"
                                    
                                elif "furnished" in desc_lower:
                                    furnished_status = "YES"
                                    
                                else:
                                    furnished_status = "UNKNOWN"
        
                                properties.append({
        
                                    "source": "bhomes",
        
                                    "emirate": "Dubai",
        
                                    "title": title,
        
                                    "price": price,
        
                                    "currency": currency,
        
                                    "developer_name": developer_name,
        
                                    "area": area,
        
                                    "heatmap_area": heatmap_area,
        
                                    "lat": lat,
        
                                    "lng": lng,
        
                                    "sqft": sqft,
        
                                    "bedrooms": bedrooms,
        
                                    "bathrooms": bathrooms,
        
                                    "property_type": property_type,

                                    "property_type_display": property_type_display(property_type),
        
                                    "url": property_url,
        
                                    "description": description,
        
                                    "tower_name": tower_name,
        
                                    "amenities": amenities,
        
                                    "completion_status": completion_status,
        
                                    "is_verified": is_verified,
                                    
                                    "furnished_status": furnished_status,
        
                                    "layout_type": "standard",
        
                                    "quality_tier": "standard",
                                })
        
                            except Exception as e:
        
                                import traceback
        
                                print("BHOMES Detail Error:", e)
        
                                traceback.print_exc()
        
                except Exception as e:
        
                    print("BHOMES Script Error:", e)
        
        
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
        
                        area_info = get_area_assignment(
                            lat,
                            lng,
                            raw_area
                        )
                        
                        area = area_info["comparable_area"]
                        
                        heatmap_area = area_info["heatmap_area"]
        
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
        
                            "emirate": "Dubai",
        
                            "title":
                            title,
        
                            "price":
                            price,
        
                            "currency":
                            currency,
        
                            "area":
                            area,
        
                            "heatmap_area": heatmap_area,
        
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
        
                            "tower_name": (
                                location.get("name")
                            ),
                            
                            "location_type": (
                                location.get("type")
                            ),
                            
                            "community_path": (
                                location.get("path_name")
                            ),
                            
                            "completion_status": (
                                property_data.get(
                                    "completion_status"
                                )
                            ),
                            
                            "furnished_status": (
                                property_data.get(
                                    "furnished"
                                )
                            ),
                            
                            "listing_level": (
                                property_data.get(
                                    "listing_level"
                                )
                            ),
                            
                            "is_verified": (
                                property_data.get(
                                    "is_verified"
                                )
                            ),
                            
                            "is_new_construction": (
                                property_data.get(
                                    "is_new_construction"
                                )
                            ),
                        
                            
                            "amenities": normalize_amenities(
                            
                                property_data.get(
                                    "amenity_names",
                                    []
                                )
                            ),
        
                            "layout_type": "standard",
        
                            "quality_tier": "standard",
                        })
        
                    except Exception as e:
        
                        import traceback
        
                        print(
                            "PROPERTYFINDER Listing Error:",
                            e
                        )
        
                        traceback.print_exc()
        
            except Exception as e:
        
                print(
                    "PROPERTYFINDER NEXT_DATA Error:",
                    e
                )
        
        # =========================================
        # 99ACRES PARSER
        # =========================================
        
        for source_data in all_soups:
        
            if source_data["source"] != "99acres":
                continue
        
            soup = source_data["soup"]
        
            try:
        
                scripts = soup.find_all("script")
        
                json_text = None
        
                for script in scripts:
        
                    text = script.string
        
                    if not text:
                        continue
        
                    if "window.__initialData__" in text:
        
                        match = re.search(
                            r'window\.__initialData__\s*=\s*({.*?});',
                            text,
                            re.DOTALL
                        )
        
                        if match:
                            json_text = match.group(1)
                            break
        
                if not json_text:
                    print("99ACRES: __initialData__ NOT FOUND")
                    continue
        
        
                data = json.loads(json_text)
        
                properties_data = (
                    data
                    .get("srp", {})
                    .get("pageData", {})
                    .get("properties", [])
                )
        
                count = len(properties_data)
        
                print(
                    "99ACRES PROPERTY COUNT:",
                    count
                )
                
                if count == 0:
                
                    print(
                        "99ACRES PAGE DATA KEYS:",
                        list(
                            data
                            .get("srp", {})
                            .get("pageData", {})
                            .keys()
                        )
                    )
        
                for prop in properties_data:
        
                    property_type_raw = prop.get(
                        "PROPERTY_TYPE",
                        ""
                    )
                    
                    if property_type_raw != "Residential Apartment":
                        continue
        
                    try:
        
                        property_url = (
                            "https://www.99acres.com/"
                            + prop.get(
                                "PROP_DETAILS_URL",
                                ""
                            )
                        )
        
                        if not property_url:
                            continue
        
                        if property_url in seen_urls:
                            continue
        
                        seen_urls.add(property_url)
        
                        title = prop.get(
                            "PROP_HEADING",
                            "Unknown"
                        )
        
                        try:
        
                            original_price = float(
                                prop.get(
                                    "MIN_PRICE",
                                    0
                                )
                            )
        
                        except:
                            continue
        
                        price = normalize_price_to_aed(
                            original_price,
                            "INR"
                        )
                        
                        currency = "AED"
                        
                        if not price or price <= 0:
                            continue
                        
                        try:
                        
                            sqft = float(
                                prop.get(
                                    "CARPET_AREA",
                                    0
                                )
                            )
                        
                            if sqft <= 0:
                                continue
                        
                        except:
                            continue
        
                        try:
        
                            bedrooms = int(
                                prop.get(
                                    "BEDROOM_NUM",
                                    0
                                )
                            )
        
                        except:
                            bedrooms = 0
        
                        try:
        
                            bathrooms = int(
                                prop.get(
                                    "BATHROOM_NUM",
                                    0
                                )
                            )
        
                        except:
                            bathrooms = None
        
                        map_details = prop.get(
                            "MAP_DETAILS",
                            {}
                        )
        
                        try:
        
                            lat = float(
                                map_details.get("LATITUDE")
                            )
                            
                            lng = float(
                                map_details.get("LONGITUDE")
                            )
                            
                            # 99acres sometimes swaps them
                            if lat > 40:
                                lat, lng = lng, lat
        
                        except:
        
                            lat = None
                            lng = None
        
                        raw_area = prop.get(
                            "LOCALITY",
                            "Unknown"
                        )
        
                        area_info = get_area_assignment(
                            lat,
                            lng,
                            raw_area
                        )
        
                        area = area_info[
                            "comparable_area"
                        ]
        
                        heatmap_area = area_info[
                            "heatmap_area"
                        ]
        
                        description = prop.get(
                            "DESCRIPTION",
                            ""
                        )
        
                        tower_name = prop.get(
                            "BUILDING_NAME",
                            "Unknown"
                        )
        
                        amenities = normalize_amenities(
                            prop.get(
                                "TOP_USPS",
                                []
                            )
                        )
        
                        furnished_status = "UNKNOWN"
        
                        furnish_value = str(
                            prop.get(
                                "FURNISH",
                                ""
                            )
                        )
        
                        if furnish_value == "1":
                            furnished_status = "YES"
        
                        elif furnish_value == "4":
                            furnished_status = "PARTIAL"
        
                        completion_status = "unknown"
        
                        secondary_tags = prop.get(
                            "SECONDARY_TAGS",
                            []
                        )
        
                        if (
                            "Ready To Move"
                            in secondary_tags
                        ):
                            completion_status = "ready"
        
                        elif (
                            "Under Construction"
                            in secondary_tags
                        ):
                            completion_status = "off_plan"
        
                        property_type = normalize_property_type(
                            "apartment",
                            title=title,
                            description=description
                        )
        
                        if is_duplicate_property(
                            lat,
                            lng,
                            price,
                            sqft,
                            bedrooms
                        ):
                            continue
        
                        print(
                            "ADDING 99ACRES:",
                            title,
                            area,
                            bedrooms,
                            sqft,
                            price
                        )
        
                        properties.append({
        
                            "source": "99acres",
        
                            "emirate": "Dubai",
        
                            "title": title,
        
                            "price": price,
        
                            "currency": "AED",
        
                            "original_price":
                            original_price,
        
                            "original_currency":
                            "INR",
        
                            "area": area,
        
                            "heatmap_area":
                            heatmap_area,
        
                            "raw_area":
                            raw_area,
        
                            "lat": lat,
        
                            "lng": lng,
        
                            "sqft": sqft,
        
                            "bedrooms": bedrooms,
        
                            "bathrooms": bathrooms,
        
                            "property_type":
                            property_type,
        
                            "url": property_url,
        
                            "description":
                            description,
        
                            "tower_name":
                            tower_name,
        
                            "amenities":
                            amenities,
        
                            "completion_status":
                            completion_status,
        
                            "furnished_status":
                            furnished_status,
        
                            "is_verified":
                            False,
        
                            "layout_type":
                            "standard",
        
                            "quality_tier":
                            "standard"
                        })
        
                    except Exception as e:
        
                        print(
                            "99ACRES LISTING ERROR:",
                            e
                        )
        
            except Exception as e:
        
                print(
                    "99ACRES PARSER ERROR:",
                    e
                )
        
        count_99 = sum(
            1
            for p in properties
            if p["source"] == "99acres"
        )
        
        print("99ACRES SAVED:", count_99)

# =========================================
# INVESTOR VERIFICATION LINKS
# =========================================

for property in properties:

    emirate = property.get(
        "emirate",
        "Dubai"
    )

    if emirate == "Dubai":

        property["verify_before_buying"] = {
            "source": "DLD",
            "url": "https://dubailand.gov.ae/en/#/",
            "message": (
                "Verify ownership records, transaction history "
                "and project details through DLD before purchase."
            )
        }

    elif emirate == "Ras Al Khaimah":

        property["verify_before_buying"] = {
            "source": "RAK Municipality",
            "url": "https://mun.rak.ae/",
            "message": (
                "Verify ownership records and project details "
                "through Ras Al Khaimah authorities before purchase."
            )
        }

    elif emirate == "Abu Dhabi":

        property["verify_before_buying"] = {
            "source": "DARI",
            "url": "https://dari.ae/",
            "message": (
                "Verify ownership records, transaction history "
                "and project details through Abu Dhabi authorities "
                "before purchase."
            )
        }

    elif emirate == "Sharjah":

        property["verify_before_buying"] = {
            "source": "Sharjah Real Estate Registration Department",
            "url": "https://www.shjrerd.gov.ae/",
            "message": (
                "Verify ownership records and project details "
                "through Sharjah authorities before purchase."
            )
        }

    elif emirate == "Al Ain":

        property["verify_before_buying"] = {
            "source": "DARI",
            "url": "https://dari.ae/",
            "message": (
                "Verify ownership records, transaction history "
                "and project details through Abu Dhabi authorities "
                "before purchase."
            )
        }
    
    elif emirate == "Fujairah":
    
        property["verify_before_buying"] = {
            "source": "Fujairah Municipality",
            "url": "https://www.fujmun.gov.ae/",
            "message": (
                "Verify ownership records and project details "
                "through Fujairah authorities before purchase."
            )
        }
    
    elif emirate == "Umm Al Quwain":
    
        property["verify_before_buying"] = {
            "source": "UAQ Municipality",
            "url": "https://uaq.ae/",
            "message": (
                "Verify ownership records and project details "
                "through Umm Al Quwain authorities before purchase."
            )
        }

    elif emirate == "Ajman":

        property["verify_before_buying"] = {
            "source": "Ajman Municipality & Planning Department",
            "url": "https://www.am.gov.ae/",
            "message": (
                "Verify ownership records and project details "
                "through Ajman authorities before purchase."
            )
        }
            
if SCRAPE_MODE == "sale":

    with open(
        "properties.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            properties,
            f,
            ensure_ascii=False,
            indent=2
        )

else:

    with open(
        "rent_properties.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            rent_properties,
            f,
            ensure_ascii=False,
            indent=2
        )

print(f"Saved {len(properties)} properties.")


# =========================================
# AI LAYOUT AUDIT
# =========================================
# =====================================
# PRE-CLASSIFY QUALITY TIERS
# =====================================

for property in properties:

    property["quality_tier"] = (
        detect_quality_tier(property)
    )
    
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

    if "price_per_sqft" not in property:
        continue
    
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

suspicious_properties = []

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

    needs_ai = (

    abs(deviation) >= 0.40

        or property["quality_tier"] == "premium"
    
        or property["quality_tier"] == "ultra_luxury"
    )
    
    if needs_ai:

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
            ai_audits_queued += 1
            continue 

        
        cache_key = property["url"]
        
        if cache_key in ai_cache:
        
            property["layout_type"] = (
        
                ai_cache[
                    cache_key
                ].get(
                    "layout_type",
                    "standard"
                )
            )

            property["quality_tier"] = (

                ai_cache[
                    cache_key
                ].get(
                    "quality_tier",
                    "standard"
                )
            )
        
            ai_cache_hits += 1
        
        else:
        
            suspicious_properties.append(
                property
            )

# =====================================
# LIMIT NEW AI AUDITS PER RUN
# =====================================

MAX_LAYOUT_AI = 10

suspicious_properties = (
    suspicious_properties[:MAX_LAYOUT_AI]
)

print(
    "NEW AI AUDITS THIS RUN:",
    len(suspicious_properties)
)

# =====================================
# BATCH GEMINI LAYOUT ANALYSIS
# =====================================

if suspicious_properties:

    print(
        "RUNNING BATCH LAYOUT ANALYSIS:",
        len(suspicious_properties)
    )

    batch_results = (
        batch_detect_layout_types(
            suspicious_properties
        )
    )

    for property in suspicious_properties:

        result = batch_results.get(
            property["url"]
        )
    
        if not result:
    
            print(
                "NO GEMINI RESULT:",
                property["url"]
            )
    
            continue
    
        layout_type = result.get(
            "layout_type",
            "standard"
        )
    
        quality_tier = result.get(
            "quality_tier",
            "standard"
        )
    
        property["layout_type"] = layout_type
    
        existing_tier = property["quality_tier"]
    
        tiers = {
            "standard": 0,
            "premium": 1,
            "ultra_luxury": 2
        }
    
        if tiers.get(quality_tier, 0) > tiers.get(existing_tier, 0):
    
            property["quality_tier"] = quality_tier
    
        ai_cache[property["url"]] = {
    
            "layout_type": layout_type,
    
            "quality_tier": quality_tier
        }


last_updated = datetime.now(timezone.utc).isoformat()

# =========================================
# PROFESSIONAL MARKET SEGMENT ENGINE
# =========================================

market_groups = {}

# heatmap uses larger parent polygons
heatmap_groups = {}

for property in properties:

    # =====================================
    # DATA QUALITY FILTERS
    # =====================================

    if property.get("area") == "Dubai, Dubai, Dubai":
        continue

    try:
        bedrooms = int(property.get("bedrooms", 0))
        sqft = float(property.get("sqft", 0))
    except:
        continue

    # impossible unit sizes

    if bedrooms == 1 and sqft > 2500:
        continue

    if bedrooms <= 2 and bedrooms > 0 and sqft > 3500:
        continue

    if bedrooms > 0 and bedrooms <= 2 and sqft > 3500:
        continue

    try:
        ppsf = property["price"] / sqft
    except:
        continue

    # obvious bad data

    if ppsf < 200:
        continue

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

    quality_tier = property.get(

        "quality_tier",
    
        "standard"
    )

    
    market_key = (
        area,
        property_type,
        bedrooms,
        layout_type,
        quality_tier
    )

    heatmap_key = (
        property["heatmap_area"],
        property_type,
        bedrooms,
        layout_type,
        quality_tier
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

    if heatmap_key not in heatmap_groups:
    
        heatmap_groups[heatmap_key] = {
            "prices": [],
            "listings": [],
            "lat": property["lat"],
            "lng": property["lng"]
        }
    
    heatmap_groups[heatmap_key]["prices"].append(
        price_per_sqft
    )
    
    heatmap_groups[heatmap_key]["listings"].append(
        property
    )

def split_market_clusters(prices, listings):

    if len(prices) <= 2:
        return [(prices, listings)]

    prices = sorted(prices)

    market_median = median(prices)

    q1 = prices[len(prices) // 4]

    q3 = prices[(len(prices) * 3) // 4]

    iqr = q3 - q1

    relative_iqr = iqr / market_median

    largest_gap = 0

    split_index = None
    
    for i in range(len(prices) - 1):
    
        gap = prices[i + 1] - prices[i]
    
        if gap > largest_gap:
    
            largest_gap = gap
    
            split_index = i

    relative_gap = largest_gap / market_median

    if (
        relative_iqr <= 0.30
        and
        relative_gap <= 0.30
    ):

        return [(prices, listings)]

    if split_index is None:
        return [(prices, listings)]

    lower_prices = prices[:split_index + 1]

    upper_prices = prices[split_index + 1:]

    lower_counter = Counter(lower_prices)

    lower_listings = []

    upper_listings = []

    lower_used = 0

    for listing in listings:

        ppsf = (
            listing["price"]
            / float(listing["sqft"])
        )

        if lower_counter[ppsf] > 0:

            lower_listings.append(listing)
        
            lower_counter[ppsf] -= 1

        else:

            upper_listings.append(listing)

    results = []

    if len(lower_prices) >= 5:
    
        results.extend(
    
            split_market_clusters(
                lower_prices,
                lower_listings
            )
    
        )
    
    if len(upper_prices) >= 5:
    
        results.extend(
    
            split_market_clusters(
                upper_prices,
                upper_listings
            )
    
        )
    
    return results

print("MARKET GROUPS CREATED:", len(market_groups))
print("HEATMAP GROUPS CREATED:", len(heatmap_groups))

def tighten_cluster(
    prices,
    listings,
    threshold=0.35,
    min_size=5
):

    prices = sorted(prices)

    listing_pairs = []

    for listing in listings:

        try:

            ppsf = (
                listing["price"]
                / float(listing["sqft"])
            )

            listing_pairs.append(
                (ppsf, listing)
            )

        except:
            continue

    listing_pairs.sort(
        key=lambda x: x[0]
    )

    while len(listing_pairs) >= min_size:

        current_prices = [
            p[0]
            for p in listing_pairs
        ]

        market_median = median(
            current_prices
        )

        min_price = current_prices[0]

        max_price = current_prices[-1]

        low_distance = (
            market_median - min_price
        ) / market_median

        high_distance = (
            max_price - market_median
        ) / market_median

        if (
            low_distance <= threshold
            and
            high_distance <= threshold
        ):
            break

        if low_distance > high_distance:

            listing_pairs.pop(0)

        else:

            listing_pairs.pop()

    final_prices = [
        p[0]
        for p in listing_pairs
    ]

    final_listings = [
        p[1]
        for p in listing_pairs
    ]

    return (
        final_prices,
        final_listings
    )

# =====================================
# MARKET CLEANING
# =====================================

market_groups_final = {}

for market_key, data in market_groups.items():

    prices = sorted(data["prices"])

    listings = data["listings"]

    clusters = split_market_clusters(
        prices,
        listings
    )
    
    tightened_clusters = []
    
    for cluster_prices, cluster_listings in clusters:
    
        cluster_prices, cluster_listings = (
            tighten_cluster(
                cluster_prices,
                cluster_listings,
                threshold=0.4,
                min_size=5
            )
        )
    
        if len(cluster_prices) >= 5:
    
            tightened_clusters.append(
                (
                    cluster_prices,
                    cluster_listings
                )
            )
    
    for cluster_prices, cluster_listings in tightened_clusters:

        cluster_min = round(
            min(cluster_prices),
            -2
        )
        
        cluster_max = round(
            max(cluster_prices),
            -2
        )

        market_segment = (

            f"{cluster_min}-"
            f"{cluster_max} PPSF"

        )

        new_key = (

            *market_key,

            market_segment
        )

        for listing in cluster_listings:

            listing[
                "market_segment"
            ] = market_segment

        market_groups_final[new_key] = {

            "prices":
            cluster_prices,

            "listings":
            cluster_listings,

            "lat":
            data["lat"],

            "lng":
            data["lng"]
        }

market_groups = market_groups_final



# =========================================
# BUILD HEATMAP
# =========================================

heatmap = []

for market_key, data in heatmap_groups.items():

    (
        area,
        property_type,
        bedrooms,
        layout_type,
        quality_tier
    ) = market_key

    prices = data["prices"]

    # SKIP WEAK DATA
    layout_required = MIN_LAYOUT_COMPS.get(
    
        layout_type,
    
        3
    )
    
    quality_required = MIN_QUALITY_COMPS.get(
    
        quality_tier,
    
        3
    )
    
    minimum_required = max(
    
        layout_required,
    
        quality_required
    )
    
    if len(prices) < minimum_required:
    
    
        continue
    

    market_median = median(prices)

    listing_count = len(prices)

    comparable_count = len(prices)

    if comparable_count < 15:
        confidence = "Low"

    elif comparable_count < 25:
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

        "property_type_display": property_type_display(property_type),

        "layout_type": layout_type,

        "quality_tier": quality_tier,

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
print("HEATMAP GROUPS:", len(heatmap))
print("TOTAL HEATMAP MARKETS:", len(heatmap_groups))

# =====================================
# MARKET DEBUG ENGINE
# =====================================

market_debug = []

for market_key, data in market_groups.items():

    prices = sorted(data["prices"])

    sorted_prices = sorted(prices)

    q1 = sorted_prices[len(sorted_prices) // 4]

    q3 = sorted_prices[(len(sorted_prices) * 3) // 4]

    if not prices:
        continue

    (
        area,
        property_type,
        bedrooms,
        layout_type,
        quality_tier,
        market_segment
    ) = market_key

    market_median = median(prices)

    min_price = min(prices)

    max_price = max(prices)

    q1 = prices[len(prices) // 4]

    q3 = prices[(len(prices) * 3) // 4]
    
    iqr = q3 - q1
    
    lower_bound = q1 - (1.5 * iqr)
    
    upper_bound = q3 + (1.5 * iqr)

    # =====================================
    # SPREAD DETECTION
    # =====================================

    try:

        spread_percent = (
            (max_price - min_price)
            / market_median
        )

    except:

        spread_percent = 0

    low_outliers = []

    high_outliers = []

    listings_debug = []

    for listing in data["listings"]:

        try:

            sqft = float(listing["sqft"])

            ppsf = round(
                listing["price"] / sqft
            )

            if ppsf < lower_bound:

                low_outliers.append({
                    "title": listing.get("title"),
                    "ppsf": ppsf,
                    "quality_tier": listing.get("quality_tier"),
                    "layout_type": listing.get("layout_type")
                })
            
            elif ppsf > upper_bound:
            
                high_outliers.append({
                    "title": listing.get("title"),
                    "ppsf": ppsf,
                    "quality_tier": listing.get("quality_tier"),
                    "layout_type": listing.get("layout_type")
                })

        except:

            continue

        listings_debug.append({

            "title": listing.get("title"),

            "area": listing.get(
                "area"
            ),

            "tower_name": listing.get(
                "tower_name",
                ""
            ),
        
            "raw_area": listing.get(
                "raw_area",
                ""
            ),

            "lat": listing.get("lat"),

            "lng": listing.get("lng"),

            "price_per_sqft": ppsf,

            "price": round(
                listing.get("price", 0)
            ),

            "sqft": round(sqft),

            "quality_tier": listing.get(
                "quality_tier"
            ),

            "layout_type": listing.get(
                "layout_type"
            ),

            "url": listing.get("url")
        })

    listings_debug.sort(
        key=lambda x: x["price_per_sqft"]
    )

    market_debug.append({

        "market_key": {

            "area": area,

            "property_type": property_type,

            "property_type_display": property_type_display(property_type),

            "bedrooms": bedrooms,

            "layout_type": layout_type,

            "quality_tier": quality_tier,

            "market_segment": market_segment
        },

        "median_price_per_sqft": round(
            market_median
        ),

        "q1": round(q1),

        "q3": round(q3),
        
        "iqr": round(iqr),
        
        "lower_bound": round(lower_bound),
        
        "upper_bound": round(upper_bound),
        
        "low_outliers": low_outliers,
        
        "high_outliers": high_outliers,

        "listing_count": len(prices),

        "min_price_per_sqft": round(
            min_price
        ),

        "max_price_per_sqft": round(
            max_price
        ),

        "price_spread_percent": round(
            spread_percent,
            2
        ),

        "prices_sorted": [
            round(x)
            for x in prices
        ],

        "listings": listings_debug
    })

# =====================================
# SORT WORST DISTORTIONS FIRST
# =====================================

market_debug.sort(

    key=lambda x: x["price_spread_percent"],

    reverse=True
)

# =====================================
# SAVE
# =====================================

with open(

    "market_debug.json",

    "w",

    encoding="utf-8"

) as f:

    json.dump(

        market_debug,

        f,

        indent=2,

        ensure_ascii=False
    )

print("Saved market_debug.json")

with open(
    "polygon_debug.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        polygon_debug,
        f,
        indent=2,
        ensure_ascii=False
    )

matched_count = sum(
    1
    for p in polygon_debug
    if p.get("selected_area")
)

unmatched_count = len(polygon_debug) - matched_count

print(
    "\nPOLYGON MATCH SUMMARY"
)

print(
    "Matched:",
    matched_count
)

print(
    "Unmatched:",
    unmatched_count
)

failed = [
    p for p in polygon_debug
    if not p.get("selected_area")
]

print(
    "Failure rate:",
    round(
        len(failed) / max(len(polygon_debug), 1) * 100,
        1
    ),
    "%"
)

print("\nAI SUMMARY")

print(
    "AI audits queued:",
    ai_audits_queued
)

print(
    "AI cache hits:",
    ai_cache_hits
)

print("Saved polygon_debug.json")

with open(
    "runtime_debug.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        runtime_debug,
        f,
        indent=2,
        ensure_ascii=False
    )

print("Saved runtime_debug.json")

# =====================================
# RENTAL MARKET ENGINE
# =====================================

rent_market_groups = {}

for property in rent_properties:

    try:

        sqft = float(property["sqft"])

        if sqft <= 0:
            continue

    except:
        continue

    try:

        rent_per_sqft = property["price"] / sqft

    except:
        continue

    area = property["area"]

    property_type = property["property_type"]

    bedrooms = property["bedrooms"]

    market_key = (
        area,
        property_type,
        bedrooms
    )

    if market_key not in rent_market_groups:

        rent_market_groups[market_key] = []

    rent_market_groups[market_key].append(
        rent_per_sqft
    )

# =========================================
# INVESTMENT OPPORTUNITY ENGINE
# =========================================

opportunities = []

for market_key, data in market_groups.items():

    prices = data["prices"]

    (
        area,
        property_type,
        bedrooms,
        layout_type,
        quality_tier,
        market_segment
    ) = market_key

    # STRONGER DATA QUALITY
    layout_required = MIN_LAYOUT_COMPS.get(
    
        layout_type,
    
        3
    )
    
    quality_required = MIN_QUALITY_COMPS.get(
    
        quality_tier,
    
        3
    )
    
    minimum_required = max(
    
        layout_required,
    
        quality_required
    )
    
    if len(prices) < minimum_required:
    
    
        continue
    

    market_median = median(prices)

    comparable_count = len(prices)

    if comparable_count < 15:
        confidence = "Low"

    elif comparable_count < 25:
        confidence = "Medium"

    else:
        confidence = "High"

    prices = sorted(data["prices"])

    if not prices:
        continue
    
    q1 = prices[len(prices) // 4]
    q3 = prices[(len(prices) * 3) // 4]

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

        opportunity = listing.copy()

        opportunity["amenities"] = (
            opportunity.get("amenities", [])[:3]
        )

        rent_key = (

            area,
        
            property_type,
        
            bedrooms
        )
        
        median_rent_per_sqft = None
        
        gross_yield = None
        
        rental_comparable_count = 0
        
        if rent_key in rent_market_groups:
        
            rents = rent_market_groups[rent_key]
        
            rental_comparable_count = len(rents)
        
            if rental_comparable_count >= minimum_required:
        
                median_rent_per_sqft = median(rents)
        
                annual_rent = (
        
                    median_rent_per_sqft
        
                    * sqft
        
                )
        
                gross_yield = (
        
                    annual_rent
        
                    / listing["price"]
        
                ) * 100

        nearest_metro_name, nearest_metro = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "metro"
            )
        )
        
        nearest_beach_name, nearest_beach = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "beach"
            )
        )
        
        nearest_mall_name, nearest_mall = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "mall"
            )
        )
        
        nearest_school_name, nearest_school = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "school"
            )
        )

        nearest_university_name, nearest_university = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "university"
            )
        )
        
        nearest_hospital_name, nearest_hospital = (
            nearest_poi(
                listing["lat"],
                listing["lng"],
                "hospital"
            )
        )

        location_score = calculate_location_score(

            nearest_metro,
        
            nearest_mall,
        
            nearest_beach,
        
            nearest_school,

            nearest_university,
        
            nearest_hospital
        )

        opportunity.update({
        
            "price": round(listing["price"]),
        
            "sqft": round(sqft),
        
            "price_per_sqft": round(
                listing_price_per_sqft
            ),
        
            "market_median_price_per_sqft": round(
                market_median
            ),

            "market_q1": round(q1),

            "market_q3": round(q3),
        
            "comparable_count": comparable_count,

            "market_segment": listing.get(
                "market_segment"
            ),
            
            "confidence": confidence,
        
            "last_updated": last_updated,
        
            "deviation_score": round(
                deviation,
                2
            ),
        
            "color": color,

            "median_rent_per_sqft":

                round(median_rent_per_sqft, 2)
            
                if median_rent_per_sqft
            
                else None,
            
            "estimated_annual_rent":
            
                round(annual_rent)
            
                if gross_yield is not None
            
                else None,
            
            "gross_yield_percent":
            
                round(gross_yield, 2)
            
                if gross_yield is not None
            
                else None,
            
            "rental_comparable_count":
            
                rental_comparable_count,
            
            "nearest_metro":
                nearest_metro_name,
            
            "nearest_metro_km":
                nearest_metro,
            
            "nearest_beach":
                nearest_beach_name,
            
            "nearest_beach_km":
                nearest_beach,
            
            "nearest_mall":
                nearest_mall_name,
            
            "nearest_mall_km":
                nearest_mall,
            
            "nearest_school":
                nearest_school_name,
            
            "nearest_school_km":
                nearest_school,

            "nearest_university":
                nearest_university_name,
            
            "nearest_university_km":
                nearest_university,
            
            "nearest_hospital":
                nearest_hospital_name,
            
            "nearest_hospital_km":
                nearest_hospital,
            
            "location_score":
                location_score,
        })
        
        opportunities.append(opportunity)


# =====================================
# AI INVESTMENT ANALYSIS
# =====================================
MAX_INVESTMENT_AI = 10
investment_ai_count = 0

for opportunity in opportunities:

    if investment_ai_count >= MAX_INVESTMENT_AI:
        break

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
    
        try:

            analysis = generate_ai_analysis(
        
                opportunity,
        
                opportunity[
                    "market_median_price_per_sqft"
                ]
            )
        
        except RuntimeError as e:
        
            if str(e) == "GEMINI_QUOTA_EXCEEDED":
        
                print(
                    "GEMINI QUOTA EXCEEDED - STOPPING INVESTMENT ANALYSIS"
                )
        
                break
        
            raise
    
        if analysis:

            ai_cache[cache_key] = analysis
        
            investment_ai_count += 1
        
            print(
                "NEW INVESTMENT ANALYSIS"
            )
        
            print(
                f"NEW AI USED: {investment_ai_count}/{MAX_INVESTMENT_AI}"
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
print("TOTAL OPPORTUNITIES:", len(opportunities))

yield_available = sum(
    1
    for o in opportunities
    if o.get("gross_yield_percent") is not None
)

yield_missing = sum(
    1
    for o in opportunities
    if o.get("gross_yield_percent") is None
)

print()
print("YIELD COVERAGE")
print("Yield Available:", yield_available)
print("Yield Missing:", yield_missing)

if len(opportunities) > 0:

    coverage = round(
        yield_available
        * 100
        / len(opportunities),
        1
    )

    print("Yield Coverage:", coverage, "%")

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

print(
    "GET_AREA_ASSIGNMENT CALLS:",
    polygon_time
)
