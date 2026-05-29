import osmnx as ox
import geopandas as gpd
import pandas as pd
import json

AREAS = [

    "Dubai Marina, Dubai, UAE",
    "Downtown Dubai, Dubai, UAE",
    "Business Bay, Dubai, UAE",
    "Jumeirah Village Circle, Dubai, UAE",
    "Jumeirah Lakes Towers, Dubai, UAE", #tested
    "Dubai Hills, Dubai, UAE", #tested
    "DIFC, Dubai, UAE",
    "City Walk, Dubai, UAE",
    "Palm Jumeirah, Dubai, UAE",
    "Dubai Harbour, Dubai, UAE",
    "Dubai Media City, Dubai, UAE",
    "Dubai Internet City, Dubai, UAE",
    "Al Wasl, Dubai, UAE",
    "Arjan, Dubai, UAE",
    "Dubai Silicon Oasis, Dubai, UAE",
    "Al Barari, Dubai, UAE",
    "Dubai Creek Harbour, Dubai, UAE",
    "Deira Island, Dubai, UAE",
    "Jumeirah Beach Residence, Dubai, UAE",
    "Bluewaters Island, Dubai, UAE",
    "Dubai Sports City, Dubai, UAE",
    "Motor City, Dubai, UAE",
    "Jumeirah Golf Estates, Dubai, UAE",
    "Mohammed Bin Rashid City, Dubai, UAE"
]

all_gdfs = []

areas_debug = []

for area in AREAS:

    print(f"Downloading: {area}")

    try:

        gdf = ox.geocode_to_gdf(area)

        gdf["canonical_area"] = area.split(",")[0]

        gdf["osm_name"] = gdf["display_name"]

        for _, row in gdf.iterrows():

            polygon = row.geometry
        
            bounds = polygon.bounds
        
            centroid = polygon.centroid
        
            areas_debug.append({
        
                "canonical_area": row["canonical_area"],
        
                "osm_name": row.get("osm_name"),
        
                "osm_type": row.get("type"),
        
                "place_rank": row.get("place_rank"),
        
                "polygon_area": polygon.area,
        
                "centroid_lat": centroid.y,
        
                "centroid_lng": centroid.x,
        
                "bounds": {
        
                    "min_lng": bounds[0],
        
                    "min_lat": bounds[1],
        
                    "max_lng": bounds[2],
        
                    "max_lat": bounds[3]
                }
            })
        
        all_gdfs.append(gdf)
    except Exception as e:

        print(f"Failed: {area}")
        print(e)

combined = gpd.GeoDataFrame(
    pd.concat(all_gdfs, ignore_index=True),
    crs="EPSG:4326"
)

combined.to_file(
    "dubai_areas.geojson",
    driver="GeoJSON"
)

print("Saved dubai_areas.geojson")

with open(
    "areas_debug.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(

        areas_debug,

        f,

        indent=2,

        ensure_ascii=False
    )

print("Saved areas_debug.json")
