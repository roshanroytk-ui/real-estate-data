import requests
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import time
import traceback

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CACHE_FILE = "poi_cache.geojson"

BAD_METRO_NAMES = {

    "prt line",
        
    "concourse a",
    "concourse b",
    "concourse d",
        
    "city centre mirdif",
    "al warqa'a",
    "سوق التنبن",
    "مدينة العالمية 1",
    "مدينة العالمية 2",
    "واحة دبي السيليكون",
    "مدينة الأكاديمية",
    "سوق السيارات",
    "إعمار العقارية",
    "دبي فيستيفال سيتي",
        
    "abu dhabi passenger station (under construction)",
    "fujairah passenger station (under construction)",
    "dubai passenger station (under construction)",
    "auto market"
}

BAD_MALL_NAMES = {

    "sparkle shine",
    "shiseido",
    "handmade carpets",
    "mmi festival city",
    "platinum link",
    "grand hyper",
    "grand hypermarket",
    "lulu shopping",
    "smart choice",
    "makani",

    "al ahlia stores",
    "the factory mart",
    "beach park plaza hotel",
    "la plage",
    "city mall",
    "manama",

    "shopping centre",
    
    "karama centre - essen",
    
    "safeer market",
    "safeer hyper market",
    
    "kenz hyper market",
    
    "lulu hypermarket kuwaitat al ain",
    
    "mirdif golden gate",
    
    "the gate avenue",
    
    "waterfront market",
    
    "ajman gold souq",
    
    "hili gifts markets",
    
    "aswaaq",

    "carrefour mall",
    "كارفور",
    "matajer",
    "the mall",
    "al souq",

    "badrah pavalion",
    "grove village",
    "al barajeel oasis complex",
}

BAD_BEACH_NAMES = {

    "mandarin oriental",
    "al-mamzar park - sadaf beach (5)",
    "al-mamzar park - danah beach (3)",

    "lagoons beach",
    "rapids beach",
    "aquaventure beach",

    "al mamzar sea island",

    "dibba hisn publlic beach",
    "dibba hisn public beach+",

    "ممشى البيت المتوحد",

    "al mamzar",
    "la mer",
    "yadi yas beach"

}

BAD_HOSPITAL_NAMES = {

    "adm.ras.alkhaima.muncipality",
    "alkhaled.car.samweel",
    "asd.saadiat",

    "american",
    "infinity",

    "clinic",
    "medical centre",
    "mediclinic",
    "medeor",

    "ibin sina",
    "mustashfa sagar",

    "pergil.burjeel",
    "ultra care",

    "hlg umar",

    "دكتور اسنان",

    "مركز شرطة هيلي",

    "مستشفى",

    "al shoala building",

    "dha central service complex",
    
    "dhcc bldg 24",
    
    "al razi building (dhcc bldg 64)",
    
    "nmc specialty building 1",
    "nmc specialty building 2",
    "nmc specialty building 3",
    
    "hr building - al ain hospital",
    
    "parking.accomodition",
    
    "prime health centre ekka's office",
    
    "preventative medecine department",

    "beverly hills",

    "nmc dip",
    "nmc hospital dip",
    "nmc hospital",
    "nmc jabel ali",

    "burjeel mhpc",

    "franco emirien",

    "gmc hospital,",

    "al saha al shifa tatim",

    "تجمعات مستشفى كرونا razeen 4"

}

BAD_HOSPITAL_WORDS = [

    "block",
    "building",

    "parking",

    "office",

    "administration",

    "department",

    "emergency -",

    "emergency department",

    "service complex",

    "staff accommodation",

    "home healthcare",

    "home health care",

    "training centre",
    "academic medical center",
    "academic medical centre",
]

BAD_SCHOOL_NAMES = {

    "freezone",
    "baraha rooms",
    "simon residence",
    "old school",
    "uips",
    "american",
    "altafawq",
    "al minhaj",
    "al refa'a",
    "muweilah",
    "foremarke",
    "arabic school",
    "premier genie",
    "brainpower talent",
    "centre for musical arts",
    "school",
    "smart",
    "safa",
    "mother care",
    "playhouse",
    "writing center",
    "hair & beauty academy",
    "online trading academy",
    "boys school",
    "girls school",

    "ahmed bin zayed",
    "abou dhabi island int school site lcation",
    
    "عجمان",
    
    "مركز مزيد",
    "special education support center",
    "victoria international school of sharjah"
}

