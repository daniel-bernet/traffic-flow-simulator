# Swiss open data sources (research notes, not implemented)

> **Status: research notes only.** None of the sources below is used by the code. This list was
> compiled from quick web searches during the project and was never checked against the
> sources themselves. Traffic volumes, quotas, layer names and URLs are **unverified and may be
> wrong or out of date**. The values that ended up in the code (gateway weights, signal
> locations, bus lines, parking garages, time-of-day curve) are placeholders, not taken from
> these datasets. The project was abandoned before any of this was integrated.

This document lists Swiss open data sources that a more realistic simulation of Lucerne would need.

---

## 1. Federal Geoportal — map.geo.admin.ch

### Overview
The **Federal Spatial Data Infrastructure (BGDI)** provides free access to over 600 geodata layers from Swiss federal offices.

### Key Endpoints

| Service | URL | Format |
|---------|-----|--------|
| Map Viewer | `https://map.geo.admin.ch` | Interactive web UI |
| REST Feature API | `https://api3.geo.admin.ch/rest/services/api/MapServer` | GeoJSON |
| WMTS Tiles | `https://wmts.geo.admin.ch/` | PNG/JPEG Tiles |
| WMS | `https://wms.geo.admin.ch/` | PNG/JPEG |
| STAC API (Bulk) | `https://data.geo.admin.ch/api/stac/v1.0/` | JSON/GeoPackage |
| Data Downloads | `https://data.geo.admin.ch/collections` | GeoPackage/Shapefile/CSV |

### Relevant Data Layers

#### 🚦 Traffic Infrastructure (ASTRA)
- **Layer ID**: `ch.astra.strassenverkehrsanlagen`
- **Content**: Traffic signal infrastructure, ramp metering, gantry signs
- **Use Case**: Validate and extend our traffic signal positions beyond the 25 hand-placed intersections
- **Format**: GeoJSON via REST API
- **Query Example**:
  ```
  GET https://api3.geo.admin.ch/rest/services/api/MapServer/find?layer=ch.astra.strassenverkehrsanlagen&searchText=Luzern&searchField=gemeinde&returnGeometry=true
  ```

#### 📊 Traffic Counting Stations (ASTRA Dauerzählstellen)
- **Layer ID**: `ch.astra.strassenverkehrszaehlung-uebergeordnet`
- **Content**: Permanent automatic traffic counting stations with Annual Average Daily Traffic (DTV/AADT) volumes
- **Key Lucerne Stations**:
  - **A2 Reussport Tunnel**: ~95,000–110,000 veh/day
  - **A2 Sonnenberg Tunnel**: ~65,000–82,000 veh/day
  - **A14 Ebikon / Rigi-Klett**: ~55,000–72,000 veh/day
- **Use Case**: Calibrate gateway inflow/outflow volumes and OD matrix proportions
- **Format**: GeoJSON, CSV (historical annual reports)
- **Query Example**:
  ```
  GET https://api3.geo.admin.ch/rest/services/api/MapServer/find?layer=ch.astra.strassenverkehrszaehlung-uebergeordnet&searchText=Luzern&returnGeometry=true
  ```

#### 🛣️ Road Network (swissTLM3D)
- **Layer ID**: `ch.swisstopo.swisstlm3d-strassen`
- **Content**: Complete Swiss road network with classification, lane counts, speed limits, surface type
- **Use Case**: Cross-reference and validate OSMnx lane data and speed limits
- **Format**: GeoPackage (bulk download), GeoJSON (API)
- **Note**: Coordinates in **EPSG:2056 (LV95)** — must be converted to **EPSG:4326 (WGS84)** for Leaflet

#### 🅿️ Parking Facilities
- **Layer ID**: `ch.bfe.ladestellen-elektromobilitaet` (EV charging + parking)
- **Content**: Federal parking/charging registry
- **Use Case**: Complement our 7 hardcoded parking garages with additional facilities

---

## 2. ASTRA (Federal Roads Office) — Traffic Counting Data

### ASTRA Verkehrszählung (Historical DTV)
- **Portal**: `https://www.astra.admin.ch/astra/de/home/dokumentation/daten-informationsprodukte/verkehrsdaten/daten-publikationen/automatische-strassenverkehrszaehlung.html`
- **Data**: Annual DTV reports (PDF + Excel) for all Swiss highways and national roads
- **Use Case**: Ground truth for gateway calibration

### Key DTV Values for Lucerne AOI Gateway Calibration

