# 🚘 Traffic Simulation Engine Architecture & Modeling Specification

This document describes the mathematical principles, congestion delay formulas, Origin-Destination (O-D) matrix generation, and multi-class vehicle dynamics used in the **Lucerne Traffic Flow Simulator**.

---

## 1. Bureau of Public Roads (BPR) Dynamic Congestion Model

Road segment travel times $T_e$ are re-evaluated dynamically every simulation tick using the **Bureau of Public Roads (BPR) function**:

$$T_e = T_{e,0} \left[ 1 + \alpha \left( \frac{V_e}{C_e} \right)^\beta \right]$$

Where:
* $T_{e,0}$: Free-flow travel time on road edge $e$ (length / speed limit).
* $V_e$: Total active volume on edge $e$ in Passenger Car Equivalents (PCE).
* $C_e$: Base capacity of edge $e$ (lanes $\times$ capacity per lane).
* $\alpha = 0.15$: Standard BPR delay scaling factor.
* $\beta = 4.0$: Congestion exponent shaping non-linear queue formation.

### Dynamic Speed and Level of Service (LOS)

| Volume / Capacity ($V/C$) Ratio | Level of Service (LOS) | Map Edge Color | Traffic Flow State |
| :--- | :--- | :--- | :--- |
| $V/C < 0.5$ | LOS A / B | **Green** (`#2ecc71`) | Free Flow |
| $0.5 \le V/C < 0.8$ | LOS C | **Yellow** (`#f1c40f`) | Moderate Traffic |
| $0.8 \le V/C < 1.0$ | LOS D / E | **Orange** (`#e67e22`) | Heavy Traffic |
| $V/C \ge 1.0$ | LOS F | **Red** (`#e74c3c`) | Congested Chokepoint |
| Blocked | Closed | **Purple Striped** (`#8e44ad`) | Temporary Closure / Detour |

---

## 2. Multi-Class Vehicle Specification Matrix

Vehicles operate with distinct Passenger Car Equivalent (PCE) weights, speed capabilities, length dimensions, and origin-destination preferences:

| Traffic Class | PCE Weight | Speed Multiplier | Marker Color | Primary Routing Destination |
| :--- | :--- | :--- | :--- | :--- |
| **Personal Car** | 1.0 | $1.0\times$ | Blue (`#3498db`) | Residential $\leftrightarrow$ Commercial & Regional Portals |
| **Tourism Coach** | 1.5 | $0.85\times$ | Purple (`#9b59b6`) | Kapellbrücke, Lion Monument, KKL, Hotels |
| **Freight Truck** | 2.0 | $0.80\times$ | Orange (`#f39c12`) | Supermarkets, Industrial Zones, Highway Portals |
| **Public Bus** | 2.0 | $0.90\times$ | Red (`#e74c3c`) | Dedicated VBL Transit Hub Corridors |

---

## 3. Dynamic Rerouting Engine

When a road segment is manually closed by clicking it on the map:
1. Edge speed drops to near zero ($0.5\,\text{m/s}$), and edge $V/C$ ratio spikes to $5.0$.
2. All active vehicles heading towards or currently on that edge trigger dynamic **A* shortest path recalculation** via NetworkX:
   $$\text{Weight}(u, v) = \begin{cases} 10^9 & \text{if edge } (u,v) \text{ is blocked} \\ T_e & \text{otherwise} \end{cases}$$
3. Traffic dynamically diverts to parallel bypass arterial roads in real time.
