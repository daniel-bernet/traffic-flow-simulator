// Lucerne Traffic Flow Simulator Frontend App

let map;
let edgePolylines = {};  // edge_id -> L.polyline
let vehicleMarkers = {}; // vehicle_id -> L.circleMarker
let gatewayMarkers = {}; // gateway_id -> L.marker
let poiLayerGroup;
let gatewayLayerGroup;
let boundaryLayerGroup;

let gatewaysData = [];
let isAddingGatewayMode = false;
let socket;
let simParameters = {
    spawn_rate: 2.0,
    sim_speed_multiplier: 1.0,
    flow_internal_ratio: 0.50,
    flow_inflow_ratio: 0.25,
    flow_outflow_ratio: 0.25,
    class_personal_pct: 60,
    class_tourism_pct: 20,
    class_logistics_pct: 10,
    class_bus_pct: 10
};

// Active legend filter
let activeLegendFilter = null;

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    loadInitialData();
    initWebSocket();
});

// Initialize Leaflet Map Canvas with Esri Dark Gray Canvas (Watermark Free)
function initMap() {
    map = L.map('map', {
        center: [47.0502, 8.3103],
        zoom: 14,
        zoomControl: false
    });

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Esri World Dark Gray Base Tile Server (100% Free & Watermark-Free)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
        maxZoom: 19
    }).addTo(map);

    boundaryLayerGroup = L.layerGroup().addTo(map);
    poiLayerGroup = L.layerGroup().addTo(map);
    gatewayLayerGroup = L.layerGroup().addTo(map);

    // Map Click Listener for "+ Add Gateway" Tool
    map.on('click', async (e) => {
        if (!isAddingGatewayMode) return;

        const lat = e.latlng.lat;
        const lon = e.latlng.lng;
        const name = prompt("Enter Custom Gateway Portal Name:", "Custom Boundary Portal");
        if (!name) {
            cancelAddGateway();
            return;
        }

        try {
            const res = await fetch('/api/gateways', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    lat: lat,
                    lon: lon,
                    weight: 5.0,
                    corridor_type: "secondary"
                })
            });
            const newGw = await res.json();
            gatewaysData.push(newGw);
            renderGatewayMarkers();
            renderGatewayManagerList();
        } catch (err) {
            console.error("Failed to add custom gateway:", err);
        }

        cancelAddGateway();
    });
}

function enableAddGatewayTool() {
    isAddingGatewayMode = true;
    document.getElementById('add-gateway-banner').classList.remove('hidden');
    map.getContainer().style.cursor = 'crosshair';
}

function cancelAddGateway() {
    isAddingGatewayMode = false;
    document.getElementById('add-gateway-banner').classList.add('hidden');
    map.getContainer().style.cursor = '';
}

// Fetch Initial Road Network Geometry, POIs, Boundary Polygon, & Gateways
async function loadInitialData() {
    try {
        const response = await fetch('/api/initial-data');
        const data = await response.json();

        // 1. Draw Simulation Boundary Polygon (Cyan dashed ring)
        if (data.boundary_polygon && data.boundary_polygon.length > 0) {
            boundaryLayerGroup.clearLayers();
            const boundaryPoly = L.polyline(data.boundary_polygon, {
                color: '#38bdf8',
                weight: 2,
                dashArray: '6, 6',
                opacity: 0.8
            });
            boundaryPoly.bindTooltip("<strong>Simulation Area Boundary Ring</strong>", { sticky: true });
            boundaryLayerGroup.addLayer(boundaryPoly);
        }

        // 2. Draw Road Network Polylines
        data.edges.forEach(edge => {
            if (!edge.geometry || edge.geometry.length === 0) return;

            const latlngs = edge.geometry.map(coord => [coord[0], coord[1]]);
            const polyline = L.polyline(latlngs, {
                color: '#334155',
                weight: Math.max(2, edge.lanes * 1.5),
                opacity: 0.65
            }).addTo(map);

            polyline.bindTooltip(`<strong>${edge.name}</strong><br>Speed Limit: ${edge.maxspeed} km/h`, { sticky: true });

            polyline.on('click', () => {
                toggleRoadBlock(edge.id);
            });

            edgePolylines[edge.id] = polyline;
        });

        // 3. Draw POIs
        data.pois.forEach(poi => {
            const poiIcon = L.divIcon({
                className: 'poi-marker-icon',
                html: `<div style="background-color:#38bdf8; border:2px solid #ffffff; width:12px; height:12px; border-radius:50%; box-shadow:0 0 10px #38bdf8;"></div>`,
                iconSize: [12, 12]
            });
            const marker = L.marker([poi.lat, poi.lon], { icon: poiIcon })
                .bindPopup(`<strong>📍 ${poi.name}</strong><br>Category: ${poi.category}`);
            poiLayerGroup.addLayer(marker);
        });

        // 4. Draw Clean Gateways
        gatewaysData = data.gateways || [];
        renderGatewayMarkers();
        renderGatewayManagerList();

        console.log(`Loaded ${data.edges.length} edges, ${data.pois.length} POIs, ${gatewaysData.length} true gateways.`);
    } catch (err) {
        console.error("Failed to load initial map data:", err);
    }
}

