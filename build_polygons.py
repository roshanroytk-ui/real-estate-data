import osmnx as ox
import geopandas as gpd
import pandas as pd

AREAS = [

    "Dubai Marina, Dubai, UAE",
    "Downtown Dubai, Dubai, UAE",
    "Business Bay, Dubai, UAE",
    "Jumeirah Village Circle, Dubai, UAE",
    "Jumeirah Lake Towers, Dubai, UAE",
    "Dubai Hills Estate, Dubai, UAE",
    "DIFC, Dubai, UAE",
    "City Walk, Dubai, UAE",
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
    "Dubai Islands, Dubai, UAE",
    "Jumeirah Beach Residence, Dubai, UAE",
    "Bluewaters Island, Dubai, UAE",
    "Dubai Sports City, Dubai, UAE",
    "Motor City, Dubai, UAE",
    "Jumeirah Golf Estates, Dubai, UAE",
    "Mohammed Bin Rashid City, Dubai, UAE"
]

all_gdfs = []

for area in AREAS:

    print(f"Downloading: {area}")

    try:

        gdf = ox.geocode_to_gdf(area)

        gdf["canonical_area"] = area.split(",")[0]

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
