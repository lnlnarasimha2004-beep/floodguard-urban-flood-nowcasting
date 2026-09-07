import json
import os
import networkx as nx

OUTPUT_PATH = os.path.join("..", "backend", "app_data", "road_network.json")

# Road network follows a simple grid over our study area,
# roughly aligned with real street directions in Green Glen Layout / Bellandur.
# Grid points: 5x5 = 25 intersections, connected horizontally + vertically.

LAT_MIN, LAT_MAX = 12.9250, 12.9310
LON_MIN, LON_MAX = 77.6740, 77.6800
GRID_SIZE = 5  # 5x5 intersections

def generate_roads():
    G = nx.Graph()

    lat_step = (LAT_MAX - LAT_MIN) / (GRID_SIZE - 1)
    lon_step = (LON_MAX - LON_MIN) / (GRID_SIZE - 1)

    # create intersection nodes
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            node_id = f"R_{i}_{j}"
            lat = LAT_MIN + i * lat_step
            lon = LON_MIN + j * lon_step
            G.add_node(node_id, lat=lat, lon=lon)

    # connect horizontal and vertical neighbors (grid roads)
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            node_id = f"R_{i}_{j}"
            if j < GRID_SIZE - 1:
                right = f"R_{i}_{j+1}"
                G.add_edge(node_id, right, base_weight=1.0, risk_level="LOW")
            if i < GRID_SIZE - 1:
                down = f"R_{i+1}_{j}"
                G.add_edge(node_id, down, base_weight=1.0, risk_level="LOW")

    data = {
        "nodes": [{"id": n, "lat": G.nodes[n]["lat"], "lon": G.nodes[n]["lon"]} for n in G.nodes],
        "edges": [{"from": u, "to": v, "base_weight": d["base_weight"], "risk_level": d["risk_level"]}
                   for u, v, d in G.edges(data=True)],
        "data_label": "Prototype / representative road network"
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Road network written: {len(data['nodes'])} nodes, {len(data['edges'])} edges")

if __name__ == "__main__":
    generate_roads()