| Gateway Corridor | Road | DTV (veh/day) | Proposed Weight |
|-----------------|------|---------------|-----------------|
| A2 North (Emmen/Reussport) | Motorway A2 | ~95,000–110,000 | 10.0 |
| A2 South (Luzern Süd/Horw) | Motorway A2 | ~65,000–82,000 | 8.0 |
| A14 East (Ebikon/Rigi-Klett) | Motorway A14 | ~55,000–72,000 | 8.0 |
| Haldenstrasse (Meggen) | Cantonal | ~18,000–22,000 | 6.0 |
| Maihofstrasse (Ebikon) | Cantonal | ~14,000–18,000 | 5.0 |
| Zürichstrasse | Federal | ~12,000–16,000 | 5.0 |
| Baselstrasse (Littau) | Federal | ~10,000–14,000 | 4.0 |
| Kriens entrance | Cantonal | ~8,000–12,000 | 4.0 |

> These figures are unverified and were never used to weight the gateways.

---

## 3. Open Transport Data Switzerland — opentransportdata.swiss

### Overview
Central platform operated by the **Federal Office of Transport (BAV)** for all Swiss public transport data.

### Key Endpoints

| Service | URL | Format | Auth |
|---------|-----|--------|------|
| Portal | `https://opentransportdata.swiss` | — | — |
| API Hub | `https://data.opentransportdata.swiss/` | REST | API Key (free) |
| GTFS Static | `https://opentransportdata.swiss/dataset/timetable-2025-gtfs2` | ZIP/CSV | Free download |
| GTFS-RT Trip Updates | `https://api.opentransportdata.swiss/gtfsrt2020` | Protocol Buffers | API Key |
| DIDOK Stop Registry | `https://opentransportdata.swiss/dataset/service-points-full` | CSV/JSON | Free |

### Authentication
- **API Key Required** for real-time feeds (free registration)
- **Standard Quota**: 260,000 API calls / 6 months
- **Extended Quota**: Available on request via email

### GTFS Static Feed for VBL Lucerne
The national GTFS feed includes **all** VBL (Verkehrsbetriebe Luzern) routes:
- Filter by `agency_id` or `route_short_name` to extract Lucerne bus lines
- Contains: `routes.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`, `stops.txt`, `calendar.txt`
- **Use Case**: Replace our hardcoded VBL bus line definitions with exact GTFS-derived routes, stop sequences, and headways

### GTFS-RT Real-Time Feeds
- **Trip Updates**: `https://api.opentransportdata.swiss/gtfsrt2020`
- **Vehicle Positions**: Real-time GPS locations of all transit vehicles
- **Use Case**: Live delay injection into bus schedule simulation; real-time validation of transit lateness model

### DIDOK Master Stop Registry
- **Dataset**: `service-points-full`
- **Content**: All official Swiss public transport stops with coordinates, names, SLOID identifiers
- **Use Case**: Snap bus stops to exact official coordinates instead of nearest-node approximation

---

## 4. opendata.swiss — Swiss Open Data Portal

### Overview
Central catalog for all Swiss open government data (~11,000+ datasets).

### Relevant Datasets

| Dataset | Publisher | Use Case |
|---------|-----------|----------|
| Strassenverkehrszählung (Traffic Counts) | ASTRA | DTV gateway calibration |
| Swiss Public Transport (GTFS) | BAV | Transit route modeling |
| Motorisierungsgrad (Vehicle ownership) | BFS | Calibrate car density |
| Pendlermobilität (Commuter mobility) | BFS | OD matrix flow patterns |
| Bevölkerung Gemeinden (Population) | BFS | Residential density weights |

### Search Endpoint
```
https://opendata.swiss/api/3/action/package_search?q=Verkehrszählung+Luzern
```

---

## 5. Canton of Lucerne — geo.lu.ch

### Overview
The Canton of Lucerne follows an **"Open-By-Default"** policy for cantonal geodata.

### Key Endpoints

| Service | URL | Format |
|---------|-----|--------|
| Geoportal Map Viewer | `https://geoportal.lu.ch` | Interactive web UI |
| STAC API / Downloads | `https://daten.geo.lu.ch` | GeoPackage/CSV/GeoJSON |
| WMS/WFS | `https://geo.lu.ch/wms/` | WMS/WFS |

### Relevant Cantonal Datasets

#### 🚦 Traffic Signal Infrastructure (Lichtsignalanlagen)
- **STAC Collection**: `LICHTSGN_DS` / `LICHTSGN_V2_PT`
- **Content**: All cantonal traffic signal installations (position, type, operating status)
- **Use Case**: Replace the 25 hand-placed signals with all signalised intersections in the study area
- **Format**: GeoPackage, point geometry with attributes

#### 📊 Cantonal Traffic Counting Stations (KTV Zählstellen)
- **STAC Collection**: `VERKZLNG_COL`
- **Content**: Permanent and temporary counting stations on cantonal roads
- **Coverage**: Maihofstrasse, Haldenstrasse, Ostring/Sedel, Kriens, Littau corridors
- **Use Case**: Calibrate non-highway gateway volumes

