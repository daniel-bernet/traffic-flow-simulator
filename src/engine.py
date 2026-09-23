import time
import math
import logging
import random
from collections import defaultdict
from src.vehicle import TrafficClass, Vehicle
from src.od_generator import ODGenerator
from src.bus_transit import BusTransitManager
from src.traffic_signals import TrafficSignalManager
from src.parking import ParkingManager

logger = logging.getLogger("SimulationEngine")

class TrafficSimulationEngine:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.od_generator = ODGenerator(data_loader)
        self.bus_transit_manager = BusTransitManager(data_loader, self.od_generator)
        self.signal_manager = TrafficSignalManager(data_loader)
        self.parking_manager = ParkingManager(data_loader)
        
        self.edges_dict = {edge["edge_id"]: edge for edge in data_loader.edges_list}
        self.active_vehicles = {}  # vehicle_id -> Vehicle
        self.completed_trips = []  # list of trip travel times
        
        self.blocked_edges = set()  # set of blocked edge_ids
        self.vehicle_id_counter = 0
        self.sim_time = 0.0  # simulation seconds
        self.is_paused = False

        # Demand accounting. generate_vehicle() returns None for unroutable O-D pairs; those
        # used to vanish silently, so spawn_rate overstated the demand actually loaded onto the
        # network by ~25%. Both counters are reported in the state payload.
        self.dropped_spawns = 0   # requested but unroutable
        self.stranded_count = 0   # removed mid-trip because a closure cut off the destination
        
        # User tweakable parameters
        self.params = {
            "spawn_rate": 2.0,           # Vehicles spawned per second
            "sim_speed_multiplier": 1.0, # 0.25x to 10x
            "flow_internal_ratio": 0.50, # 50% internal-internal
            "flow_inflow_ratio": 0.25,   # 25% outside -> inside
            "flow_outflow_ratio": 0.25,  # 25% inside -> outside
            "class_personal_pct": 60,
            "class_tourism_pct": 20,
            "class_logistics_pct": 10,
            "class_bus_pct": 10,
            "max_active_vehicles": 3500  # Expanded cap for high realism & density
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
        self.signal_manager.reload_network()
        self.parking_manager.reload_network()
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

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        return self.is_paused

    def set_paused(self, paused: bool):
        self.is_paused = bool(paused)
        return self.is_paused

    def toggle_blocked_edge(self, edge_id: str):
        """User click action: block/unblock a road segment."""
        if edge_id in self.blocked_edges:
            self.blocked_edges.remove(edge_id)
            logger.info(f"Unblocked edge: {edge_id}")
        else:
            self.blocked_edges.add(edge_id)
            logger.info(f"Blocked edge: {edge_id}")
        # The route cache is keyed on O-D only, so it holds paths computed under the previous
        # closure set. Without this, newly spawned vehicles keep planning through closed roads.
        self.od_generator.invalidate_route_cache()
        self._reroute_affected_vehicles()

    def _reroute_affected_vehicles(self):
        """Reroute every vehicle whose remaining path crosses a closed edge.

        Rerouting starts from the vehicle's current position, not its origin. The previous
        implementation replanned from `origin_id` and reset `current_edge_idx` to 0, which
        teleported vehicles back to the start of their trip.
        """
        stranded = []
        for v_id, veh in self.active_vehicles.items():
            remaining = veh.route_edges[veh.current_edge_idx:]
            if not any(e in self.blocked_edges for e in remaining):
                continue
            if not self._replan_from_current_position(veh):
                stranded.append(v_id)

        # A vehicle with no remaining path to its destination is removed and counted, rather
        # than being left to drive through the closure.
        for v_id in stranded:
            self.active_vehicles.pop(v_id, None)
            self.stranded_count += 1

    def _replan_from_current_position(self, veh) -> bool:
        """Recompute a vehicle's route from the node it is currently heading towards.

        Keeps the current edge as the head of the new route so the vehicle finishes the link it
        is physically committed to. Returns False if no unblocked path to the destination exists.
        """
        curr_edge_id = veh.current_edge_id
        if not curr_edge_id:
            return False
        curr_edge = self.edges_dict.get(curr_edge_id)
        if not curr_edge:
            return False

        # Node the vehicle will reach at the end of its current edge.
        from_node = curr_edge["v"]
        if from_node == veh.destination_id:
            veh.route_edges = [curr_edge_id]
            veh.current_edge_idx = 0
            return True

        new_tail = self.od_generator.get_route_edges(
            origin_node=from_node,
            dest_node=veh.destination_id,
            current_blocked_edges=self.blocked_edges
        )
        if not new_tail:
            return False

        veh.route_edges = [curr_edge_id] + new_tail
        veh.current_edge_idx = 0
        # distance_on_edge is deliberately preserved: the vehicle stays where it physically is.
        return True

    def _replan_from_node(self, veh, from_node: str) -> str:
        """Recompute a vehicle's route from a junction it has just reached.

        Returns "ARRIVED" if the junction is already the destination, "OK" if a new path was
        found, or "STRANDED" if the closure leaves no route to the destination.
        """
        if from_node == veh.destination_id:
            veh.status = "ARRIVED"
            return "ARRIVED"
        new_route = self.od_generator.get_route_edges(
            origin_node=from_node,
            dest_node=veh.destination_id,
            current_blocked_edges=self.blocked_edges
        )
        if not new_route:
            return "STRANDED"
        veh.route_edges = new_route
        veh.current_edge_idx = 0
        veh.distance_on_edge = 0.0
        veh.lane_edge_id = None
        return "OK"

    def reset(self, clear_closures: bool = False):
        """Reset the simulation.

        Road closures are preserved by default so a scenario survives a reset; pass
        clear_closures=True to drop them as well.
        """
        self.active_vehicles.clear()
        self.completed_trips.clear()
        self.sim_time = 0.0
        self.vehicle_id_counter = 0
        self.dropped_spawns = 0
        self.stranded_count = 0
        if clear_closures:
            self.blocked_edges.clear()
        self.is_paused = False
        self._init_edge_stats()

    def tick(self, dt=1.0):
        """Execute one simulation tick of dt seconds."""
        if self.is_paused:
            return self.get_simulation_state()

        effective_dt = dt * self.params["sim_speed_multiplier"]
        self.sim_time += effective_dt

        # 0. Advance Traffic Signal Controllers
        self.signal_manager.tick(effective_dt)

        # 1. Update Edge Congestion & Speeds using BPR Formula
        self._update_edge_congestion()

        # 2. Advance Active Vehicles using IDM Microscopic Car-Following
        arrived_ids = []
        stranded_ids = []

        # Group vehicles by (edge, lane). Grouping by edge alone put every vehicle on a
        # multi-lane road into a single car-following file, so a 3-lane arterial carried no more
        # traffic than a 1-lane street.
        lane_vehicles = defaultdict(list)
        for v_id, veh in self.active_vehicles.items():
            curr_edge_id = veh.current_edge_id
            if not curr_edge_id:
                # Ran past the end of its route: genuinely arrived.
                arrived_ids.append(v_id)
                continue
            edge_dict = self.edges_dict.get(curr_edge_id)
            if not edge_dict:
                # Edge disappeared under it (AOI was redrawn): drop, do not count as a trip.
                stranded_ids.append(v_id)
                continue
            # Vehicles already on a link that was closed under them stay on it and drive it out;
            # they are not teleported across. Entry to a closed link is prevented downstream.
            if veh.lane_edge_id != curr_edge_id:
                veh.assign_lane(edge_dict)
            lane_vehicles[(curr_edge_id, veh.lane_index)].append(veh)

        # Update each lane group with IDM lead vehicle gap & queue offset
        for (e_id, _lane), v_list in lane_vehicles.items():
            v_list.sort(key=lambda x: x.distance_on_edge, reverse=True)
            edge_dict = self.edges_dict[e_id]

            is_red = self.signal_manager.is_edge_red(e_id)

            for idx, veh in enumerate(v_list):
                if idx == 0:
                    lead_dist = None
                    lead_speed = 0.0
                else:
                    lead_veh = v_list[idx - 1]
                    lead_dist = max(0.1, lead_veh.distance_on_edge - veh.distance_on_edge - lead_veh.props["length_meters"])
                    lead_speed = lead_veh.speed_ms

                queue_offset = idx * 6.0  # 6m physical spacing per vehicle queued behind

                edge_finished = veh.update_position(
                    edge_dict=edge_dict,
                    dt=effective_dt,
                    lead_vehicle_dist_m=lead_dist,
                    lead_vehicle_speed_ms=lead_speed,
                    is_red_light=is_red,
                    queue_offset_m=queue_offset
                )
                if edge_finished:
                    if veh.advance_to_next_edge():
                        arrived_ids.append(veh.id)
                    elif veh.current_edge_id in self.blocked_edges:
                        # Next link on the plan is closed: replan from this junction rather than
                        # driving into (and previously, straight through) the closure.
                        outcome = self._replan_from_node(veh, edge_dict["v"])
                        if outcome == "ARRIVED":
                            arrived_ids.append(veh.id)
                        elif outcome == "STRANDED":
                            stranded_ids.append(veh.id)

        # 3. Clean up Arrived Vehicles & Check Parking Garages Arrival
        for veh_id in arrived_ids:
            veh = self.active_vehicles.pop(veh_id, None)
            if veh:
                self.completed_trips.append(veh.total_travel_time)
                self.parking_manager.handle_vehicle_arrival(veh.id, veh.destination_id)

        # Vehicles cut off by a closure are removed without being counted as completed trips.
        for veh_id in stranded_ids:
            if self.active_vehicles.pop(veh_id, None):
                self.stranded_count += 1

        # 4. Advance Parking Garages & Timetable Transit Buses
        self.parking_manager.tick(effective_dt)
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
                class_override=cls_override,
                blocked_edges=self.blocked_edges
            )
            if vehicle:
                self.active_vehicles[v_id] = vehicle
            else:
                # Unroutable O-D pair. Counted rather than discarded silently so the reported
                # demand matches what actually entered the network.
                self.dropped_spawns += 1

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
            "is_paused": self.is_paused,
            "active_vehicles_count": len(self.active_vehicles),
            "completed_trips_count": len(self.completed_trips),
            "avg_travel_time_sec": round(avg_travel_time, 1),
            "dropped_spawns": self.dropped_spawns,
            "stranded_count": self.stranded_count,
            "co2_kg_hr": round(co2_rate_kg_hr, 1),
            "fuel_l_hr": round(fuel_rate_l_hr, 1),
            "vehicles": vehicle_points,
            "congested_edges": congested_edges,
            "blocked_edges": list(self.blocked_edges),
            "top_chokepoints": sorted_chokepoints,
            "bus_lines": self.bus_transit_manager.get_transit_state(),
            "signals": self.signal_manager.get_signals_state(),
            "parking_garages": self.parking_manager.get_parking_state()
        }
