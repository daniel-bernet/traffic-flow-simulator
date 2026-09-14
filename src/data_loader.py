import os
import json
import logging
import math
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np
from shapely.geometry import Point, Polygon, MultiPolygon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataLoader")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CACHE_FILE = os.path.join(DATA_DIR, "lucerne_data_cache.json")

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
        
    def load_data(self, use_cache=True):
        os.makedirs(DATA_DIR, exist_ok=True)
        
        if use_cache and os.path.exists(CACHE_FILE):
            logger.info("Loading cached Lucerne network & POI data...")
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._reconstruct_from_json(data)
                    logger.info(f"Loaded {len(self.nodes_dict)} nodes, {len(self.edges_list)} edges, "
                                f"{len(self.pois)} POIs, {len(self.gateway_nodes)} gateways from cache.")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Re-fetching from OpenStreetMap...")

        logger.info("Fetching expanded Lucerne regional road network & arterial portals...")
        
        try:
            ox.settings.use_cache = True
            ox.settings.log_console = False
        except AttributeError:
            pass

        places = ["Lucerne, Switzerland", "Ebikon, Switzerland", "Emmen, Switzerland", "Kriens, Switzerland"]
        try:
            self.graph = ox.graph_from_place(places, network_type="drive", simplify=True)
        except Exception as e:
            logger.warning(f"ox.graph_from_place multi-place failed: {e}. Falling back to Lucerne place query...")
            self.graph = ox.graph_from_place(self.place_name, network_type="drive", simplify=True)

        logger.info(f"Expanded network retrieved: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")
        
        try:
            self.graph_proj = ox.project_graph(self.graph, to_crs="EPSG:2056")
        except Exception:
            self.graph_proj = self.graph

        self._extract_network_structure()
        self._fetch_pois_and_landuse()
        self._identify_gateways()
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

                nearest_node = self._find_nearest_node(lat, lon)
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
            {"name": "Luzerner Kantonsspital", "category": "Public Facility / Hospital", "lat": 47.0580, "lon": 8.3005},
            {"name": "Emmen Center / Shopping Mall", "category": "Supermarket/Shopping", "lat": 47.0710, "lon": 8.2890},
            {"name": "Verkehrshaus der Schweiz", "category": "Tourism / Hotel", "lat": 47.0531, "lon": 8.3356}
        ]
        for item in fallback_landmarks:
            nearest = self._find_nearest_node(item["lat"], item["lon"])
            if nearest:
                item["node_id"] = nearest
                self.pois.append(item)
                self.nodes_dict[nearest]["is_poi"] = True
                self.nodes_dict[nearest]["weight_dest"] += 15.0

    def _identify_gateways(self):
        """
        Identify high-capacity gateway portals at the spatial boundary of the road network,
        weighted by road hierarchy (Motorway > Primary Hauptstrasse > Secondary > Local).
        Specifically includes corridors like Maihof/Ebikon, Seetalplatz/Emmen, A2 Autobahn, Horw, Meggen.
        """
        lats = [n["lat"] for n in self.nodes_dict.values()]
        lons = [n["lon"] for n in self.nodes_dict.values()]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        lat_span = max_lat - min_lat
        lon_span = max_lon - min_lon
        
        # Perimeter buffer zone: 10% from outer boundaries
        thresh_lat = 0.10 * lat_span
        thresh_lon = 0.10 * lon_span

        # Map connecting road types for each node
        node_highways = {}
        for edge in self.edges_list:
            u, v = edge["u"], edge["v"]
            h_type = edge["highway"]
            for n_id in [u, v]:
                if n_id not in node_highways:
                    node_highways[n_id] = set()
                node_highways[n_id].add(h_type)

        self.gateway_nodes = []
        self.gateway_details = []

        for n_id, n in self.nodes_dict.items():
            is_perimeter = (n["lat"] <= min_lat + thresh_lat or n["lat"] >= max_lat - thresh_lat or
                            n["lon"] <= min_lon + thresh_lon or n["lon"] >= max_lon - thresh_lon)
            
            if not is_perimeter:
                continue

            hw_types = node_highways.get(n_id, set())
            
            # Determine gateway weight and corridor name based on road type & geographic direction
            weight = 1.0
            portal_name = "Local Gateway Portal"

            if any(h in hw_types for h in ["motorway", "motorway_link", "trunk", "trunk_link"]):
                weight = 10.0
                portal_name = "Highway Portal (A2 / A14)"
            elif any(h in hw_types for h in ["primary", "primary_link"]):
                weight = 6.0
                portal_name = "Hauptstrasse Corridor"
            elif any(h in hw_types for h in ["secondary", "secondary_link"]):
                weight = 3.0
                portal_name = "Regional Arterial"
            else:
                weight = 1.0  # Minor street

            # Named corridor identification based on coordinates
            lat, lon = n["lat"], n["lon"]
            if lat >= max_lat - thresh_lat and lon >= 8.310:
                portal_name = "Gateway Maihof / Ebikon (Zürichstrasse)"
                weight = max(weight, 7.0)
            elif lat >= max_lat - thresh_lat and lon < 8.300:
                portal_name = "Gateway Seetalplatz / Emmen"
                weight = max(weight, 8.0)
            elif lon <= min_lon + thresh_lon:
                portal_name = "Gateway West (Littau / Malters / Bernstrasse)"
                weight = max(weight, 6.0)
            elif lat <= min_lat + thresh_lat and lon <= 8.310:
                portal_name = "Gateway Süd (Kriens / Horw / A2 Süd)"
                weight = max(weight, 8.0)
            elif lon >= max_lon - thresh_lon:
                portal_name = "Gateway Ost (Haldenstrasse / Meggen)"
                weight = max(weight, 6.0)

            n["is_gateway"] = True
            n["gateway_weight"] = weight
            n["gateway_name"] = portal_name
            
            self.gateway_nodes.append(n_id)
            self.gateway_details.append({
                "id": n_id,
                "name": portal_name,
                "weight": weight,
                "lat": lat,
                "lon": lon
            })

        logger.info(f"Identified {len(self.gateway_nodes)} hierarchical gateway portals.")

    def _find_nearest_node(self, lat, lon):
        best_node = None
        min_dist = float("inf")
        for n_id, data in self.nodes_dict.items():
            dist = math.hypot(data["lat"] - lat, data["lon"] - lon)
            if dist < min_dist:
                min_dist = dist
                best_node = n_id
        return best_node

    def _save_cache(self):
        data = {
            "nodes": self.nodes_dict,
            "edges": self.edges_list,
            "pois": self.pois,
            "residential_nodes": self.residential_nodes,
            "commercial_nodes": self.commercial_nodes,
            "gateway_nodes": self.gateway_nodes,
            "gateway_details": self.gateway_details
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


if __name__ == "__main__":
    loader = LucerneDataLoader()
    loader.load_data(use_cache=False)
    print("DataLoader test completed successfully!")
