from enum import Enum
import math

class TrafficClass(str, Enum):
    PERSONAL = "personal"
    TOURISM = "tourism"
    LOGISTICS = "logistics"
    BUS = "bus"

# Properties per class
CLASS_PROPERTIES = {
    TrafficClass.PERSONAL: {
        "pce": 1.0,             # Passenger Car Equivalent weight
        "speed_factor": 1.0,    # Max speed factor relative to speed limit
        "color": "#3498db",     # Blue
        "length_meters": 4.5,
        "name": "Personal Car"
    },
    TrafficClass.TOURISM: {
        "pce": 1.5,
        "speed_factor": 0.85,
        "color": "#9b59b6",     # Purple
        "length_meters": 10.0,
        "name": "Tourism / Coach"
    },
    TrafficClass.LOGISTICS: {
        "pce": 2.0,
        "speed_factor": 0.80,
        "color": "#f39c12",     # Orange/Yellow
        "length_meters": 12.0,
        "name": "Logistics / Freight"
    },
    TrafficClass.BUS: {
        "pce": 2.0,
        "speed_factor": 0.90,
        "color": "#e74c3c",     # Red
        "length_meters": 15.0,
        "name": "Public Bus"
    }
}

class Vehicle:
    def __init__(self, vehicle_id: str, vehicle_class: TrafficClass, origin_id: str, destination_id: str, route_edges: list):
        self.id = vehicle_id
        self.vehicle_class = vehicle_class
        self.props = CLASS_PROPERTIES[vehicle_class]
        self.origin_id = origin_id
        self.destination_id = destination_id
        self.route_edges = route_edges  # List of edge_id strings
        
        self.current_edge_idx = 0
        self.distance_on_edge = 0.0  # meters
        self.speed_ms = 0.0          # current velocity m/s
        self.accel_ms2 = 0.0         # current acceleration m/s^2
        self.status = "IN_TRANSIT"
        
        self.lat = 0.0
        self.lon = 0.0
        self.heading = 0.0 # orientation degrees
        self.total_travel_time = 0.0

        # Public Transit metadata
        self.bus_line_id = None
        self.scheduled_travel_time = 0.0
        self.schedule_delay_sec = 0.0

    @property
    def current_edge_id(self):
        if 0 <= self.current_edge_idx < len(self.route_edges):
            return self.route_edges[self.current_edge_idx]
        return None

    def update_position(self, edge_dict, dt=1.0, lead_vehicle_dist_m=None, is_red_light=False, queue_offset_m=0.0):
        """
        Microscopic Intelligent Driver Model (IDM) position update.
        Computes continuous acceleration, deceleration, lead vehicle car-following, and red-light stopping.
        """
        if self.status != "IN_TRANSIT" or not edge_dict:
            return False

        self.total_travel_time += dt
        edge_length = edge_dict["length"]
        v_limit_ms = (edge_dict["maxspeed"] / 3.6) * self.props["speed_factor"]

        # IDM Model Constants
        a_max = 2.0        # Max acceleration (m/s^2) ~0 to 50 km/h in 7s
        b_comf = 2.5       # Comfortable deceleration (m/s^2)
        s0 = 4.0           # Standstill minimum gap (m)
        headway_T = 1.2    # Safe time headway (s)

        # Determine effective distance to hurdle (lead vehicle or red signal stop line)
        dist_to_end_m = max(0.1, edge_length - self.distance_on_edge)
        
        if is_red_light and dist_to_end_m <= 80.0:
            effective_gap = min(dist_to_end_m, lead_vehicle_dist_m if lead_vehicle_dist_m is not None else 1000.0)
            v_lead = 0.0
        elif lead_vehicle_dist_m is not None:
            effective_gap = max(0.5, lead_vehicle_dist_m)
            v_lead = 0.0
        else:
            effective_gap = 1000.0
            v_lead = self.speed_ms

        delta_v = self.speed_ms - v_lead
        s_star = s0 + self.speed_ms * headway_T + (self.speed_ms * delta_v) / (2.0 * math.sqrt(max(0.1, a_max * b_comf)))

        # IDM Acceleration formula
        accel = a_max * (1.0 - math.pow(self.speed_ms / max(0.1, v_limit_ms), 4) - math.pow(s_star / max(0.1, effective_gap), 2))
        self.accel_ms2 = max(-6.0, min(a_max, accel))

        # Velocity & position integration
        self.speed_ms = max(0.0, min(v_limit_ms, self.speed_ms + self.accel_ms2 * dt))
        move_dist = self.speed_ms * dt
        self.distance_on_edge += move_dist

        # Calculate visual coordinates with physical queue spacing offset
        visual_dist = max(0.0, min(edge_length, self.distance_on_edge - queue_offset_m))
        progress_frac = visual_dist / max(1.0, edge_length)
        self._interpolate_coordinates(edge_dict["geometry"], min(1.0, progress_frac))

        if self.distance_on_edge >= edge_length:
            return True
        return False

    def advance_to_next_edge(self):
        self.current_edge_idx += 1
        self.distance_on_edge = 0.0
        if self.current_edge_idx >= len(self.route_edges):
            self.status = "ARRIVED"
            return True
        return False

    def _interpolate_coordinates(self, geometry_coords, progress_fraction):
        """Geometry is list of [lat, lon] points."""
        if not geometry_coords or len(geometry_coords) == 0:
            return
        if len(geometry_coords) == 1 or progress_fraction <= 0.0:
            self.lat, self.lon = geometry_coords[0][0], geometry_coords[0][1]
            return
        if progress_fraction >= 1.0:
            self.lat, self.lon = geometry_coords[-1][0], geometry_coords[-1][1]
            return

        total_segments = len(geometry_coords) - 1
        segment_float = progress_fraction * total_segments
        idx = min(total_segments - 1, int(segment_float))
        frac = segment_float - idx

        p1 = geometry_coords[idx]
        p2 = geometry_coords[idx + 1]

        self.lat = p1[0] + frac * (p2[0] - p1[0])
        self.lon = p1[1] + frac * (p2[1] - p1[1])
        
        # Calculate heading angle
        dy = p2[0] - p1[0]
        dx = (p2[1] - p1[1]) * math.cos(math.radians(p1[0]))
        self.heading = math.degrees(math.atan2(dy, dx))

    def to_dict(self):
        res = {
            "id": self.id,
            "class": self.vehicle_class.value,
            "color": self.props["color"],
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "heading": round(self.heading, 1),
            "speed_kmh": round(self.speed_ms * 3.6, 1),
            "status": self.status,
            "edge_id": self.current_edge_id
        }
        if self.bus_line_id:
            res["bus_line_id"] = self.bus_line_id
            res["delay_sec"] = round(self.schedule_delay_sec, 1)
        return res
