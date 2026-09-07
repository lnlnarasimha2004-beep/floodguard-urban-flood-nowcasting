import json
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import joblib
import networkx as nx
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shapely import wkt
from shapely.geometry import Point, shape

APP_DATA_DIR = Path(__file__).resolve().parent / "app_data"
MODEL_PATH = APP_DATA_DIR / "trained_flood_model.joblib"
RAINFALL_BUILDUP = {0: 0.25, 1: 0.55, 2: 0.80, 3: 1.00}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the trained model once, before the API accepts requests."""
    model_bundle = joblib.load(MODEL_PATH)
    required_keys = {"model", "features", "model_type"}
    if not required_keys.issubset(model_bundle):
        raise RuntimeError(f"Invalid FloodGuard model bundle: expected {required_keys}")

    app.state.flood_model = model_bundle["model"]
    app.state.model_features = model_bundle["features"]
    yield


app = FastAPI(title="FloodGuard API", lifespan=lifespan)

# Allow the frontend (running on a different port) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev, we'll tighten later if needed
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    return {"status": "ok", "message": "FloodGuard backend is alive"}

@app.get("/study-area")
def get_study_area():
    with open(APP_DATA_DIR / "study_area.geojson", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def probability_to_risk(probability: float) -> str:
    """Keep the existing four risk labels for the hybrid prediction."""
    if probability < 0.30:
        return "LOW"
    if probability < 0.50:
        return "MODERATE"
    if probability < 0.72:
        return "HIGH"
    return "CRITICAL"


def derive_ml_features(props: dict, rainfall: float, utilization: float) -> dict:
    """Create repeatable local-condition proxies for the prototype ML model."""
    zone_number = int(str(props["zone_id"]).rsplit("_", 1)[-1])
    elevation = float(props["elevation_m"])

    # The generated terrain falls 12 m per row. Lower zones receive greater
    # contributing flow; the fixed offsets represent local terrain variation.
    terrain_drop = max(0.0, 925.2 - elevation)
    slope_percent = min(8.0, 0.8 + terrain_drop * 0.12 + (zone_number % 4) * 0.18)
    flow_accumulation = min(1.0, 0.20 + terrain_drop / 55 + (zone_number % 4) * 0.04)
    blockage_factor = 0.05 + ((zone_number * 7) % 6) * 0.04

    return {
        "rainfall_mm_hr": rainfall,
        "slope_percent": slope_percent,
        "flow_accumulation": flow_accumulation,
        "imperviousness": float(props["imperviousness"]),
        "drainage_capacity": float(props["drainage_capacity"]),
        # Match the training definition: physics utilization adjusted for the
        # deterministic blocked share of the drain. The returned `utilization`
        # remains the original, unmodified physics calculation.
        "drainage_utilization": utilization / (1 - blockage_factor),
        "blockage_factor": blockage_factor,
    }


def effective_rainfall(rainfall: float, hour: int) -> float:
    """Apply the transparent four-frame prototype rainfall buildup."""
    return rainfall * RAINFALL_BUILDUP.get(hour, RAINFALL_BUILDUP[3])


def zone_center(feature: dict) -> tuple[float, float]:
    """Return a polygon's centroid proxy without adding a geometry dependency."""
    ring = feature["geometry"]["coordinates"][0][:-1]
    lon = sum(point[0] for point in ring) / len(ring)
    lat = sum(point[1] for point in ring) / len(ring)
    return lat, lon


def nearest_drainage_node(feature: dict, nodes: list[dict]) -> dict:
    """Associate each zone with its geographically nearest drainage node."""
    zone_lat, zone_lon = zone_center(feature)
    return min(
        nodes,
        key=lambda node: (node["lat"] - zone_lat) ** 2 + (node["lon"] - zone_lon) ** 2,
    )


