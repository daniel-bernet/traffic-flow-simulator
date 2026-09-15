// Lucerne Traffic Flow Simulator Frontend App

let map;
let baseTileLayer;
let edgePolylines = {};  // edge_id -> L.polyline
let vehicleMarkers = {}; // vehicle_id -> L.circleMarker
let gatewayMarkers = {}; // gateway_id -> L.marker
let poiLayerGroup;
let gatewayLayerGroup;
let boundaryLayerGroup;
let previewGatewayLayerGroup;
let aoiHandleLayerGroup;
let busLineLayerGroup;

let gatewaysData = [];
let masterHighspeedEdges = []; // All >30 km/h edges from master graph for live gateway preview
let aoiPolygonCoords = []; // Current active AOI polygon ring
let latestBusLinesData = [];
let activeHighlightedBusLine = null;

let isAddingGatewayMode = false;
let isDrawingAOIMode = false;
let isEditingAOIMode = false;

let drawnAOIVertices = []; // [[lat, lon], ...]
let tempAOIPolyline = null;
let tempAOIMarkers = [];

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
    initKeyboardShortcuts();
});

// Initialize Leaflet Map Canvas
function initMap() {
    map = L.map('map', {
        center: [47.0502, 8.3103],
        zoom: 14,
        zoomControl: false
    });

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // Default Tile Server: Esri Dark Gray (Watermark Free)
    baseTileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
        maxZoom: 19
    }).addTo(map);

    boundaryLayerGroup = L.layerGroup().addTo(map);
    poiLayerGroup = L.layerGroup().addTo(map);
    gatewayLayerGroup = L.layerGroup().addTo(map);
    previewGatewayLayerGroup = L.layerGroup().addTo(map);
    aoiHandleLayerGroup = L.layerGroup().addTo(map);
    busLineLayerGroup = L.layerGroup().addTo(map);

    // Map Click Handler for Gateway placement or AOI Drawing
    map.on('click', async (e) => {
        if (isDrawingAOIMode) {
            const lat = e.latlng.lat;
            const lon = e.latlng.lng;
            drawnAOIVertices.push([lat, lon]);

            renderTempAOIGraphics();
            updateLiveGatewayPreview(drawnAOIVertices);
            return;
        }

        if (isAddingGatewayMode) {
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
        }
    });
}

// Keyboard Shortcuts Listener
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (isDrawingAOIMode) cancelDrawAOI();
            if (isAddingGatewayMode) cancelAddGateway();
            if (isEditingAOIMode) toggleEditAOIMode();
        } else if (isDrawingAOIMode) {
            if (e.key === 'Enter') {
                finishDrawAOI();
            } else if (e.key === 'Backspace' || (e.ctrlKey && e.key === 'z')) {
                undoLastAOINode();
            }
        }
    });
}

// Tile Theme Switcher
function changeTileTheme() {
    const theme = document.getElementById('select-tile-theme').value;
    map.removeLayer(baseTileLayer);

    if (theme === 'osm_standard') {
        baseTileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        });
    } else if (theme === 'carto_voyager') {
        baseTileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        });
    } else {
        baseTileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
            maxZoom: 19
        });
    }

    baseTileLayer.addTo(map);
}

// ==========================================
// AOI Drawing & Interactive Editing Engine
// ==========================================

function startDrawAOI() {
    if (isEditingAOIMode) toggleEditAOIMode();

    isDrawingAOIMode = true;
    drawnAOIVertices = [];
    clearTempAOIGraphics();
    previewGatewayLayerGroup.clearLayers();

    document.getElementById('draw-aoi-banner').classList.remove('hidden');
    map.getContainer().style.cursor = 'crosshair';
}

function undoLastAOINode() {
    if (!isDrawingAOIMode || drawnAOIVertices.length === 0) return;
    drawnAOIVertices.pop();
    renderTempAOIGraphics();
    updateLiveGatewayPreview(drawnAOIVertices);
}

function cancelDrawAOI() {
    isDrawingAOIMode = false;
    clearTempAOIGraphics();
    previewGatewayLayerGroup.clearLayers();
    document.getElementById('draw-aoi-banner').classList.add('hidden');
    map.getContainer().style.cursor = '';
}

