import os
import json
import logging
import math
import time
from datetime import datetime, timezone
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
# data/gateways.json is a reference snapshot of the gateways the default study area produced
# (OSM data of September 2026). The app never reads or writes it: gateways are always derived
# from the cached network, and custom gateways added in the UI live in memory only.

# Bumped whenever the meaning of a cached field changes, so an existing cache built by an older
# version is not silently reused. v2: `lanes` is per-direction. v3: merged OSM tags resolved
# deterministically (min maxspeed, highest road class) instead of by arbitrary list position.
CACHE_SCHEMA_VERSION = 3

# Relative weight per OSM road class, used to rank merged tags and to weight gateways.
# UNVERIFIED PLACEHOLDER VALUES, NOT AUTHORITATIVE.
HIGHWAY_WEIGHTS = {
    'motorway': 10.0, 'motorway_link': 8.0,
    'trunk': 8.0, 'trunk_link': 7.0,
    'primary': 6.0, 'primary_link': 5.0,
    'secondary': 4.0, 'secondary_link': 3.0,
    'tertiary': 2.0
}

DEFAULT_AOI_COORDS = [
    [47.004857194771745, 8.299827575683596],
    [47.007665915999446, 8.312015533447267],
    [46.995727830829125, 8.33141326904297],
    [47.0100064042086, 8.350982666015627],
    [47.0275567967975, 8.361282348632814],
    [47.046504741498126, 8.38909149169922],
    [47.05293615577914, 8.381195068359377],
    [47.05878222307229, 8.37364196777344],
    [47.06801724679478, 8.374714851379396],
    [47.07429996581871, 8.37385654449463],
    [47.083616572472536, 8.371067047119142],
    [47.093081429668786, 8.365745544433596],
    [47.098046885708555, 8.359308242797853],
    [47.10258672285211, 8.353300094604494],
    [47.104923229559226, 8.34617614746094],
    [47.101214445578854, 8.332056999206545],
    [47.10616586910025, 8.313817977905275],
    [47.10464730447498, 8.297939300537111],
    [47.0946587423539, 8.28171730041504],
    [47.09103669554458, 8.270645141601564],
    [47.087063844818566, 8.26000213623047],
    [47.08057811358643, 8.256053924560549],
    [47.055795027605704, 8.243608474731447],
    [47.03802000005698, 8.250560760498049],
    [47.03638252856205, 8.256568908691408],
    [47.02433387203582, 8.26249122619629],
    [47.01017615051699, 8.280086517333986],
    [47.004851408021956, 8.299741744995119],
    [47.004857194771745, 8.299827575683596]
]