#### 🚗 Level of Service Quality (LoS)
- **STAC Collection**: `ASVVQSVK_V3_PT`
- **Content**: Level of service quality metrics at key network nodes
- **Use Case**: Validate our BPR formula congestion calculations against official measurements

#### 🅿️ Parkleitsystem (PLS) Lucerne — Real-Time Parking Guidance
- **Feed URL**: Available via `https://pls.luzern.ch` or cantonal data feeds
- **Content**: Real-time occupancy data for all 7 major Lucerne parking garages
- **Coverage**:
  - Parkhaus Bahnhof (1,100 spaces)
  - Parkhaus Kesselturm (500 spaces)
  - Parkhaus Schweizerhof (420 spaces)
  - Parkhaus Altstadt (350 spaces)
  - Parkhaus Kantonalbank (300 spaces)
  - Parkhaus Hirzenmatt (250 spaces)
  - Parkhaus Kasernenplatz (200 spaces)
- **Use Case**: Initialize parking occupancy with real data; validate parking search traffic model

> [!TIP]
> The PLS data shows that parking search traffic (*Parksuchverkehr*) contributes **15–25%** of downtown Lucerne traffic volume during peak hours. This is already modeled in our `src/parking.py` module.

---

## 6. VBL (Verkehrsbetriebe Luzern) — Public Transport

### Data Access
VBL data is integrated into the national GTFS feed via `opentransportdata.swiss`.

### VBL Route Identification in GTFS
- Filter by `agency_name = "Verkehrsbetriebe Luzern"` or `agency_id`
- Key lines for our simulation:
  - **Line 1**: Obernau – Kriens – Bahnhof – Maihof (6 min headway peak)
  - **Line 6**: Matthof – Bahnhof – Biregghof (8 min headway)
  - **Line 12**: Littau Gare – Bahnhof – Würzenbach (7.5 min headway)
  - **Line 14**: Horw Zentrum – Bahnhof – Brüelstrasse (10 min headway)
  - **Line 24**: Bahnhof – Verkehrshaus – Meggen (15 min headway)
  - Additional lines: 2, 4, 7, 8, 9, 10, 11, 18, 19, 20, 22, 23

### Live Tracking
- **VBL Website**: `https://www.vbl.ch` (visual live tracker)
- **GTFS-RT Vehicle Positions**: Available via national GTFS-RT feed

---

## 7. Coordinate Systems

> [!WARNING]
> Swiss federal geodata uses **EPSG:2056 (LV95 / CH1903+)** coordinates. Our simulation uses **EPSG:4326 (WGS84)** for Leaflet. All swisstopo/geo.admin.ch data must be reprojected.

### Python Conversion Example
```python
from pyproj import Transformer
transformer = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
lon, lat = transformer.transform(east_lv95, north_lv95)
```

---

## 8. Integration roadmap (never started)

| Priority | Data Source | Effort | Impact |
|----------|-----------|--------|--------|
| 🔴 P0 | ASTRA DTV Gateway Calibration | Low | High — realistic inflow/outflow volumes |
| 🔴 P0 | GTFS Static (VBL exact routes) | Medium | High — accurate bus routes & schedules |
| 🟡 P1 | Canton Lichtsignalanlagen | Medium | High — replace the 25 hand-placed signals with real ones |
| 🟡 P1 | DIDOK Stop Registry | Low | Medium — exact stop coordinates |
| 🟡 P1 | PLS Real-Time Parking | Low | Medium — realistic initial occupancy |
| 🟢 P2 | ASTRA Strassenverkehrsanlagen | Medium | Medium — federal signal infrastructure |
| 🟢 P2 | Cantonal KTV Zählstellen | Medium | Medium — arterial road calibration |
| 🟢 P2 | GTFS-RT Live Delays | High | Low — requires API key & real-time loop |
| ⚪ P3 | swissTLM3D Road Network | High | Low — OSMnx already provides good coverage |

---

## 9. API Authentication Summary

| Source | Auth Required | Cost |
|--------|:---:|------|
| map.geo.admin.ch | ❌ No | Free |
| data.geo.admin.ch | ❌ No | Free |
| opendata.swiss | ❌ No | Free |
| geo.lu.ch | ❌ No | Free |
| ASTRA DTV Downloads | ❌ No | Free |
| opentransportdata.swiss (Static) | ❌ No | Free |
| opentransportdata.swiss (RT) | ✅ API Key | Free (260K calls/6mo) |
| PLS Luzern | ❌ No | Free |

---

*Last updated: September 2026*
