import os
import asyncio
import logging
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.data_loader import LucerneDataLoader
from src.engine import TrafficSimulationEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

app = FastAPI(title="Lucerne Traffic Flow Simulator")

# Global instances
data_loader = LucerneDataLoader()
data_loader.load_data(use_cache=True)
engine = TrafficSimulationEngine(data_loader)

# Mount web frontend static directory
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

# Background Simulation Loop Task
simulation_running = True

async def simulation_loop():
    logger.info("Starting background simulation tick loop...")
    while simulation_running:
        if manager.active_connections:
            state = engine.tick(dt=0.2)  # Tick step
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
    return HTMLResponse("<h1>Lucerne Traffic Flow Simulator Backend Running</h1><p>Frontend file index.html is loading...</p>")

@app.get("/api/initial-data")
async def get_initial_data():
    """Returns static road network geometry, POIs, gateways, and building nodes for UI map rendering."""
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
    
    gateways_payload = data_loader.gateway_details if hasattr(data_loader, "gateway_details") and data_loader.gateway_details else [
        {"id": g_id, "name": data_loader.nodes_dict[g_id].get("gateway_name", "Gateway"), "weight": data_loader.nodes_dict[g_id].get("gateway_weight", 1.0), "lat": data_loader.nodes_dict[g_id]["lat"], "lon": data_loader.nodes_dict[g_id]["lon"]}
        for g_id in data_loader.gateway_nodes if g_id in data_loader.nodes_dict
    ]

    return {
        "edges": network_edges,
        "pois": data_loader.pois,
        "gateways": gateways_payload
    }

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
            # Handle incoming WebSocket commands if any
            data = await websocket.receive_text()
            cmd = json.loads(data)
            if cmd.get("action") == "toggle_block" and "edge_id" in cmd:
                engine.toggle_blocked_edge(cmd["edge_id"])
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        manager.disconnect(websocket)
