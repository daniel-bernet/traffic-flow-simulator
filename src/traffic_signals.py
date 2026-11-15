import logging
import math
from typing import Dict, List, Set, Optional

logger = logging.getLogger("TrafficSignalManager")

# Hand-placed signal locations in Lucerne. UNVERIFIED PLACEHOLDER VALUES, NOT AUTHORITATIVE.
# Names and coordinates come from quick web searches and map reading; each point is snapped to
# the nearest network node. Phase plans are generic (two phases, 60/75/90 s by approach count),
# not the real signal programmes.
MAJOR_LUCERNE_SIGNALS = [
    {"name": "Pilatusplatz Signal", "lat": 47.0490, "lon": 8.3035},
    {"name": "Kasernenplatz Signal", "lat": 47.0515, "lon": 8.3005},
    {"name": "Schweizerhofquai / Schwanenplatz", "lat": 47.0525, "lon": 8.3075},
    {"name": "Seebrücke South Portal", "lat": 47.0508, "lon": 8.3090},
    {"name": "Maihofstrasse / Schlossberg", "lat": 47.0630, "lon": 8.3150},
    {"name": "Haldenstrasse / National", "lat": 47.0535, "lon": 8.3200},
    {"name": "Seetalplatz Major Portal", "lat": 47.0710, "lon": 8.2890},
    {"name": "Luzernerstrasse / Kriens Entrance", "lat": 47.0380, "lon": 8.2950},
    {"name": "Baselstrasse / Bernstrasse Fork", "lat": 47.0510, "lon": 8.2920},
    {"name": "Ostring / Spitalstrasse", "lat": 47.0580, "lon": 8.3005},
    {"name": "Bundesplatz / Pilatusstrasse", "lat": 47.0460, "lon": 8.3070},
    {"name": "Hirschengraben / Löwenplatz", "lat": 47.0555, "lon": 8.3095},
    {"name": "Reusszopf / Spreuerbrücke", "lat": 47.0535, "lon": 8.3040},
    {"name": "Reussport / Baselstrasse North", "lat": 47.0560, "lon": 8.2960},
    {"name": "Tribschen / Allmendstrasse", "lat": 47.0430, "lon": 8.3120},
    {"name": "Allmend / Messestrasse", "lat": 47.0360, "lon": 8.3080},
    {"name": "Kriens Luzernerstrasse / Ringstrasse", "lat": 47.0348, "lon": 8.2810},
    {"name": "Ebikon Zentralstrasse Signal", "lat": 47.0780, "lon": 8.3400},
    {"name": "Seetalplatz West / Emmen", "lat": 47.0720, "lon": 8.2860},
    {"name": "Sedel / Reussport Viaduct", "lat": 47.0610, "lon": 8.2930},
    {"name": "Horw Bahnhofstrasse Signal", "lat": 47.0180, "lon": 8.3110},
    {"name": "Zinggentorstrasse / Obergrund", "lat": 47.0448, "lon": 8.3050},
    {"name": "Friedenstrasse / Alpenquai", "lat": 47.0485, "lon": 8.3140},
    {"name": "Kantonalbank / Zentralstrasse", "lat": 47.0495, "lon": 8.3050},
    {"name": "Brünigstrasse / Rothenburg", "lat": 47.0900, "lon": 8.2700},
]