function clearTempAOIGraphics() {
    if (tempAOIPolyline) map.removeLayer(tempAOIPolyline);
    tempAOIMarkers.forEach(m => map.removeLayer(m));
    tempAOIPolyline = null;
    tempAOIMarkers = [];
}

function renderTempAOIGraphics() {
    clearTempAOIGraphics();

    drawnAOIVertices.forEach(v => {
        const marker = L.circleMarker([v[0], v[1]], {
            radius: 5,
            fillColor: '#38bdf8',
            color: '#ffffff',
            weight: 2
        }).addTo(map);
        tempAOIMarkers.push(marker);
    });

    if (drawnAOIVertices.length >= 2) {
        tempAOIPolyline = L.polyline(drawnAOIVertices, {
            color: '#38bdf8',
            weight: 3,
            dashArray: '4, 4'
        }).addTo(map);
    }
}

async function finishDrawAOI() {
    if (drawnAOIVertices.length < 3) {
        alert("Please click at least 3 points on the map to define a valid polygon boundary.");
        return;
    }

    // Close polygon
    const polygon = [...drawnAOIVertices, drawnAOIVertices[0]];

    try {
        const res = await fetch('/api/aoi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ polygon: polygon })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            updateAOIDisplay(data);
        }
    } catch (err) {
        console.error("Failed to update AOI polygon:", err);
    }

    cancelDrawAOI();
}

async function resetAOIPolygon() {
    if (isEditingAOIMode) toggleEditAOIMode();
    try {
        const res = await fetch('/api/aoi', { method: 'DELETE' });
        const data = await res.json();
        updateAOIDisplay(data);
    } catch (err) {
        console.error("Failed to reset AOI polygon:", err);
    }
}

function updateAOIDisplay(data) {
    loadInitialData();
}

// ------------------------------------------
// Interactive Polygon Handles (Drag & Edit)
// ------------------------------------------

function toggleEditAOIMode() {
    isEditingAOIMode = !isEditingAOIMode;
    const btn = document.getElementById('btn-toggle-edit-aoi');

    if (isEditingAOIMode) {
        if (isDrawingAOIMode) cancelDrawAOI();

        btn.innerText = '🖐️ Done Editing';
        btn.classList.add('btn-accent');

        // Copy active AOI polygon coordinates (excluding closing duplicate if present)
        drawnAOIVertices = [...aoiPolygonCoords];
        if (drawnAOIVertices.length > 3 &&
            drawnAOIVertices[0][0] === drawnAOIVertices[drawnAOIVertices.length - 1][0] &&
            drawnAOIVertices[0][1] === drawnAOIVertices[drawnAOIVertices.length - 1][1]) {
            drawnAOIVertices.pop();
        }

        renderAOIHandles();
        updateLiveGatewayPreview(drawnAOIVertices);
    } else {
        btn.innerText = '🖐️ Drag & Edit Handles';
        btn.classList.remove('btn-accent');
        aoiHandleLayerGroup.clearLayers();
        previewGatewayLayerGroup.clearLayers();
    }
}

