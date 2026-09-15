import os
import asyncio
import logging
import json
from typing import Optional, Literal, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.data_loader import LucerneDataLoader, DEFAULT_AOI_COORDS
from src.engine import TrafficSimulationEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

app = FastAPI(title="Lucerne Traffic Flow Simulator")

# Global instances
data_loader = LucerneDataLoader()
data_loader.load_data(use_cache=True)
engine = TrafficSimulationEngine(data_loader)

# Mount web static directory
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
os.makedirs(WEB_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New WebSocket client connected.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected.")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

simulation_running = True

async def simulation_loop():
    logger.info("Starting background simulation tick loop...")
    while simulation_running:
        if manager.active_connections:
            state = engine.tick(dt=0.2)
            await manager.broadcast(state)
        await asyncio.sleep(0.05)  # ~20 FPS stream

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())

@app.get("/")
async def get_index():
    index_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Lucerne Traffic Flow Simulator Backend Running</h1>")

@app.get("/api/initial-data")
async def get_initial_data():
    """Returns static road network geometry, master highspeed edges, POIs, gateways, and AOI polygon for UI map rendering."""
    network_edges = [
        {
            "id": e["edge_id"],
            "name": e["name"],
            "highway": e["highway"],
            "geometry": e["geometry"],
            "lanes": e["lanes"],
            "maxspeed": e["maxspeed"]
        }
        for e in data_loader.edges_list
    ]
    
    master_highspeed_edges = [
        {
            "id": e["edge_id"],
            "name": e["name"],
            "highway": e["highway"],
            "maxspeed": e["maxspeed"],
            "u_lat": data_loader.nodes_dict[e["u"]]["lat"],
            "u_lon": data_loader.nodes_dict[e["u"]]["lon"],
            "v_lat": data_loader.nodes_dict[e["v"]]["lat"],
            "v_lon": data_loader.nodes_dict[e["v"]]["lon"]
        }
        for e in data_loader.all_edges_list
        if e["maxspeed"] > 30.0 and e["u"] in data_loader.nodes_dict and e["v"] in data_loader.nodes_dict
    ]
    
    return {
        "edges": network_edges,
        "master_highspeed_edges": master_highspeed_edges,
        "pois": data_loader.pois,
        "gateways": data_loader.gateway_details,
        "aoi_polygon": data_loader.aoi_polygon_coords,
        "bus_lines": engine.bus_transit_manager.get_transit_state(),
        "signals": engine.signal_manager.get_signals_state()
    }

@app.get("/api/bus-lines")
async def get_bus_lines():
    """Returns VBL Lucerne public bus lines, stop sequences, headways, and real-time lateness."""
    return engine.bus_transit_manager.get_transit_state()

class SignalUpdatePayload(BaseModel):
    green_split: float
    cycle_time: Optional[float] = None

@app.get("/api/signals")
async def get_traffic_signals():
    return engine.signal_manager.get_signals_state()

@app.post("/api/signals/{signal_id}")
async def update_traffic_signal(signal_id: str, payload: SignalUpdatePayload):
    updated = engine.signal_manager.update_signal_split(signal_id, payload.green_split, payload.cycle_time)
    if not updated:
        raise HTTPException(status_code=404, detail="Signal not found.")
    return updated

# Area of Interest (AOI) Endpoints
class AOIPayload(BaseModel):
    polygon: List[List[float]]  # List of [lat, lon] coordinates

@app.get("/api/aoi")
async def get_aoi():
    return {
        "polygon": data_loader.aoi_polygon_coords,
        "active_edges_count": len(data_loader.edges_list),
        "gateways_count": len(data_loader.gateway_details)
    }

@app.post("/api/aoi")
async def update_aoi(payload: AOIPayload):
    if len(payload.polygon) < 3:
        raise HTTPException(status_code=400, detail="Polygon must have at least 3 vertex coordinates.")

    data_loader.apply_aoi_clipping_and_gateways(payload.polygon)
    engine.reload_aoi()
    
    return {
        "status": "ok",
        "polygon": data_loader.aoi_polygon_coords,
        "active_edges_count": len(data_loader.edges_list),
        "gateways_count": len(data_loader.gateway_details),
        "gateways": data_loader.gateway_details
    }

@app.delete("/api/aoi")
async def reset_aoi():
    data_loader.apply_aoi_clipping_and_gateways(DEFAULT_AOI_COORDS)
    engine.reload_aoi()
    return {
        "status": "reset",
        "polygon": data_loader.aoi_polygon_coords,
        "active_edges_count": len(data_loader.edges_list),
        "gateways_count": len(data_loader.gateway_details)
    }

# Gateway Manager Schemas
class GatewayCreatePayload(BaseModel):
    name: str
    lat: float
    lon: float
    weight: float = 5.0
    corridor_type: str = "secondary"

class GatewayUpdatePayload(BaseModel):
    name: Optional[str] = None
    weight: Optional[float] = None
    enabled: Optional[bool] = None
    direction: Optional[str] = None

