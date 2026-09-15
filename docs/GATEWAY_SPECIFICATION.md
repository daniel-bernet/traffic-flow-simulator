# 🚪 Lucerne Regional Gateway Portal Specification

This document details the topological extraction algorithms, official highway corridors, capacity weighting rules, and custom Gateway Manager architecture for the **Lucerne Traffic Flow Simulator**.

---

## 1. Official Lucerne Regional Arterial Corridors

The simulator models entry and exit portals across the Lucerne metropolitan area. The default portals map directly to official high-capacity Swiss highway corridors:

```
                  [Gateway Seetalplatz / Emmenbrücke]
                                 |
 [Gateway Bernstrasse / Littau] --- [Bahnhof / City Core] --- [Gateway Maihof / Ebikon]
                                 |                          |
                   [Gateway A2 Süd / Kriens]       [Gateway Haldenstrasse / Meggen]
```

### Official Arterial Portal Matrix

| Portal ID | Gateway Name | Primary Highway | OSM Classification | Default Capacity Weight |
| :--- | :--- | :--- | :--- | :--- |
| `gw_a2_south` | **Gateway A2 Süd (Kriens / Schlund / Horw)** | A2 / N2 | `motorway`, `motorway_link` | **10.0x** |
| `gw_a2_kasernenplatz` | **Gateway A2 Kasernenplatz / Reussport** | A2 / N2 | `motorway`, `primary` | **10.0x** |
| `gw_a2_sedel` | **Gateway A2 Sedel / Emmen Süd** | A2 / N2 | `motorway`, `primary` | **10.0x** |
| `gw_a14_east` | **Gateway A14 East (Ebikon / Buchrain)** | A14 / N14 | `motorway`, `motorway_link` | **10.0x** |
| `gw_maihof` | **Gateway Maihof / Ebikon (Zürichstrasse)** | Hauptstrasse 2 (H2) | `primary`, `primary_link` | **6.0x** |
| `gw_seetalplatz` | **Gateway Seetalplatz / Emmenbrücke** | Hauptstrasse 26 (H26) | `primary`, `primary_link` | **6.0x** |
| `gw_bernstrasse` | **Gateway West (Bernstrasse / Littau / Malters)** | Hauptstrasse 10 (H10) | `primary` | **6.0x** |
| `gw_haldenstrasse` | **Gateway Ost (Haldenstrasse / Meggen)** | Hauptstrasse 4 (H4) | `primary` | **6.0x** |
| `gw_horwerstrasse` | **Gateway Horwerstrasse (Horw / Allmend)** | Regional Arterial | `secondary` | **4.0x** |

---

## 2. Topological Cut-Node Boundary Extraction Algorithm

To prevent low-capacity residential dead-ends from becoming default entry points, `src/data_loader.py` implements a **Convex Hull Boundary Cut Algorithm**:

1. **Spatial Boundary Hull**: Computes the 2D spatial convex hull surrounding all projected road network nodes in Lucerne, Ebikon, Emmen, and Kriens.
2. **Functional Highway Filter**: Discards all edges whose `highway` tag is not contained within `ALLOWED_HIGHWAYS`:
   $$\text{ALLOWED\_HIGHWAYS} = \{\text{'motorway'}, \text{'motorway\_link'}, \text{'trunk'}, \text{'trunk\_link'}, \text{'primary'}, \text{'primary\_link'}, \text{'secondary'}, \text{'secondary\_link'}\}$$
3. **Capacity Weight Allocation**: Assigns relative spawn weights based on road class:
   - Motorway / Autobahn: `10.0x`
   - Trunk / Expressway: `8.0x`
   - Primary / Hauptstrasse: `6.0x`
   - Secondary Arterial: `4.0x`
4. **Spatial Portal Clustering**: Merges duplicate dual-carriageway node portals within $300\,\text{m}$ radius into single unified gateway entities.

---

## 3. Interactive Gateway Manager UI & JSON Persistence

Traffic planners can dynamically manage, modify, or add custom gateway portals directly from the browser interface:

* **Persistence File**: `data/gateways.json`
* **Custom Gateway Creation**: Click **"+ Add Gateway"** in the sidebar, then click anywhere on the Leaflet map canvas. The simulator snaps the location to the nearest road network node and instantiates a custom portal.
* **Live Attribute Tuning**: Adjust capacity weight sliders or toggle enabled state in the **Gateway Manager** panel. Updates hot-reload into the simulation engine without restarting.