BAD_SCHOOL_WORDS = [

    "driving",
    "driving institute",
    "driving center",
    "driving company",

    "training center",
    "training centre",

    "accomodation",
    "accommodation",

    "residence",

    "freezone",

    "medical centre",

    "hospital",

    "block ",
    "training",
    "traffic safety",

    "clinic"
]


def fetch_pois():

    query = """
    [out:json][timeout:300];

    area["ISO3166-1"="AE"]->.uae;

    (
      node["railway"="station"]["station"="subway"](area.uae);
      way["railway"="station"]["station"="subway"](area.uae);
    
      way["shop"="mall"](area.uae);
      relation["shop"="mall"](area.uae);
    
      way["natural"="beach"](area.uae);
      relation["natural"="beach"](area.uae);
    
      node["amenity"="school"](area.uae);
      way["amenity"="school"](area.uae);

      node["amenity"="college"](area.uae);
      way["amenity"="college"](area.uae);
    
      node["amenity"="university"](area.uae);
      way["amenity"="university"](area.uae);
    
      node["amenity"="kindergarten"](area.uae);
      way["amenity"="kindergarten"](area.uae);
    
      node["amenity"="hospital"](area.uae);
      way["amenity"="hospital"](area.uae);
    );
    
    out center tags;
    """

    for attempt in range(5):

        try:

            response = requests.post(
                OVERPASS_URL,
                data=query,
                headers={
                    "User-Agent": "DubaiResearch/1.0"
                },
                timeout=300
            )

            response.raise_for_status()

            return response.json()

        except Exception as e:

            print(
                f"Attempt {attempt + 1}/5 failed: {e}"
            )

            if attempt < 4:

                wait_time = (
                    10 * (attempt + 1)
                )

                print(
                    f"Waiting {wait_time}s..."
                )

                time.sleep(wait_time)

    return {"elements": []}


print("Downloading POIs...")

data = fetch_pois()

records = []

for element in data.get("elements", []):

    try:

        tags = element.get(
            "tags",
            {}
        )
        bounds = element.get("bounds")

        name = (
            tags.get("name:en")
            or tags.get("name")
        )
        
        if not name:
            continue
        
        name = str(name).strip()
        
        if len(name) < 3:
            continue

        bad_names = {
            "تمت ازالته",
            "beach",
            "private beach",
            "شاطئ"
        }
        
        if name.lower() in {
            x.lower()
            for x in bad_names
        }:
            continue

        lower_name = name.lower()

        if lower_name in BAD_METRO_NAMES:
            continue

        if lower_name in BAD_MALL_NAMES:
            continue

        if lower_name in BAD_BEACH_NAMES:
            continue

        if lower_name in BAD_HOSPITAL_NAMES:
            continue
        
        if tags.get("amenity") == "hospital":
        
            if any(
                word in lower_name
                for word in BAD_HOSPITAL_WORDS
            ):
                continue

        if lower_name in BAD_SCHOOL_NAMES:
            continue
        
        if (
            tags.get("amenity") in {
                "school",
                "college",
                "university",
                "kindergarten"
            }
            and any(
                word in lower_name
                for word in BAD_SCHOOL_WORDS
            )
        ):
            continue

        if tags.get("shop") == "mall":

            bad_words = [
                "tower",
                "commercial centre",
                "commercial center",
            
                "retail",
                "stores",
                "store",
            
                "hotel",
            
                "cooperative",
                "coop",
            
                "garden",
                "gardens",
            
                "walk",
            
                "boulevard",
            
                "wharf"
            ]
        
            if any(
                word in lower_name
                for word in bad_words
            ):
                continue


            if "u/c" in lower_name:
                continue
            
            if "under construction" in lower_name:
                continue


        if any(
            x in lower_name
            for x in [
                "hypermarket",
                "hyper market",
                "supermarket",
                "grocery",
                "mini mart",
                "minimart"
            ]
        ):
            continue


        if (
            lower_name == "beach"
            or lower_name == "private beach"
            or lower_name == "شاطئ"
            or "wasteland" in lower_name
            or "общественный" in lower_name
            or "private beach" in lower_name
        ):
            continue

        poi_type = None

        if (
            tags.get("railway")
            == "station"
            and
            tags.get("station")
            == "subway"
        ):

            poi_type = "metro"

        elif (
            tags.get("shop")
            == "mall"
        ):
        
            poi_type = "mall"

        elif (
            tags.get("natural")
            == "beach"
        ):

            poi_type = "beach"

        elif tags.get("amenity") in {

            "school",
            "college",
            "university",
            "kindergarten"
        
        }:
        
            poi_type = "school"

        elif (
            tags.get("amenity")
            == "hospital"
        ):
        
            poi_type = "hospital"

        if poi_type is None:
            continue

        if element["type"] == "node":

            lat = element.get("lat")
            lng = element.get("lon")

        else:

            center = element.get(
                "center",
                {}
            )

            lat = center.get("lat")
            lng = center.get("lon")

        if lat is None or lng is None:
            continue

        records.append({

            "osm_id":
                element["id"],

            "osm_type":
                element["type"],

            "poi_type":
                poi_type,

            "name":
                name,

            "lat":
                lat,

            "lng":
                lng,

            "geometry":
                Point(
                    lng,
                    lat
                )
        })

    except Exception as e:
        print("ERROR:", e)

