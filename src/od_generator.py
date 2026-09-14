import random
import logging
import networkx as nx
from src.vehicle import TrafficClass, Vehicle

logger = logging.getLogger("ODGenerator")

class ODGenerator:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.nx_graph = self._build_networkx_graph()
        self.shortest_paths_cache = {}

    def _build_networkx_graph(self):
        G = nx.DiGraph()
        for node_id, data in self.data_loader.nodes_dict.items():
            G.add_node(node_id, lat=data["lat"], lon=data["lon"])
            
        for edge in self.data_loader.edges_list:
            u = edge["u"]
            v = edge["v"]
            weight = edge["free_flow_time"]
            G.add_edge(u, v, id=edge["edge_id"], weight=weight, length=edge["length"], maxspeed=edge["maxspeed"])
        return G

    def generate_vehicle(self, vehicle_id: str, flow_type="internal_internal", class_override=None) -> Vehicle:
        if not class_override:
            rand_val = random.random()
            if rand_val < 0.65:
                traffic_class = TrafficClass.PERSONAL
            elif rand_val < 0.80:
                traffic_class = TrafficClass.TOURISM
            elif rand_val < 0.92:
                traffic_class = TrafficClass.LOGISTICS
            else:
                traffic_class = TrafficClass.BUS
        else:
            traffic_class = class_override

        origin_node, dest_node = self._select_od_pair(flow_type, traffic_class)
        if not origin_node or not dest_node or origin_node == dest_node:
            return None

        route_edges = self.get_route_edges(origin_node, dest_node)
        if not route_edges or len(route_edges) == 0:
            return None

        vehicle = Vehicle(
            vehicle_id=vehicle_id,
            vehicle_class=traffic_class,
            origin_id=origin_node,
            destination_id=dest_node,
            route_edges=route_edges
        )
        return vehicle

    def _select_weighted_gateway(self):
        """Pick a gateway node randomly, weighted by road hierarchy capacity (gateway_weight)."""
        gateways = self.data_loader.gateway_nodes
        if not gateways:
            return None
        weights = [self.data_loader.nodes_dict[g_id].get("gateway_weight", 1.0) for g_id in gateways if g_id in self.data_loader.nodes_dict]
        if not weights:
            return random.choice(gateways)
        return random.choices(gateways, weights=weights, k=1)[0]

    def _select_od_pair(self, flow_type: str, traffic_class: TrafficClass):
        nodes_dict = self.data_loader.nodes_dict
        res_nodes = self.data_loader.residential_nodes or list(nodes_dict.keys())
        comm_nodes = self.data_loader.commercial_nodes or list(nodes_dict.keys())
        poi_nodes = [poi["node_id"] for poi in self.data_loader.pois if poi.get("node_id")]

        if flow_type == "inflow":
            # Entry from Outside -> Inside
            origin = self._select_weighted_gateway()
            if traffic_class == TrafficClass.TOURISM and poi_nodes:
                dest = random.choice(poi_nodes)
            elif traffic_class == TrafficClass.LOGISTICS:
                dest = random.choice(comm_nodes)
            else:
                dest = random.choice(comm_nodes if random.random() < 0.7 else res_nodes)
        elif flow_type == "outflow":
            # Inside -> Outside Exit
            dest = self._select_weighted_gateway()
            origin = random.choice(res_nodes if random.random() < 0.7 else comm_nodes)
        else: # internal_internal
            if traffic_class == TrafficClass.TOURISM and poi_nodes:
                origin = random.choice(res_nodes)
                dest = random.choice(poi_nodes)
            elif traffic_class == TrafficClass.LOGISTICS:
                origin = self._select_weighted_gateway() or random.choice(comm_nodes)
                dest = random.choice(comm_nodes)
            elif traffic_class == TrafficClass.BUS and poi_nodes:
                origin = random.choice(poi_nodes)
                dest = random.choice([p for p in poi_nodes if p != origin] or comm_nodes)
            else:
                origin = random.choice(res_nodes)
                dest = random.choice(comm_nodes if random.random() < 0.75 else poi_nodes)

        return origin, dest

    def get_route_edges(self, origin_node: str, dest_node: str, current_blocked_edges=None):
        cache_key = f"{origin_node}_{dest_node}"
        if not current_blocked_edges and cache_key in self.shortest_paths_cache:
            return self.shortest_paths_cache[cache_key]

        try:
            if current_blocked_edges and len(current_blocked_edges) > 0:
                def weight_fn(u, v, d):
                    if d.get("id") in current_blocked_edges:
                        return 1e9
                    return d.get("weight", 1.0)
                node_path = nx.shortest_path(self.nx_graph, source=origin_node, target=dest_node, weight=weight_fn)
            else:
                node_path = nx.shortest_path(self.nx_graph, source=origin_node, target=dest_node, weight="weight")

            edge_ids = []
            for i in range(len(node_path) - 1):
                u, v = node_path[i], node_path[i+1]
                edge_data = self.nx_graph.get_edge_data(u, v)
                if edge_data and "id" in edge_data:
                    edge_ids.append(edge_data["id"])

            if not current_blocked_edges:
                self.shortest_paths_cache[cache_key] = edge_ids
            return edge_ids
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
