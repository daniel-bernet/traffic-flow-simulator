# 🇨🇭 Lucerne Traffic Flow Simulator

An interactive, high-performance Python simulation software designed to model traffic flow, discover chokepoints, and analyze congestion dynamics across the city of Lucerne, Switzerland and its key regional gateways.

![Lucerne Traffic Simulator](https://img.shields.io/badge/Python-3.12-blue) ![Framework](https://img.shields.io/badge/FastAPI-WebGL%2FLeaflet-emerald) ![GIS](https://img.shields.io/badge/OSMnx-NetworkX-orange)

---

## 🌟 Key Features

* **Interactive Drag-and-Drop AOI Polygon Drawer & Graph Clipping**:
  * Planners can draw custom **AOI Boundary Polygons** directly on the Leaflet map canvas using the **"✍️ Draw AOI"** tool.
  * **Expanded Master Network**: Includes 11 core & outer ring municipalities (Lucerne, Ebikon, Emmen, Kriens, Horw, Meggen, Adligenswil, Dierikon, Buchrain, Malters, Rothenburg) with 4,204 nodes & 9,158 edges so drawn AOIs never hit "out of bounds".
  * **"Undo Last Node" (`↩️ Undo Node`)**: Remove placed vertices during polygon creation.
  * **Draggable Vertex Handles (`🖐️ Drag & Edit Handles`)**: Reshape polygon boundaries dynamically by dragging vertex handles or right-clicking to delete nodes.
  * **Edge Midpoint Insertion**: Insert new polygon vertices by dragging out edge segment midpoints.
  * **Real-Time Live Gateway Preview**: Client-side ray-casting calculates and renders glowing preview markers for $>30\text{ km/h}$ gateways live as polygon vertices are placed or dragged.
  * Traffic calculations and road network physics are clipped strictly inside the defined AOI polygon.

* **Boundary Crossing Gateway Extraction ($> 30\text{ km/h}$ Rule)**:
  * Gateways are extracted where roads cross the border of the drawn AOI polygon with a speed limit **$> 30\text{ km/h}$**.
  * Residential $20\text{--}30\text{ km/h}$ zones, alleyways, and footpaths are automatically filtered out.
  * Internal roundabouts (e.g. *Seetalplatz*) and internal intersections are 100% mathematically immune from being marked as gateways.

* **Watermark-Free Basemap Tile Switcher**:
  * Integrated **Esri World Dark Gray Canvas**, **OpenStreetMap Standard**, and **CartoDB Voyager** tile servers with zero `API KEY REQUIRED` watermarks.

* **3 Required Traffic Flow Categories**:
  1. **Internal ↔ Internal**: Resident commutes between residential neighborhoods, workplaces, and local POIs.
  2. **Outside → Simulation Area (Inflow)**: Commuters, tourists, and freight entering from regional gateways.
  3. **Simulation Area → Outside (Outflow)**: Outward traffic heading to highway portals.

* **Multi-Class Vehicle Dynamics**:
  * 🚗 **Personal Cars** (1.0 PCE): Standard commuter dynamics & dynamic shortest path routing.
  * 🚌 **Tourism Coaches** (1.5 PCE): Cautious speeds, high attraction to Kapellbrücke, Lion Monument, KKL, and Hotels.
  * 🚚 **Logistics / Freight** (2.0 PCE): Capped urban speeds, targeted towards commercial hubs & supermarkets.
  * 🚍 **Public Buses** (2.0 PCE): Dedicated transit corridors connecting main hubs.

* **Public Transit Bus Line Timetables & Delay Tracking (VBL Lucerne)**:
  * Models **5 core VBL public bus lines** (Line 1: 6 min headway, Line 6, Line 12, Line 14, Line 24).
  * Calculates real-time **Schedule Delay / Lateness (minutes)** for each line based on traffic congestion.
  * Dedicated **VBL Bus Transit Dashboard** in the sidebar with live delay status tags (🟢 *On Time*, 🟡 *Minor Delay*, 🔴 *Heavy Delay*).
  * **Click to Highlight Route**: Click any bus line card to highlight its full physical route on the map canvas.

* **Environmental $\text{CO}_2$ & Fuel Emissions Analytics**:
  * Live status header tracking estimated $\text{CO}_2$ emission rates ($\text{kg/hr}$) and fuel consumption ($\text{L/hr}$) across all active vehicles, incorporating stop-and-go congestion penalties.

* **BPR Delay Congestion Model & Bottleneck Detection**:
  * Dynamic travel time computed per road segment using the **Bureau of Public Roads (BPR) formula**:
    $$T_e = T_{e,0} \left[ 1 + 0.15 \left( \frac{V_e}{C_e} \right)^4 \right]$$
  * Dynamic edge color coding (Green $\to$ Yellow $\to$ Orange $\to$ Red).
  * Real-time **Chokepoint Leaderboard** highlighting top 5 congested road segments.

* **Interactive Dark Glassmorphism Web GUI**:
  * Real-time WebGL/Leaflet particle movement streaming at ~20 FPS via WebSockets.
  * **Instant Effect Layer & Vehicle Filters**: Checkboxes to toggle POIs, Gateways, Congestion Lines, or filter map rendering to isolate specific vehicle classes (e.g. view **Freight Trucks ONLY**).
  * **Interactive Legend**: Click any legend row to highlight or isolate road segments matching that specific congestion level on screen.
  * **Interactive Road Closures**: Click any road segment on the map to block/unblock it and watch vehicles dynamically reroute in real time!

---

## 🚀 Quick Start Guide

### Prerequisites
* Linux / macOS / Windows WSL2
* Python 3.10+
* `git`

### Installation & Launching

1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd traffic-flow-simulator
   ```

2. **Run the Launcher Script**:
   ```bash
   ./run.sh
   ```
   *`run.sh` will automatically create the `.venv` virtual environment, install dependencies, build/load the Lucerne network cache, and start the web application.*

3. **Open the Simulator in your Browser**:
   Navigate to:
   ```text
   http://localhost:8000
   ```

---

## 📚 Detailed Documentation (`docs/`)

* 🚪 [**Gateway & AOI Specification**](docs/GATEWAY_SPECIFICATION.md): AOI polygon drawing, graph clipping, $> 30\text{ km/h}$ gateway extraction, and REST API.
* 🚘 [**Traffic Simulation Model**](docs/TRAFFIC_SIMULATION_MODEL.md): BPR congestion formulas, vehicle kinematics, and dynamic rerouting.
* 💻 [**API & GUI User Guide**](docs/API_AND_GUI_GUIDE.md): REST endpoints, WebSocket JSON schema, and interface controls.

---

## 📜 License
MIT License - Open for urban research and traffic engineering analysis.