if not records:

    print(
        "No POIs found"
    )

    raise SystemExit

gdf = gpd.GeoDataFrame(
    records,
    geometry="geometry",
    crs="EPSG:4326"
)

gdf["unique_id"] = (
    gdf["osm_type"].astype(str)
    + "_"
    + gdf["osm_id"].astype(str)
)

gdf = gdf.drop_duplicates(
    subset=["unique_id"]
)

gdf = gdf.drop(
    columns=["unique_id"]
)

print()

print(
    gdf["poi_type"]
    .value_counts()
)

print()

print(
    gdf[
        [
            "poi_type",
            "name"
        ]
    ]
    .head(20)
)

def normalize_station_name(name):

    return (
        str(name)
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
    )

metro_mask = (
    gdf["poi_type"] == "metro"
)

gdf.loc[
    metro_mask,
    "norm_name"
] = (
    gdf.loc[
        metro_mask,
        "name"
    ]
    .apply(
        normalize_station_name
    )
)

gdf = pd.concat([

    gdf[~metro_mask],

    gdf[metro_mask]
    .drop_duplicates(
        subset=["norm_name"]
    )

])

gdf = gdf.drop(
    columns=["norm_name"],
    errors="ignore"
)

mall_mask = (
    gdf["poi_type"] == "mall"
)

gdf.loc[
    mall_mask,
    "norm_name"
] = (
    gdf.loc[
        mall_mask,
        "name"
    ]
    .str.lower()
    .str.replace(" ", "", regex=False)
    .str.replace("-", "", regex=False)
)

gdf = pd.concat([

    gdf[~mall_mask],

    gdf[mall_mask]
    .drop_duplicates(
        subset=["norm_name"]
    )

])

beach_mask = (
    gdf["poi_type"] == "beach"
)

gdf.loc[
    beach_mask,
    "norm_name"
] = (
    gdf.loc[
        beach_mask,
        "name"
    ]
    .str.lower()
    .str.replace(" ", "", regex=False)
    .str.replace("-", "", regex=False)
)

gdf = pd.concat([

    gdf[~beach_mask],

    gdf[beach_mask]
    .drop_duplicates(
        subset=["norm_name"]
    )

])

gdf = gdf.drop(
    columns=["norm_name"],
    errors="ignore"
)

gdf = gdf.drop(
    columns=["norm_name"],
    errors="ignore"
)

mall_mask = (
    gdf["poi_type"] == "mall"
)

small_malls = []

for idx, row in gdf[mall_mask].iterrows():

    bounds = row.get("bounds")

    if not bounds:
        continue

    try:

        height = (
            bounds["maxlat"]
            - bounds["minlat"]
        )

        width = (
            bounds["maxlon"]
            - bounds["minlon"]
        )

        approx_area = height * width

        if approx_area < 0.000002:
            small_malls.append(idx)

    except:
        pass

gdf = gdf.drop(index=small_malls)

print(
    f"Removed {len(small_malls)} tiny malls"
)

print()

print("SCHOOL")

print(
    gdf[
        gdf["poi_type"] == "school"
    ][["name"]]
    .sort_values("name")
    .to_string(index=False)
)

gdf.to_file(
    CACHE_FILE,
    driver="GeoJSON"
)

print()

print(
    f"Saved {CACHE_FILE}"
)
