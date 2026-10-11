from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
import logging
from fastapi import FastAPI, HTTPException, Header, Query, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from app.config import settings
from app.schemas.models import ReportCreate, ReportUpdate, Report, RouteRequest, Status
from app.services.reports import list_reports, get_report, create_report, update_report
from app.services.susceptibility import sample, status as raster_status, overlay_data, overlay_bounds
from app.services.hazards import clusters, at_location
from app.services.routing import compare
from app.services.responder import overview, pump_priorities
from app.services.flood_hazard import geojson as flood_hazard_geojson, classify as classify_flood_hazard, status as flood_hazard_status

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jalsuraksha")

# Statuses that may only be set by a privileged responder
PRIVILEGED_STATUSES = {Status.verified, Status.rejected}

@asynccontextmanager
async def lifespan(app):
    cfg = settings()
    cfg.reports_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.photos_path.mkdir(parents=True, exist_ok=True)
    if cfg.responder_token == "responder-dev-key":
        log.warning("Using development responder token. Set JALSURAKSHA_RESPONDER_TOKEN before any shared deployment.")
    if cfg.storage_backend not in {"json", "sqlite"}:
        raise RuntimeError("JALSURAKSHA_STORAGE_BACKEND must be 'json' or 'sqlite'.")
    yield

app = FastAPI(title="JalSuraksha API", version="1.0.0",
    description="Flood susceptibility, community reports, hazard clustering, and risk-aware route comparison.",
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins,
    allow_credentials=False, allow_methods=["GET","POST","PATCH","OPTIONS"],
    allow_headers=["Content-Type","Authorization","X-Request-ID","X-Responder-Token"])

@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

@app.exception_handler(HTTPException)
async def http_errors(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={"error":{
        "code": f"HTTP_{exc.status_code}", "message": str(exc.detail),
        "request_id": getattr(request.state, "request_id", None)}})

@app.exception_handler(Exception)
async def server_errors(request: Request, exc: Exception):
    log.exception("Unhandled API error")
    return JSONResponse(status_code=500, content={"error":{"code":"INTERNAL_SERVER_ERROR",
        "message":"An unexpected server error occurred.", "request_id":getattr(request.state,"request_id",None)}})

@app.get("/", tags=["System"])
def root():
    return {"service":"JalSuraksha API","version":"1.0.0","docs":"/docs","health":"/api/v1/health"}

@app.get("/api/v1/health", tags=["System"])
def health():
    return {"status":"ok","timestamp":datetime.now(timezone.utc)}

@app.get("/api/v1/status", tags=["System"])
def api_status():
    cfg = settings()
    return {"name":"JalSuraksha API","version":"1.0.0","environment":"development",
        "components":{"susceptibility_raster":raster_status(),
        "flood_hazard":flood_hazard_status(),
        "road_graph":{"available":cfg.graph_path.exists(),"path":str(cfg.graph_path)},
        "report_store":{"configured":True,"path":str(cfg.reports_path)},
        "live_sensor_feed":{"available":False},"sagemaker_online_endpoint":{"configured":False}},
        "safety_notice":"Susceptibility is not live flood observation or calibrated probability. No road graph means routing is unavailable."}

@app.get("/api/v1/flood-hazards", tags=["Flood hazard"])
def flood_hazards():
    """Static GCC/OpenCity 100-year return-period hazard polygons; not live conditions."""
    return flood_hazard_geojson()

@app.get("/api/v1/flood-hazards/at", tags=["Flood hazard"])
def flood_hazard_at(latitude:float=Query(ge=-90,le=90), longitude:float=Query(ge=-180,le=180)):
    result = classify_flood_hazard(latitude, longitude)
    return {"latitude":latitude, "longitude":longitude, **result,
            "source":"OpenCity / Greater Chennai Corporation",
            "return_period_years":100,
            "warning":"Static design hazard only. UNCLASSIFIED does not mean flood-free."}

@app.get("/api/v1/susceptibility", tags=["Susceptibility"])
def susceptibility(latitude:float=Query(ge=-90,le=90), longitude:float=Query(ge=-180,le=180)):
    value = sample(latitude, longitude)
    if value is None:
        if not raster_status()["available"]: raise HTTPException(503,"Susceptibility raster is unavailable.")
        raise HTTPException(404,"Location is outside raster coverage or has no valid score.")
    return {"latitude":latitude,"longitude":longitude,"score":round(value,6),
        "interpretation":"higher_relative_susceptibility" if value>=.67 else "moderate_relative_susceptibility" if value>=.34 else "lower_relative_susceptibility",
        "model_type":"relative_susceptibility","warning":"Not a calibrated flood probability or live flood observation."}

