# 🇨🇭 Lucerne Traffic Flow Simulator

An interactive, high-performance Python simulation software designed to model traffic flow, discover chokepoints, and analyze congestion dynamics across the city of Lucerne, Switzerland and its key regional gateways.

![Lucerne Traffic Simulator](https://img.shields.io/badge/Python-3.12-blue) ![Framework](https://img.shields.io/badge/FastAPI-WebGL%2FLeaflet-emerald) ![GIS](https://img.shields.io/badge/OSMnx-NetworkX-orange)

---

## 🌟 Key Features

* **Expanded Regional Road Network & GIS Topology**:
  * Captures **2,607 nodes** and **5,714 road edges** covering Lucerne, Ebikon, Emmen/Seetalplatz, and Kriens via **OSMnx** / OpenStreetMap.
  * Extracted **159 Points of Interest (POIs)** including *Bahnhof Luzern*, *Kapellbrücke*, *KKL Luzern*, *Löwendenkmal*, *Luzerner Kantonsspital (LUKS)*, and major supermarket hubs.

* **Topological Convex Hull Gateway Extraction & Custom Gateway Manager**:
  * Programmatically filters out minor residential and service dead-ends, retaining **high-capacity arterial portals**:
    * **Gateway Maihof / Ebikon (Zürichstrasse - H2)**
    * **Gateway Seetalplatz / Emmenbrücke (H26 / Sedel)**
    * **Gateway A2 Süd (Luzern-Süd / Kriens / Schlund)**
    * **Gateway A14 East (Ebikon / Buchrain)**
    * **Gateway West (Bernstrasse / Littau / Malters - H10)**
    * **Gateway Ost (Haldenstrasse / Meggen - H4)**
    * **Gateway Horwerstrasse (Horw / Allmend)**
  * **Interactive Gateway Manager UI**: View, edit capacity weights, enable/disable, or place custom portals directly on the Leaflet map canvas using the **"+ Add Gateway"** tool.

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
  * **Scenario Presets**: One-click configuration for *Morning Peak*, *Tourist Rush*, and *Freight Heavy* traffic.

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

* 🚪 [**Gateway Specification**](docs/GATEWAY_SPECIFICATION.md): Topological convex hull extraction, arterial corridors, capacity weights, and custom manager API.
* 🚘 [**Traffic Simulation Model**](docs/TRAFFIC_SIMULATION_MODEL.md): BPR congestion formulas, vehicle kinematics, and dynamic rerouting.
* 💻 [**API & GUI User Guide**](docs/API_AND_GUI_GUIDE.md): REST endpoints, WebSocket JSON schema, and interface controls.

---

## 📂 Code Architecture

```text
traffic-flow-simulator/
├── .venv/                         # Python virtual environment
├── data/
│   ├── gateways.json              # Custom gateway portal persistence file
│   └── lucerne_data_cache.json    # Cached OSMnx graph, POIs & gateways
├── docs/
│   ├── GATEWAY_SPECIFICATION.md   # Gateway topology & portal specs
│   ├── TRAFFIC_SIMULATION_MODEL.md# BPR delay model & vehicle physics
│   └── API_AND_GUI_GUIDE.md       # API endpoints & dashboard guide
├── src/
│   ├── __init__.py
│   ├── data_loader.py             # Convex hull boundary cut & OSMnx parser
│   ├── vehicle.py                 # Traffic class specifications & particle kinematics
│   ├── od_generator.py            # Weighted Gravity model & NetworkX shortest path router
│   ├── engine.py                  # Simulation tick engine with BPR congestion formula
│   └── api.py                     # FastAPI server, Gateway CRUD endpoints & WebSocket streamer
├── web/
│   ├── index.html                 # Dark glassmorphism frontend dashboard
│   ├── style.css                  # UI styling & legend rules
│   └── app.js                     # Leaflet map canvas, Gateway Manager & WebSocket client
├── tests/
│   └── test_simulation.py         # Unit test suite
├── .gitignore                     # Git ignore file
├── run.sh                         # Execution script
├── requirements.txt               # Dependencies
└── README.md                      # Project documentation
```

---

## 🧪 Running Unit Tests

To run the automated simulation unit test suite:

```bash
source .venv/bin/activate
python3 -m unittest tests/test_simulation.py
```

---

## 📜 License
MIT License - Open for urban research and traffic engineering analysis.