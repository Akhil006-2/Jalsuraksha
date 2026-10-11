import { useCallback, useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, ImageOverlay, CircleMarker, Polyline, Popup, useMap, useMapEvents } from 'react-leaflet'
import type { LeafletMouseEvent } from 'leaflet'
import { AlertTriangle, ArrowDownRight, ArrowRight, CheckCircle2, Clock3, Droplets, LocateFixed, MapPin, Navigation, RefreshCw, ShieldCheck, Upload, Users, Waves, X } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import './App.css'

// In development, Vite proxies /api to FastAPI. In deployment, set VITE_API_BASE_URL.
const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
type Depth = 'ankle' | 'knee' | 'waist_or_stalled_cars' | 'unknown'
type Report = { id:string; latitude:number; longitude:number; depth:Depth; description?:string|null; photo_key?:string|null; observed_at:string; received_at:string; status:'new'|'corroborated'|'verified'|'resolved'|'rejected'; reporter_id?:string }
type Cluster = { id:string; latitude:number; longitude:number; report_count:number; report_ids?:string[]; distinct_reporters:number; max_reported_depth:Depth; status:'corroborated'|'unconfirmed'; newest_report_at:string; influence_score:number }
type Route = { route_id:string; distance_m:number; estimated_minutes:number; relative_susceptibility_exposure:number|null; hazard_warnings:string[]; geometry:{type:'LineString';coordinates:[number,number][]}; explanation:string[] }
type Status = { components?:{susceptibility_raster?:{available:boolean};road_graph?:{available:boolean};live_sensor_feed?:{available:boolean}} }
type Coord = {latitude:number;longitude:number}
const CHENNAI: [number,number] = [13.03,80.22]
const depthLabel:Record<Depth,string> = { ankle:'Ankle-deep', knee:'Knee-deep', waist_or_stalled_cars:'Waist-deep / stalled cars', unknown:'Unknown depth' }
const depthColor:Record<Depth,string> = { ankle:'#d6a03c', knee:'#e77b45', waist_or_stalled_cars:'#d95757', unknown:'#73858b' }
const statusLabel:Record<string,string> = {new:'Unverified',corroborated:'Corroborated by community',verified:'Verified by reviewer',resolved:'Resolved',rejected:'Rejected'}
async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const res = await fetch(`${API}${path}`, init)
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try { const body = await res.json(); message = body?.error?.message || body?.detail || message } catch {}
    throw new Error(message)
  }
  return res.json() as Promise<T>
}
function reporterId() {
  const key='jalsuraksha_reporter_token'
  let id=localStorage.getItem(key)
  if(!id){id=crypto.randomUUID();localStorage.setItem(key,id)}
  return id
}
function fmtAge(date:string) {
  const mins=Math.max(0,Math.floor((Date.now()-new Date(date).getTime())/60000))
  if(mins<1)return 'Just now'
  if(mins<60)return `${mins} min ago`
  const hours=Math.floor(mins/60)
  return hours<24?`${hours} hr ago`:`${Math.floor(hours/24)} day ago`
}
function fmtDistance(m:number){return m>=1000?`${(m/1000).toFixed(1)} km`:`${Math.round(m)} m`}
function FlyTo({target}:{target:[number,number]|null}) { const map=useMap(); useEffect(()=>{if(target)map.flyTo(target,Math.max(map.getZoom(),14),{duration:.7})},[target,map]); return null }
function MapClick({onPick}:{onPick:(lat:number,lon:number)=>void}) { useMapEvents({click:(e:LeafletMouseEvent)=>onPick(e.latlng.lat,e.latlng.lng)}); return null }
function App(){
  const [reports,setReports]=useState<Report[]>([])
  const [clusters,setClusters]=useState<Cluster[]>([])
  const [status,setStatus]=useState<Status|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [success,setSuccess]=useState('')
  const [filter,setFilter]=useState('all')
  const [showOverlay,setShowOverlay]=useState(true)
  const [opacity,setOpacity]=useState(0.72)
  const [bounds,setBounds]=useState<[[number,number],[number,number]]|null>(null)
  const [mapTarget,setMapTarget]=useState<[number,number]|null>(null)
  const [pickMode,setPickMode]=useState<'report'|'origin'|'destination'|null>(null)
  const [origin,setOrigin]=useState<Coord>({latitude:12.947,longitude:80.220})
  const [destination,setDestination]=useState<Coord>({latitude:12.976,longitude:80.221})
  const [routes,setRoutes]=useState<Route[]>([])
  const [selectedRoute,setSelectedRoute]=useState(0)
  const [routeBusy,setRouteBusy]=useState(false)
  const [vehicle,setVehicle]=useState('two_wheeler')
  const [avoidHazards,setAvoidHazards]=useState(true)
  const [depth,setDepth]=useState<Depth>('ankle')
  const [description,setDescription]=useState('')
  const [photo,setPhoto]=useState<File|null>(null)
  const [reportLocation,setReportLocation]=useState<Coord|null>(null)
  const [activeView,setActiveView]=useState<'community'|'responder'>('community')
  const [responderToken,setResponderToken]=useState('')
  const [responderData,setResponderData]=useState<any>(null)
  const [helpOpen,setHelpOpen]=useState(false)
  const [search,setSearch]=useState('')
  const [searchBusy,setSearchBusy]=useState(false)
  const [searchResults,setSearchResults]=useState<any[]>([])
  const [lastUpdated,setLastUpdated]=useState<Date|null>(null)
  const refresh=useCallback(async()=>{
    setError('')
    try {
      const [r,c,s,b]=await Promise.all([
        api<Report[]>('/api/v1/reports'),
        api<Cluster[]>('/api/v1/hazards/clusters'),
        api<Status>('/api/v1/status'),
        api<{bounds:[[number,number],[number,number]]}>('/api/v1/susceptibility/bounds')
      ])
      setReports(r);setClusters(c);setStatus(s);setBounds(b.bounds);setLastUpdated(new Date())
    } catch(e){setError(e instanceof Error?e.message:'Unable to connect to backend')}
  },[])
  useEffect(()=>{void refresh();const t=window.setInterval(()=>void refresh(),45000);return()=>window.clearInterval(t)},[refresh])
  const activeReports=reports.filter(r=>!['resolved','rejected'].includes(r.status))
  const corroboratedClusterIds=new Set(clusters.filter(c=>c.status==='corroborated').flatMap(c=>c.report_ids||[]))
  const corroborated=clusters.filter(c=>c.status==='corroborated').length
  const isCommunityCorroborated=(r:Report)=>corroboratedClusterIds.has(r.id)
  const visibleReports=activeReports.filter(r=>filter==='all'||(filter==='unverified'&&r.status==='new'&&!isCommunityCorroborated(r))||(filter==='corroborated'&&(r.status==='corroborated'||isCommunityCorroborated(r)))||(filter==='verified'&&r.status==='verified'))
  const routeLines=useMemo(()=>routes.map((r,i)=>({positions:r.geometry.coordinates.map(([lon,lat])=>[lat,lon] as [number,number]),color:i===selectedRoute?'#087f70':['#4575d4','#d88b30','#8556bd'][i%3],weight:i===selectedRoute?6:3,opacity:i===selectedRoute?.95:.58})),[routes,selectedRoute])
  const submitReport=async()=>{
    setError('');setSuccess('')
    if(!reportLocation){setError('Choose a report location on the map or use your current location.');return}
    if(photo && (!['image/jpeg','image/png','image/webp'].includes(photo.type)||photo.size>8*1024*1024)){setError('Choose a JPEG, PNG, or WebP image under 8 MB.');return}
    setBusy(true)
    try{
      let photoKey:string|undefined
      if(photo){
        const form=new FormData();form.append('file',photo)
        const uploaded=await api<{photo_key:string}>('/api/v1/reports/photo',{method:'POST',body:form})
        photoKey=uploaded.photo_key
      }
      await api<Report>('/api/v1/reports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        latitude:reportLocation.latitude,longitude:reportLocation.longitude,depth,reporter_id:reporterId(),description:description.trim()||null,photo_key:photoKey||null
      })})
      setSuccess('Thank you. Your observation has been submitted and will appear on the map.')
      setDescription('');setPhoto(null);setReportLocation(null);setPickMode(null)
      await refresh()
    }catch(e){setError(e instanceof Error?e.message:'Report submission failed')}
    finally{setBusy(false)}
  }
  const findRoute=async()=>{
    setError('');setRoutes([]);setRouteBusy(true)
    try{
      const data=await api<{status:string;routes:Route[];message:string}>('/api/v1/routes/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin,destination,vehicle,alternatives:3,avoid_uncertain_hazards:avoidHazards})})
      if(data.status!=='ok'||!data.routes.length)throw new Error(data.message||'No route could be calculated. Try different endpoints.')
      setRoutes(data.routes);setSelectedRoute(0)
      const first=data.routes[0].geometry.coordinates
      if(first.length)setMapTarget([first[Math.floor(first.length/2)][1],first[Math.floor(first.length/2)][0]])
    }catch(e){setError(e instanceof Error?e.message:'Route comparison failed')}
    finally{setRouteBusy(false)}
  }
  const locateMe=()=>{
    if(!navigator.geolocation){setError('Location is not supported by this browser.');return}
    navigator.geolocation.getCurrentPosition(p=>setReportLocation({latitude:p.coords.latitude,longitude:p.coords.longitude}),e=>setError(e.message||'Location permission was not granted.'),{enableHighAccuracy:false,timeout:10000})
  }
  const searchPlaces=async()=>{
    if(search.trim().length<3)return
    setSearchBusy(true);setSearchResults([]);setError('')
    try{
      const res=await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&countrycodes=in&q=${encodeURIComponent(search+', Chennai, Tamil Nadu')}`,{headers:{'Accept':'application/json'}})
      if(!res.ok)throw new Error('Location search is temporarily unavailable.')
      const data=await res.json();setSearchResults(data)
      if(!data.length)setError('No matching location found.')
    }catch(e){setError(e instanceof Error?e.message:'Search failed')}
    finally{setSearchBusy(false)}
  }
  const loadResponder=async()=>{
    setError('')
    try{setResponderData(await api('/api/v1/responder/overview'))}catch(e){setError(e instanceof Error?e.message:'Responder overview unavailable')}
  }
  const updateReportStatus=async(id:string,next:'verified'|'rejected')=>{
    if(!responderToken.trim()){setError('Enter the responder token configured on the backend.');return}
    try{await api(`/api/v1/reports/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Responder-Token':responderToken},body:JSON.stringify({status:next})});await refresh();await loadResponder()}catch(e){setError(e instanceof Error?e.message:'Update failed')}
  }
  const onMapPick=(lat:number,lon:number)=>{
    if(pickMode==='report'){setReportLocation({latitude:lat,longitude:lon});setPickMode(null)}
    if(pickMode==='origin'){setOrigin({latitude:lat,longitude:lon});setPickMode(null)}
    if(pickMode==='destination'){setDestination({latitude:lat,longitude:lon});setPickMode(null)}
  }
  const locateReport=(r:Report)=>{setMapTarget([r.latitude,r.longitude]);setReportLocation({latitude:r.latitude,longitude:r.longitude})}
  const cityState=status?.components?.road_graph?.available?'Road graph ready':'Road routing unavailable'
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><div className="brand-mark"><Droplets size={22}/></div><div><b>jalsuraksha</b><small>CHENNAI FLOOD WATCH</small></div></div>
      <div className="top-location"><span className="live-dot"/><span>Chennai, Tamil Nadu</span><i/>{lastUpdated?<span>Updated {fmtAge(lastUpdated.toISOString())}</span>:<span>Connecting to API…</span>}</div>
      <div className="top-actions"><span className={`pill ${error?'pill-warn':'pill-green'}`}>{error?'CHECK CONNECTION':'BACKEND CONNECTED'}</span><button className="icon-button" onClick={()=>setHelpOpen(true)} aria-label="Help">?</button><div className="avatar">J</div></div>
    </header>
    <main className="page">
      <section className="intro-row"><div><div className="eyebrow">MONSOON RESPONSE · CHENNAI</div><h1>Stay ahead of the water.</h1><p>Community observations and model-informed route planning for flood awareness.</p></div><div className="view-switch"><button className={activeView==='community'?'active':''} onClick={()=>setActiveView('community')}>Community view</button><button className={activeView==='responder'?'active':''} onClick={()=>{setActiveView('responder');void loadResponder()}}>Responder view <span className="amber-dot"/></button></div></section>
      {error&&<div className="notice notice-error"><AlertTriangle size={17}/><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
      {success&&<div className="notice notice-success"><CheckCircle2 size={17}/><span>{success}</span><button onClick={()=>setSuccess('')} aria-label="Dismiss success"><X size={16}/></button></div>}
      <section className="stats-grid">
        <article className="stat-card"><div className="stat-icon blue"><Waves size={19}/></div><div><small>City awareness</small><strong>{status?.components?.susceptibility_raster?.available?'Model available':'Model unavailable'}</strong><span className="stat-note">Static susceptibility · not live flood data</span></div></article>
        <article className="stat-card"><div className="stat-icon amber"><AlertTriangle size={19}/></div><div><small>Active community reports</small><strong>{activeReports.length}</strong><span className="stat-note">{corroborated} community-corroborated clusters</span></div></article>
        <article className="stat-card"><div className="stat-icon green"><ShieldCheck size={19}/></div><div><small>Hazard clusters</small><strong>{clusters.length}</strong><span className="stat-note">Based on recent reports</span></div></article>
        <article className="stat-card"><div className="stat-icon grey"><Clock3 size={19}/></div><div><small>Last data refresh</small><strong>{lastUpdated?fmtAge(lastUpdated.toISOString()):'Waiting…'}</strong><span className="stat-note">{cityState}</span></div></article>
      </section>
      <section className="main-grid">
        <article className="panel map-panel">
          <div className="panel-heading"><div><h2>Chennai situation map <span className="map-status-dot"/> <small>OPENSTREETMAP</small></h2><p>Choose a point to report water or set a route endpoint.</p></div><div className="map-tools"><label className="toggle-label"><input type="checkbox" checked={showOverlay} onChange={e=>setShowOverlay(e.target.checked)}/> Susceptibility</label><button className="icon-button" title="Refresh data" onClick={()=>void refresh()}><RefreshCw size={16}/></button></div></div>
          <div className="searchbar"><input value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')void searchPlaces()}} placeholder="Search a place in Chennai…"/><button onClick={()=>void searchPlaces()} disabled={searchBusy}>{searchBusy?'…':'Search'}</button></div>
          {searchResults.length>0&&<div className="search-results">{searchResults.map((r:any)=><button key={r.place_id} onClick={()=>{setMapTarget([Number(r.lat),Number(r.lon)]);setSearchResults([]);setSearch(r.display_name)}}>{r.display_name}</button>)}</div>}
          <div className="map-actions">
            <button className={pickMode==='report'?'selected':''} onClick={()=>{setPickMode('report');setError('Click the map to choose the report location.')}}><MapPin size={15}/> Pick report location</button>
            <button className={pickMode==='origin'?'selected':''} onClick={()=>{setPickMode('origin');setError('Click the map to set the route origin.')}}><span className="origin-dot"/> Set origin</button>
            <button className={pickMode==='destination'?'selected':''} onClick={()=>{setPickMode('destination');setError('Click the map to set the route destination.')}}><span className="destination-dot"/> Set destination</button>
          </div>
          <div className={`map-wrap ${pickMode?'map-picking':''}`}>
            <MapContainer center={CHENNAI} zoom={11} scrollWheelZoom className="leaflet-map">
              <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
              {showOverlay&&bounds&&<ImageOverlay url={`${API}/api/v1/susceptibility/overlay.png`} bounds={bounds} opacity={opacity} />}
              <FlyTo target={mapTarget}/>
              <MapClick onPick={onMapPick}/>
              {activeReports.map(r=><CircleMarker key={r.id} center={[r.latitude,r.longitude]} radius={r.status==='verified'?8:6} pathOptions={{color:'#fff',weight:2,fillColor:depthColor[r.depth],fillOpacity:.95}} eventHandlers={{click:()=>{setMapTarget([r.latitude,r.longitude]);setReportLocation({latitude:r.latitude,longitude:r.longitude})}}}><Popup><b>{depthLabel[r.depth]}</b><br/>{(r.status==='new'&&isCommunityCorroborated(r))?'Corroborated by community':(statusLabel[r.status]||r.status)}<br/>{fmtAge(r.observed_at)}{r.description&&<><br/>{r.description}</>}</Popup></CircleMarker>)}
              {clusters.map(c=><CircleMarker key={c.id} center={[c.latitude,c.longitude]} radius={Math.min(17,8+c.report_count)} pathOptions={{color:c.status==='corroborated'?'#087f70':'#c28b2c',weight:2,fillOpacity:.14,fillColor:c.status==='corroborated'?'#087f70':'#c28b2c'}}><Popup><b>{c.status==='corroborated'?'Community-corroborated':'Unconfirmed cluster'}</b><br/>{c.distinct_reporters} distinct reporter tokens<br/>{c.report_count} reports</Popup></CircleMarker> )}
              {routes.length>0&&routeLines.map((line,i)=><Polyline key={routes[i].route_id} positions={line.positions} pathOptions={{color:line.color,weight:line.weight,opacity:line.opacity}} eventHandlers={{click:()=>setSelectedRoute(i)}}/>)}
              {reportLocation&&<CircleMarker center={[reportLocation.latitude,reportLocation.longitude]} radius={9} pathOptions={{color:'#fff',weight:3,fillColor:'#087f70',fillOpacity:1}}/>}
              <CircleMarker center={[origin.latitude,origin.longitude]} radius={7} pathOptions={{color:'#fff',weight:2,fillColor:'#178b63',fillOpacity:1}}/>
              <CircleMarker center={[destination.latitude,destination.longitude]} radius={7} pathOptions={{color:'#fff',weight:2,fillColor:'#d95b52',fillOpacity:1}}/>
            </MapContainer>
            {pickMode&&<div className="map-instruction">Click the map to select {pickMode==='report'?'a report location':pickMode==='origin'?'route origin':'route destination'} <button onClick={()=>setPickMode(null)}>Cancel</button></div>}
          </div>
          <div className="map-footer"><div className="legend"><span><i className="legend-ankle"/>Ankle</span><span><i className="legend-knee"/>Knee</span><span><i className="legend-waist"/>Waist / stalled</span><span><i className="legend-cluster"/>Community cluster</span></div><label className="opacity-control">Overlay opacity <input type="range" min="0.1" max="1" step="0.05" value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/></label></div>
          <div className="map-caveat"><span/> Static susceptibility layer · community reports are observations, not official flood confirmation.</div>
        </article>
        <div className="side-stack">
          {activeView==='community'?<>
            <article className="panel report-panel">
              <div className="section-eyebrow">COMMUNITY REPORT</div><div className="form-title-row"><h2>See water? Let us know.</h2><span className="time-chip">~1 min</span></div><p className="muted">A location and depth observation help neighbours understand conditions.</p>
              <div className="form-label">How deep is it?</div>
              <div className="depth-options">{(['ankle','knee','waist_or_stalled_cars'] as Depth[]).map(d=><button key={d} className={`depth-option ${depth===d?'chosen':''}`} onClick={()=>setDepth(d)}><span className={`person-icon ${d}`}>●</span><b>{depthLabel[d]}</b><small>{d==='ankle'?'About 10–15 cm':d==='knee'?'About 30–50 cm':'Deep or impassable'}</small></button>)}</div>
              <div className="location-row"><div className="field-icon"><LocateFixed size={16}/></div><div className="location-copy"><b>{reportLocation?`${reportLocation.latitude.toFixed(5)}, ${reportLocation.longitude.toFixed(5)}`:'Report location not selected'}</b><small>Click “Pick report location” above or use device location.</small></div><button className="text-button" onClick={locateMe}>Use my location</button></div>
              <textarea value={description} onChange={e=>setDescription(e.target.value)} maxLength={1000} placeholder="Optional details (e.g. road name, direction, water movement)…"/>
              <label className="upload-row"><div className="field-icon"><Upload size={16}/></div><div><b>Add a photo <small>optional</small></b><small>{photo?photo.name:'JPEG, PNG or WebP · max 8 MB'}</small></div><input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>setPhoto(e.target.files?.[0]||null)}/><span className="text-button">{photo?'Change':'Attach +'}</span></label>
              <div className="privacy-note"><ShieldCheck size={14}/> No account required. A random app token helps reduce repeat counting; it does not prove that reports come from different people.</div>
              <button className="primary-button" disabled={busy} onClick={()=>void submitReport()}>{busy?'Submitting…':'Send flood report'} <ArrowRight size={17}/></button>
            </article>
            <article className="panel route-panel">
              <div className="route-title"><div><div className="section-eyebrow">SAFER ROUTE</div><h2>Plan around reported hazards</h2></div><div className="route-icon"><Navigation size={17}/></div></div>
              <div className="coord-field"><span className="origin-dot"/><label>Origin<input value={`${origin.latitude}, ${origin.longitude}`} onChange={e=>{const v=e.target.value.split(',').map(Number);if(v.length===2&&v.every(Number.isFinite))setOrigin({latitude:v[0],longitude:v[1]})}}/></label><button onClick={()=>setPickMode('origin')} aria-label="Pick origin on map"><MapPin size={15}/></button></div>
              <div className="coord-field"><span className="destination-dot"/><label>Destination<input value={`${destination.latitude}, ${destination.longitude}`} onChange={e=>{const v=e.target.value.split(',').map(Number);if(v.length===2&&v.every(Number.isFinite))setDestination({latitude:v[0],longitude:v[1]})}}/></label><button onClick={()=>setPickMode('destination')} aria-label="Pick destination on map"><MapPin size={15}/></button></div>
              <div className="route-options"><label>Travelling by<select value={vehicle} onChange={e=>setVehicle(e.target.value)}><option value="pedestrian">Walking</option><option value="two_wheeler">Two-wheeler</option><option value="sedan">Car</option><option value="ambulance">Ambulance</option><option value="emergency_vehicle">Emergency vehicle</option></select></label><label className="avoid-check"><input type="checkbox" checked={avoidHazards} onChange={e=>setAvoidHazards(e.target.checked)}/> Avoid recent report locations</label></div>
              <button className="primary-button" disabled={routeBusy} onClick={()=>void findRoute()}>{routeBusy?'Calculating routes…':'Find route alternatives'} <ArrowRight size={17}/></button>
              <p className="route-disclaimer">Prototype route ranking. Static susceptibility is not a live road-closure or safety feed.</p>
              {routes.length>0&&<div className="route-results"><div className="result-heading">Route alternatives <span>{routes.length} found</span></div>{routes.map((r,i)=><button key={r.route_id} className={`route-result ${selectedRoute===i?'route-selected':''}`} onClick={()=>{setSelectedRoute(i);const c=r.geometry.coordinates[Math.floor(r.geometry.coordinates.length/2)];if(c)setMapTarget([c[1],c[0]])}}><span className={`route-number route-n-${i}`}>{i+1}</span><span className="route-result-main"><b>{fmtDistance(r.distance_m)} · {r.estimated_minutes} min est.</b><small>Relative susceptibility exposure: {r.relative_susceptibility_exposure==null?'Unavailable':(r.relative_susceptibility_exposure*100).toFixed(0)+'/100'}</small></span><ArrowDownRight size={16}/></button>)}</div>}
            </article>
          </>:<article className="panel responder-panel"><div className="section-eyebrow">AUTHORIZED OPERATIONS</div><h2>Responder overview</h2><p className="muted">Reviewer actions require the backend's configured responder token. This development token is not production authentication.</p><label className="token-field">Responder token<input type="password" value={responderToken} onChange={e=>setResponderToken(e.target.value)} placeholder="Enter X-Responder-Token"/></label><button className="secondary-button" onClick={()=>void loadResponder()}><RefreshCw size={15}/> Refresh overview</button>{responderData&&<div className="responder-metrics"><div><small>Total reports</small><b>{responderData.total_reports}</b></div><div><small>Active reports</small><b>{responderData.active_reports}</b></div><div><small>Corroborated clusters</small><b>{responderData.corroborated_clusters}</b></div></div>}<div className="review-list"><h3>Reports requiring review</h3>{activeReports.filter(r=>r.status==='new'||r.status==='corroborated').slice(0,20).map(r=><div className="review-item" key={r.id}><div><b>{depthLabel[r.depth]}</b><small>{r.latitude.toFixed(4)}, {r.longitude.toFixed(4)} · {fmtAge(r.observed_at)}</small><small>{statusLabel[r.status]}</small></div><div className="review-actions"><button onClick={()=>void updateReportStatus(r.id,'verified')}>Verify</button><button onClick={()=>void updateReportStatus(r.id,'rejected')}>Reject</button></div></div>)}</div></article>}
        </div>
      </section>
      <section className="panel recent-panel"><div className="recent-heading"><div><div className="section-eyebrow">WHAT'S HAPPENING NEAR YOU</div><h2>Recent community reports <span className="count-badge">{activeReports.length}</span></h2></div><div className="filter-pills">{[['all','All'],['unverified','Unverified'],['corroborated','Corroborated'],['verified','Verified']].map(([v,l])=><button key={v} className={filter===v?'filter-active':''} onClick={()=>setFilter(v)}>{l}</button>)}</div></div>
        {visibleReports.length===0?<div className="empty-state"><Users size={24}/><b>No reports in this view</b><span>New community observations will appear here after submission.</span></div>:<div className="report-list">{visibleReports.slice(0,16).map(r=><article className="report-card" key={r.id}><div className={`depth-symbol ${r.depth}`}>{r.depth==='ankle'?'≈':'!'}</div><div className="report-card-main"><b>{depthLabel[r.depth]}</b><small>{r.latitude.toFixed(4)}, {r.longitude.toFixed(4)} · {fmtAge(r.observed_at)}</small>{r.description&&<p>{r.description}</p>}</div><div className="report-card-end"><span className={`status-badge status-${r.status}`}>{(r.status==='new'&&isCommunityCorroborated(r))?'Corroborated by community':(statusLabel[r.status]||r.status)}</span><button onClick={()=>locateReport(r)}>Locate on map</button></div></article>)}</div>}
        {visibleReports.length>16&&<div className="more-row">Showing 16 of {visibleReports.length} active reports</div>}
      </section>
      <footer><span>JalSuraksha · Community-powered flood awareness</span><span>For emergencies, contact local emergency services. This tool does not replace official warnings.</span></footer>
    </main>
    {helpOpen&&<div className="modal-backdrop" onClick={()=>setHelpOpen(false)}><section className="help-modal" onClick={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setHelpOpen(false)}><X size={18}/></button><div className="brand-mark"><Droplets size={22}/></div><h2>About JalSuraksha</h2><p>JalSuraksha combines a static flood-susceptibility model with community observations and prototype road-network routing.</p><ul><li>Modelled susceptibility is not live flood observation.</li><li>Three distinct recent reporter tokens within 150 m can mark a cluster as community-corroborated. Tokens are pseudonymous, not verified identities.</li><li>Community corroboration is not official verification.</li><li>Routes are decision support and may not reflect actual road conditions.</li></ul><button className="primary-button" onClick={()=>setHelpOpen(false)}>Understood</button></section></div>}
  </div>
}
export default App
