import requests
import json
import geopandas as gpd
from shapely.geometry import Polygon
from shapely.ops import unary_union
import os
import pandas as pd
import time


searched_points = set()

CACHE_FILE = "polygon_cache.geojson"

existing_osm_ids = set()

if os.path.exists(CACHE_FILE):

    cache = gpd.read_file(
        "polygon_cache.geojson"
    )

    existing_osm_ids = set(
        cache["osm_id"]
        .astype(int)
        .tolist()
    )

else:

    cache = None

OVERPASS_URL = "https://overpass-api.de/api/interpreter"




def fetch_polygons(lat, lng):

    query = f"""
    [out:json][timeout:300];

    is_in({lat},{lng})->.a;

    (
      way(pivot.a)["landuse"="residential"];
      relation(pivot.a)["landuse"="residential"];

      way(pivot.a)["place"="suburb"];
      relation(pivot.a)["place"="suburb"];

      way(pivot.a)["place"="neighbourhood"];
      relation(pivot.a)["place"="neighbourhood"];

      way(pivot.a)["boundary"="administrative"]["admin_level"!~"^(1|2|3|4)$"];
      relation(pivot.a)["boundary"="administrative"]["admin_level"!~"^(1|2|3|4)$"];

      way(pivot.a)["place"="island"];
      relation(pivot.a)["place"="island"];

      way(pivot.a)["landuse"="commercial"];
      relation(pivot.a)["landuse"="commercial"];
    );

    out geom;
    """

    for attempt in range(5):

        try:

            response = requests.post(
                OVERPASS_URL,
                data=query,
                headers={
                    "User-Agent": "DubaiResearch/1.0"
                },
                timeout=180
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:

            print(
                f"Attempt {attempt + 1}/5 failed for {lat},{lng}: {e}"
            )

            if attempt < 4:

                wait_time = 10 * (attempt + 1)

                print(
                    f"Waiting {wait_time} seconds before retry..."
                )

                time.sleep(wait_time)

    print(
        f"Giving up on {lat},{lng}"
    )

    return {"elements": []}


def build_geometry(element):

    if element["type"] == "way":

        coords = [
            (p["lon"], p["lat"])
            for p in element["geometry"]
        ]

        if len(coords) < 4:
            return None

        poly = Polygon(coords)

        if not poly.is_valid:
            poly = poly.buffer(0)

        return poly

    if element["type"] == "relation":

        polygons = []

        for member in element.get("members", []):

            if member.get("role") != "outer":
                continue

            if "geometry" not in member:
                continue

            coords = [
                (p["lon"], p["lat"])
                for p in member["geometry"]
            ]

            if len(coords) < 4:
                continue

            poly = Polygon(coords)

            if not poly.is_valid:
                poly = poly.buffer(0)

            polygons.append(poly)

        if not polygons:
            return None

        if len(polygons) == 1:
            return polygons[0]

        return unary_union(polygons)

    return None


with open(
    "polygon_debug.json",
    "r",
    encoding="utf-8"
) as f:

    points = json.load(f)

records = []

for point in points:

    if point["selected_area"] is not None:
        continue

    lat = point["lat"]
    lng = point["lng"]

    cache_key = (
        round(lat, 3),
        round(lng, 3)
    )

    if cache_key in searched_points:
        continue

    searched_points.add(cache_key)

    print(
        "Searching:",
        lat,
        lng
    )

    data = fetch_polygons(
        lat,
        lng
    )

    time.sleep(2)

    for element in data.get("elements", []):

        try:

            geometry = build_geometry(element)

            if geometry is None:
                continue

            if geometry.area > 0.01:
                continue

            if geometry.area < 0.00001:
                continue

            tags = element.get("tags", {})

            if int(element["id"]) in existing_osm_ids:
                continue

            records.append({

                "osm_id": element["id"],

                "osm_type": element["type"],

                "name": (
                    tags.get("name:en")
                    or tags.get("name")
                ),

                "landuse": tags.get("landuse"),

                "place": tags.get("place"),

                "boundary": tags.get("boundary"),

                "polygon_area": geometry.area,

                "geometry": geometry
            })

        except Exception as e:

            print("ERROR:", e)

if not records:
    print("No new polygons found")
    exit(0)


if records:

    gdf = gpd.GeoDataFrame(
        records,
        geometry="geometry",
        crs="EPSG:4326"
    )

else:

    gdf = gpd.GeoDataFrame(
        geometry=[],
        crs="EPSG:4326"
    )

if "polygon_area" in gdf.columns:
    gdf = gdf.sort_values(
        "polygon_area"
    )

if len(gdf) > 0:
    print(
        gdf[
            [
                "name",
                "landuse",
                "place",
                "boundary",
                "polygon_area"
            ]
        ]
    )
else:
    print("No polygons found")


if cache is not None:

    gdf = pd.concat(
        [cache, gdf],
        ignore_index=True
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

gdf.to_file(
    CACHE_FILE,
    driver="GeoJSON"
)
print("Saved polygon_cache.geojson")
