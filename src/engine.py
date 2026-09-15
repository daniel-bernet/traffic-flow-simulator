import time
import math
import logging
import random
from collections import defaultdict
from src.vehicle import TrafficClass, Vehicle
from src.od_generator import ODGenerator
from src.bus_transit import BusTransitManager

logger = logging.getLogger("SimulationEngine")

class TrafficSimulationEngine:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.od_generator = ODGenerator(data_loader)
        self.bus_transit_manager = BusTransitManager(data_loader, self.od_generator)
        
        self.edges_dict = {edge["edge_id"]: edge for edge in data_loader.edges_list}
        self.active_vehicles = {}  # vehicle_id -> Vehicle
        self.completed_trips = []  # list of trip travel times
        
        self.blocked_edges = set()  # set of blocked edge_ids
        self.vehicle_id_counter = 0
        self.sim_time = 0.0  # simulation seconds
        
        # User tweakable parameters
        self.params = {
            "spawn_rate": 2.0,           # Vehicles spawned per second
            "sim_speed_multiplier": 1.0, # 1x to 10x fast forward
            "flow_internal_ratio": 0.50, # 50% internal-internal
            "flow_inflow_ratio": 0.25,   # 25% outside -> inside
            "flow_outflow_ratio": 0.25,  # 25% inside -> outside
            "class_personal_pct": 60,
            "class_tourism_pct": 20,
            "class_logistics_pct": 10,
            "class_bus_pct": 10,
            "max_active_vehicles": 1500  # Cap for performance
        }

        # Dynamic Edge Status (vehicle count, PCE total, current speed, V/C ratio)
        self.edge_stats = {}
        self._init_edge_stats()

    def _init_edge_stats(self):
        self.edge_stats = {}
        for edge_id, edge in self.edges_dict.items():
            self.edge_stats[edge_id] = {
                "active_pce": 0.0,
                "vehicle_count": 0,
                "vc_ratio": 0.0,
                "current_speed": edge["maxspeed"] / 3.6,
                "color": "#2ecc71" # Green
            }

    def reload_aoi(self):
        """Hot-reload network graph, edges, and gateways when AOI polygon changes."""
        self.edges_dict = {edge["edge_id"]: edge for edge in self.data_loader.edges_list}
        self.od_generator.reload_network_graph()
        self.bus_transit_manager.reload_network()
        self.reset()
        logger.info(f"Engine hot-reloaded AOI: {len(self.edges_dict)} active edges.")

    def reload_gateways(self, gateway_details):
        self.od_generator.reload_gateways(gateway_details)

    def set_parameters(self, new_params: dict):
        """Update simulation parameters on the fly."""
        for key, val in new_params.items():
            if key in self.params:
                self.params[key] = float(val)
        logger.info(f"Updated simulation parameters: {self.params}")

    def toggle_blocked_edge(self, edge_id: str):
        """User click action: block/unblock a road segment."""
        if edge_id in self.blocked_edges:
            self.blocked_edges.remove(edge_id)
            logger.info(f"Unblocked edge: {edge_id}")
        else:
            self.blocked_edges.add(edge_id)
            logger.info(f"Blocked edge: {edge_id}")
            # Trigger dynamic rerouting for vehicles currently aiming at or on this edge
            self._reroute_affected_vehicles(edge_id)

    def _reroute_affected_vehicles(self, blocked_edge_id: str):
        for v_id, veh in self.active_vehicles.items():
            if blocked_edge_id in veh.route_edges[veh.current_edge_idx:]:
                new_route = self.od_generator.get_route_edges(
                    origin_node=veh.origin_id,
                    dest_node=veh.destination_id,
                    current_blocked_edges=self.blocked_edges
                )
                if new_route:
                    veh.route_edges = new_route
                    veh.current_edge_idx = 0
                    veh.distance_on_edge = 0.0

    def reset(self):
        self.active_vehicles.clear()
        self.completed_trips.clear()
        self.sim_time = 0.0
        self.vehicle_id_counter = 0
        self.blocked_edges.clear()
        self._init_edge_stats()

    def tick(self, dt=1.0):
        """Execute one simulation tick of dt seconds."""
        effective_dt = dt * self.params["sim_speed_multiplier"]
        self.sim_time += effective_dt

        # 1. Update Edge Congestion & Speeds using BPR Formula
        self._update_edge_congestion()

        # 2. Advance Active Vehicles
        arrived_ids = []
        for veh_id, vehicle in list(self.active_vehicles.items()):
            curr_edge_id = vehicle.current_edge_id
            if not curr_edge_id or curr_edge_id in self.blocked_edges:
                # Vehicle on blocked edge or lost path -> try advance or remove
                if not vehicle.advance_to_next_edge():
                    continue
                else:
                    arrived_ids.append(veh_id)
                    continue

            edge_dict = self.edges_dict.get(curr_edge_id)
            curr_speed = self.edge_stats[curr_edge_id]["current_speed"]
            
            edge_finished = vehicle.update_position(edge_dict, dt=effective_dt, current_edge_speed=curr_speed)
            if edge_finished:
                arrived = vehicle.advance_to_next_edge()
                if arrived:
                    arrived_ids.append(veh_id)

        # 3. Clean up Arrived Vehicles
        for veh_id in arrived_ids:
            veh = self.active_vehicles.pop(veh_id, None)
            if veh:
                self.completed_trips.append(veh.total_travel_time)

        # 4. Spawn New Standard Vehicles & Timetable Transit Buses
        self._spawn_vehicles(effective_dt)
        new_transit_buses = self.bus_transit_manager.tick(effective_dt, self.active_vehicles)
        for bus in new_transit_buses:
            self.active_vehicles[bus.id] = bus

        return self.get_simulation_state()

    def _update_edge_congestion(self):
        # Reset edge vehicle counters
        edge_counts = defaultdict(int)
        edge_pce = defaultdict(float)

        for veh in self.active_vehicles.values():
            e_id = veh.current_edge_id
            if e_id:
                edge_counts[e_id] += 1
                edge_pce[e_id] += veh.props["pce"]

        for edge_id, edge in self.edges_dict.items():
            cnt = edge_counts[edge_id]
            pce = edge_pce[edge_id]
            capacity = edge["capacity"]
            
            if edge_id in self.blocked_edges:
                vc_ratio = 5.0
                curr_speed = 0.5  # Almost stopped
                color = "#8e44ad"  # Purple/Black for blocked
            else:
                # BPR Formula: T = T0 * (1 + 0.15 * (V/C)^4)
                # Max capacity reference per tick
                vc_ratio = pce / max(5.0, capacity * 0.05)
                bpr_delay_factor = 1.0 + 0.15 * math.pow(vc_ratio, 4)
                free_speed = edge["maxspeed"] / 3.6
                curr_speed = max(2.0, free_speed / bpr_delay_factor)

                # Color coding
                if vc_ratio < 0.5:
                    color = "#2ecc71" # Green
                elif vc_ratio < 0.8:
                    color = "#f1c40f" # Yellow
                elif vc_ratio < 1.1:
                    color = "#e67e22" # Orange
                else:
                    color = "#e74c3c" # Red (Congested)

            self.edge_stats[edge_id] = {
                "active_pce": round(pce, 1),
                "vehicle_count": cnt,
                "vc_ratio": round(vc_ratio, 2),
                "current_speed": round(curr_speed, 2),
                "color": color
            }

    def _spawn_vehicles(self, dt):
        if len(self.active_vehicles) >= self.params["max_active_vehicles"]:
            return

        spawn_chance = self.params["spawn_rate"] * dt
        num_to_spawn = int(spawn_chance)
        if random.random() < (spawn_chance - num_to_spawn):
            num_to_spawn += 1

        for _ in range(num_to_spawn):
            self.vehicle_id_counter += 1
            v_id = f"veh_{self.vehicle_id_counter}"

            # Flow selection
            rand_flow = random.random()
            if rand_flow < self.params["flow_internal_ratio"]:
                flow_type = "internal_internal"
            elif rand_flow < self.params["flow_internal_ratio"] + self.params["flow_inflow_ratio"]:
                flow_type = "inflow"
            else:
                flow_type = "outflow"

            # Class selection
            rand_class = random.randint(1, 100)
            if rand_class <= self.params["class_personal_pct"]:
                cls_override = TrafficClass.PERSONAL
            elif rand_class <= self.params["class_personal_pct"] + self.params["class_tourism_pct"]:
                cls_override = TrafficClass.TOURISM
            elif rand_class <= self.params["class_personal_pct"] + self.params["class_tourism_pct"] + self.params["class_logistics_pct"]:
                cls_override = TrafficClass.LOGISTICS
            else:
                cls_override = TrafficClass.BUS

            vehicle = self.od_generator.generate_vehicle(
                vehicle_id=v_id,
                flow_type=flow_type,
                class_override=cls_override
            )
            if vehicle:
                self.active_vehicles[v_id] = vehicle

    def get_simulation_state(self):
        """Returns JSON-serializable state dict for Web Socket transmission."""
        # Top 5 Congested Chokepoints
        sorted_chokepoints = sorted(
            [{"edge_id": k, "name": self.edges_dict[k]["name"], "vc_ratio": v["vc_ratio"], "count": v["vehicle_count"]}
             for k, v in self.edge_stats.items() if k not in self.blocked_edges],
            key=lambda x: x["vc_ratio"],
            reverse=True
        )[:5]

        # Vehicle points payload
        vehicle_points = [v.to_dict() for v in self.active_vehicles.values()]

        # Edge congestion payload (only send changed/congested edges or active summary to keep WebSocket message lightweight)
        congested_edges = {
            k: {"vc": v["vc_ratio"], "color": v["color"]}
            for k, v in self.edge_stats.items()
            if v["vc_ratio"] >= 0.5 or k in self.blocked_edges
        }

        avg_travel_time = (sum(self.completed_trips) / len(self.completed_trips)) if self.completed_trips else 0.0

        # Environmental CO2 & Fuel Emissions Calculator
        co2_rate_kg_hr = 0.0
        fuel_rate_l_hr = 0.0

        for veh in self.active_vehicles.values():
            e_id = veh.current_edge_id
            if not e_id or e_id not in self.edge_stats:
                continue
            curr_speed_kmh = self.edge_stats[e_id]["current_speed"] * 3.6
            vc_ratio = self.edge_stats[e_id]["vc_ratio"]

            if veh.vehicle_class == TrafficClass.PERSONAL:
                base_co2, base_fuel = 0.14, 0.06
            elif veh.vehicle_class == TrafficClass.BUS:
                base_co2, base_fuel = 0.65, 0.26
            else: # LOGISTICS / TOURISM
                base_co2, base_fuel = 0.85, 0.35

            penalty = 1.0 + 1.2 * math.pow(min(3.0, vc_ratio), 2)
            dist_km = (curr_speed_kmh / 3600.0)

            co2_rate_kg_hr += base_co2 * dist_km * penalty * 3600.0
            fuel_rate_l_hr += base_fuel * dist_km * penalty * 3600.0

        return {
            "sim_time": round(self.sim_time, 1),
            "active_vehicles_count": len(self.active_vehicles),
            "completed_trips_count": len(self.completed_trips),
            "avg_travel_time_sec": round(avg_travel_time, 1),
            "co2_kg_hr": round(co2_rate_kg_hr, 1),
            "fuel_l_hr": round(fuel_rate_l_hr, 1),
            "vehicles": vehicle_points,
            "congested_edges": congested_edges,
            "blocked_edges": list(self.blocked_edges),
            "top_chokepoints": sorted_chokepoints,
            "bus_lines": self.bus_transit_manager.get_transit_state()
        }