class TrafficSignal:
    def __init__(self, signal_id: str, node_id: str, name: str, lat: float, lon: float, incoming_edges: List[str]):
        self.id = signal_id
        self.node_id = node_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.incoming_edges = incoming_edges
        
        # Differentiate cycle times: major intersections get longer cycles
        if len(incoming_edges) >= 4:
            self.cycle_time_sec = 90.0   # Major intersection
        elif len(incoming_edges) >= 3:
            self.cycle_time_sec = 75.0   # Medium intersection  
        else:
            self.cycle_time_sec = 60.0   # Minor intersection
        self.green_split = 0.50     # 50% Phase A, 50% Phase B
        self.yellow_time_sec = 3.0
        
        self.timer = 0.0
        self.phase = "PHASE_A_GREEN"  # "PHASE_A_GREEN", "PHASE_A_YELLOW", "PHASE_B_GREEN", "PHASE_B_YELLOW"
        
        # Split incoming edges into two directional approach groups (Phase A vs Phase B)
        half = max(1, len(incoming_edges) // 2)
        self.phase_a_edges: Set[str] = set(incoming_edges[:half])
        self.phase_b_edges: Set[str] = set(incoming_edges[half:])

    def tick(self, dt: float):
        self.timer = (self.timer + dt) % self.cycle_time_sec
        
        phase_a_green_sec = (self.cycle_time_sec - 2 * self.yellow_time_sec) * self.green_split
        phase_a_end = phase_a_green_sec
        phase_a_yellow_end = phase_a_end + self.yellow_time_sec
        phase_b_green_sec = (self.cycle_time_sec - 2 * self.yellow_time_sec) * (1.0 - self.green_split)
        phase_b_end = phase_a_yellow_end + phase_b_green_sec

        if self.timer < phase_a_end:
            self.phase = "PHASE_A_GREEN"
        elif self.timer < phase_a_yellow_end:
            self.phase = "PHASE_A_YELLOW"
        elif self.timer < phase_b_end:
            self.phase = "PHASE_B_GREEN"
        else:
            self.phase = "PHASE_B_YELLOW"

    def is_edge_red(self, edge_id: str) -> bool:
        if edge_id in self.phase_a_edges:
            return self.phase != "PHASE_A_GREEN"
        elif edge_id in self.phase_b_edges:
            return self.phase != "PHASE_B_GREEN"
        return False

    def to_dict(self) -> dict:
        phase_a_is_green = (self.phase == "PHASE_A_GREEN")
        return {
            "id": self.id,
            "node_id": self.node_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "phase": self.phase,
            "phase_a_green": phase_a_is_green,
            "cycle_time_sec": self.cycle_time_sec,
            "green_split": round(self.green_split, 2),
            "phase_a_edges": list(self.phase_a_edges),
            "phase_b_edges": list(self.phase_b_edges)
        }

class TrafficSignalManager:
    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.signals: Dict[str, TrafficSignal] = {} # signal_id -> TrafficSignal
        self.edge_to_signal_map: Dict[str, TrafficSignal] = {} # edge_id -> TrafficSignal
        
        self._init_signals()

    def _init_signals(self):
        self.signals = {}
        self.edge_to_signal_map = {}
        
        # 1. Map incoming edges for all nodes
        incoming_map = {}
        for edge in self.data_loader.edges_list:
            v = edge["v"]
            if v not in incoming_map:
                incoming_map[v] = []
            incoming_map[v].append(edge["edge_id"])

        signal_counter = 0

        # 2. Add major Lucerne key signals
        for item in MAJOR_LUCERNE_SIGNALS:
            nearest_node = self.data_loader.find_nearest_node(item["lat"], item["lon"])
            if nearest_node and nearest_node in self.data_loader.nodes_dict:
                incoming = incoming_map.get(nearest_node, [])
                if incoming:
                    n_data = self.data_loader.nodes_dict[nearest_node]
                    sig_id = f"sig_{nearest_node}"
                    signal = TrafficSignal(
                        signal_id=sig_id,
                        node_id=nearest_node,
                        name=item["name"],
                        lat=n_data["lat"],
                        lon=n_data["lon"],
                        incoming_edges=incoming
                    )
                    self.signals[sig_id] = signal
                    for e_id in incoming:
                        self.edge_to_signal_map[e_id] = signal
                    signal_counter += 1

        # 3. Add OSM signalized nodes
        for n_id, n_data in self.data_loader.nodes_dict.items():
            if n_data.get("is_signalized", False) and f"sig_{n_id}" not in self.signals:
                incoming = incoming_map.get(n_id, [])
                if len(incoming) >= 2:
                    sig_id = f"sig_{n_id}"
                    name = f"Signal Jct #{n_id}"
                    signal = TrafficSignal(
                        signal_id=sig_id,
                        node_id=n_id,
                        name=name,
                        lat=n_data["lat"],
                        lon=n_data["lon"],
                        incoming_edges=incoming
                    )
                    self.signals[sig_id] = signal
                    for e_id in incoming:
                        self.edge_to_signal_map[e_id] = signal

        logger.info(f"Initialized {len(self.signals)} Traffic Signal Controllers across Lucerne.")

    def reload_network(self):
        self._init_signals()

    def tick(self, dt: float):
        for signal in self.signals.values():
            signal.tick(dt)

    def is_edge_red(self, edge_id: str) -> bool:
        signal = self.edge_to_signal_map.get(edge_id)
        if signal:
            return signal.is_edge_red(edge_id)
        return False

    def update_signal_split(self, signal_id: str, new_green_split: float, cycle_time: float = None):
        if signal_id in self.signals:
            sig = self.signals[signal_id]
            sig.green_split = max(0.15, min(0.85, float(new_green_split)))
            if cycle_time:
                sig.cycle_time_sec = max(30.0, min(120.0, float(cycle_time)))
            logger.info(f"Updated signal {sig.name}: split={sig.green_split}, cycle={sig.cycle_time_sec}s")
            return sig.to_dict()
        return None

    def get_signals_state(self) -> List[dict]:
        return [sig.to_dict() for sig in self.signals.values()]