def compute_drainage_status(zones: list[dict]) -> dict:
    """Compute deterministic zone inflow and directed drainage-network loading."""
    with open(APP_DATA_DIR / "drainage_graph.json", "r", encoding="utf-8") as file:
        graph_data = json.load(file)

    nodes = graph_data["nodes"]
    node_by_id = {node["id"]: node for node in nodes}
    drainage_graph = nx.DiGraph()
    for node in nodes:
        node["direct_inflow"] = 0.0
        node["inflow"] = 0.0
        drainage_graph.add_node(node["id"])
    for edge in graph_data["edges"]:
        drainage_graph.add_edge(edge["from"], edge["to"], capacity=edge["capacity"])

    for feature in zones:
        props = feature["properties"]
        node = nearest_drainage_node(feature, nodes)
        blockage_factor = props["blockage_factor"]
        zone_effective_capacity = props["drainage_capacity"] * (1 - blockage_factor)
        # A zone's drains absorb part of local runoff before the remainder
        # enters its nearest network node. This uses the same deterministic
        # runoff, capacity, and blockage inputs exposed by /simulate.
        node_inflow = max(0.0, props["runoff_mm_hr"] - zone_effective_capacity * 0.15)
        node["direct_inflow"] += node_inflow
        props["drainage_node_id"] = node["id"]

    # The supplied network is directed and acyclic. Carry treated flow toward
    # the outlet while respecting each node and connecting-edge capacity.
    for node_id in nx.topological_sort(drainage_graph):
        node = node_by_id[node_id]
        effective_capacity = node["capacity"] * (1 - node["blockage_factor"])
        total_inflow = node["inflow"] + node["direct_inflow"]
        node["inflow"] = total_inflow
        node["utilization"] = total_inflow / effective_capacity if effective_capacity else 0.0
        node["surcharge"] = node["utilization"] > 1.0

        outgoing_edges = list(drainage_graph.out_edges(node_id, data=True))
        if outgoing_edges:
            transferable_flow = min(total_inflow, effective_capacity)
            combined_edge_capacity = sum(edge[2]["capacity"] for edge in outgoing_edges)
            transferable_flow = min(transferable_flow, combined_edge_capacity)
            for _, downstream_id, edge_data in outgoing_edges:
                share = edge_data["capacity"] / combined_edge_capacity
                node_by_id[downstream_id]["inflow"] += transferable_flow * share

    for node in nodes:
        node["direct_inflow"] = round(node["direct_inflow"], 2)
        node["inflow"] = round(node["inflow"], 2)
        node["utilization"] = round(node["utilization"], 2)

    return graph_data


@app.get("/simulate")
def simulate(rainfall: float = 0, hour: int = 3):
    with open(APP_DATA_DIR / "study_area.geojson", "r", encoding="utf-8") as f:
        data = json.load(f)
    simulation_rainfall = effective_rainfall(rainfall, hour)

    for feature in data["features"]:
        props = feature["properties"]
        imperviousness = props["imperviousness"]  # 0-1, acts as runoff coefficient C
        capacity = props["drainage_capacity"]      # mm/hr equivalent capacity
        elevation = props["elevation_m"]

        # RATIONAL METHOD: Q = C x i x A  (we drop A since it's constant per zone,
        # so we compare runoff intensity directly against drainage capacity)
        runoff = imperviousness * simulation_rainfall

        # low-elevation zones (closer to lake) get an extra runoff boost,
        # simulating water flowing downhill into them
        elevation_factor = max(0.8, 1.4 - (elevation - 850) / 500)
        runoff = runoff * elevation_factor

        utilization = runoff / capacity  # >1 means drainage is overwhelmed

        # estimated water depth (cm) - simple proportional model for prototype
        water_depth_cm = round(max(0, (utilization - 0.5) * 15), 1)

        # rough time-to-flood estimate (minutes) - higher utilization = faster onset
        if utilization > 0.5:
            time_to_flood_min = round(max(5, 90 - utilization * 40))
        else:
            time_to_flood_min = None

        props["runoff_mm_hr"] = round(runoff, 1)
        props["utilization"] = round(utilization, 2)
        props["water_depth_cm"] = water_depth_cm
        props["time_to_flood_min"] = time_to_flood_min
        props["blockage_factor"] = derive_ml_features(props, simulation_rainfall, utilization)["blockage_factor"]

    drainage_status = compute_drainage_status(data["features"])
    node_by_id = {node["id"]: node for node in drainage_status["nodes"]}

    for feature in data["features"]:
        props = feature["properties"]
        utilization = props["utilization"]
        physics_probability = min(0.98, max(0.02, utilization * 0.6))
        ml_features = derive_ml_features(props, simulation_rainfall, utilization)
        feature_frame = pd.DataFrame([ml_features], columns=app.state.model_features)
        ml_probability = float(app.state.flood_model.predict(feature_frame)[0])
        ml_probability = min(0.98, max(0.02, ml_probability))

        # Physics remains the primary signal; ML refines it using terrain and
        # drainage-condition features learned during training.
        base_hybrid_probability = min(
            0.98,
            max(0.02, 0.65 * physics_probability + 0.35 * ml_probability),
        )
        drainage_node = node_by_id[props["drainage_node_id"]]
        drainage_pressure = min(
            0.20,
            max(0.0, drainage_node["utilization"] - 0.65) * 0.18
            + (0.08 if drainage_node["surcharge"] else 0.0),
        )
        hybrid_probability = min(
            0.98,
            base_hybrid_probability + (1 - base_hybrid_probability) * drainage_pressure,
        )
        hybrid_severity = probability_to_risk(hybrid_probability)

        props["risk"] = hybrid_severity
        props["ml_probability"] = round(ml_probability, 2)
        props["flood_probability"] = round(hybrid_probability, 2)
        props["hybrid_severity"] = hybrid_severity
        props["drainage_surcharge"] = drainage_node["surcharge"]
        props["drainage_utilization"] = drainage_node["utilization"]
        props["data_label"] = "Prototype / simulated flood values"

    return data

