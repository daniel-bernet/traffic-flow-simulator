# 🇨🇭 Lucerne Traffic Flow Simulator

An interactive, high-performance Python simulation software designed to model traffic flow, discover chokepoints, and analyze congestion dynamics across the city of Lucerne, Switzerland and its key regional gateways.

![Lucerne Traffic Simulator](https://img.shields.io/badge/Python-3.12-blue) ![Framework](https://img.shields.io/badge/FastAPI-WebGL%2FLeaflet-emerald) ![GIS](https://img.shields.io/badge/OSMnx-NetworkX-orange)

---

## 🌟 Key Features

* **Expanded Regional Road Network & GIS Topology**:
  * Captures **2,607 nodes** and **5,714 road edges** covering Lucerne, Ebikon, Emmen/Seetalplatz, and Kriens via **OSMnx** / OpenStreetMap.
  * Extracted **159 Points of Interest (POIs)** including *Bahnhof Luzern*, *Kapellbrücke*, *KKL Luzern*, *Löwendenkmal*, *Luzerner Kantonsspital*, and major supermarket hubs.

* **Arterial Gateway Hierarchy**:
  * Identifies **199 regional gateway portals** weighted by road hierarchy capacity:
    * **Gateway Nord-Ost (Maihof / Ebikon)** via Zürichstrasse corridor.
    * **Gateway Nord (Seetalplatz / Emmen)** via Sedel & Seetalstrasse corridor.
    * **Gateway Süd-West (Kriens / A2 Autobahn Süd)** via Luzernerstrasse & A2 portal.
    * **Gateway Ost (Haldenstrasse / Meggen)** via Haldenstrasse corridor.
    * **Gateway West (Bernstrasse / Littau / Malters)** via Hauptstrasse 10.

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
  * **Map Display Filters & Checkboxes**: Show/hide POIs, Gateways, Congestion Lines, or filter map rendering to isolate specific vehicle classes (e.g., view **Freight Trucks ONLY**).
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

## 📂 Code Architecture

```text
traffic-flow-simulator/
├── .venv/                         # Python virtual environment
├── data/
│   └── lucerne_data_cache.json    # Cached OSMnx graph, POIs & gateways
├── src/
│   ├── __init__.py
│   ├── data_loader.py             # OSMnx regional network query & gateway analyzer
│   ├── vehicle.py                 # Traffic class specifications & particle kinematics
│   ├── od_generator.py            # Weighted Gravity model & NetworkX shortest path router
│   ├── engine.py                  # Simulation tick engine with BPR congestion formula
│   └── api.py                     # FastAPI server & WebSocket simulation streamer
├── web/
│   ├── index.html                 # Dark glassmorphism frontend dashboard
│   ├── style.css                  # UI styling & legend rules
│   └── app.js                     # Leaflet map canvas, filter controls & WebSocket client
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