function renderAOIHandles() {
    aoiHandleLayerGroup.clearLayers();
    if (!isEditingAOIMode || drawnAOIVertices.length < 3) return;

    // 1. Polygon Outline Polyline
    const closedCoords = [...drawnAOIVertices, drawnAOIVertices[0]];
    const handlePolyline = L.polyline(closedCoords, {
        color: '#38bdf8',
        weight: 3,
        dashArray: '6, 6'
    });
    aoiHandleLayerGroup.addLayer(handlePolyline);

    // 2. Vertex Handles (Draggable)
    drawnAOIVertices.forEach((v, idx) => {
        const icon = L.divIcon({
            className: 'aoi-vertex-handle',
            iconSize: [14, 14]
        });

        const marker = L.marker([v[0], v[1]], {
            icon: icon,
            draggable: true
        });

        marker.bindTooltip(`Vertex #${idx + 1} (Right-click to remove)`, { sticky: true });

        marker.on('drag', (e) => {
            const newLat = e.latlng.lat;
            const newLon = e.latlng.lng;
            drawnAOIVertices[idx] = [newLat, newLon];

            const updatedClosed = [...drawnAOIVertices, drawnAOIVertices[0]];
            handlePolyline.setLatLngs(updatedClosed);
            updateLiveGatewayPreview(drawnAOIVertices);
        });

        marker.on('dragend', () => {
            renderAOIHandles();
            saveEditedAOIPolygon();
        });

        marker.on('contextmenu', (e) => {
            if (drawnAOIVertices.length <= 3) {
                alert("Polygon must have at least 3 vertices.");
                return;
            }
            drawnAOIVertices.splice(idx, 1);
            renderAOIHandles();
            updateLiveGatewayPreview(drawnAOIVertices);
            saveEditedAOIPolygon();
        });

        aoiHandleLayerGroup.addLayer(marker);
    });

    // 3. Edge Midpoint Handles (Insert Node)
    const n = drawnAOIVertices.length;
    for (let i = 0; i < n; i++) {
        const v1 = drawnAOIVertices[i];
        const v2 = drawnAOIVertices[(i + 1) % n];

        const midLat = (v1[0] + v2[0]) / 2;
        const midLon = (v1[1] + v2[1]) / 2;

        const midIcon = L.divIcon({
            className: 'aoi-midpoint-handle',
            iconSize: [10, 10]
        });

        const midMarker = L.marker([midLat, midLon], {
            icon: midIcon,
            draggable: true
        });

        midMarker.bindTooltip("Click or drag to insert new node", { sticky: true });

        midMarker.on('dragstart click', (e) => {
            const insertIdx = i + 1;
            const newLat = e.latlng ? e.latlng.lat : midLat;
            const newLon = e.latlng ? e.latlng.lng : midLon;
            drawnAOIVertices.splice(insertIdx, 0, [newLat, newLon]);

            renderAOIHandles();
            updateLiveGatewayPreview(drawnAOIVertices);
        });

        midMarker.on('drag', (e) => {
            const newLat = e.latlng.lat;
            const newLon = e.latlng.lng;
            const targetIdx = i + 1;
            drawnAOIVertices[targetIdx] = [newLat, newLon];

            const updatedClosed = [...drawnAOIVertices, drawnAOIVertices[0]];
            handlePolyline.setLatLngs(updatedClosed);
            updateLiveGatewayPreview(drawnAOIVertices);
        });

        midMarker.on('dragend', () => {
            renderAOIHandles();
            saveEditedAOIPolygon();
        });

        aoiHandleLayerGroup.addLayer(midMarker);
    }
}

async function saveEditedAOIPolygon() {
    if (drawnAOIVertices.length < 3) return;

    const polygon = [...drawnAOIVertices, drawnAOIVertices[0]];
    try {
        const res = await fetch('/api/aoi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ polygon: polygon })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            aoiPolygonCoords = polygon;
        }
    } catch (err) {
        console.error("Failed to save edited AOI polygon:", err);
    }
}

// ------------------------------------------
// Client-side Real-time Live Gateway Preview
// ------------------------------------------