// Render Gateway Map Markers
function renderGatewayMarkers() {
    gatewayLayerGroup.clearLayers();
    gatewayMarkers = {};

    gatewaysData.forEach(gw => {
        if (!gw.enabled) return;

        const isHighCap = gw.weight >= 6.0;
        const color = gw.is_custom ? '#10b981' : (isHighCap ? '#a855f7' : '#f59e0b');
        const size = isHighCap ? 16 : 12;

        const gwIcon = L.divIcon({
            className: 'gw-marker-icon',
            html: `<div style="background-color:${color}; border:2px solid #ffffff; width:${size}px; height:${size}px; border-radius:3px; transform:rotate(45deg); box-shadow:0 0 12px ${color}; cursor:pointer;"></div>`,
            iconSize: [size, size]
        });

        const marker = L.marker([gw.lat, gw.lon], { icon: gwIcon })
            .bindPopup(`
                <div style="font-size:12px;">
                    <strong>🚪 ${gw.name}</strong><br>
                    Capacity Weight: <strong>${gw.weight}x</strong><br>
                    Corridor Class: ${gw.corridor_type}<br>
                    <button style="margin-top:6px; padding:2px 6px; font-size:10px; cursor:pointer;" onclick="deleteGateway('${gw.id}')">Delete Gateway</button>
                </div>
            `);

        gatewayLayerGroup.addLayer(marker);
        gatewayMarkers[gw.id] = marker;
    });
}

// Render Gateway Manager List in Sidebar
function renderGatewayManagerList() {
    const container = document.getElementById('gateway-manager-list');
    if (!gatewaysData || gatewaysData.length === 0) {
        container.innerHTML = `<p class="empty-msg">No active gateways.</p>`;
        return;
    }

    container.innerHTML = gatewaysData.map(gw => `
        <div class="gateway-card">
            <div class="gateway-card-header">
                <span class="gw-title" title="${gw.name}">${gw.name}</span>
                <span class="gw-weight-tag">${gw.weight.toFixed(1)}x</span>
            </div>
            <div class="gateway-card-controls">
                <input type="range" min="1.0" max="15.0" step="0.5" value="${gw.weight}" onchange="updateGatewayWeight('${gw.id}', this.value)">
                <input type="checkbox" ${gw.enabled ? 'checked' : ''} onchange="toggleGatewayEnabled('${gw.id}', this.checked)">
            </div>
        </div>
    `).join('');
}

async function updateGatewayWeight(gwId, newWeight) {
    try {
        await fetch(`/api/gateways/${gwId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ weight: parseFloat(newWeight) })
        });
        const gw = gatewaysData.find(g => g.id === gwId);
        if (gw) gw.weight = parseFloat(newWeight);
        renderGatewayMarkers();
        renderGatewayManagerList();
    } catch (err) {
        console.error("Failed to update gateway weight:", err);
    }
}

async function toggleGatewayEnabled(gwId, enabled) {
    try {
        await fetch(`/api/gateways/${gwId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });
        const gw = gatewaysData.find(g => g.id === gwId);
        if (gw) gw.enabled = enabled;
        renderGatewayMarkers();
        renderGatewayManagerList();
    } catch (err) {
        console.error("Failed to toggle gateway enabled:", err);
    }
}

async function deleteGateway(gwId) {
    try {
        await fetch(`/api/gateways/${gwId}`, { method: 'DELETE' });
        gatewaysData = gatewaysData.filter(g => g.id !== gwId);
        renderGatewayMarkers();
        renderGatewayManagerList();
    } catch (err) {
        console.error("Failed to delete gateway:", err);
    }
}

// WebSocket Live Stream Connection
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("Connected to Lucerne Simulator WebSocket stream.");
    };

    socket.onmessage = (event) => {
        const state = JSON.parse(event.data);
        renderSimulationState(state);
    };

    socket.onclose = () => {
        console.warn("WebSocket disconnected. Reconnecting in 3 seconds...");
        setTimeout(initWebSocket, 3000);
    };
}

