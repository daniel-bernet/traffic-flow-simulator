// Lucerne Traffic Flow Simulator Frontend App

let map;
let edgePolylines = {};  // edge_id -> L.polyline
let vehicleMarkers = {}; // vehicle_id -> L.circleMarker
let poiLayerGroup;
let gatewayLayerGroup;

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

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    loadInitialData();
    initWebSocket();
});

// Initialize Leaflet Map Canvas
function initMap() {
    map = L.map('map', {
        center: [47.0502, 8.3103],
        zoom: 14,
        zoomControl: false
    });

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Dark Matter basemap tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    poiLayerGroup = L.layerGroup().addTo(map);
    gatewayLayerGroup = L.layerGroup().addTo(map);
}

// Fetch Initial Road Network Geometry & POIs from Backend
async function loadInitialData() {
    try {
        const response = await fetch('/api/initial-data');
        const data = await response.json();

        // 1. Draw Road Network Polylines
        data.edges.forEach(edge => {
            if (!edge.geometry || edge.geometry.length === 0) return;

            const latlngs = edge.geometry.map(coord => [coord[0], coord[1]]);
            const polyline = L.polyline(latlngs, {
                color: '#334155', // Default dark slate road line
                weight: Math.max(2, edge.lanes * 1.5),
                opacity: 0.65
            }).addTo(map);

            polyline.bindTooltip(`<strong>${edge.name}</strong><br>Speed Limit: ${edge.maxspeed} km/h`, { sticky: true });

            // Click to toggle bottleneck closure
            polyline.on('click', () => {
                toggleRoadBlock(edge.id);
            });

            edgePolylines[edge.id] = polyline;
        });

        // 2. Draw Landmark POIs
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

        // 3. Draw Gateways with named corridor tooltip
        data.gateways.forEach(gw => {
            const isHighCap = gw.weight >= 6.0;
            const color = isHighCap ? '#a855f7' : '#e2e8f0';
            const size = isHighCap ? 14 : 10;

            const gwIcon = L.divIcon({
                className: 'gw-marker-icon',
                html: `<div style="background-color:${color}; width:${size}px; height:${size}px; transform:rotate(45deg); box-shadow:0 0 8px ${color};"></div>`,
                iconSize: [size, size]
            });
            const marker = L.marker([gw.lat, gw.lon], { icon: gwIcon })
                .bindTooltip(`<strong>🚪 ${gw.name}</strong><br>Capacity Weight: ${gw.weight}x`);
            gatewayLayerGroup.addLayer(marker);
        });

        console.log(`Loaded ${data.edges.length} edges, ${data.pois.length} POIs, ${data.gateways.length} gateways.`);
    } catch (err) {
        console.error("Failed to load initial map data:", err);
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

// Layer & Vehicle Visibility Checkbox Toggles
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

    // Read active vehicle class checkboxes
    const showPersonal = document.getElementById('chk-veh-personal').checked;
    const showTourism = document.getElementById('chk-veh-tourism').checked;
    const showLogistics = document.getElementById('chk-veh-logistics').checked;
    const showBus = document.getElementById('chk-veh-bus').checked;

    // 2. Filter & Render Vehicles
    const currentVehIds = new Set();

    state.vehicles.forEach(veh => {
        // Filter by class checkbox
        let isVisible = false;
        if (veh.class === 'personal' && showPersonal) isVisible = true;
        else if (veh.class === 'tourism' && showTourism) isVisible = true;
        else if (veh.class === 'logistics' && showLogistics) isVisible = true;
        else if (veh.class === 'bus' && showBus) isVisible = true;

        if (!isVisible) return;

        currentVehIds.add(veh.id);

        if (vehicleMarkers[veh.id]) {
            vehicleMarkers[veh.id].setLatLng([veh.lat, veh.lon]);
        } else {
            const marker = L.circleMarker([veh.lat, veh.lon], {
                radius: veh.class === 'logistics' || veh.class === 'bus' ? 5 : 4,
                fillColor: veh.color,
                color: '#ffffff',
                weight: 1,
                fillOpacity: 0.9
            }).addTo(map);

            marker.bindTooltip(`Vehicle ${veh.id} [${veh.class.toUpperCase()}]`);
            vehicleMarkers[veh.id] = marker;
        }
    });

    // Remove despawned or hidden vehicle markers
    Object.keys(vehicleMarkers).forEach(vehId => {
        if (!currentVehIds.has(vehId)) {
            map.removeLayer(vehicleMarkers[vehId]);
            delete vehicleMarkers[vehId];
        }
    });

    // 3. Update Congestion Edge Colors (if enabled)
    const showCongestion = document.getElementById('chk-show-congestion').checked;
    if (showCongestion) {
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
