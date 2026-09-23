import logging
import math
import random
from typing import List, Dict, Optional
from src.vehicle import TrafficClass, Vehicle

logger = logging.getLogger("ParkingManager")

LUCERNE_PARKING_GARAGES_DEF = [
    {
        "id": "park_bahnhof",
        "name": "Parkhaus Bahnhof",
        "capacity": 1100,
        "lat": 47.0495,
        "lon": 8.3105,
        "hourly_fee_chf": 3.50
    },
    {
        "id": "park_kesselturm",
        "name": "Parkhaus Kesselturm",
        "capacity": 500,
        "lat": 47.0508,
        "lon": 8.3015,
        "hourly_fee_chf": 3.00
    },
    {
        "id": "park_schweizerhof",
        "name": "Parkhaus Schweizerhof",
        "capacity": 420,
        "lat": 47.0535,
        "lon": 8.3090,
        "hourly_fee_chf": 3.80
    },
    {
        "id": "park_altstadt",
        "name": "Parkhaus Altstadt",
        "capacity": 350,
        "lat": 47.0560,
        "lon": 8.3095,
        "hourly_fee_chf": 3.20
    },
    {
        "id": "park_kantonalbank",
        "name": "Parkhaus Kantonalbank",
        "capacity": 300,
        "lat": 47.0485,
        "lon": 8.3040,
        "hourly_fee_chf": 3.20
    },
    {
        "id": "park_hirzenmatt",
        "name": "Parkhaus Hirzenmatt",
        "capacity": 250,
        "lat": 47.0470,
        "lon": 8.3060,
        "hourly_fee_chf": 2.80
    },
    {
        "id": "park_kasernenplatz",
        "name": "Parkhaus Kasernenplatz",
        "capacity": 200,
        "lat": 47.0518,
        "lon": 8.3000,
        "hourly_fee_chf": 2.50
    }
]

class ParkingGarage:
    def __init__(self, garage_id: str, name: str, capacity: int, lat: float, lon: float, hourly_fee_chf: float, node_id: str):
        self.id = garage_id
        self.name = name
        self.capacity = capacity
        self.occupied = int(capacity * random.uniform(0.40, 0.70)) # Initial 40-70% occupancy
        self.lat = lat
        self.lon = lon
        self.hourly_fee_chf = hourly_fee_chf
        self.node_id = node_id
        
        self.entry_queue: List[str] = [] # List of vehicle_ids waiting at barrier gate
        self.parked_vehicles: Dict[str, float] = {} # vehicle_id -> remaining dwell time (sec)
        self.gate_cooldown_sec = 0.0 # Entrance gate barrier processing timer

    @property
    def occupancy_pct(self) -> float:
        return min(100.0, (self.occupied / max(1, self.capacity)) * 100.0)

    @property
    def available_spaces(self) -> int:
        return max(0, self.capacity - self.occupied)

class ParkingManager:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.garages: Dict[str, ParkingGarage] = {}
        self.node_to_garage: Dict[str, str] = {} # node_id -> garage_id
        self._init_garages()

    def _init_garages(self):
        self.garages.clear()
        self.node_to_garage.clear()

        for g_def in LUCERNE_PARKING_GARAGES_DEF:
            nearest_node = self.data_loader.find_nearest_node(g_def["lat"], g_def["lon"])
            if nearest_node:
                garage = ParkingGarage(
                    garage_id=g_def["id"],
                    name=g_def["name"],
                    capacity=g_def["capacity"],
                    lat=g_def["lat"],
                    lon=g_def["lon"],
                    hourly_fee_chf=g_def["hourly_fee_chf"],
                    node_id=nearest_node
                )
                self.garages[g_def["id"]] = garage
                self.node_to_garage[nearest_node] = g_def["id"]

    def reload_network(self):
        self._init_garages()

    def get_nearest_garage_node(self, target_lat: float, target_lon: float) -> Optional[str]:
        """Finds the nearest available parking garage node."""
        best_node = None
        min_dist = float("inf")

        for g in self.garages.values():
            if g.available_spaces > 0:
                dist = math.hypot(g.lat - target_lat, g.lon - target_lon)
                if dist < min_dist:
                    min_dist = dist
                    best_node = g.node_id

        return best_node

    def tick(self, dt: float) -> List[dict]:
        """Advances entrance gate barriers and vehicle dwell timers."""
        departing_vehicles = []

        for g_id, garage in self.garages.items():
            # Process gate barrier queue (1 car enters every 2 seconds)
            garage.gate_cooldown_sec = max(0.0, garage.gate_cooldown_sec - dt)
            if garage.entry_queue and garage.gate_cooldown_sec <= 0.0 and garage.available_spaces > 0:
                veh_id = garage.entry_queue.pop(0)
                garage.occupied += 1
                dwell_time = random.uniform(300.0, 1200.0) # 5-20 min sim time dwell
                garage.parked_vehicles[veh_id] = dwell_time
                garage.gate_cooldown_sec = 2.0

            # Process parked vehicle dwell times
            expired_ids = []
            for veh_id, remaining_t in list(garage.parked_vehicles.items()):
                remaining_t -= dt
                if remaining_t <= 0.0:
                    expired_ids.append(veh_id)
                else:
                    garage.parked_vehicles[veh_id] = remaining_t

            for veh_id in expired_ids:
                garage.parked_vehicles.pop(veh_id, None)
                garage.occupied = max(0, garage.occupied - 1)
                departing_vehicles.append({
                    "vehicle_id": veh_id,
                    "garage_id": g_id,
                    "node_id": garage.node_id
                })

        return departing_vehicles

    def handle_vehicle_arrival(self, vehicle_id: str, dest_node_id: str) -> bool:
        """If destination is a parking garage, vehicle enters entry queue."""
        if dest_node_id in self.node_to_garage:
            g_id = self.node_to_garage[dest_node_id]
            garage = self.garages[g_id]
            garage.entry_queue.append(vehicle_id)
            return True
        return False

    def get_parking_state(self) -> List[dict]:
        """Returns JSON state payload for UI dashboard."""
        return [
            {
                "id": g.id,
                "name": g.name,
                "capacity": g.capacity,
                "occupied": g.occupied,
                "available": g.available_spaces,
                "occupancy_pct": round(g.occupancy_pct, 1),
                "queue_count": len(g.entry_queue),
                "lat": g.lat,
                "lon": g.lon,
                "node_id": g.node_id,
                "hourly_fee_chf": g.hourly_fee_chf
            }
            for g in self.garages.values()
        ]
