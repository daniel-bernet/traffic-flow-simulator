# Study area and gateways

How the study area (AOI, area of interest) clips the road network and where traffic enters and
leaves it. Code: `src/data_loader.py`, `apply_aoi_clipping_and_gateways`.

## 1. Master network

On first run, `python -m src.data_loader` downloads the drivable road network for 11
municipalities from OpenStreetMap through OSMnx: Lucerne, Ebikon, Emmen, Kriens, Horw, Meggen,
Adligenswil, Dierikon, Buchrain, Malters and Rothenburg. The download takes a few minutes.

The size depends on the OSM snapshot. In November 2026 it was about 4,200 nodes and 9,150
directed edges. If the download fails, it is retried three times and then the build stops with
an error. (Earlier versions silently fell back to the city of Lucerne alone.) The processed
network is cached in `data/lucerne_data_cache.json`, together with when and how it was fetched.

## 2. Clipping

The study area is a polygon. A segment stays in the simulation if at least one of its two
end nodes lies inside the polygon. With the default polygon (`data/aoi_polygon.json`), about
7,500 of the ~9,150 segments remain.

## 3. Gateways

A gateway is a directed segment that crosses the polygon boundary (one end inside, one
outside) and has a speed limit above 30 km/h. Residential 30 km/h zones and slower roads are
therefore never gateways. Segments with both ends inside the polygon, such as roundabouts near
the boundary, can't become gateways by construction.

Crossings within about 100 m of each other (coordinates rounded to three decimals) are merged
into one gateway, keeping the highest weight. A gateway's weight is its road-class weight
(motorway 10, trunk 8, primary 6, secondary 4, tertiary 2, others 4) times a hand-picked
multiplier for a few named roads. These weights are unverified placeholders.

The default study area produces 32 gateways. `data/gateways.json` is a reference snapshot of
that set; the app does not read or write it.

## 4. Drawing a study area in the UI

- **Draw AOI:** click to place vertices; Undo Node (or Ctrl+Z / Backspace) removes the last one.
- **Drag & Edit Handles:** drag a vertex to move it, right-click or double-click to delete it,
  drag an edge midpoint to insert a vertex.
- While drawing, the browser previews where segments faster than 30 km/h cross the boundary.
- Applying the polygon recomputes clipping and gateways on the server, saves the polygon to
  `data/aoi_polygon.json` and resets the simulation. **Reset AOI** restores the default.

## 5. Gateway Manager

The Gateway Manager panel lists all gateways. Each can be enabled or disabled and given a new
weight. **+ Add Gateway** places a custom gateway at the nearest network node. Custom gateways
survive a study-area change but are kept in memory only and are lost when the server restarts.

## 6. Basemaps

The map can show the Esri World Dark Gray Canvas (default) or OpenStreetMap Standard. Each shows
its provider's attribution. Both work without an API key; the CARTO basemaps that earlier
versions offered now require one and were removed.