@app.get("/drainage-network")
def get_drainage_network():
    with open(APP_DATA_DIR / "drainage_graph.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

@app.get("/drainage-status")
def get_drainage_status(rainfall: float = 0, hour: int = 3):
    # Reuse the same zone runoff and directed-network calculation as /simulate.
    zones = simulate(rainfall, hour)
    return compute_drainage_status(zones["features"])

ROUTE_ANCHORS = {
    # These geographic positions preserve the UI's familiar selectors. They are
    # snapped to the closest *real* OSM node when a route is requested.
    "R_0_0": {"label": "North-West Junction", "lat": 12.9310, "lon": 77.6740},
    "R_0_4": {"label": "North-East Junction", "lat": 12.9310, "lon": 77.6800},
    "R_4_0": {"label": "South-West Junction", "lat": 12.9250, "lon": 77.6740},
    "R_4_4": {"label": "South-East Junction", "lat": 12.9250, "lon": 77.6800},
    "R_2_2": {"label": "Central Junction", "lat": 12.9280, "lon": 77.6770},
}
RISK_PENALTY = {"LOW": 1.0, "MODERATE": 2.0, "HIGH": 12.0, "CRITICAL": 1000.0}


@lru_cache(maxsize=1)
def load_road_graph():
    """Load the offline OSMnx GraphML once; never route over the demo grid."""
    graph = nx.read_graphml(APP_DATA_DIR / "road_network.graphml", force_multigraph=True)
    for _, attrs in graph.nodes(data=True):
        attrs["lat"] = float(attrs["y"])
        attrs["lon"] = float(attrs["x"])
    for _, _, _, attrs in graph.edges(keys=True, data=True):
        attrs["length_m"] = float(attrs["length"])
    # Boundary extracts commonly include one-way stubs that cannot reach the
    # rest of the map. Selector anchors must land in the routable road core,
    # otherwise an apparently nearby endpoint can make a valid trip impossible.
    graph.graph["routable_nodes"] = frozenset(
        max(nx.strongly_connected_components(graph), key=len)
    )
    return graph


def nearest_osm_node(graph, lat: float, lon: float) -> str:
    """Snap an anchor to the nearest node that can route both ways in the OSM graph."""
    # The study area is small, so squared degrees are sufficient for snapping.
    return min(
        graph.graph.get("routable_nodes", graph.nodes),
        key=lambda node: (graph.nodes[node]["lat"] - lat) ** 2
        + (graph.nodes[node]["lon"] - lon) ** 2,
    )


def edge_geometry_coords(graph, u, v, attrs) -> list[list[float]]:
    """Return directed edge geometry as [lat, lon], including every OSM turn."""
    if attrs.get("geometry"):
        coords = [[lat, lon] for lon, lat in wkt.loads(attrs["geometry"]).coords]
    else:
        coords = [
            [graph.nodes[u]["lat"], graph.nodes[u]["lon"]],
            [graph.nodes[v]["lat"], graph.nodes[v]["lon"]],
        ]
    # OSMnx normally stores geometry in edge direction, but orient it defensively.
    start = graph.nodes[u]
    end = graph.nodes[v]
    forward_error = (coords[0][0] - start["lat"]) ** 2 + (coords[0][1] - start["lon"]) ** 2
    reverse_error = (coords[-1][0] - start["lat"]) ** 2 + (coords[-1][1] - start["lon"]) ** 2
    if reverse_error < forward_error:
        coords.reverse()
    return coords


def sampled_edge_risks(coords: list[list[float]], zones: list[tuple[object, str]]) -> list[str]:
    """Classify points along an entire road shape rather than just its midpoint."""
    line = wkt.loads("LINESTRING (" + ", ".join(f"{lon} {lat}" for lat, lon in coords) + ")")
    # At least five samples makes short curved links representative; longer roads
    # receive approximately one sample every 15 m.
    sample_count = max(5, int(line.length / 0.000135) + 1)
    risks = []
    for index in range(sample_count):
        point = line.interpolate(index / (sample_count - 1), normalized=True)
        risks.append(next((risk for polygon, risk in zones if polygon.covers(point)), "LOW"))
    return risks


def choose_edge(graph, u, v, weight_name: str):
    """Identify the selected parallel OSM edge for a node-to-node path step."""
    key, attrs = min(
        graph[u][v].items(), key=lambda item: item[1][weight_name]
    )
    return key, attrs


def route_metrics(graph, path: list[str], weight_name: str) -> dict:
    coords, distance_m, weighted_cost = [], 0.0, 0.0
    risk_counts = {risk: 0 for risk in RISK_PENALTY}
    high_risk_segments = 0
    for u, v in zip(path, path[1:]):
        _, attrs = choose_edge(graph, u, v, weight_name)
        edge_coords = edge_geometry_coords(graph, u, v, attrs)
        if coords and coords[-1] == edge_coords[0]:
            coords.extend(edge_coords[1:])
        else:
            coords.extend(edge_coords)
        distance_m += attrs["length_m"]
        weighted_cost += attrs[weight_name]
        edge_risks = attrs["sampled_risks"]
        for risk in edge_risks:
            risk_counts[risk] += 1
        if any(risk in {"HIGH", "CRITICAL"} for risk in edge_risks):
            high_risk_segments += 1
    return {
        "path_coords": coords,
        "distance_m": round(distance_m, 1),
        "weighted_cost": round(weighted_cost, 1),
        "high_risk_segments": high_risk_segments,
        "route_risk_summary": risk_counts,
    }


@app.get("/route")
def get_route(start: str, end: str, rainfall: float = 0, safe: bool = True, hour: int = 3):
    if start not in ROUTE_ANCHORS or end not in ROUTE_ANCHORS:
        return {"error": "Unknown route anchor"}
    graph = load_road_graph().copy()
    simulated_zones = simulate(rainfall, hour)
    zones = [(shape(feature["geometry"]), feature["properties"]["risk"])
             for feature in simulated_zones["features"]]

    for u, v, key, attrs in graph.edges(keys=True, data=True):
        geometry = edge_geometry_coords(graph, u, v, attrs)
        risks = sampled_edge_risks(geometry, zones)
        # The mean sampled multiplier keeps mixed-risk roads proportional to
        # their exposure while allowing CRITICAL links to be practically closed.
        attrs["sampled_risks"] = risks
        attrs["normal_weight"] = attrs["length_m"]
        attrs["safe_weight"] = attrs["length_m"] * sum(RISK_PENALTY[r] for r in risks) / len(risks)

    start_osm = nearest_osm_node(graph, **{k: ROUTE_ANCHORS[start][k] for k in ("lat", "lon")})
    end_osm = nearest_osm_node(graph, **{k: ROUTE_ANCHORS[end][k] for k in ("lat", "lon")})

    try:
        path = nx.shortest_path(graph, source=start_osm, target=end_osm,
                                weight="safe_weight" if safe else "normal_weight")
    except nx.NetworkXNoPath:
        return {"error": "No path found between these points"}

    metrics = route_metrics(graph, path, "safe_weight" if safe else "normal_weight")
    # Expose both measures for the returned geometry: raw travel distance and
    # flood-aware cost. This keeps normal-versus-safe comparisons explicit.
    metrics["normal_weighted_cost"] = route_metrics(graph, path, "normal_weight")["weighted_cost"]
    metrics["safe_weighted_cost"] = route_metrics(graph, path, "safe_weight")["weighted_cost"]
    normal_path = nx.shortest_path(graph, source=start_osm, target=end_osm, weight="normal_weight")
    normal_metrics = route_metrics(graph, normal_path, "normal_weight")
    metrics.update({
        "path_nodes": path,
        "total_weight": metrics["weighted_cost"],  # backward-compatible frontend field
        "mode": "safe" if safe else "normal",
        "start": {"label": ROUTE_ANCHORS[start]["label"], "lat": graph.nodes[start_osm]["lat"],
                  "lon": graph.nodes[start_osm]["lon"], "osm_node": start_osm},
        "end": {"label": ROUTE_ANCHORS[end]["label"], "lat": graph.nodes[end_osm]["lat"],
                "lon": graph.nodes[end_osm]["lon"], "osm_node": end_osm},
        "high_risk_segments_avoided": max(0, normal_metrics["high_risk_segments"] - metrics["high_risk_segments"]),
    })
    return metrics


@app.get("/road-network")
def get_road_network():
    graph = load_road_graph()
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"length_m": attrs["length_m"]},
             "geometry": {"type": "LineString", "coordinates": [
                 [lon, lat] for lat, lon in edge_geometry_coords(graph, u, v, attrs)
             ]}}
            for u, v, _, attrs in graph.edges(keys=True, data=True)
        ],
    }
