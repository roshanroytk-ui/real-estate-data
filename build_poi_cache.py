import requests
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import time

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CACHE_FILE = "poi_cache.geojson"


def fetch_pois():

    query = """
    [out:json][timeout:300];

    area["name"="United Arab Emirates"]->.uae;

    (

      node["railway"="station"](area.uae);
      node["station"="subway"](area.uae);

      node["shop"="mall"](area.uae);
      way["shop"="mall"](area.uae);

      way["natural"="beach"](area.uae);
      relation["natural"="beach"](area.uae);

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

        name = (
            tags.get("name:en")
            or tags.get("name")
        )

        if not name:
            continue

        poi_type = None

        if (
            tags.get("railway")
            == "station"
            or
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

        print(
            "ERROR:",
            e
        )

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

gdf.to_file(
    CACHE_FILE,
    driver="GeoJSON"
)

print()

print(
    f"Saved {CACHE_FILE}"
)
