# 🚪 Lucerne Regional Gateway Portal Specification

This document details the mathematical directed edge boundary crossing algorithms, official highway corridors, capacity weighting rules, and custom Gateway Manager architecture for the **Lucerne Traffic Flow Simulator**.

---

## 1. Directed Spatial Edge Boundary Crossing Algorithm

Traditional node-based heuristics (such as spatial distance to bounding box or convex hull) suffer from high false-positive rates by erroneously selecting internal roundabouts, intersections, or dead-ends inside the simulation study area.

The simulator uses a **Directed Edge Boundary Crossing Algorithm** with **Mathematical Internal Node Immunity**:

```
                       OUTSIDE SIMULATION REGION (Ext B)
  ======================================================================== BOUNDARY RING (∂B)
                        INSIDE SIMULATION REGION (Int B)

   Node u (OUTSIDE) -------> [Edge e (INFLOW)] -------> Node v (INSIDE)
   Node u (INSIDE)  -------> [Edge e (OUTFLOW)] ------> Node v (OUTSIDE)
```

### Mathematical Definitions
1. **Simulation Region Polygon ($B$)**: A closed polygon enclosing the Lucerne study region.
2. **Containment Predicate ($\text{loc}(v)$)**:
   $$\text{loc}(v) = \begin{cases} \text{INSIDE} & \text{if } v \in \text{Int}(B) \\ \text{OUTSIDE} & \text{if } v \in \text{Ext}(B) \end{cases}$$
3. **Directed Gateway Edge ($e = (u, v)$)**:
   - **Inflow Gateway Edge**: $\text{loc}(u) = \text{OUTSIDE} \land \text{loc}(v) = \text{INSIDE}$.
   - **Outflow Gateway Edge**: $\text{loc}(u) = \text{INSIDE} \land \text{loc}(v) = \text{OUTSIDE}$.

### Guaranteed Internal Node Immunity
For any internal node $w \in \text{Int}(B)$ (such as a roundabout at Seetalplatz or Kasernenplatz, an internal junction, or dead-end inside Lucerne), all connected edges $e = (u, w)$ have both endpoints inside $B$ ($\text{loc}(u) = \text{INSIDE}$ and $\text{loc}(w) = \text{INSIDE}$). Since $\text{loc}(u) = \text{loc}(w)$, **internal roundabouts and internal intersections are mathematically IMMUNE to being designated as gateways.**

---

## 2. Official Gateway Corridor Matrix

The algorithm identifies **16 clean arterial gateway portals** located strictly at the perimeter ring of the study area:

| Portal ID | Gateway Name | Primary Highway | OSM Classification | Capacity Weight |
| :--- | :--- | :--- | :--- | :--- |
| `gw_a2_south` | **Gateway A2 Süd (Luzern-Süd / Kriens / Schlund)** | A2 / N2 | `motorway` | **10.0x** |
| `gw_a2_kasernenplatz` | **Gateway A2 Kasernenplatz / Reussport** | A2 / N2 | `motorway`, `primary` | **10.0x** |
| `gw_a2_sedel` | **Gateway A2 Sedel / Emmen Süd** | A2 / N2 | `motorway`, `primary` | **10.0x** |
| `gw_a14_east` | **Gateway A14 East (Ebikon / Buchrain)** | A14 / N14 | `motorway` | **10.0x** |
| `gw_maihof` | **Gateway Maihof / Ebikon (Zürichstrasse)** | Hauptstrasse 2 (H2) | `primary` | **6.0x** |
| `gw_seetalplatz` | **Gateway Seetalplatz / Emmenbrücke** | Hauptstrasse 26 (H26) | `primary` | **6.0x** |
| `gw_bernstrasse` | **Gateway West (Bernstrasse / Littau / Malters)** | Hauptstrasse 10 (H10) | `primary` | **6.0x** |
| `gw_haldenstrasse` | **Gateway Ost (Haldenstrasse / Meggen)** | Hauptstrasse 4 (H4) | `primary` | **6.0x** |
| `gw_horwerstrasse` | **Gateway Horwerstrasse (Horw / Allmend)** | Regional Arterial | `secondary` | **4.0x** |

---

## 3. Watermark-Free Map Tile Basemap

The map canvas uses **Esri World Dark Gray Canvas**:
- **Tile URL**: `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`
- **Attribution**: `Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ`
- **Result**: Crisp dark aesthetic with **zero `API KEY REQUIRED` watermarks**.

---

## 4. Custom Gateway Manager UI

Traffic planners can dynamically manage or add custom gateway portals:
- **Persistence**: `data/gateways.json`
- **Canvas Tool**: Click **+ Add Gateway** in the sidebar, then click anywhere on the Leaflet map canvas to drop a custom portal snapped to the nearest road network node.