// Instant Effect Map Layer & Checkbox Controls
function toggleLayerVisibility() {
    // 1. POI Layer
    const showPois = document.getElementById('chk-show-pois').checked;
    if (showPois) {
        if (!map.hasLayer(poiLayerGroup)) map.addLayer(poiLayerGroup);
    } else {
        if (map.hasLayer(poiLayerGroup)) map.removeLayer(poiLayerGroup);
    }

    // 2. Gateway Layer
    const showGateways = document.getElementById('chk-show-gateways').checked;
    if (showGateways) {
        if (!map.hasLayer(gatewayLayerGroup)) map.addLayer(gatewayLayerGroup);
    } else {
        if (map.hasLayer(gatewayLayerGroup)) map.removeLayer(gatewayLayerGroup);
    }

    // 3. Congestion Lines Reset if hidden
    const showCongestion = document.getElementById('chk-show-congestion').checked;
    if (!showCongestion) {
        Object.keys(edgePolylines).forEach(edgeId => {
            edgePolylines[edgeId].setStyle({ color: '#334155', weight: 2 });
        });
    }

    filterVehicleMarkersInstant();
}

function filterVehicleMarkersInstant() {
    const showPersonal = document.getElementById('chk-veh-personal').checked;
    const showTourism = document.getElementById('chk-veh-tourism').checked;
    const showLogistics = document.getElementById('chk-veh-logistics').checked;
    const showBus = document.getElementById('chk-veh-bus').checked;

    Object.keys(vehicleMarkers).forEach(vehId => {
        const marker = vehicleMarkers[vehId];
        const vClass = marker.vehicleClass;
        
        let visible = false;
        if (vClass === 'personal' && showPersonal) visible = true;
        else if (vClass === 'tourism' && showTourism) visible = true;
        else if (vClass === 'logistics' && showLogistics) visible = true;
        else if (vClass === 'bus' && showBus) visible = true;

        if (visible) {
            if (!map.hasLayer(marker)) map.addLayer(marker);
        } else {
            if (map.hasLayer(marker)) map.removeLayer(marker);
        }
    });
}

// Interactive Legend Filtering
function filterLegend(colorName) {
    if (activeLegendFilter === colorName) {
        activeLegendFilter = null;
    } else {
        activeLegendFilter = colorName;
    }

    const colorHexMap = {
        'green': '#2ecc71',
        'yellow': '#f1c40f',
        'orange': '#e67e22',
        'red': '#e74c3c',
        'purple': '#8e44ad'
    };

    const targetHex = colorHexMap[activeLegendFilter];

    Object.keys(edgePolylines).forEach(edgeId => {
        const line = edgePolylines[edgeId];
        if (!activeLegendFilter) {
            line.setStyle({ opacity: 0.65 });
        } else {
            if (line.options.color === targetHex) {
                line.setStyle({ opacity: 1.0, weight: 5 });
            } else {
                line.setStyle({ opacity: 0.15 });
            }
        }
    });
}

// Render Simulation Frame
function renderSimulationState(state) {
    // 1. Header Metrics
    document.getElementById('val-active-count').innerText = state.active_vehicles_count;
    document.getElementById('val-completed-count').innerText = state.completed_trips_count;
    document.getElementById('val-avg-delay').innerText = state.avg_travel_time_sec.toFixed(1);

    const mins = Math.floor(state.sim_time / 60);
    const secs = Math.floor(state.sim_time % 60);
    document.getElementById('val-sim-time').innerText = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    const showPersonal = document.getElementById('chk-veh-personal').checked;
    const showTourism = document.getElementById('chk-veh-tourism').checked;
    const showLogistics = document.getElementById('chk-veh-logistics').checked;
    const showBus = document.getElementById('chk-veh-bus').checked;

    // 2. Render Vehicles
    const currentVehIds = new Set();

    state.vehicles.forEach(veh => {
        currentVehIds.add(veh.id);

        let isVisible = false;
        if (veh.class === 'personal' && showPersonal) isVisible = true;
        else if (veh.class === 'tourism' && showTourism) isVisible = true;
        else if (veh.class === 'logistics' && showLogistics) isVisible = true;
        else if (veh.class === 'bus' && showBus) isVisible = true;

        if (vehicleMarkers[veh.id]) {
            vehicleMarkers[veh.id].setLatLng([veh.lat, veh.lon]);
            if (isVisible && !map.hasLayer(vehicleMarkers[veh.id])) {
                map.addLayer(vehicleMarkers[veh.id]);
            } else if (!isVisible && map.hasLayer(vehicleMarkers[veh.id])) {
                map.removeLayer(vehicleMarkers[veh.id]);
            }
        } else {
            const marker = L.circleMarker([veh.lat, veh.lon], {
                radius: veh.class === 'logistics' || veh.class === 'bus' ? 5 : 4,
                fillColor: veh.color,
                color: '#ffffff',
                weight: 1,
                fillOpacity: 0.9
            });

            marker.vehicleClass = veh.class;
            marker.bindTooltip(`Vehicle ${veh.id} [${veh.class.toUpperCase()}]`);
            
            if (isVisible) {
                marker.addTo(map);
            }
            vehicleMarkers[veh.id] = marker;
        }
    });

    // Remove despawned vehicles
    Object.keys(vehicleMarkers).forEach(vehId => {
        if (!currentVehIds.has(vehId)) {
            if (map.hasLayer(vehicleMarkers[vehId])) map.removeLayer(vehicleMarkers[vehId]);
            delete vehicleMarkers[vehId];
        }
    });

    // 3. Update Congestion Lines
    const showCongestion = document.getElementById('chk-show-congestion').checked;
    if (showCongestion && !activeLegendFilter) {
        Object.keys(edgePolylines).forEach(edgeId => {
            edgePolylines[edgeId].setStyle({ color: '#334155', weight: 2 });
        });

        if (state.congested_edges) {
            Object.keys(state.congested_edges).forEach(edgeId => {
                if (edgePolylines[edgeId]) {
                    const info = state.congested_edges[edgeId];
                    edgePolylines[edgeId].setStyle({
                        color: info.color,
                        weight: info.vc >= 1.0 ? 5 : 3
                    });
                }
            });
        }

        if (state.blocked_edges) {
            state.blocked_edges.forEach(edgeId => {
                if (edgePolylines[edgeId]) {
                    edgePolylines[edgeId].setStyle({
                        color: '#8e44ad',
                        weight: 6,
                        dashArray: '5, 5'
                    });
                }
            });
        }
    }

    // 4. Update Chokepoint Leaderboard
    renderChokepointLeaderboard(state.top_chokepoints);
}

