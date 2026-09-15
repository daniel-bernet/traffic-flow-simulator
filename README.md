# 🇨🇭 Lucerne Traffic Flow Simulator

An interactive, high-performance Python simulation software designed to model traffic flow, discover chokepoints, and analyze congestion dynamics across the city of Lucerne, Switzerland and its key regional gateways.

![Lucerne Traffic Simulator](https://img.shields.io/badge/Python-3.12-blue) ![Framework](https://img.shields.io/badge/FastAPI-WebGL%2FLeaflet-emerald) ![GIS](https://img.shields.io/badge/OSMnx-NetworkX-orange)

---

## 🌟 Key Features

* **Expanded Regional Road Network & GIS Topology**:
  * Captures **2,607 nodes** and **5,714 road edges** covering Lucerne, Ebikon, Emmen/Seetalplatz, and Kriens via **OSMnx** / OpenStreetMap.
  * Extracted **159 Points of Interest (POIs)** including *Bahnhof Luzern*, *Kapellbrücke*, *KKL Luzern*, *Löwendenkmal*, *Luzerner Kantonsspital (LUKS)*, and major supermarket hubs.

* **Directed Edge Boundary Crossing Gateway Algorithm**:
  * Mathematically guarantees **zero false internal gateways** (internal roundabouts, intersections, and dead-ends inside Lucerne are 100% immune from being marked as gateways).
  * Extracts **16 clean arterial gateway portals** where high-capacity roads cross the simulation perimeter boundary ring:
    * **Gateway Maihof / Ebikon (Zürichstrasse - H2)**
    * **Gateway Seetalplatz / Emmenbrücke (H26 / Sedel)**
    * **Gateway A2 Süd (Luzern-Süd / Kriens / Schlund)**
    * **Gateway A14 East (Ebikon / Buchrain)**
    * **Gateway West (Bernstrasse / Littau / Malters - H10)**
    * **Gateway Ost (Haldenstrasse / Meggen - H4)**
    * **Gateway Horwerstrasse (Horw / Allmend)**
  * **Interactive Gateway Manager UI**: View, edit capacity weights, enable/disable, or place custom portals directly on the Leaflet map canvas using the **"+ Add Gateway"** tool.

* **Watermark-Free Dark Basemap**:
  * Powered by **Esri World Dark Gray Canvas** tile server with zero `API KEY REQUIRED` watermarks.

* **3 Required Traffic Flow Categories**:
  1. **Internal ↔ Internal**: Resident commutes between residential neighborhoods, workplaces, and local POIs.
  2. **Outside → Simulation Area (Inflow)**: Commuters, tourists, and freight entering from regional gateways.
  3. **Simulation Area → Outside (Outflow)**: Outward traffic heading to highway portals.

* **Multi-Class Vehicle Dynamics**:
  * 🚗 **Personal Cars** (1.0 PCE): Standard commuter dynamics & dynamic shortest path routing.
  * 🚌 **Tourism Coaches** (1.5 PCE): Cautious speeds, high attraction to Kapellbrücke, Lion Monument, KKL, and Hotels.
  * 🚚 **Logistics / Freight** (2.0 PCE): Capped urban speeds, targeted towards commercial hubs & supermarkets.
  * 🚍 **Public Buses** (2.0 PCE): Dedicated transit corridors connecting main hubs.

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

* 🚪 [**Gateway Specification**](docs/GATEWAY_SPECIFICATION.md): Directed edge boundary crossing algorithm, zero internal node proof, arterial corridors, and custom manager API.
* 🚘 [**Traffic Simulation Model**](docs/TRAFFIC_SIMULATION_MODEL.md): BPR congestion formulas, vehicle kinematics, and dynamic rerouting.
* 💻 [**API & GUI User Guide**](docs/API_AND_GUI_GUIDE.md): REST endpoints, WebSocket JSON schema, and interface controls.

---

## 📜 License
MIT License - Open for urban research and traffic engineering analysis.