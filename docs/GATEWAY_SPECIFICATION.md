# 🚪 Lucerne Area of Interest (AOI) & Boundary Gateway Specification

This document details the Area of Interest (AOI) polygon drawing mechanism, spatial graph clipping, and the $> 30\text{ km/h}$ directed boundary crossing algorithm for the **Lucerne Traffic Flow Simulator**.

---

## 1. Interactive Area of Interest (AOI) Polygon Concept

Instead of static administrative boundaries, planners can define their exact study region by drawing an **AOI Boundary Polygon** directly on the Leaflet map canvas:

```
           OUTSIDE SIMULATION REGION (Traffic Calculations Omitted)
  ======================================================================== AOI BOUNDARY RING (∂P_AOI)
           INSIDE SIMULATION REGION (Traffic & Physics Active)

    Outside Node u ------> [Edge e (maxspeed > 30 km/h)] ------> Inside Node v  ===> INFLOW GATEWAY
    Inside Node u  ------> [Edge e (maxspeed > 30 km/h)] ------> Outside Node v ===> OUTFLOW GATEWAY
```

### Key Principles

1. **Graph & Traffic Clipping**:
   - Only road network edges located inside or intersecting the user's drawn AOI polygon $P_{\text{AOI}}$ are included in traffic simulation calculations.
   - Roads outside $P_{\text{AOI}}$ are omitted to maximize performance and focus analysis strictly on the study area.

2. **Boundary Crossing Gateways ($> 30\text{ km/h}$ Rule)**:
   - Gateways are extracted as directed edges $(u, v)$ crossing the border of $P_{\text{AOI}}$ (one endpoint outside $P_{\text{AOI}}$ and one endpoint inside $P_{\text{AOI}}$).
   - **Speed Limit Filter**: Only roads with speed limit **$> 30\text{ km/h}$** (`maxspeed > 30`) are designated as gateways. Residential $20\text{--}30\text{ km/h}$ zones, alleyways, and footpaths are automatically filtered out.

3. **Guaranteed Internal Node Immunity**:
   - Roundabouts (e.g. Seetalplatz), internal intersections, and internal dead-ends have all their nodes inside $P_{\text{AOI}}$.
   - Since both endpoints are inside $P_{\text{AOI}}$, **internal roundabouts and junctions are mathematically 100% immune from being marked as gateways.**

---

## 2. Watermark-Free Basemap Tile Options

The application includes a live **Basemap Tile Theme Switcher**:
1. **Esri World Dark Gray Canvas** (`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`) - *Default (Watermark-Free)*.
2. **OpenStreetMap Standard** (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`).
3. **CartoDB Voyager** (`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`).

---

## 3. AOI Persistence & REST API

* **Persistence File**: `data/aoi_polygon.json`
* **REST Endpoints**:
  * `GET /api/aoi`: Returns active AOI polygon coordinates, clipped edge count, and gateways.
  * `POST /api/aoi`: Receives new `{ "polygon": [[lat, lon], ...] }`, clips road graph, extracts $> 30\text{ km/h}$ gateways, and hot-reloads simulation engine.
  * `DELETE /api/aoi`: Resets to default Lucerne AOI polygon.
