# Simulation model

This document describes what the simulation engine actually computes, including where it falls
short of a valid traffic model. Code references are to `src/`.

## 1. Overview

Each tick (`engine.py`, `TrafficSimulationEngine.tick`):

1. Signal controllers advance their phase timers.
2. A congestion state (V/C ratio, colour, nominal speed) is computed per road segment.
3. Vehicles move along their pre-computed routes using the Intelligent Driver Model (IDM).
4. Arrived vehicles are removed; parking garages and the bus timetable are updated.
5. New vehicles are spawned according to the spawn rate and the time-of-day multiplier.

The web server runs one tick of `dt = 0.2 s` (times the speed multiplier) per loop with a 50 ms
pause, so "1.0x" runs roughly three to four times faster than real time and varies with machine
load. The simulation clock is not calibrated.

## 2. Demand (who travels where)

`od_generator.py`.

- **Flow types:** each new vehicle is internal (start and end inside the study area), inflow
  (starts at a gateway) or outflow (ends at a gateway), drawn from adjustable ratios (default
  50 / 25 / 25 %).
- **Land use is random.** At build time, all network nodes are shuffled with a fixed seed and
  split 60 / 40 into "residential" and "commercial". It does not reflect real land use.
- **Origins** are picked uniformly from the residential or commercial set, or from a gateway
  weighted by its road-class weight.
- **Destinations** use a gravity-style choice: 25 random candidates, weighted by
  `attractiveness / (distance_km + 0.5)^1.5`. Points of interest from OpenStreetMap (city of
  Lucerne only) get a higher attractiveness.
- **Time of day:** the spawn rate is multiplied by a 24-hour curve with peaks at 08:00 (2.2x)
  and 17:00 (2.5x). The curve is an unverified placeholder, and the same curve applies to
  every day; weekends are not modelled.
- Unroutable origin–destination pairs are counted as `dropped_spawns`.

Gateway weights are road-class weights (motorway 10, primary 6, secondary 4, ...) with
hand-picked multipliers for a few named roads. They are unverified placeholders and are not
calibrated against traffic counts.

## 3. Route choice

Each vehicle gets the fastest route under **free-flow conditions** (segment length divided by
speed limit) when it is created. Routes are cached per origin–destination pair. A vehicle is
only rerouted when a road on its remaining route is closed; it then replans from its current
position. **Congestion never changes a route.** There is no traffic assignment or equilibrium.

## 4. Vehicle movement (IDM)

`vehicle.py`, `Vehicle.update_position`.

Each vehicle follows the Intelligent Driver Model:

$$a = a_{\max}\left[1 - \left(\frac{v}{v_0}\right)^4 - \left(\frac{s^*}{s}\right)^2\right], \qquad s^* = s_0 + vT + \frac{v\,\Delta v}{2\sqrt{a_{\max} b}}$$

with $a_{\max} = 2.0$ m/s², $b = 2.5$ m/s², $s_0 = 4$ m, $T = 1.2$ s. The desired speed $v_0$ is the
speed limit times a class factor. A red signal within 80 m acts as a stationary obstacle at the
stop line, and a hard constraint stops vehicles from crossing it in one large step. A vehicle
that has stopped with more than 10 m of free road ahead creeps at 0.5 m/s.

Limitations:

- Vehicles only interact with the vehicle ahead **on the same segment and lane**. A full
  segment does not block the one behind it, so queues never spill back through junctions.
- Only 25 hand-placed signals (plus any OSM-tagged signal that survives graph simplification)
  control junctions. About 2,000 other junctions have no control at all; vehicles pass through
  them without yielding.
- Lanes are assigned at random on entering a segment; there is no lane changing.
- On screen, queued vehicles are drawn 6 m apart for readability.

## 5. Congestion state (BPR)

`engine.py`, `_update_edge_congestion`.

Each segment gets a ratio and a nominal speed from the Bureau of Public Roads function:

$$T = T_0 \left[1 + 0.15 \left(\frac{V}{C}\right)^4\right]$$

How it is used, and how it is not:

- **V/C is dimensionally incorrect.** `V` is the number of vehicles (in passenger car
  equivalents) currently on the segment, and `C` is 5 % of the segment's hourly capacity
  (minimum 5). A count is divided by a flow, so the ratio grows with segment length: long
  segments look congested at the same traffic density.
- The resulting nominal speed is **not used by the vehicles** (they move by IDM) and **not used
  for routing**. It only drives the map colours, the chokepoint leaderboard and the CO₂/fuel
  estimate.

| V/C | Colour |
|---|---|
| < 0.5 | Green |
| 0.5 – 0.8 | Yellow |
| 0.8 – 1.1 | Orange |
| ≥ 1.1 | Red |
| closed | Purple |

Capacity per lane is 1,200 veh/h for motorway, trunk and primary roads and 600 veh/h otherwise
(minimum 300 per segment). Lane counts are per direction (see PR #1 for the OSM lane fix).

## 6. Vehicle classes

| Class | PCE | Speed factor | Length | Main destinations |
|---|---|---|---|---|
| Personal car | 1.0 | 1.00 | 4.5 m | Commercial nodes, POIs |
| Tourist coach | 1.5 | 0.85 | 10 m | POIs |
| Freight truck | 2.0 | 0.80 | 12 m | Commercial nodes |
| Bus (random) | 2.0 | 0.90 | 15 m | Between POIs |

Timetable buses (section 8) are added on top of the randomly spawned "bus" class.

## 7. Signals

`traffic_signals.py`. 25 hand-placed locations (unverified placeholder coordinates) snapped to
the nearest node. Each has two phases: the incoming segments are split in half by list order,
not by real approach direction. The cycle length is 90 s for 4+ incoming segments, 75 s for 3
and 60 s otherwise, with 3 s yellow. Green split and cycle can be changed in the UI.

## 8. Bus lines and lateness

`bus_transit.py`. Five simplified VBL lines (unverified placeholder stops and headways). Buses
are dispatched at the line headway and follow shortest paths between the listed stops. The
nominal trip time assumes 35 km/h. Lateness per bus:

$$\Delta T = \max\left(0,\ T_{\text{actual}} - \frac{k}{N}\,T_{\text{nominal}}\right)$$

where $k/N$ is the fraction of route segments completed. A line is "on time" below 1.5 min average
lateness, "minor delay" up to 4 min, "heavy delay" above.

## 9. Parking garages

`parking.py`. Seven garages (unverified placeholder names, capacities and fees) start 40–70 %
full. A vehicle whose destination is a garage node is removed from the road and joins a gate
queue (one entry every 2 s); parked vehicles leave the garage count after 5–20 minutes. The
queue is bookkeeping only; vehicles do not wait on the road.

## 10. CO₂ and fuel (illustrative only)

The header shows a rough CO₂ and fuel rate: per vehicle, a base rate per km (car 0.14 kg CO₂,
bus 0.65 kg, coach and truck 0.85 kg) times the segment's nominal speed, times a congestion
penalty `1 + 1.2 · min(3, V/C)²`. Because it inherits the incorrect V/C ratio, the numbers are
far too high and are only meant as a relative indicator.

## 11. Known issues

- Two carriageways that cross the study-area boundary at the same node produce two gateways
  with the same ID (4 such pairs in the default area), so editing one in the Gateway Manager
  can affect both.
- Custom gateways added in the UI are kept in memory only and are lost on restart.
