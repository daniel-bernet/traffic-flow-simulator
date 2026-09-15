import random
from enum import Enum
import math
import random

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
        self.lane_index = 0          # assigned lane index (0 to lanes-1)
        self.lane_edge_id = None     # edge the current lane_index was drawn for

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

    def assign_lane(self, edge_dict):
        """Draw a lane for this edge. Called once per edge entry, not per tick."""
        lanes = max(1, edge_dict.get("lanes", 1))
        self.lane_index = random.randint(0, lanes - 1)
        self.lane_edge_id = edge_dict.get("edge_id")
        return self.lane_index

    def update_position(self, edge_dict, dt=1.0, lead_vehicle_dist_m=None, lead_vehicle_speed_ms=0.0,
                        is_red_light=False, queue_offset_m=0.0):
        """
        Microscopic Intelligent Driver Model (IDM) position update.
        Computes continuous acceleration, deceleration, lead vehicle car-following, and red-light stopping.
        """
        if self.status != "IN_TRANSIT" or not edge_dict:
            return False

        self.total_travel_time += dt
        edge_length = edge_dict["length"]
        v_limit_ms = (edge_dict["maxspeed"] / 3.6) * self.props["speed_factor"]

        # Ensure valid lane assignment for this edge
        lanes = max(1, edge_dict.get("lanes", 1))
        if self.lane_index >= lanes:
            self.lane_index = random.randint(0, lanes - 1)

        # IDM Model Constants
        a_max = 2.0        # Max acceleration (m/s^2) ~0 to 50 km/h in 7s
        b_comf = 2.5       # Comfortable deceleration (m/s^2)
        s0 = 4.0           # Standstill minimum gap (m)
        headway_T = 1.2    # Safe time headway (s)

        # Determine effective distance to hurdle (lead vehicle or red signal stop line)
        dist_to_end_m = max(0.1, edge_length - self.distance_on_edge)
        
        # A red signal is a stationary obstacle at the stop line; a lead vehicle moves at its own
        # speed. Treating a moving leader as stationary (the previous behaviour) makes every
        # follower in a platoon brake far harder than it should.
        if is_red_light and dist_to_end_m <= 80.0:
            stop_line_gap = dist_to_end_m
            if lead_vehicle_dist_m is not None and lead_vehicle_dist_m < stop_line_gap:
                effective_gap = max(0.5, lead_vehicle_dist_m)
                v_lead = max(0.0, lead_vehicle_speed_ms)
            else:
                effective_gap = max(0.5, stop_line_gap)
                v_lead = 0.0
        elif lead_vehicle_dist_m is not None:
            effective_gap = max(0.5, lead_vehicle_dist_m)
            v_lead = max(0.0, lead_vehicle_speed_ms)
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
        # Prevent permanent stall: creep at 0.5 m/s if gap is large and speed is 0
        if self.speed_ms < 0.1 and effective_gap > 10.0 and not is_red_light:
            self.speed_ms = 0.5
        move_dist = self.speed_ms * dt
        self.distance_on_edge += move_dist

        # Hard stop-line constraint. IDM deceleration is clamped at -6 m/s^2, so from ~50 km/h a
        # single large dt step can still carry a vehicle across the stop line. Without this, cars
        # visibly run red lights.
        if is_red_light and self.distance_on_edge >= edge_length:
            self.distance_on_edge = edge_length - 0.1
            self.speed_ms = 0.0

        # Calculate visual coordinates with physical queue spacing offset
        visual_dist = max(0.0, min(edge_length, self.distance_on_edge - queue_offset_m))
        progress_frac = visual_dist / max(1.0, edge_length)
        self._interpolate_coordinates(edge_dict["geometry"], min(1.0, progress_frac), edge_dict)

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

    def _interpolate_coordinates(self, geometry_coords, progress_fraction, edge_dict=None):
        """Geometry is list of [lat, lon] points."""
        if not geometry_coords or len(geometry_coords) == 0:
            return

        total_segments = max(1, len(geometry_coords) - 1)
        progress_clamped = max(0.0, min(1.0, progress_fraction))
        segment_float = progress_clamped * total_segments
        idx = min(total_segments - 1, int(segment_float))
        frac = segment_float - idx

        p1 = geometry_coords[idx]
        p2 = geometry_coords[min(len(geometry_coords) - 1, idx + 1)] if len(geometry_coords) > 1 else p1

        base_lat = p1[0] + frac * (p2[0] - p1[0])
        base_lon = p1[1] + frac * (p2[1] - p1[1])
        
        # Calculate heading angle
        dy = p2[0] - p1[0]
        dx = (p2[1] - p1[1]) * math.cos(math.radians(p1[0]))
        if dy != 0.0 or dx != 0.0:
            self.heading = math.degrees(math.atan2(dy, dx))

        # Apply multi-lane lateral coordinate offset if road has >1 lanes
        lanes = max(1, edge_dict.get("lanes", 1)) if edge_dict else 1
        if lanes > 1:
            heading_rad = math.radians(self.heading)
            # Perpendicular shift in meters (1.8m shift per lane index from center)
            lane_shift_m = (self.lane_index - (lanes - 1) / 2.0) * 1.8
            
            lat_offset_deg = (lane_shift_m * math.cos(heading_rad + math.pi/2)) / 111139.0
            lon_offset_deg = (lane_shift_m * math.sin(heading_rad + math.pi/2)) / (111139.0 * math.cos(math.radians(base_lat)))
            
            self.lat = base_lat + lat_offset_deg
            self.lon = base_lon + lon_offset_deg
        else:
            self.lat = base_lat
            self.lon = base_lon

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
