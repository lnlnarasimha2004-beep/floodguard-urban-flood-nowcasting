import json
import os

OUTPUT_PATH = os.path.join("..", "backend", "app_data", "drainage_graph.json")

# Nodes: manholes/junctions spread across the study area, generally flowing
# toward the north (toward Bellandur Lake, which is the natural low point/outlet)
NODES = [
    {"id": "N1", "type": "manhole", "lat": 12.9255, "lon": 77.6745, "capacity": 50, "blockage_factor": 0.0},
    {"id": "N2", "type": "manhole", "lat": 12.9255, "lon": 77.6775, "capacity": 50, "blockage_factor": 0.1},
    {"id": "N3", "type": "manhole", "lat": 12.9255, "lon": 77.6795, "capacity": 45, "blockage_factor": 0.0},
    {"id": "N4", "type": "junction", "lat": 12.9270, "lon": 77.6760, "capacity": 80, "blockage_factor": 0.05},
    {"id": "N5", "type": "junction", "lat": 12.9270, "lon": 77.6790, "capacity": 75, "blockage_factor": 0.15},
    {"id": "N6", "type": "junction", "lat": 12.9285, "lon": 77.6750, "capacity": 90, "blockage_factor": 0.0},
    {"id": "N7", "type": "junction", "lat": 12.9285, "lon": 77.6780, "capacity": 85, "blockage_factor": 0.2},
    {"id": "N8", "type": "manhole", "lat": 12.9300, "lon": 77.6765, "capacity": 100, "blockage_factor": 0.0},
    {"id": "OUT1", "type": "outlet", "lat": 12.9308, "lon": 77.6770, "capacity": 200, "blockage_factor": 0.0},
]

# Edges: pipes connecting nodes, generally flowing north toward the outlet
EDGES = [
    {"id": "E1", "from": "N1", "to": "N4", "capacity": 45},
    {"id": "E2", "from": "N2", "to": "N4", "capacity": 45},
    {"id": "E3", "from": "N2", "to": "N5", "capacity": 40},
    {"id": "E4", "from": "N3", "to": "N5", "capacity": 40},
    {"id": "E5", "from": "N4", "to": "N6", "capacity": 70},
    {"id": "E6", "from": "N5", "to": "N7", "capacity": 65},
    {"id": "E7", "from": "N6", "to": "N8", "capacity": 85},
    {"id": "E8", "from": "N7", "to": "N8", "capacity": 80},
    {"id": "E9", "from": "N8", "to": "OUT1", "capacity": 180},
]

def generate():
    graph = {
        "nodes": NODES,
        "edges": EDGES,
        "data_label": "Prototype / representative drainage data"
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(graph, f, indent=2)
    print(f"Drainage graph written to {OUTPUT_PATH} ({len(NODES)} nodes, {len(EDGES)} edges)")

if __name__ == "__main__":
    generate()