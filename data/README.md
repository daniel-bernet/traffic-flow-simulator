# Data files

| File | What it is | Read by the app? |
|---|---|---|
| `aoi_polygon.json` | The default study-area polygon (29 vertices around Lucerne). Drawing a new area in the UI overwrites this file. | Yes, at startup |
| `gateways.json` | A reference snapshot of the 32 boundary gateways that the default study area produced from the OpenStreetMap data of September 2026. | No. Gateways are always recomputed from the cached network. |
| `lucerne_data_cache.json` | The processed road network, built on first run by `python -m src.data_loader`. Not in the repository (about 10 MB, git-ignored). | Yes |

## OpenStreetMap attribution

The road network is downloaded from OpenStreetMap at runtime.
`gateways.json` is derived from it (node IDs, street names, coordinates and
speed limits).

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

OpenStreetMap changes continuously, so a fresh download produces slightly
different node, edge and gateway counts than the snapshot here.