# Gateway weights are the road-class weights in HIGHWAY_WEIGHTS, adjusted for a few named
# corridors below. UNVERIFIED PLACEHOLDER VALUES, NOT AUTHORITATIVE.
# The multipliers were picked by hand from figures found in quick web searches; they are not
# calibrated against ASTRA or cantonal traffic counts.
NAMED_CORRIDOR_MULTIPLIERS = {
    'A2': 1.5,
    'A14': 1.2,
    'Haldenstrasse': 1.3,   # Major eastbound arterial to Meggen/Küssnacht
    'Zürichstrasse': 1.1,   # Federal road to Ebikon
    'Maihofstrasse': 1.1,   # Important access to eastern Lucerne
    'Baselstrasse': 1.0,    # Westbound to Littau/Malters
    'Bernstrasse': 1.0,     # Southwest to Kriens
    'Seetalstrasse': 1.1,   # Seetalplatz corridor
    'Ostring': 0.9,
    'Spitalstrasse': 0.9,
}

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
        self.provenance = {}
        self.poi_source = "unknown"

    def load_data(self, use_cache=True, allow_fetch=True):
        """Load the road network.

        By default a missing cache triggers a live OpenStreetMap fetch. Pass allow_fetch=False to
        fail loudly instead, so a batch run can never silently pick up a different network than
        the one it was calibrated against.
        """
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
                    logger.info(f"Network snapshot: {self.describe_provenance()}")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Re-fetching from OpenStreetMap...")

        if not allow_fetch:
            raise RuntimeError(
                f"No usable network cache at '{CACHE_FILE}' and allow_fetch=False. "
                f"Build one first with: python -m src.data_loader --rebuild"
            )

        logger.info("Fetching expanded master regional road network (Lucerne + outer ring)...")
        logger.info("This queries the live OpenStreetMap Overpass API and typically takes 3-6 minutes.")

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
        # No silent fallback: a failed multi-place query used to fall back to the city of Lucerne
        # alone (~1,200 nodes, 2 gateways instead of ~4,200 nodes, ~32 gateways) while still
        # reporting 11 municipalities. Overpass failures are usually transient, so retry and
        # then stop with a clear error instead of building a much smaller network.
        self.graph = self._fetch_graph_with_retry(places)

        logger.info(f"Expanded master network retrieved: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges.")

        # Record which OSM snapshot this network came from. OSM changes continuously, so two
        # rebuilds weeks apart produce different networks (an earlier snapshot of this area gave
        # 36 gateways where a later one gave 33, with several speed limits changed). Without a
        # recorded snapshot, results are not comparable across rebuilds.
        self.provenance = {
            "source": "OpenStreetMap via OSMnx graph_from_place",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "osmnx_version": getattr(ox, "__version__", "unknown"),
            "places": places,
            "network_type": "drive",
            "simplify": True,
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
        }

        self._extract_network_structure()
        self._fetch_pois_and_landuse()
        self.provenance["poi_source"] = self.poi_source
        self.provenance["poi_count"] = len(self.pois)
        self._load_aoi_polygon_file()
        self.apply_aoi_clipping_and_gateways()
        self._save_cache()
        return True

    @staticmethod
    def _fetch_graph_with_retry(places, attempts=3, wait_sec=20):
        """Fetch the drive network for all places, retrying transient Overpass failures.

        Raises RuntimeError after the last attempt rather than returning a smaller network.
        """
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return ox.graph_from_place(places, network_type="drive", simplify=True)
            except Exception as e:  # Overpass/Nominatim errors surface as several exception types
                last_error = e
                logger.warning(f"OSM fetch attempt {attempt}/{attempts} failed: {e}")
                if attempt < attempts:
                    time.sleep(wait_sec * attempt)
        raise RuntimeError(
            f"Could not fetch the road network for {len(places)} places from OpenStreetMap after "
            f"{attempts} attempts (last error: {last_error}). The Overpass API is probably busy; "
            f"try again later with: python -m src.data_loader --rebuild"
        )

    @staticmethod
    def _first(value, default=None):
        """OSM tags arrive as a scalar, or as a list when simplification merged several ways.

        Taking element [0] of a merged list is NOT reproducible: the list order follows OSMnx's
        traversal order, which varies between processes. Two rebuilds from the very same OSM data
        produced 187 edges with different speed limits, which in turn changed how many boundary
        gateways the >30 km/h rule found (33 vs 32 vs 35). Sorting first makes the pick stable.
        """
        if isinstance(value, list):
            if not value:
                return default
            return sorted(value, key=str)[0]
        return value if value is not None else default

    @staticmethod
    def _merged_maxspeed(value, default=50.0) -> float:
        """Speed limit for a simplified edge that may span several OSM ways.

        The most restrictive limit along the merged path governs it, and taking the minimum is
        deterministic regardless of the order OSMnx merged the ways in.
        """
        candidates = value if isinstance(value, list) else [value]
        parsed = []
        for raw in candidates:
            if raw is None:
                continue
            try:
                parsed.append(float(str(raw).replace(" km/h", "").replace("mph", "").strip()))
            except (ValueError, TypeError):
                continue
        return min(parsed) if parsed else default

    @staticmethod
    def _merged_highway(value, default="unclassified") -> str:
        """Road class for a merged edge: the highest class present, ranked by HIGHWAY_WEIGHTS.

        A corridor that is part primary and part secondary behaves like a primary, and ranking by
        an explicit hierarchy is deterministic where list order is not.
        """
        candidates = [v for v in (value if isinstance(value, list) else [value]) if v]
        if not candidates:
            return default
        return max(sorted(set(candidates)), key=lambda h: HIGHWAY_WEIGHTS.get(h, 1.0))

    def _resolve_directional_lanes(self, data) -> int:
        """Lane count for ONE direction of travel.

        In OSM, a bare `lanes=*` on a two-way road counts both directions, but OSMnx copies the
        tag verbatim onto each directed edge. Taking it at face value doubled the capacity of
        every two-way street: 1817 edges in the Lucerne extract carried `lanes>=2`, giving
        residential streets like Klosterstrasse 1200 veh/h per direction. `lanes:forward` and
        `lanes:backward` are authoritative where present; otherwise a bare count on a two-way
        road is halved.
        """
        reversed_flag = self._first(data.get("reversed"), False)
        directional_key = "lanes:backward" if reversed_flag else "lanes:forward"
        directional = self._first(data.get(directional_key))
        if directional is not None:
            try:
                return max(1, int(float(directional)))
            except (ValueError, TypeError):
                pass

        lanes_raw = self._first(data.get("lanes"), 1)
        try:
            total_lanes = max(1, int(float(lanes_raw)))
        except (ValueError, TypeError):
            return 1

        oneway = self._first(data.get("oneway"), False)
        is_oneway = oneway in (True, "yes", "true", "1", 1)
        if is_oneway:
            return total_lanes
        # Two-way road with only a combined count: split it across the directions.
        return max(1, total_lanes // 2)

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
            maxspeed = self._merged_maxspeed(data.get("maxspeed"), default=50.0)
            lanes = self._resolve_directional_lanes(data)
            highway = self._merged_highway(data.get("highway"))
            name = self._first(data.get("name"), f"Road {u}-{v}")

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
        self.poi_source = "osm"
        try:
            # Note: POIs are only queried for the city of Lucerne, not the other 10 municipalities.
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
        except Exception as e:
            logger.warning(f"POI query failed ({e}); using the built-in fallback landmark list.")
            self._add_fallback_pois()
            self.poi_source = "fallback_list"

        if len(self.pois) == 0:
            self._add_fallback_pois()
            self.poi_source = "fallback_list"

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
        # Used only when the OSM POI query fails. Hand-entered approximate coordinates.
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
            # Road-class weight (unverified placeholder values, see HIGHWAY_WEIGHTS)
            weight = HIGHWAY_WEIGHTS.get(highway, 4.0)
            road_name = edge["name"]

            # Apply the named-corridor multiplier (unverified placeholder values)
            for corridor_name, multiplier in NAMED_CORRIDOR_MULTIPLIERS.items():
                if corridor_name.lower() in road_name.lower():
                    weight = round(weight * multiplier, 1)
                    break

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

    def find_nearest_node(self, lat, lon):
        best_node = None
        min_dist = float("inf")
        for n_id, data in self.nodes_dict.items():
            dist = math.hypot(data["lat"] - lat, data["lon"] - lon)
            if dist < min_dist:
                min_dist = dist
                best_node = n_id
        return best_node

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

    def describe_provenance(self) -> str:
        """One-line summary of which OSM snapshot the loaded network came from."""
        if not self.provenance:
            return "unknown snapshot (cache predates provenance tracking; rebuild to record it)"
        p = self.provenance
        return (f"OSM fetched {p.get('fetched_at_utc', '?')} "
                f"via OSMnx {p.get('osmnx_version', '?')}, "
                f"{len(p.get('places', []))} municipalities, "
                f"{p.get('nodes', '?')} nodes / {p.get('edges', '?')} edges, "
                f"POIs from {p.get('poi_source', '?')}")

    def _save_cache(self):
        data = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "provenance": self.provenance,
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
        cached_version = data.get("cache_schema_version", 1)
        if cached_version != CACHE_SCHEMA_VERSION:
            raise ValueError(
                f"Cache schema v{cached_version} is stale (expected v{CACHE_SCHEMA_VERSION}); "
                f"lane counts and capacities would be wrong."
            )
        self.provenance = data.get("provenance", {})
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
    import argparse

    parser = argparse.ArgumentParser(description="Build or inspect the Lucerne network cache.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force a fresh OpenStreetMap fetch, overwriting the existing cache.")
    args = parser.parse_args()

    loader = LucerneDataLoader()
    loader.load_data(use_cache=not args.rebuild)
    print(f"Nodes: {len(loader.nodes_dict)}  Edges (master): {len(loader.all_edges_list)}  "
          f"Edges (AOI): {len(loader.edges_list)}  POIs: {len(loader.pois)}  "
          f"Gateways: {len(loader.gateway_details)}")
    print(f"Snapshot: {loader.describe_provenance()}")
