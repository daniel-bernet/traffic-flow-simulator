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

## 4. Expanded Master Regional Graph Coverage

To ensure that user-drawn AOI polygons never go out of bounds, the simulator fetches a comprehensive master regional road network encompassing **11 core and outer ring municipalities**:
* **Core City**: Lucerne
* **Outer Ring Municipalities**: Ebikon, Emmen, Kriens, Horw, Meggen, Adligenswil, Dierikon, Buchrain, Malters, Rothenburg.

Master network size: **4,204 nodes** and **9,158 directed edges**.

---

## 5. Advanced Interactive AOI Drawer & Drag-and-Drop Tool

The interactive web canvas provides full control over the AOI polygon boundary:

1. **"Undo Last Node" (`↩️ Undo Node` / `Ctrl+Z` / `Backspace`)**:
   - Allows planners to step backward while placing polygon boundary vertices.

2. **Draggable Vertex Handles (`🖐️ Drag & Edit Handles`)**:
   - Displays interactive handles on every polygon vertex.
   - Dragging handles reshapes the AOI boundary in real time.
   - Right-clicking or double-clicking a handle deletes that vertex.

3. **Edge Midpoint Node Insertion**:
   - Midpoint handles are rendered along each polygon edge segment.
   - Dragging or clicking a midpoint handle instantly inserts a new vertex handle at that edge.

4. **Real-Time Live Gateway Preview**:
   - As the polygon is drawn or vertex handles are dragged, client-side ray-casting line intersection calculates where directed road edges with `maxspeed > 30 km/h` cross the candidate boundary ring.
   - Pulsing amber diamond markers preview the exact gateway entry/exit portals that will be generated before applying changes.

5. **Custom Gateway CRUD & Persistence**:
   - Custom gateways created via map clicks snap to nearest master road graph nodes and persist in `data/gateways.json`.
   - Custom gateways remain preserved even when the AOI boundary polygon is edited or reset.