@app.get("/api/gateways")
async def get_gateways():
    return data_loader.gateway_details

@app.post("/api/gateways")
async def create_custom_gateway(payload: GatewayCreatePayload):
    nearest_node_id = data_loader.find_nearest_node(payload.lat, payload.lon)
    if not nearest_node_id or nearest_node_id not in data_loader.nodes_dict:
        raise HTTPException(status_code=400, detail="Could not snap to nearest road network node.")

    import time
    node_data = data_loader.nodes_dict[nearest_node_id]
    gw_id = f"gw_custom_{nearest_node_id}_{int(time.time()*1000)}"
    new_gw = {
        "id": gw_id,
        "node_id": nearest_node_id,
        "name": payload.name,
        "corridor_type": payload.corridor_type,
        "lat": node_data["lat"],
        "lon": node_data["lon"],
        "weight": float(payload.weight),
        "direction": "both",
        "capacity_veh_per_hr": int(payload.weight * 400),
        "enabled": True,
        "is_custom": True
    }

    data_loader.gateway_details.append(new_gw)
    data_loader.save_gateways_to_json()
    engine.reload_gateways(data_loader.gateway_details)
    return new_gw

@app.put("/api/gateways/{gateway_id}")
async def update_gateway(gateway_id: str, payload: GatewayUpdatePayload):
    found = None
    for gw in data_loader.gateway_details:
        if gw["id"] == gateway_id:
            if payload.name is not None: gw["name"] = payload.name
            if payload.weight is not None: gw["weight"] = float(payload.weight)
            if payload.enabled is not None: gw["enabled"] = bool(payload.enabled)
            if payload.direction is not None: gw["direction"] = payload.direction
            found = gw
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Gateway not found.")

    data_loader.save_gateways_to_json()
    engine.reload_gateways(data_loader.gateway_details)
    return found

@app.delete("/api/gateways/{gateway_id}")
async def delete_gateway(gateway_id: str):
    updated = [gw for gw in data_loader.gateway_details if gw["id"] != gateway_id]
    if len(updated) == len(data_loader.gateway_details):
        raise HTTPException(status_code=404, detail="Gateway not found.")

    data_loader.gateway_details = updated
    data_loader.save_gateways_to_json()
    engine.reload_gateways(data_loader.gateway_details)
    return {"status": "deleted", "id": gateway_id}

class ParamPayload(BaseModel):
    spawn_rate: float = 2.0
    sim_speed_multiplier: float = 1.0
    flow_internal_ratio: float = 0.50
    flow_inflow_ratio: float = 0.25
    flow_outflow_ratio: float = 0.25
    class_personal_pct: float = 60.0
    class_tourism_pct: float = 20.0
    class_logistics_pct: float = 10.0
    class_bus_pct: float = 10.0

@app.post("/api/parameters")
async def update_parameters(payload: ParamPayload):
    engine.set_parameters(payload.dict())
    return {"status": "ok", "params": engine.params}

class ToggleBlockPayload(BaseModel):
    edge_id: str

@app.post("/api/toggle-block")
async def toggle_block(payload: ToggleBlockPayload):
    engine.toggle_blocked_edge(payload.edge_id)
    return {"status": "ok", "blocked_edges": list(engine.blocked_edges)}

@app.post("/api/reset")
async def reset_simulation():
    engine.reset()
    return {"status": "ok"}

class PresetPayload(BaseModel):
    preset_name: str

@app.post("/api/preset")
async def apply_preset(payload: PresetPayload):
    name = payload.preset_name
    if name == "morning_peak":
        engine.set_parameters({
            "spawn_rate": 4.5,
            "flow_internal_ratio": 0.60,
            "flow_inflow_ratio": 0.30,
            "flow_outflow_ratio": 0.10,
            "class_personal_pct": 75,
            "class_tourism_pct": 5,
            "class_logistics_pct": 10,
            "class_bus_pct": 10
        })
    elif name == "tourist_rush":
        engine.set_parameters({
            "spawn_rate": 3.5,
            "flow_internal_ratio": 0.30,
            "flow_inflow_ratio": 0.50,
            "flow_outflow_ratio": 0.20,
            "class_personal_pct": 35,
            "class_tourism_pct": 50,
            "class_logistics_pct": 5,
            "class_bus_pct": 10
        })
    elif name == "freight_heavy":
        engine.set_parameters({
            "spawn_rate": 3.0,
            "flow_internal_ratio": 0.30,
            "flow_inflow_ratio": 0.35,
            "flow_outflow_ratio": 0.35,
            "class_personal_pct": 40,
            "class_tourism_pct": 10,
            "class_logistics_pct": 40,
            "class_bus_pct": 10
        })
    return {"status": "ok", "preset": name, "params": engine.params}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            if cmd.get("action") == "toggle_block" and "edge_id" in cmd:
                engine.toggle_blocked_edge(cmd["edge_id"])
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        manager.disconnect(websocket)
