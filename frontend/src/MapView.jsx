import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, CircleMarker, Polyline, Pane } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const STUDY_AREA_CENTER = [12.9280, 77.6770]
const RISK_COLORS = { LOW: '#34C77B', MODERATE: '#E8B93C', HIGH: '#E8822C', CRITICAL: '#E24C3F' }
const ROAD_NODE_OPTIONS = [
  { id: 'R_0_0', label: 'North-West Junction' }, { id: 'R_0_4', label: 'North-East Junction' },
  { id: 'R_4_0', label: 'South-West Junction' }, { id: 'R_4_4', label: 'South-East Junction' },
  { id: 'R_2_2', label: 'Central Junction' },
]

function zoneStyle(feature) {
  const risk = feature.properties.risk
  return { color: RISK_COLORS[risk] || '#2DA8D8', weight: 1, fillColor: RISK_COLORS[risk] || '#2DA8D8', fillOpacity: 0.48 }
}

function onEachZone(feature, layer) {
  const p = feature.properties
  layer.bindPopup(`<div class="zone-popup"><strong>${p.zone_id}</strong><span class="popup-risk">${p.risk}</span><hr/>
    Flood probability: <b>${p.flood_probability}</b><br/>Water depth: <b>${p.water_depth_cm} cm</b><br/>
    Time to flood: <b>${p.time_to_flood_min !== null ? `${p.time_to_flood_min} min` : 'N/A'}</b><br/>
    Drainage utilization: <b>${Math.round(p.utilization * 100)}%</b><br/>
    Drainage node: <b>${p.drainage_node_id || 'N/A'}${p.drainage_surcharge ? ' (surcharge)' : ''}</b><br/>
    <em>${p.data_label}</em></div>`)
}

function computeStats(zones) {
  const counts = { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 }
  zones.features.forEach((feature) => { counts[feature.properties.risk] = (counts[feature.properties.risk] || 0) + 1 })
  return counts
}

function nodeColor(node) {
  if (node.surcharge) return '#E24C3F'
  if (node.utilization > 0.7) return '#E8B93C'
  return '#34C77B'
}

