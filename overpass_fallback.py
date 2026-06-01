import requests
import json
import geopandas as gpd
from shapely.geometry import Polygon
from shapely.ops import unary_union

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

      way(pivot.a)["boundary"="administrative"];
      relation(pivot.a)["boundary"="administrative"];

      way(pivot.a)["place"="island"];
      relation(pivot.a)["place"="island"];

      way(pivot.a)["landuse"="commercial"];
      relation(pivot.a)["landuse"="commercial"];
    );

    out geom;
    """

    response = requests.post(
        OVERPASS_URL,
        data=query,
        timeout=180
    )

    response.raise_for_status()

    return response.json()


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


lat = 25.179355
lng = 55.304135

data = fetch_polygons(lat, lng)

records = []

for element in data.get("elements", []):

    try:

        geometry = build_geometry(element)

        if geometry is None:
            continue

        tags = element.get("tags", {})

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

gdf = gpd.GeoDataFrame(
    records,
    geometry="geometry",
    crs="EPSG:4326"
)

gdf = gdf.sort_values(
    "polygon_area"
)

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

gdf.to_file(
    "overpass_result.geojson",
    driver="GeoJSON"
)

print("Saved overpass_result.geojson")
