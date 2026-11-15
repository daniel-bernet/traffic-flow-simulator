# API and user interface

The FastAPI server (`src/api.py`) serves the web app at `http://localhost:8000` and listens on
`127.0.0.1` only. There is no authentication: the endpoints below can change the study area
and gateways, so don't expose the server to a network.

## 1. REST endpoints

### Network and state

| Method | Path | What it does |
|---|---|---|
| GET | `/api/initial-data` | Network segments in the study area, segments above 30 km/h in the whole master network (for the gateway preview), POIs, gateways, study-area polygon, bus lines, signals and parking garages |
| GET | `/api/bus-lines` | Bus lines with stops, headways and current lateness |
| GET | `/api/signals` | All signal controllers with phase, cycle and green split |
| POST | `/api/signals/{id}` | `{"green_split": 0.6, "cycle_time": 80}`; split is clamped to 0.15–0.85, cycle to 30–120 s |
| GET | `/api/parking-garages` | Garages with capacity, occupancy, queue and fee |

### Simulation control

| Method | Path | What it does |
|---|---|---|
| POST | `/api/parameters` | Spawn rate, speed multiplier, flow ratios and class percentages (see below) |
| POST | `/api/preset` | `{"preset_name": "morning_peak" \| "tourist_rush" \| "freight_heavy"}` |
| POST | `/api/set-time` | `{"hour": 17.5}` jumps the simulation clock to that time of day |
| POST | `/api/toggle-block` | `{"edge_id": "e_412"}` closes or reopens a segment |
| POST | `/api/reset` | Clears vehicles and statistics; closures stay unless `{"clear_closures": true}` |
| POST | `/api/pause`, `/api/resume`, `/api/toggle-pause` | Pause control |

`/api/parameters` payload (all fields optional, defaults shown):

```json
{
  "spawn_rate": 2.0,
  "sim_speed_multiplier": 1.0,
  "flow_internal_ratio": 0.50,
  "flow_inflow_ratio": 0.25,
  "flow_outflow_ratio": 0.25,
  "class_personal_pct": 60,
  "class_tourism_pct": 20,
  "class_logistics_pct": 10,
  "class_bus_pct": 10
}
```

### Study area and gateways

| Method | Path | What it does |
|---|---|---|
| GET | `/api/aoi` | Current polygon, number of active segments and gateways |
| POST | `/api/aoi` | `{"polygon": [[lat, lon], ...]}` (3+ vertices); recomputes clipping and gateways, saves `data/aoi_polygon.json`, resets the simulation |
| DELETE | `/api/aoi` | Restores the default polygon |
| GET | `/api/gateways` | All gateways |
| POST | `/api/gateways` | `{"name", "lat", "lon", "weight", "corridor_type"}`; adds a custom gateway at the nearest node (in memory only) |
| PUT | `/api/gateways/{id}` | Updates `name`, `weight`, `enabled` or `direction` |
| DELETE | `/api/gateways/{id}` | Removes a gateway |

## 2. WebSocket (`ws://localhost:8000/ws`)

While a client is connected, the server sends one state object per tick (roughly 15–20 per
second):

```json
{
  "sim_time": 124.6,
  "time_of_day_hour": 6.03,
  "diurnal_multiplier": 0.46,
  "is_paused": false,
  "active_vehicles_count": 312,
  "completed_trips_count": 85,
  "avg_travel_time_sec": 42.1,
  "dropped_spawns": 17,
  "stranded_count": 0,
  "co2_kg_hr": 1234.5,
  "fuel_l_hr": 523.0,
  "vehicles": [
    {"id": "veh_102", "class": "logistics", "color": "#f39c12", "lat": 47.0512, "lon": 8.3088,
     "heading": 124.0, "speed_kmh": 38.2, "status": "IN_TRANSIT", "edge_id": "e_412"}
  ],
  "congested_edges": {"e_412": {"vc": 1.12, "color": "#e74c3c"}},
  "blocked_edges": ["e_65"],
  "top_chokepoints": [{"edge_id": "e_412", "name": "Seebrücke", "vc_ratio": 1.12, "count": 24}],
  "bus_lines": ["..."],
  "signals": ["..."],
  "parking_garages": ["..."]
}
```

Timetable buses also carry `bus_line_id` and `delay_sec`. `avg_travel_time_sec` is the average
trip time of completed trips, not a delay. `co2_kg_hr` and `fuel_l_hr` are illustrative only
(see the model document).

## 3. User interface

- **Header:** active vehicles, completed trips, average trip time, CO₂ and fuel (illustrative),
  time of day, demand multiplier, pause button (also the space bar).
- **Left panel:** scenario presets, spawn rate, simulation speed (0.25x to 5x), jump to time of
  day (06:00, 08:00, 12:00, 17:30, 22:00), flow split and vehicle class proportions, reset.
- **Right panel:** study-area drawing tools, basemap choice, map layers (study area, POIs,
  gateways, signals, parking, congestion colours), vehicle class filters, bus lines with
  lateness (click a line to highlight its route), Gateway Manager, signal tuner, parking
  garages, chokepoint leaderboard and an interactive legend.
- **Map:** click a segment to close or reopen it. Click a legend row to highlight segments of
  that congestion level.
