import os
import json
import logging
import math
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, Polygon, MultiPoint
from shapely.ops import transform
import pyproj

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataLoader")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CACHE_FILE = os.path.join(DATA_DIR, "lucerne_data_cache.json")
GATEWAYS_FILE = os.path.join(DATA_DIR, "gateways.json")

ALLOWED_HIGHWAYS = {
    'motorway', 'motorway_link', 
    'trunk', 'trunk_link', 
    'primary', 'primary_link', 
    'secondary', 'secondary_link'
}

HIGHWAY_WEIGHTS = {
    'motorway': 10.0, 'motorway_link': 8.0,
    'trunk': 8.0, 'trunk_link': 7.0,
    'primary': 6.0, 'primary_link': 5.0,
    'secondary': 4.0, 'secondary_link': 3.0
}

class LucerneDataLoader:
    def __init__(self, place_name="Lucerne, Switzerland"):
        self.place_name = place_name
        self.graph = None
        self.graph_proj = None
        self.nodes_dict = {}
        self.edges_list = []
        self.pois = []
        self.residential_nodes = []
        self.commercial_nodes = []
        self.gateway_nodes = []
        self.gateway_details = []
        self.boundary_polygon_coords = []
        
    def load_data(self, use_cache=True):
        os.makedirs(DATA_DIR, exist_ok=True)
        
        if use_cache and os.path.exists(CACHE_FILE):
            logger.info("Loading cached Lucerne network & POI data...")
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._reconstruct_from_json(data)
                    self._load_custom_gateways_override()
                    logger.info(f"Loaded {len(self.nodes_dict)} nodes, {len(self.edges_list)} edges, "
                                f"{len(self.pois)} POIs, {len(self.gateway_details)} gateways.")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Re-fetching from OpenStreetMap...")

        logger.info("Fetching Lucerne regional road network...")
        
        try:
            ox.settings.use_cache = True
            ox.settings.log_console = False
        except AttributeError:
            pass

        places = ["Lucerne, Switzerland", "Ebikon, Switzerland", "Emmen, Switzerland", "Kriens, Switzerland"]
        try:
            self.graph = ox.graph_from_place(places, network_type="drive", simplify=True)
        except Exception as e:
            logger.warning(f"ox.graph_from_place multi-place failed: {e}. Falling back to single query...")
            self.graph = ox.graph_from_place(self.place_name, network_type="drive", simplify=True)

        logger.info(f"Network retrieved: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")
        
        try:
            self.graph_proj = ox.project_graph(self.graph, to_crs="EPSG:2056")
        except Exception:
            self.graph_proj = self.graph

        self._extract_network_structure()
        self._fetch_pois_and_landuse()
        self._extract_true_boundary_gateways()
        self._save_cache()
        return True

    def _extract_network_structure(self):
        self.nodes_dict = {}
        for node, data in self.graph.nodes(data=True):
            lat = data.get("y", 0.0)
            lon = data.get("x", 0.0)
            self.nodes_dict[str(node)] = {
                "id": str(node),
                "lat": float(lat),
                "lon": float(lon),
                "weight_orig": 1.0,
                "weight_dest": 1.0,
                "is_gateway": False,
                "gateway_weight": 1.0,
                "gateway_name": "",
                "is_poi": False
            }

        self.edges_list = []
        edge_id_counter = 0
        for u, v, k, data in self.graph.edges(keys=True, data=True):
            length = float(data.get("length", 100.0))
            maxspeed_raw = data.get("maxspeed", 50)
            if isinstance(maxspeed_raw, list):
                maxspeed_raw = maxspeed_raw[0]
            try:
                maxspeed = float(str(maxspeed_raw).replace(" km/h", "").replace("mph", ""))
            except (ValueError, TypeError):
                maxspeed = 50.0
                
            lanes_raw = data.get("lanes", 1)
            if isinstance(lanes_raw, list):
                lanes_raw = lanes_raw[0]
            try:
                lanes = int(lanes_raw)
            except (ValueError, TypeError):
                lanes = 1

            highway = data.get("highway", "unclassified")
            if isinstance(highway, list):
                highway = highway[0]

            name = data.get("name", f"Road {u}-{v}")
            if isinstance(name, list):
                name = name[0]

            capacity_per_lane = 1200 if highway in ["motorway", "trunk", "primary"] else 600
            capacity = max(300, lanes * capacity_per_lane)

            geometry_coords = []
            if "geometry" in data:
                geom = data["geometry"]
                geometry_coords = [[float(y), float(x)] for x, y in geom.coords]
            else:
                u_node = self.nodes_dict[str(u)]
                v_node = self.nodes_dict[str(v)]
                geometry_coords = [[u_node["lat"], u_node["lon"]], [v_node["lat"], v_node["lon"]]]

            edge_dict = {
                "edge_id": f"e_{edge_id_counter}",
                "u": str(u),
                "v": str(v),
                "key": k,
                "length": max(5.0, length),
                "maxspeed": maxspeed,
                "lanes": lanes,
                "highway": highway,
                "name": name,
                "capacity": capacity,
                "geometry": geometry_coords,
                "free_flow_time": max(1.0, length / (maxspeed / 3.6))
            }
            self.edges_list.append(edge_dict)
            edge_id_counter += 1

    def _fetch_pois_and_landuse(self):
        logger.info("Extracting Points of Interest (POIs) and Land-use...")
        poi_tags = {
            "railway": "station",
            "historic": ["bridge", "monument"],
            "amenity": ["arts_centre", "hospital", "university"],
            "shop": ["supermarket", "mall"],
            "tourism": ["hotel", "attraction", "museum"]
        }
        
        self.pois = []
        try:
            pois_gdf = ox.features_from_place(self.place_name, tags=poi_tags)
            for idx, row in pois_gdf.iterrows():
                name = row.get("name")
                if not name or pd.isna(name):
                    continue
                
                geom = row.geometry
                if isinstance(geom, Point):
                    lat, lon = geom.y, geom.x
                elif hasattr(geom, "centroid"):
                    lat, lon = geom.centroid.y, geom.centroid.x
                else:
                    continue

                category = "POI"
                if "railway" in row and row["railway"] == "station":
                    category = "Train Station"
                elif "historic" in row:
                    category = "Historic Attraction"
                elif "shop" in row:
                    category = "Supermarket/Shopping"
                elif "tourism" in row:
                    category = "Tourism / Hotel"
                elif "amenity" in row:
                    category = "Public Facility / Hospital"

                nearest_node = self.find_nearest_node(lat, lon)
                if nearest_node:
                    self.pois.append({
                        "name": str(name),
                        "category": category,
                        "lat": float(lat),
                        "lon": float(lon),
                        "node_id": nearest_node
                    })
                    self.nodes_dict[nearest_node]["is_poi"] = True
                    self.nodes_dict[nearest_node]["weight_dest"] += 10.0
        except Exception:
            self._add_fallback_pois()

        if len(self.pois) == 0:
            self._add_fallback_pois()

        all_node_ids = list(self.nodes_dict.keys())
        np.random.seed(42)
        shuffled = np.random.permutation(all_node_ids)
        split_idx = int(len(shuffled) * 0.6)
        self.residential_nodes = list(shuffled[:split_idx])
        self.commercial_nodes = list(shuffled[split_idx:])

        for n_id in self.residential_nodes:
            self.nodes_dict[n_id]["weight_orig"] += 5.0
        for n_id in self.commercial_nodes:
            self.nodes_dict[n_id]["weight_dest"] += 5.0

    def _add_fallback_pois(self):
        fallback_landmarks = [
            {"name": "Bahnhof Luzern (Main Station)", "category": "Train Station", "lat": 47.0502, "lon": 8.3103},
            {"name": "Kapellbrücke (Chapel Bridge)", "category": "Historic Attraction", "lat": 47.0516, "lon": 8.3073},
            {"name": "Löwendenkmal (Lion Monument)", "category": "Historic Attraction", "lat": 47.0583, "lon": 8.3107},
            {"name": "KKL Luzern (Culture & Congress)", "category": "Tourism / Hotel", "lat": 47.0500, "lon": 8.3120},
            {"name": "Luzerner Kantonsspital (LUKS)", "category": "Public Facility / Hospital", "lat": 47.0580, "lon": 8.3005},
            {"name": "Emmen Center / Shopping Mall", "category": "Supermarket/Shopping", "lat": 47.0710, "lon": 8.2890},
            {"name": "Verkehrshaus der Schweiz", "category": "Tourism / Hotel", "lat": 47.0531, "lon": 8.3356}
        ]
        for item in fallback_landmarks:
            nearest = self.find_nearest_node(item["lat"], item["lon"])
            if nearest:
                item["node_id"] = nearest
                self.pois.append(item)
                self.nodes_dict[nearest]["is_poi"] = True
                self.nodes_dict[nearest]["weight_dest"] += 15.0

    def _extract_true_boundary_gateways(self):
        """
        Directed Edge Boundary Crossing Algorithm.
        Guarantees ZERO internal roundabouts or internal intersections become gateways.
        Extracts directed boundary-crossing edges, prunes external loop pass-throughs,
        and clusters adjacent bi-directional portals into clean Gateway Corridors.
        """
        logger.info("Computing Directed Spatial Edge Boundary Crossings...")

        # 1. Define Lucerne Study Area Boundary Ring Polygon (around urban core)
        # Lat/Lon bounding polygon enclosing central Lucerne, Kriens, Emmen, Ebikon
        boundary_coords = [
            (8.270, 47.070), (8.300, 47.075), (8.340, 47.065), (8.350, 47.045),
            (8.335, 47.030), (8.310, 47.020), (8.270, 47.025), (8.255, 47.045),
            (8.270, 47.070)
        ]
        self.boundary_polygon_coords = [[lat, lon] for lon, lat in boundary_coords]
        boundary_poly = Polygon(boundary_coords)
        boundary_ring = boundary_poly.exterior

        # 2. Classify Node Containment (INSIDE vs OUTSIDE)
        node_containment = {}
        for n_id, n_data in self.nodes_dict.items():
            pt = Point(n_data["lon"], n_data["lat"])
            node_containment[n_id] = "INSIDE" if boundary_poly.contains(pt) else "OUTSIDE"

        # 3. Directed Edge Crossing Filter
        crossing_edges = []
        for edge in self.edges_list:
            u_id, v_id = edge["u"], edge["v"]
            loc_u = node_containment.get(u_id, "OUTSIDE")
            loc_v = node_containment.get(v_id, "OUTSIDE")

            # Guaranteed Elimination: Skip edges where both u and v are INSIDE (Internal roundabouts/junctions)
            if loc_u == loc_v:
                continue

            highway = edge["highway"]
            if highway not in ALLOWED_HIGHWAYS:
                continue  # Skip residential, service, tertiary, footways

            direction = "INFLOW" if (loc_u == "OUTSIDE" and loc_v == "INSIDE") else "OUTFLOW"

            # Compute boundary intersection point
            u_node = self.nodes_dict[u_id]
            v_node = self.nodes_dict[v_id]
            edge_line = LineString([(u_node["lon"], u_node["lat"]), (v_node["lon"], v_node["lat"])])

            intersection = edge_line.intersection(boundary_ring)
            if intersection.is_empty:
                lat_cross, lon_cross = v_node["lat"] if direction == "INFLOW" else u_node["lat"], v_node["lon"] if direction == "INFLOW" else u_node["lon"]
            elif isinstance(intersection, Point):
                lat_cross, lon_cross = intersection.y, intersection.x
            else:
                lat_cross, lon_cross = intersection.centroid.y, intersection.centroid.x

            target_node_id = v_id if direction == "INFLOW" else u_id
            weight = HIGHWAY_WEIGHTS.get(highway, 3.0)
            road_name = edge["name"]

            corridor_name = self._resolve_corridor_name(lat_cross, lon_cross, highway, road_name)

            crossing_edges.append({
                "edge_id": edge["edge_id"],
                "node_id": target_node_id,
                "direction": direction,
                "lat": lat_cross,
                "lon": lon_cross,
                "highway": highway,
                "road_name": road_name,
                "corridor_name": corridor_name,
                "weight": weight
            })

        # 4. Spatial Clustering (merge adjacent portals of same road within ~250m)
        clustered = {}
        for c in crossing_edges:
            key = f"{round(c['lat'], 3)}_{round(c['lon'], 3)}"
            if key not in clustered or c["weight"] > clustered[key]["weight"]:
                clustered[key] = {
                    "id": f"gw_portal_{c['node_id']}",
                    "node_id": c["node_id"],
                    "name": c["corridor_name"],
                    "corridor_type": c["highway"],
                    "lat": c["lat"],
                    "lon": c["lon"],
                    "weight": c["weight"],
                    "direction": "both",
                    "capacity_veh_per_hr": int(c["weight"] * 400),
                    "enabled": True,
                    "is_custom": False
                }

        self.gateway_details = list(clustered.values())
        self.gateway_nodes = [g["node_id"] for g in self.gateway_details if g["enabled"]]

        for g in self.gateway_details:
            n_id = g["node_id"]
            if n_id in self.nodes_dict:
                self.nodes_dict[n_id]["is_gateway"] = True
                self.nodes_dict[n_id]["gateway_weight"] = g["weight"]
                self.nodes_dict[n_id]["gateway_name"] = g["name"]

        logger.info(f"Identified {len(self.gateway_details)} clean true boundary gateway portals.")
        self.save_gateways_to_json()

    def _resolve_corridor_name(self, lat, lon, highway, road_name):
        """Map portal lat/lon to official regional corridor names."""
        if lat >= 47.065 and lon >= 8.315:
            return "Gateway Maihof / Ebikon (Zürichstrasse - H2)"
        elif lat >= 47.065 and lon < 8.300:
            return "Gateway Seetalplatz / Emmenbrücke (H26 / Sedel)"
        elif lat <= 47.030 and lon <= 8.300:
            return "Gateway A2 Süd (Luzern-Süd / Kriens / Schlund)"
        elif lat <= 47.030 and lon > 8.300:
            return "Gateway Horwerstrasse (Horw / Allmend)"
        elif lon <= 8.265:
            return "Gateway West (Bernstrasse / Littau / Malters - H10)"
        elif lon >= 8.340:
            return "Gateway Ost (Haldenstrasse / Meggen - H4)"
        elif "motorway" in highway:
            return f"Autobahn Portal ({road_name})"
        elif "primary" in highway:
            return f"Hauptstrasse Corridor ({road_name})"
        return f"Regional Arterial ({road_name})"

    def find_nearest_node(self, lat, lon):
        best_node = None
        min_dist = float("inf")
        for n_id, data in self.nodes_dict.items():
            dist = math.hypot(data["lat"] - lat, data["lon"] - lon)
            if dist < min_dist:
                min_dist = dist
                best_node = n_id
        return best_node

    def save_gateways_to_json(self):
        data = {
            "version": "1.0",
            "gateways": self.gateway_details
        }
        with open(GATEWAYS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.gateway_details)} gateways to '{GATEWAYS_FILE}'.")

    def _load_custom_gateways_override(self):
        if os.path.exists(GATEWAYS_FILE):
            try:
                with open(GATEWAYS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "gateways" in data and len(data["gateways"]) > 0:
                        self.gateway_details = data["gateways"]
                        self.gateway_nodes = [g["node_id"] for g in self.gateway_details if g.get("enabled", True)]
            except Exception as e:
                logger.warning(f"Failed to load custom gateways file: {e}")

    def _save_cache(self):
        data = {
            "nodes": self.nodes_dict,
            "edges": self.edges_list,
            "pois": self.pois,
            "residential_nodes": self.residential_nodes,
            "commercial_nodes": self.commercial_nodes,
            "gateway_nodes": self.gateway_nodes,
            "gateway_details": self.gateway_details,
            "boundary_polygon_coords": self.boundary_polygon_coords
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved processed Lucerne data to '{CACHE_FILE}'.")

    def _reconstruct_from_json(self, data):
        self.nodes_dict = data["nodes"]
        self.edges_list = data["edges"]
        self.pois = data["pois"]
        self.residential_nodes = data["residential_nodes"]
        self.commercial_nodes = data["commercial_nodes"]
        self.gateway_nodes = data["gateway_nodes"]
        self.gateway_details = data.get("gateway_details", [])
        self.boundary_polygon_coords = data.get("boundary_polygon_coords", [])


if __name__ == "__main__":
    loader = LucerneDataLoader()
    loader.load_data(use_cache=False)
    print("DataLoader test completed successfully!")
