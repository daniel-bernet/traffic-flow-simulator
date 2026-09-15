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

---

## 4. Public Transit Schedule Lateness Engine (VBL Lucerne)

Public buses operate on fixed timetable departure headways along 5 primary Verkehrsbetriebe Luzern (VBL) transit corridors:
* **Line 1** (*Obernau – Kriens – Bahnhof – Maihof*): 6 min headway ($10\text{ buses/hr}$)
* **Line 6** (*Matthof – Bahnhof – Biregghof*): 8 min headway
* **Line 12** (*Littau Gare – Bahnhof – Würzenbach*): 7.5 min headway
* **Line 14** (*Horw Zentrum – Bahnhof – Brüelstrasse*): 10 min headway
* **Line 24** (*Bahnhof – Verkehrshaus – Meggen*): 15 min headway

### Schedule Delay (Lateness) Formula

For each active bus on Line $L$, the real-time schedule delay (lateness in seconds) is evaluated as:

$$\Delta T_{\text{schedule}} = \max\left(0, T_{\text{actual}} - \frac{k}{N} T_{\text{nominal}}\right)$$

Where:
* $T_{\text{actual}}$: Actual elapsed travel time of the bus since origin dispatch.
* $k / N$: Fractional distance completed along the line's route edge sequence.
* $T_{\text{nominal}}$: Target nominal schedule duration for the full line length under free-flow conditions.

Punctuality Status:
* 🟢 **ON TIME**: Average line lateness $< 1.5\text{ minutes}$.
* 🟡 **MINOR DELAY**: Average line lateness $1.5\text{--}4.0\text{ minutes}$.
* 🔴 **HEAVY DELAY**: Average line lateness $> 4.0\text{ minutes}$.

---

## 5. Environmental $\text{CO}_2$ & Fuel Emissions Model

The simulator evaluates total hourly $\text{CO}_2$ emissions ($\text{kg/hr}$) and fuel burn ($\text{L/hr}$) across all active vehicles:

$$\text{CO}_2\text{ Rate} = \sum_{v \in \text{Vehicles}} E_{\text{base}}(v) \times \left(\frac{\text{Speed}_v}{3600}\right) \times \left[ 1 + 1.2 \left(\min\left(3, \frac{V_e}{C_e}\right)\right)^2 \right] \times 3600$$

Where $E_{\text{base}}$ is the base emission rate per kilometer:
* **Personal Car**: $0.14\text{ kg CO}_2/\text{km}$ ($0.06\text{ L fuel/km}$)
* **Public Bus**: $0.65\text{ kg CO}_2/\text{km}$ ($0.26\text{ L fuel/km}$)
* **Freight Truck / Coach**: $0.85\text{ kg CO}_2/\text{km}$ ($0.35\text{ L fuel/km}$)