function pointInPolygon(lat, lon, polygon) {
    let x = lon, y = lat;
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        let xi = polygon[i][1], yi = polygon[i][0];
        let xj = polygon[j][1], yj = polygon[j][0];
        let intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

function segmentIntersection(lat1, lon1, lat2, lon2, lat3, lon3, lat4, lon4) {
    const d = (lon2 - lon1) * (lat4 - lat3) - (lat2 - lat1) * (lon4 - lon3);
    if (Math.abs(d) < 1e-9) return null;
    const u = ((lat3 - lat1) * (lon4 - lon3) - (lon3 - lon1) * (lat4 - lat3)) / d;
    const v = ((lat3 - lat1) * (lon2 - lon1) - (lon3 - lon1) * (lat2 - lat1)) / d;
    if (u >= 0 && u <= 1 && v >= 0 && v <= 1) {
        return [lat1 + u * (lat2 - lat1), lon1 + u * (lon2 - lon1)];
    }
    return null;
}

function updateLiveGatewayPreview(candidateVertices) {
    previewGatewayLayerGroup.clearLayers();
    if (!candidateVertices || candidateVertices.length < 3 || masterHighspeedEdges.length === 0) return;

    const poly = [...candidateVertices, candidateVertices[0]];
    const previewGateways = [];

    // Test master highspeed edges (>30km/h) for border crossing
    masterHighspeedEdges.forEach(edge => {
        const uIn = pointInPolygon(edge.u_lat, edge.u_lon, poly);
        const vIn = pointInPolygon(edge.v_lat, edge.v_lon, poly);

        // Cross condition: one endpoint inside, one outside
        if (uIn !== vIn) {
            let intersectPt = null;

            // Find segment intersection against candidate polygon ring
            for (let i = 0; i < poly.length - 1; i++) {
                const pt = segmentIntersection(
                    edge.u_lat, edge.u_lon, edge.v_lat, edge.v_lon,
                    poly[i][0], poly[i][1], poly[i + 1][0], poly[i + 1][1]
                );
                if (pt) {
                    intersectPt = pt;
                    break;
                }
            }

            const crossLat = intersectPt ? intersectPt[0] : (uIn ? edge.v_lat : edge.u_lat);
            const crossLon = intersectPt ? intersectPt[1] : (uIn ? edge.v_lon : edge.u_lon);

            previewGateways.push({
                lat: crossLat,
                lon: crossLon,
                name: edge.name,
                maxspeed: edge.maxspeed,
                highway: edge.highway
            });
        }
    });

    // Cluster preview markers within ~150m
    const clustered = {};
    previewGateways.forEach(gw => {
        const key = `${gw.lat.toFixed(3)}_${gw.lon.toFixed(3)}`;
        if (!clustered[key]) {
            clustered[key] = gw;
        }
    });

    // Render Preview Markers on Map
    Object.values(clustered).forEach(gw => {
        const previewIcon = L.divIcon({
            className: 'gw-preview-icon',
            html: `<div style="background-color:#f59e0b; border:2px solid #ffffff; width:14px; height:14px; border-radius:3px; transform:rotate(45deg); box-shadow:0 0 12px #f59e0b;"></div>`,
            iconSize: [14, 14]
        });

        const marker = L.marker([gw.lat, gw.lon], { icon: previewIcon })
            .bindTooltip(`🚪 <strong>PREVIEW GATEWAY</strong><br>${gw.name} (${gw.maxspeed} km/h)`, { sticky: true });

        previewGatewayLayerGroup.addLayer(marker);
    });
}

// Fetch Initial Road Network Geometry, POIs, Boundary Polygon, & Gateways
async function loadInitialData() {
    try {
        const response = await fetch('/api/initial-data');
        const data = await response.json();

        aoiPolygonCoords = data.aoi_polygon || [];
        masterHighspeedEdges = data.master_highspeed_edges || [];

        // 1. Draw AOI Boundary Ring Polygon (Cyan glowing polygon)
        boundaryLayerGroup.clearLayers();
        if (aoiPolygonCoords.length > 0) {
            const boundaryPoly = L.polygon(aoiPolygonCoords, {
                color: '#38bdf8',
                fillColor: '#38bdf8',
                fillOpacity: 0.05,
                weight: 2,
                dashArray: '6, 6'
            });
            boundaryPoly.bindTooltip("<strong>Defined Area of Interest (AOI) Ring</strong>", { sticky: true });
            boundaryLayerGroup.addLayer(boundaryPoly);
        }

        // 2. Draw Clipped Road Network Polylines
        Object.keys(edgePolylines).forEach(k => map.removeLayer(edgePolylines[k]));
        edgePolylines = {};

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
        poiLayerGroup.clearLayers();
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

        // 4. Draw AOI Gateways (>30km/h rule)
        gatewaysData = data.gateways || [];
        renderGatewayMarkers();
        renderGatewayManagerList();

        if (isEditingAOIMode) {
            renderAOIHandles();
        }

        console.log(`Loaded ${data.edges.length} active AOI edges, ${masterHighspeedEdges.length} master highspeed edges, ${data.pois.length} POIs, ${gatewaysData.length} AOI gateways (>30km/h).`);
    } catch (err) {
        console.error("Failed to load initial map data:", err);
    }
}

// Add Custom Gateway Tool
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
        container.innerHTML = `<p class="empty-msg">No active AOI gateways (>30km/h).</p>`;
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
    const showAoi = document.getElementById('chk-show-aoi').checked;
    if (showAoi) {
        if (!map.hasLayer(boundaryLayerGroup)) map.addLayer(boundaryLayerGroup);
    } else {
        if (map.hasLayer(boundaryLayerGroup)) map.removeLayer(boundaryLayerGroup);
    }

    const showPois = document.getElementById('chk-show-pois').checked;
    if (showPois) {
        if (!map.hasLayer(poiLayerGroup)) map.addLayer(poiLayerGroup);
    } else {
        if (map.hasLayer(poiLayerGroup)) map.removeLayer(poiLayerGroup);
    }

    const showGateways = document.getElementById('chk-show-gateways').checked;
    if (showGateways) {
        if (!map.hasLayer(gatewayLayerGroup)) map.addLayer(gatewayLayerGroup);
    } else {
        if (map.hasLayer(gatewayLayerGroup)) map.removeLayer(gatewayLayerGroup);
    }

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

// VBL Bus Transit Dashboard & Route Highlighting
function renderBusTransitDashboard(busLines) {
    const container = document.getElementById('bus-lines-list');
    if (!container) return;
    if (!busLines || busLines.length === 0) {
        container.innerHTML = `<p class="empty-msg">No active VBL transit lines.</p>`;
        return;
    }

    container.innerHTML = busLines.map(line => `
        <div class="bus-line-card ${activeHighlightedBusLine === line.id ? 'active-highlight' : ''}" style="border-left-color:${line.color};" onclick="highlightBusLineRoute('${line.id}')">
            <div class="bus-line-header">
                <span class="bus-line-title" title="${line.name}">${line.name}</span>
                <span class="bus-delay-tag" style="background-color:${line.status_color};">${line.status_tag}</span>
            </div>
            <div class="bus-line-meta">
                <span>Headway: ${line.headway_min}m</span>
                <span>Active Buses: <strong>${line.active_buses}</strong></span>
            </div>
        </div>
    `).join('');
}

function highlightBusLineRoute(lineId) {
    if (activeHighlightedBusLine === lineId) {
        activeHighlightedBusLine = null;
        busLineLayerGroup.clearLayers();
    } else {
        activeHighlightedBusLine = lineId;
        busLineLayerGroup.clearLayers();

        const line = (latestBusLinesData || []).find(l => l.id === lineId);
        if (line && line.route_edges) {
            const bounds = [];
            line.route_edges.forEach(eId => {
                if (edgePolylines[eId]) {
                    const poly = L.polyline(edgePolylines[eId].getLatLngs(), {
                        color: line.color,
                        weight: 6,
                        opacity: 0.9,
                        dashArray: '8, 8'
                    });
                    busLineLayerGroup.addLayer(poly);
                    bounds.push(...edgePolylines[eId].getLatLngs());
                }
            });
            if (bounds.length > 0) {
                map.fitBounds(L.latLngBounds(bounds), { maxZoom: 15 });
            }
        }
    }
    renderBusTransitDashboard(latestBusLinesData);
}

// Render Simulation Frame
function renderSimulationState(state) {
    document.getElementById('val-active-count').innerText = state.active_vehicles_count;
    document.getElementById('val-completed-count').innerText = state.completed_trips_count;
    document.getElementById('val-avg-delay').innerText = `${state.avg_travel_time_sec.toFixed(1)}s`;

    if (state.co2_kg_hr !== undefined) {
        document.getElementById('val-co2-rate').innerText = `${state.co2_kg_hr.toFixed(0)} kg/h`;
    }
    if (state.fuel_l_hr !== undefined) {
        document.getElementById('val-fuel-rate').innerText = `${state.fuel_l_hr.toFixed(0)} L/h`;
    }

    if (state.bus_lines) {
        latestBusLinesData = state.bus_lines;
        renderBusTransitDashboard(state.bus_lines);
    }

    const mins = Math.floor(state.sim_time / 60);
    const secs = Math.floor(state.sim_time % 60);
    document.getElementById('val-sim-time').innerText = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    const showPersonal = document.getElementById('chk-veh-personal').checked;
    const showTourism = document.getElementById('chk-veh-tourism').checked;
    const showLogistics = document.getElementById('chk-veh-logistics').checked;
    const showBus = document.getElementById('chk-veh-bus').checked;

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

    Object.keys(vehicleMarkers).forEach(vehId => {
        if (!currentVehIds.has(vehId)) {
            if (map.hasLayer(vehicleMarkers[vehId])) map.removeLayer(vehicleMarkers[vehId]);
            delete vehicleMarkers[vehId];
        }
    });

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
