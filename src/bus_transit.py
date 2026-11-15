import logging
import math
import random
from typing import List, Dict, Optional
from src.vehicle import TrafficClass, Vehicle

logger = logging.getLogger("BusTransitManager")

# Simplified versions of five VBL bus lines. UNVERIFIED PLACEHOLDER VALUES, NOT AUTHORITATIVE.
# Stops, coordinates and headways come from quick web searches, not from the official GTFS
# timetable; routes are shortest paths between the listed stops.
VBL_BUS_LINES_DEF = [
    {
        "id": "vbl_line_1",
        "name": "Line 1: Obernau – Kriens – Bahnhof – Maihof",
        "headway_sec": 360, # 6 min peak frequency (10 buses/hr)
        "color": "#e11d48", # Rose Red
        "stops": [
            {"name": "Obernau Dorf", "lat": 47.0325, "lon": 8.2710},
            {"name": "Kriens Zentrum", "lat": 47.0348, "lon": 8.2800},
            {"name": "Eichhof", "lat": 47.0410, "lon": 8.2950},
            {"name": "Pilatusplatz", "lat": 47.0490, "lon": 8.3035},
            {"name": "Bahnhof Luzern", "lat": 47.0502, "lon": 8.3103},
            {"name": "Schwanenplatz", "lat": 47.0525, "lon": 8.3075},
            {"name": "Maihof", "lat": 47.0630, "lon": 8.3150}
        ]
    },
    {
        "id": "vbl_line_6",
        "name": "Line 6: Matthof – Bahnhof – Biregghof",
        "headway_sec": 480, # 8 min frequency
        "color": "#a855f7", # Purple
        "stops": [
            {"name": "Matthof", "lat": 47.0310, "lon": 8.3150},
            {"name": "Schönbühl", "lat": 47.0380, "lon": 8.3180},
            {"name": "Bahnhof Luzern", "lat": 47.0502, "lon": 8.3103},
            {"name": "Bundesplatz", "lat": 47.0460, "lon": 8.3070},
            {"name": "Biregghof", "lat": 47.0390, "lon": 8.2990}
        ]
    },
    {
        "id": "vbl_line_12",
        "name": "Line 12: Littau Gare – Bahnhof – Würzenbach",
        "headway_sec": 450, # 7.5 min frequency
        "color": "#059669", # Emerald Green
        "stops": [
            {"name": "Littau Bahnhof", "lat": 47.0550, "lon": 8.2600},
            {"name": "Kasernenplatz", "lat": 47.0515, "lon": 8.3005},
            {"name": "Bahnhof Luzern", "lat": 47.0502, "lon": 8.3103},
            {"name": "Casino-Palace", "lat": 47.0540, "lon": 8.3180},
            {"name": "Würzenbach", "lat": 47.0535, "lon": 8.3370}
        ]
    },
    {
        "id": "vbl_line_14",
        "name": "Line 14: Horw Zentrum – Bahnhof – Brüelstrasse",
        "headway_sec": 600, # 10 min frequency
        "color": "#d97706", # Amber
        "stops": [
            {"name": "Horw Zentrum", "lat": 47.0165, "lon": 8.3100},
            {"name": "Allmend / Messe", "lat": 47.0360, "lon": 8.3080},
            {"name": "Bahnhof Luzern", "lat": 47.0502, "lon": 8.3103},
            {"name": "Brüelstrasse", "lat": 47.0610, "lon": 8.3220}
        ]
    },
    {
        "id": "vbl_line_24",
        "name": "Line 24: Bahnhof – Verkehrshaus – Meggen",
        "headway_sec": 900, # 15 min frequency
        "color": "#0284c7", # Sky Blue
        "stops": [
            {"name": "Bahnhof Luzern", "lat": 47.0502, "lon": 8.3103},
            {"name": "Verkehrshaus", "lat": 47.0531, "lon": 8.3356},
            {"name": "Hermitage", "lat": 47.0520, "lon": 8.3480},
            {"name": "Meggen Gottlieben", "lat": 47.0460, "lon": 8.3750}
        ]
    }
]

