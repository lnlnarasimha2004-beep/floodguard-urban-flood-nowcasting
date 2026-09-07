import json
import os

STUDY_AREA_PATH = os.path.join("..", "backend", "app_data", "study_area.geojson")

# Reference point = Bellandur Lake (north of our study area)
# Zones closer to the lake (higher latitude) sit lower and get more runoff
LAKE_LAT = 12.9350

def generate_terrain():
    with open(STUDY_AREA_PATH, "r") as f:
        data = json.load(f)

    for feature in data["features"]:
        coords = feature["geometry"]["coordinates"][0]
        lats = [pt[1] for pt in coords]
        center_lat = sum(lats) / len(lats)

        # distance to lake (smaller = closer = lower elevation = more flood-prone)
        dist_to_lake = abs(LAKE_LAT - center_lat)

        # synthetic elevation: closer to lake -> lower elevation
        elevation = round(850 + dist_to_lake * 8000, 1)  # meters, arbitrary but consistent

        # synthetic imperviousness (0-1): assume fairly built-up area, some variation
        # use zone_id to vary it deterministically instead of random, so it's reproducible
        zone_num = int(feature["properties"]["zone_id"].split("_")[1])
        imperviousness = round(0.5 + (zone_num % 5) * 0.08, 2)  # 0.5 - 0.82

        # synthetic drainage capacity (mm/hr equivalent capacity per zone)
        drainage_capacity = round(40 + (zone_num % 4) * 10, 1)  # 40-70

        feature["properties"]["elevation_m"] = elevation
        feature["properties"]["imperviousness"] = imperviousness
        feature["properties"]["drainage_capacity"] = drainage_capacity
        feature["properties"]["data_label"] = "Prototype / synthetic terrain data"

    with open(STUDY_AREA_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print("Terrain features added to study_area.geojson")

if __name__ == "__main__":
    generate_terrain()