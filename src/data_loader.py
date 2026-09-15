import os
import json
import logging
import math
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
from shapely.geometry import Point, LineString, Polygon, MultiPoint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataLoader")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CACHE_FILE = os.path.join(DATA_DIR, "lucerne_data_cache.json")
AOI_FILE = os.path.join(DATA_DIR, "aoi_polygon.json")
GATEWAYS_FILE = os.path.join(DATA_DIR, "gateways.json")

HIGHWAY_WEIGHTS = {
    'motorway': 10.0, 'motorway_link': 8.0,
    'trunk': 8.0, 'trunk_link': 7.0,
    'primary': 6.0, 'primary_link': 5.0,
    'secondary': 4.0, 'secondary_link': 3.0,
    'tertiary': 2.0
}

DEFAULT_AOI_COORDS = [
    [47.070, 8.270], [47.075, 8.300], [47.065, 8.340], [47.045, 8.350],
    [47.030, 8.335], [47.020, 8.310], [47.025, 8.270], [47.045, 8.255],
    [47.070, 8.270]
]

class LucerneDataLoader:
    def __init__(self, place_name="Lucerne, Switzerland"):
        self.place_name = place_name
        self.graph = None
        self.nodes_dict = {}
        self.edges_list = []
        self.all_edges_list = []  # Unclipped master regional edge set
        self.pois = []
        self.residential_nodes = []
        self.commercial_nodes = []
        self.gateway_nodes = []
        self.gateway_details = []
        self.aoi_polygon_coords = DEFAULT_AOI_COORDS
        
    def load_data(self, use_cache=True):
        os.makedirs(DATA_DIR, exist_ok=True)
        
        if use_cache and os.path.exists(CACHE_FILE):
            logger.info("Loading cached Lucerne master network & POI data...")
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._reconstruct_from_json(data)
                    self._load_aoi_polygon_file()
                    self.apply_aoi_clipping_and_gateways()
                    logger.info(f"Loaded {len(self.nodes_dict)} master nodes, {len(self.edges_list)} active AOI edges, "
                                f"{len(self.pois)} POIs, {len(self.gateway_details)} AOI gateways.")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Re-fetching from OpenStreetMap...")

        logger.info("Fetching expanded master regional road network (Lucerne + outer ring)...")
        
        try:
            ox.settings.use_cache = True
            ox.settings.log_console = False
        except AttributeError:
            pass

        # Expanded master list including Lucerne + all outer ring municipalities
        places = [
            "Lucerne, Switzerland", "Ebikon, Switzerland", "Emmen, Switzerland", 
            "Kriens, Switzerland", "Horw, Switzerland", "Meggen, Switzerland", 
            "Adligenswil, Switzerland", "Dierikon, Switzerland", "Buchrain, Switzerland", 
            "Malters, Switzerland", "Rothenburg, Switzerland"
        ]
        try:
            self.graph = ox.graph_from_place(places, network_type="drive", simplify=True)
        except Exception as e:
            logger.warning(f"ox.graph_from_place multi-place failed: {e}. Falling back to regional place query...")
            self.graph = ox.graph_from_place(self.place_name, network_type="drive", simplify=True)

        logger.info(f"Expanded master network retrieved: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")

        self._extract_network_structure()
        self._fetch_pois_and_landuse()
        self._load_aoi_polygon_file()
        self.apply_aoi_clipping_and_gateways()
        self._save_cache()
        return True

    def _extract_network_structure(self):
        self.nodes_dict = {}
        for node, data in self.graph.nodes(data=True):
            lat = data.get("y", 0.0)
            lon = data.get("x", 0.0)
            highway_tag = data.get("highway", "")
            is_sig = (highway_tag == "traffic_signals") or ("traffic_signals" in str(data))

            self.nodes_dict[str(node)] = {
                "id": str(node),
                "lat": float(lat),
                "lon": float(lon),
                "weight_orig": 1.0,
                "weight_dest": 1.0,
                "is_gateway": False,
                "gateway_weight": 1.0,
                "gateway_name": "",
                "is_poi": False,
                "is_signalized": is_sig
            }

        self.all_edges_list = []
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
            self.all_edges_list.append(edge_dict)
            edge_id_counter += 1

        self.edges_list = list(self.all_edges_list)

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

    def apply_aoi_clipping_and_gateways(self, polygon_coords=None):
        """
        Clips road graph strictly inside user-defined AOI Polygon.
        Computes Gateways as directed edges crossing AOI border with speed > 30 km/h.
        Guarantees zero internal roundabouts or internal intersections become gateways.
        """
        if polygon_coords:
            self.aoi_polygon_coords = polygon_coords
            self._save_aoi_polygon_file()

        # Format polygon: Shapely expects (lon, lat)
        shapely_poly_coords = [(lon, lat) for lat, lon in self.aoi_polygon_coords]
        aoi_poly = Polygon(shapely_poly_coords)
        aoi_ring = aoi_poly.exterior

        # 1. Containment Test
        node_containment = {}
        for n_id, n_data in self.nodes_dict.items():
            pt = Point(n_data["lon"], n_data["lat"])
            node_containment[n_id] = "INSIDE" if aoi_poly.contains(pt) else "OUTSIDE"

        # 2. Graph Clipping: keep edges with at least 1 node inside AOI
        self.edges_list = [
            e for e in self.all_edges_list
            if node_containment.get(e["u"]) == "INSIDE" or node_containment.get(e["v"]) == "INSIDE"
        ]

        # 3. Gateway Boundary Crossing (> 30 km/h Rule)
        crossing_gateways = []
        for edge in self.edges_list:
            u_id, v_id = edge["u"], edge["v"]
            loc_u = node_containment.get(u_id, "OUTSIDE")
            loc_v = node_containment.get(v_id, "OUTSIDE")

            # Guaranteed Elimination: skip edges where both nodes are INSIDE
            if loc_u == loc_v:
                continue

            # Speed limit rule: ONLY roads with maxspeed > 30 km/h can be gateways
            if edge["maxspeed"] <= 30.0:
                continue

            direction = "INFLOW" if (loc_u == "OUTSIDE" and loc_v == "INSIDE") else "OUTFLOW"

            u_node = self.nodes_dict[u_id]
            v_node = self.nodes_dict[v_id]
            edge_line = LineString([(u_node["lon"], u_node["lat"]), (v_node["lon"], v_node["lat"])])

            intersection = edge_line.intersection(aoi_ring)
            if intersection.is_empty:
                lat_cross = v_node["lat"] if direction == "INFLOW" else u_node["lat"]
                lon_cross = v_node["lon"] if direction == "INFLOW" else u_node["lon"]
            elif isinstance(intersection, Point):
                lat_cross, lon_cross = intersection.y, intersection.x
            else:
                lat_cross, lon_cross = intersection.centroid.y, intersection.centroid.x

            target_node_id = v_id if direction == "INFLOW" else u_id
            highway = edge["highway"]
            weight = HIGHWAY_WEIGHTS.get(highway, 4.0)
            road_name = edge["name"]

            portal_name = f"AOI Gateway: {road_name} ({int(edge['maxspeed'])} km/h)"

            crossing_gateways.append({
                "edge_id": edge["edge_id"],
                "node_id": target_node_id,
                "direction": direction,
                "lat": lat_cross,
                "lon": lon_cross,
                "highway": highway,
                "road_name": road_name,
                "portal_name": portal_name,
                "maxspeed": edge["maxspeed"],
                "weight": weight
            })

        # 4. Cluster dual carriageway crossings within ~150m
        clustered = {}
        for c in crossing_gateways:
            key = f"{round(c['lat'], 3)}_{round(c['lon'], 3)}"
            if key not in clustered or c["weight"] > clustered[key]["weight"]:
                clustered[key] = {
                    "id": f"gw_aoi_{c['node_id']}",
                    "node_id": c["node_id"],
                    "name": c["portal_name"],
                    "corridor_type": c["highway"],
                    "lat": c["lat"],
                    "lon": c["lon"],
                    "weight": c["weight"],
                    "direction": "both",
                    "capacity_veh_per_hr": int(c["weight"] * 400),
                    "enabled": True,
                    "is_custom": False
                }

        # Preserve custom gateways added by user
        existing_custom = [g for g in self.gateway_details if g.get("is_custom", False)]
        self.gateway_details = list(clustered.values()) + existing_custom
        self.gateway_nodes = [g["node_id"] for g in self.gateway_details if g.get("enabled", True)]

        for n_id, n in self.nodes_dict.items():
            n["is_gateway"] = False

        for g in self.gateway_details:
            n_id = g["node_id"]
            if n_id in self.nodes_dict:
                self.nodes_dict[n_id]["is_gateway"] = g.get("enabled", True)
                self.nodes_dict[n_id]["gateway_weight"] = g.get("weight", 1.0)
                self.nodes_dict[n_id]["gateway_name"] = g.get("name", "")

        logger.info(f"Applied AOI clipping: {len(self.edges_list)} active edges, {len(self.gateway_details)} gateways (>30 km/h).")
        self.save_gateways_to_json()

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

    def _save_aoi_polygon_file(self):
        data = {
            "polygon": self.aoi_polygon_coords
        }
        with open(AOI_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_aoi_polygon_file(self):
        if os.path.exists(AOI_FILE):
            try:
                with open(AOI_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "polygon" in data and len(data["polygon"]) >= 3:
                        self.aoi_polygon_coords = data["polygon"]
            except Exception as e:
                logger.warning(f"Failed to load AOI file: {e}")

    def _save_cache(self):
        data = {
            "nodes": self.nodes_dict,
            "edges": self.all_edges_list,
            "pois": self.pois,
            "residential_nodes": self.residential_nodes,
            "commercial_nodes": self.commercial_nodes,
            "gateway_nodes": self.gateway_nodes,
            "gateway_details": self.gateway_details,
            "aoi_polygon_coords": self.aoi_polygon_coords
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved processed Lucerne data to '{CACHE_FILE}'.")

    def _reconstruct_from_json(self, data):
        self.nodes_dict = data["nodes"]
        self.all_edges_list = data["edges"]
        self.edges_list = list(self.all_edges_list)
        self.pois = data["pois"]
        self.residential_nodes = data["residential_nodes"]
        self.commercial_nodes = data["commercial_nodes"]
        self.gateway_nodes = data.get("gateway_nodes", [])
        self.gateway_details = data.get("gateway_details", [])
        self.aoi_polygon_coords = data.get("aoi_polygon_coords", DEFAULT_AOI_COORDS)


if __name__ == "__main__":
    loader = LucerneDataLoader()
    loader.load_data(use_cache=False)
    print("DataLoader AOI test completed successfully!")