function MapView() {
  const [zones, setZones] = useState(null)
  const [drainage, setDrainage] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [dataError, setDataError] = useState(null)
  const [rainfall, setRainfall] = useState(77)
  const [hour, setHour] = useState(3)
  const [showDrainage, setShowDrainage] = useState(true)
  const [startNode, setStartNode] = useState('R_4_4')
  const [endNode, setEndNode] = useState('R_0_0')
  const [normalRoute, setNormalRoute] = useState(null)
  const [safeRoute, setSafeRoute] = useState(null)
  const [routeError, setRouteError] = useState(null)

  useEffect(() => {
    setIsLoading(true)
    setDataError(null)
    fetch(`https://floodguard-backend-itmu.onrender.com/simulate?rainfall=${rainfall}&hour=${hour}`)
      .then((res) => { if (!res.ok) throw new Error('Simulation data is unavailable'); return res.json() })
      .then(setZones).catch((err) => setDataError(err.message)).finally(() => setIsLoading(false))
    fetch(`https://floodguard-backend-itmu.onrender.com/drainage-status?rainfall=${rainfall}&hour=${hour}`)
      .then((res) => { if (!res.ok) throw new Error('Drainage data is unavailable'); return res.json() })
      .then(setDrainage).catch((err) => setDataError(err.message))
  }, [rainfall, hour])

  const findRoutes = () => {
    setRouteError(null)
    fetch(`https://floodguard-backend-itmu.onrender.com/route?start=${startNode}&end=${endNode}&rainfall=${rainfall}&hour=${hour}&safe=false`)
      .then((res) => res.json()).then((data) => {
        if (data.error) { setRouteError(data.error); setNormalRoute(null); return }
        setNormalRoute(data)
      }).catch((err) => setRouteError(String(err)))
    fetch(`https://floodguard-backend-itmu.onrender.com/route?start=${startNode}&end=${endNode}&rainfall=${rainfall}&hour=${hour}&safe=true`)
      .then((res) => res.json()).then((data) => {
        if (data.error) { setRouteError(data.error); setSafeRoute(null); return }
        setSafeRoute(data)
      }).catch((err) => setRouteError(String(err)))
  }

  useEffect(() => { findRoutes() }, [rainfall, hour])

  const stats = zones ? computeStats(zones) : null
  const nodeMap = drainage ? Object.fromEntries(drainage.nodes.map((node) => [node.id, node])) : {}

  return (
    <main className="ops-dashboard">
      <header className="ops-header">
        <div className="brand-lockup">
          <div className="brand-mark"><span /></div>
          <div><div className="brand-name">FLOODGUARD</div><div className="brand-subtitle">URBAN FLOOD INTELLIGENCE</div></div>
        </div>
        <div className="risk-chips" aria-label="Current zone risk counts">
          {stats && Object.entries(RISK_COLORS).map(([level, color]) => (
            <span key={level} className={`risk-chip risk-${level.toLowerCase()}`}><span className="risk-dot" style={{ background: color }} /><span>{level}</span><strong>{stats[level]}</strong></span>
          ))}
        </div>
        <div className="header-status"><span className="prototype-badge"><i /> LIVE PROTOTYPE</span><div className="header-rainfall"><span>RAINFALL</span><strong>{rainfall}</strong><small>mm/hr</small></div></div>
      </header>

      <div className="ops-body">
        <aside className="command-panel">
          <section className="control-card rainfall-card">
            <div className="card-heading"><span className="section-kicker">Scenario control</span><h2>Rainfall intensity</h2></div>
            <div className="rainfall-value"><strong>{rainfall}</strong><span>mm/hr</span></div>
            <input className="rainfall-slider" type="range" min="10" max="90" value={rainfall} onChange={(e) => setRainfall(Number(e.target.value))} />
            <div className="range-labels"><span>10 mm/hr</span><span>90 mm/hr</span></div><p className="card-note">Prototype rainfall simulation</p>
          </section>

          <section className="control-card timeline-card">
            <div className="card-heading timeline-heading"><div><span className="section-kicker">Forecast timeline</span><h2>Prototype forecast</h2></div><span className="hour-readout">H+{hour}</span></div>
            <div className="timeline-control" role="group" aria-label="Forecast hour">
              {[0, 1, 2, 3].map((frameHour) => <button key={frameHour} type="button" onClick={() => setHour(frameHour)} className={`timeline-step ${hour === frameHour ? 'is-active' : ''}`}><span className="step-dot" /><span>{frameHour} HR</span></button>)}
            </div>
            <p className="card-note">Selected forecast hour: <strong>{hour} hr</strong></p>
          </section>

          <section className="control-card layer-card">
            <div className="card-heading compact-heading"><div><span className="section-kicker">Map layers</span><h2>Network visibility</h2></div></div>
            <label className="layer-toggle"><input type="checkbox" checked={showDrainage} onChange={(e) => setShowDrainage(e.target.checked)} /><span className="toggle-track"><span /></span><span>Drainage network</span></label>
          </section>

          <section className="control-card route-card">
            <div className="card-heading"><span className="section-kicker">Response routing</span><h2>Flood-safe route</h2></div>
            <label className="field-label">Start location</label>
            <select className="route-select" value={startNode} onChange={(e) => setStartNode(e.target.value)}>{ROAD_NODE_OPTIONS.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select>
            <label className="field-label">Destination</label>
            <select className="route-select" value={endNode} onChange={(e) => setEndNode(e.target.value)}>{ROAD_NODE_OPTIONS.map((node) => <option key={node.id} value={node.id}>{node.label}</option>)}</select>
            <button className="route-action" onClick={findRoutes}>Find safe route <span>→</span></button>
            {routeError && <p className="route-error">{routeError}</p>}
            {normalRoute && safeRoute && <div className="route-results">
              <div className="route-result normal-result"><span>Normal route</span><strong>{Math.round(normalRoute.distance_m)} m</strong><small>cost: {Math.round(normalRoute.weighted_cost)}</small></div>
              <div className="route-result safe-result"><span>Safe route</span><strong>{Math.round(safeRoute.distance_m)} m</strong><small>cost: {Math.round(safeRoute.weighted_cost)}</small></div>
              {normalRoute.path_coords?.length === safeRoute.path_coords?.length && normalRoute.path_coords?.every((point, index) => point[0] === safeRoute.path_coords[index][0] && point[1] === safeRoute.path_coords[index][1])
                ? <p className="route-message">Routes match: no lower-risk road alternative is available for this corridor.</p>
                : <p className="route-message">Safe route avoids {safeRoute.high_risk_segments_avoided} high-risk road segment{safeRoute.high_risk_segments_avoided === 1 ? '' : 's'}.</p>}
            </div>}
          </section>
        </aside>

        <section className="map-area" aria-label="Flood intelligence map"><div className="map-canvas">
          <MapContainer center={STUDY_AREA_CENTER} zoom={16} style={{ height: '100%', width: '100%' }}>
            <Pane name="routes" style={{ zIndex: 650 }} />
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
            {zones && <GeoJSON key={`${rainfall}-${hour}`} data={zones} style={zoneStyle} onEachFeature={onEachZone} />}
            {showDrainage && drainage && drainage.edges.map((edge) => {
              const from = nodeMap[edge.from], to = nodeMap[edge.to]
              if (!from || !to) return null
              return <Polyline key={edge.id} positions={[[from.lat, from.lon], [to.lat, to.lon]]} pathOptions={{ color: '#5A7488', weight: 2, dashArray: '4' }} />
            })}
            {showDrainage && drainage && drainage.nodes.map((node) => <CircleMarker key={node.id} center={[node.lat, node.lon]} radius={7} pathOptions={{ color: nodeColor(node), fillColor: nodeColor(node), fillOpacity: 0.9 }}><Popup><strong>{node.id}</strong> ({node.type})<br />Capacity: {node.capacity}<br />Utilization: {Math.round(node.utilization * 100)}%<br />{node.surcharge ? 'SURCHARGE' : 'Normal'}</Popup></CircleMarker>)}
            {normalRoute?.path_coords && <Polyline pane="routes" positions={normalRoute.path_coords} pathOptions={{ color: '#E24C3F', weight: 6, opacity: 0.9 }} />}
            {safeRoute?.path_coords && <Polyline pane="routes" positions={safeRoute.path_coords} pathOptions={{ color: '#34C77B', weight: 6, opacity: 1, dashArray: '10 6' }} />}
            {safeRoute?.start && <Marker pane="routes" position={[safeRoute.start.lat, safeRoute.start.lon]}><Popup><strong>Start</strong><br />{safeRoute.start.label}</Popup></Marker>}
            {safeRoute?.end && <Marker pane="routes" position={[safeRoute.end.lat, safeRoute.end.lon]}><Popup><strong>End</strong><br />{safeRoute.end.label}</Popup></Marker>}
            <Marker position={STUDY_AREA_CENTER}><Popup>FloodGuard Study Area: Bellandur, Bengaluru</Popup></Marker>
          </MapContainer>
          <div className="map-context-card"><span className="map-context-eyebrow">Active study area</span><strong>BELLANDUR, BENGALURU</strong><div><span className="context-hour">FORECAST H+{hour}</span><span className="context-divider" /><span>PROTOTYPE SIMULATION</span></div><p>Rainfall, terrain, drainage and ML</p></div>
          <div className="map-legend-card"><div className="legend-title">Map key</div><div className="legend-row"><span className="legend-swatch low" /> Low <span className="legend-swatch moderate" /> Moderate <span className="legend-swatch high" /> High <span className="legend-swatch critical" /> Critical</div><div className="legend-routes"><span className="normal-line" /> Normal route <span className="safe-line" /> Safe route</div></div>
          {(isLoading || dataError) && <div className={`map-state ${dataError ? 'is-error' : ''}`}>{dataError || 'Refreshing flood intelligence…'}</div>}
        </div></section>
      </div>
    </main>
  )
}

export default MapView
