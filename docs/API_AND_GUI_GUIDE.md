# 💻 API and User Interface Guide

This guide covers the REST endpoints, WebSocket streaming protocol, and user interface features for the **Lucerne Traffic Flow Simulator**.

---

## 1. REST API Reference

### Initial Data & Configuration

* **`GET /api/initial-data`**
  * Returns static road network polylines (2,600+ edges), landmark POIs (150+ POIs), and active regional gateway portals.

* **`POST /api/parameters`**
  * Updates global simulation parameters in real time.
  * **Payload**:
    ```json
    {
      "spawn_rate": 3.5,
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

* **`POST /api/preset`**
  * Applies pre-configured traffic scenario (`morning_peak`, `tourist_rush`, `freight_heavy`).

* **`POST /api/toggle-block`**
  * Toggles temporary road segment blockage for edge ID.

* **`POST /api/reset`**
  * Resets active vehicles, travel times, and simulation clock.

---

### Gateway Manager CRUD API

* **`GET /api/gateways`**: Returns list of all active and custom regional gateway portals.
* **`POST /api/gateways`**: Creates a custom gateway portal near provided `(lat, lon)` coordinates.
* **`PUT /api/gateways/{id}`**: Updates gateway attributes (`weight`, `enabled`, `direction`, `name`).
* **`DELETE /api/gateways/{id}`**: Deletes or disables a gateway.

---

## 2. Real-Time WebSocket Protocol (`ws://localhost:8000/ws`)

The server broadcasts tick state objects at ~20 FPS containing:
```json
{
  "sim_time": 124.5,
  "active_vehicles_count": 312,
  "completed_trips_count": 85,
  "avg_travel_time_sec": 42.1,
  "vehicles": [
    {
      "id": "veh_102",
      "class": "logistics",
      "color": "#f39c12",
      "lat": 47.0512,
      "lon": 8.3088,
      "heading": 124.0,
      "status": "IN_TRANSIT",
      "edge_id": "e_412"
    }
  ],
  "congested_edges": {
    "e_412": { "vc": 1.12, "color": "#e74c3c" }
  },
  "blocked_edges": ["e_65"],
  "top_chokepoints": [
    { "edge_id": "e_412", "name": "Seebrücke", "vc_ratio": 1.12, "count": 24 }
  ]
}
```

---

## 3. Web Dashboard Features

1. **Map Display Filters**:
   - Checkbox controls to toggle POI markers, Gateway markers, and Congestion edge lines.
   - Checkboxes to filter rendering by vehicle class (Personal Cars, Tourism Coaches, Freight Trucks, Buses). Unchecking classes isolates specific flows on the map.
2. **Interactive Legend**:
   - Click any legend row to highlight or isolate road edges matching that specific congestion level on screen.
3. **Gateway Manager Panel**:
   - View, toggle, or tune capacity weights for arterial portals. Click **+ Add Gateway** to place custom gateways directly on the Leaflet map canvas.
