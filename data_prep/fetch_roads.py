import osmnx as ox
import os

# Bounding box matching our study area (Green Glen Layout, Bellandur)
NORTH, SOUTH = 12.9310, 12.9250
EAST, WEST = 77.6800, 77.6740

OUTPUT_PATH = os.path.join("..", "backend", "app_data", "road_network.graphml")

def fetch_roads():
    print("Downloading road network from OpenStreetMap...")
    # osmnx 2.x expects bbox as (left, bottom, right, top) = (west, south, east, north)
    G = ox.graph_from_bbox(bbox=(WEST, SOUTH, EAST, NORTH), network_type="drive")
    ox.save_graphml(G, OUTPUT_PATH)
    print(f"Road network saved to {OUTPUT_PATH}")
    print(f"Nodes: {len(G.nodes)}, Edges: {len(G.edges)}")

if __name__ == "__main__":
    fetch_roads()