class BusTransitManager:
    def __init__(self, data_loader, od_generator):
        self.data_loader = data_loader
        self.od_generator = od_generator
        self.bus_lines = {} # line_id -> dict with resolved node routes & stats
        self.line_dispatch_timers = {} # line_id -> seconds since last dispatch
        self.active_transit_buses = {} # vehicle_id -> dict details
        
        self._init_bus_lines()

    def _init_bus_lines(self):
        self.bus_lines = {}
        for line_def in VBL_BUS_LINES_DEF:
            line_id = line_def["id"]
            resolved_stops = []
            stop_nodes = []

            for s in line_def["stops"]:
                nearest_node = self.data_loader.find_nearest_node(s["lat"], s["lon"])
                if nearest_node:
                    n_data = self.data_loader.nodes_dict[nearest_node]
                    stop_nodes.append(nearest_node)
                    resolved_stops.append({
                        "name": s["name"],
                        "lat": n_data["lat"],
                        "lon": n_data["lon"],
                        "node_id": nearest_node
                    })

            # Calculate path along consecutive stops
            full_route_edges = []
            for i in range(len(stop_nodes) - 1):
                seg_edges = self.od_generator.get_route_edges(stop_nodes[i], stop_nodes[i+1])
                if seg_edges:
                    full_route_edges.extend(seg_edges)

            # Target nominal travel time (in seconds) assuming 35 km/h avg free flow speed
            edges_dict = {e["edge_id"]: e for e in self.data_loader.edges_list}
            total_dist_m = sum(edges_dict[e_id]["length"] for e_id in full_route_edges if e_id in edges_dict)
            if total_dist_m <= 0.0:
                total_dist_m = 3500.0 # Default ~3.5km route fallback
            nominal_travel_time_sec = max(180, total_dist_m / (35.0 / 3.6))

            self.bus_lines[line_id] = {
                "id": line_id,
                "name": line_def["name"],
                "headway_sec": line_def["headway_sec"],
                "color": line_def["color"],
                "stops": resolved_stops,
                "stop_nodes": stop_nodes,
                "route_edges": full_route_edges,
                "nominal_travel_time_sec": nominal_travel_time_sec,
                "active_buses_count": 0,
                "avg_lateness_sec": 0.0,
                "status_tag": "ON TIME", # ON TIME, MINOR DELAY, HEAVY DELAY
                "status_color": "#10b981" # Green, Yellow, Red
            }

            self.line_dispatch_timers[line_id] = line_def["headway_sec"] # Trigger dispatch immediately on start

    def reload_network(self):
        self._init_bus_lines()

    def tick(self, dt: float, engine_active_vehicles: dict) -> List[Vehicle]:
        """Dispatches timetable buses and updates schedule delay lateness metrics."""
        spawned_buses = []

        for line_id, line_data in self.bus_lines.items():
            if not line_data["route_edges"]:
                continue

            self.line_dispatch_timers[line_id] += dt
            if self.line_dispatch_timers[line_id] >= line_data["headway_sec"]:
                self.line_dispatch_timers[line_id] = 0.0

                # Create Transit Bus
                bus_veh_id = f"vbl_bus_{line_id}_{int(random.random()*10000)}"
                origin_node = line_data["stop_nodes"][0]
                dest_node = line_data["stop_nodes"][-1]

                vehicle = Vehicle(
                    vehicle_id=bus_veh_id,
                    vehicle_class=TrafficClass.BUS,
                    origin_id=origin_node,
                    destination_id=dest_node,
                    route_edges=list(line_data["route_edges"])
                )

                # Attach transit metadata
                vehicle.bus_line_id = line_id
                vehicle.scheduled_travel_time = line_data["nominal_travel_time_sec"]
                vehicle.schedule_delay_sec = 0.0

                spawned_buses.append(vehicle)

        # Update lateness for active transit buses
        line_delays = {line_id: [] for line_id in self.bus_lines}

        for veh_id, veh in engine_active_vehicles.items():
            if hasattr(veh, "bus_line_id") and veh.bus_line_id in self.bus_lines:
                line_id = veh.bus_line_id
                line_info = self.bus_lines[line_id]

                # Progress ratio along line route
                progress_pct = veh.current_edge_idx / max(1, len(veh.route_edges))
                target_elapsed_sec = progress_pct * line_info["nominal_travel_time_sec"]

                # Actual elapsed travel time vs scheduled expected time
                actual_elapsed_sec = veh.total_travel_time
                lateness_sec = max(0.0, actual_elapsed_sec - target_elapsed_sec)
                veh.schedule_delay_sec = lateness_sec

                line_delays[line_id].append(lateness_sec)

        # Update line dashboard status
        for line_id, delays in line_delays.items():
            line_info = self.bus_lines[line_id]
            line_info["active_buses_count"] = len(delays)

            if delays:
                avg_delay = sum(delays) / len(delays)
            else:
                avg_delay = 0.0

            line_info["avg_lateness_sec"] = round(avg_delay, 1)

            if avg_delay < 90.0:
                line_info["status_tag"] = "ON TIME"
                line_info["status_color"] = "#10b981" # Emerald Green
            elif avg_delay < 240.0:
                line_info["status_tag"] = f"+{round(avg_delay/60.0, 1)} min"
                line_info["status_color"] = "#f59e0b" # Amber Yellow
            else:
                line_info["status_tag"] = f"+{round(avg_delay/60.0, 1)} min"
                line_info["status_color"] = "#ef4444" # Red Congested

        return spawned_buses

    def get_transit_state(self) -> List[dict]:
        """Returns bus lines state summary for UI dashboard."""
        return [
            {
                "id": line["id"],
                "name": line["name"],
                "color": line["color"],
                "headway_min": round(line["headway_sec"] / 60.0, 1),
                "active_buses": line["active_buses_count"],
                "avg_lateness_min": round(line["avg_lateness_sec"] / 60.0, 1),
                "status_tag": line["status_tag"],
                "status_color": line["status_color"],
                "stops_count": len(line["stops"]),
                "route_edges": line["route_edges"]
            }
            for line in self.bus_lines.values()
        ]