@app.get("/api/v1/susceptibility/overlay.png", tags=["Susceptibility"])
def susceptibility_overlay():
    """Return a georeferenced RGBA PNG of the flood susceptibility raster (WGS84)."""
    od = overlay_data()
    if od is None:
        raise HTTPException(503, "Susceptibility raster is unavailable.")
    return Response(content=od["png_bytes"], media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"})

@app.get("/api/v1/susceptibility/bounds", tags=["Susceptibility"])
def susceptibility_bounds():
    """Return WGS84 bounding box of the susceptibility overlay."""
    od = overlay_bounds()
    if od is None:
        raise HTTPException(503, "Susceptibility raster is unavailable.")
    return {
        "bounds": od["bounds"],
        "crs": "EPSG:4326",
        "label": "Modelled flood susceptibility — static",
        "warning": "Static relative model; not live flood observation.",
        "legend": {"low": "#ffffb2","mid": "#fd8d3c","high": "#bd0026"}
    }

@app.get("/api/v1/reports", response_model=list[Report], tags=["Reports"])
def reports(include_resolved:bool=False): return list_reports(include_resolved)

@app.post("/api/v1/reports", response_model=Report, status_code=201, tags=["Reports"])
def submit_report(payload:ReportCreate):
    try: return create_report(payload)
    except ValueError as e: raise HTTPException(422,str(e)) from e

@app.get("/api/v1/reports/{report_id}", response_model=Report, tags=["Reports"])
def report_detail(report_id:str):
    r=get_report(report_id)
    if not r: raise HTTPException(404,"Report not found.")
    return r

@app.patch("/api/v1/reports/{report_id}", response_model=Report, tags=["Reports"])
def patch_report(report_id:str, payload:ReportUpdate,
                 x_responder_token:str|None=Header(default=None)):
    cfg = settings()
    if payload.status == Status.corroborated:
        raise HTTPException(400, "Corroboration is calculated from independent recent reports and cannot be set manually.")
    if payload.status in PRIVILEGED_STATUSES:
        if x_responder_token != cfg.responder_token:
            raise HTTPException(403,
                "Setting verified or rejected status requires a valid X-Responder-Token header. "
                "This is a development-grade token; implement proper authentication before production use.")
    r=update_report(report_id,payload, actor="responder" if payload.status in PRIVILEGED_STATUSES else "community")
    if not r: raise HTTPException(404,"Report not found.")
    return r

@app.get("/api/v1/reports/photo/{photo_key}", tags=["Reports"])
def serve_photo(photo_key:str, x_responder_token:str|None=Header(default=None)):
    """Serve uploaded photos only to an authorized responder."""
    cfg = settings()
    if "/" in photo_key or "\\" in photo_key or ".." in photo_key:
        raise HTTPException(400, "Invalid photo key.")
    if not x_responder_token or x_responder_token != cfg.responder_token:
        raise HTTPException(403, "Photo access requires responder authorization.")
    path = cfg.photos_path / photo_key
    if not path.exists():
        raise HTTPException(404, "Photo not found.")
    ext = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext)
    if not mime:
        raise HTTPException(415, "Unsupported file type.")
    return Response(content=path.read_bytes(), media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@app.get("/api/v1/hazards/clusters", tags=["Hazards"])
def hazard_clusters(): return clusters()

@app.get("/api/v1/hazards/at", tags=["Hazards"])
def hazard_query(latitude:float=Query(ge=-90,le=90),longitude:float=Query(ge=-180,le=180),radius_m:float=Query(150,ge=10,le=2000)):
    return at_location(latitude,longitude,radius_m)

@app.post("/api/v1/routes/compare", tags=["Routing"])
def route_compare(payload:RouteRequest): return compare(payload)

@app.get("/api/v1/responder/overview", tags=["Responder"])
def responder_overview(): return overview()

@app.get("/api/v1/responder/pump-priorities", tags=["Responder"])
def responder_pump_priorities(): return pump_priorities()

@app.post("/api/v1/reports/photo", tags=["Reports"])
async def upload_photo(file:UploadFile=File(...)):
    cfg=settings()
    ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}.get(file.content_type)
    if not ext: raise HTTPException(415,"Only JPEG, PNG, and WebP images are accepted.")
    content=await file.read(cfg.max_photo_bytes+1)
    if not content: raise HTTPException(400,"Empty upload.")
    if len(content)>cfg.max_photo_bytes: raise HTTPException(413,"Image exceeds the configured size limit.")
    valid={"image/jpeg":content.startswith(b"\xff\xd8\xff"),
           "image/png":content.startswith(b"\x89PNG\r\n\x1a\n"),
           "image/webp":len(content)>=12 and content[:4]==b"RIFF" and content[8:12]==b"WEBP"}
    if not valid[file.content_type]: raise HTTPException(415,"File signature does not match declared image type.")
    cfg.photos_path.mkdir(parents=True,exist_ok=True)
    key=f"{uuid4().hex}{ext}"
    (cfg.photos_path/key).write_bytes(content)
    return {"photo_key":key,"size_bytes":len(content),"status":"stored",
            "note":"Local development storage only; production needs private object storage, retention, and access controls."}