// Render Leaderboard
function renderChokepointLeaderboard(chokepoints) {
    const container = document.getElementById('chokepoint-list');
    if (!chokepoints || chokepoints.length === 0) {
        container.innerHTML = `<p class="empty-msg">No active bottlenecks detected.</p>`;
        return;
    }

    container.innerHTML = chokepoints.map(cp => `
        <div class="chokepoint-card" onclick="zoomToEdge('${cp.edge_id}')">
            <span class="cp-name">${cp.name}</span>
            <span class="cp-ratio">V/C ${cp.vc_ratio}</span>
        </div>
    `).join('');
}

// Parameter Controls
function updateParameters() {
    simParameters.spawn_rate = parseFloat(document.getElementById('slider-spawn-rate').value);
    simParameters.sim_speed_multiplier = parseFloat(document.getElementById('slider-sim-speed').value);

    document.getElementById('lbl-spawn-rate').innerText = `${simParameters.spawn_rate.toFixed(1)} veh/s`;
    document.getElementById('lbl-sim-speed').innerText = `${simParameters.sim_speed_multiplier.toFixed(0)}x`;

    sendParametersToBackend();
}

function updateClassMix(changedClass) {
    simParameters.class_personal_pct = parseFloat(document.getElementById('slider-class-personal').value);
    simParameters.class_tourism_pct = parseFloat(document.getElementById('slider-class-tourism').value);
    simParameters.class_logistics_pct = parseFloat(document.getElementById('slider-class-logistics').value);

    document.getElementById('lbl-class-personal').innerText = `${simParameters.class_personal_pct}%`;
    document.getElementById('lbl-class-tourism').innerText = `${simParameters.class_tourism_pct}%`;
    document.getElementById('lbl-class-logistics').innerText = `${simParameters.class_logistics_pct}%`;

    sendParametersToBackend();
}

async function sendParametersToBackend() {
    try {
        await fetch('/api/parameters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(simParameters)
        });
    } catch (err) {
        console.error("Failed to update parameters:", err);
    }
}

async function applyPreset(presetName) {
    try {
        const res = await fetch('/api/preset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preset_name: presetName })
        });
        const data = await res.json();
        if (data.params) {
            document.getElementById('slider-spawn-rate').value = data.params.spawn_rate;
            document.getElementById('slider-class-personal').value = data.params.class_personal_pct;
            document.getElementById('slider-class-tourism').value = data.params.class_tourism_pct;
            document.getElementById('slider-class-logistics').value = data.params.class_logistics_pct;
            updateParameters();
        }
    } catch (err) {
        console.error("Failed to apply preset:", err);
    }
}

async function toggleRoadBlock(edgeId) {
    try {
        await fetch('/api/toggle-block', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ edge_id: edgeId })
        });
    } catch (err) {
        console.error("Failed to toggle road block:", err);
    }
}

async function resetSimulation() {
    try {
        await fetch('/api/reset', { method: 'POST' });
    } catch (err) {
        console.error("Failed to reset simulation:", err);
    }
}

function zoomToEdge(edgeId) {
    if (edgePolylines[edgeId]) {
        map.fitBounds(edgePolylines[edgeId].getBounds(), { maxZoom: 16 });
    }
}
