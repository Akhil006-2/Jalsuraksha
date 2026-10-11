from functools import lru_cache
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]

class Settings:
    raster_path = Path(os.getenv("JALSURAKSHA_RASTER", str(ROOT / "data/processed/susceptibility/chennai_flood_susceptibility_v1.tif")))
    graph_path = Path(os.getenv("JALSURAKSHA_ROAD_GRAPH", str(ROOT / "data/processed/roads/chennai.graphml")))
    reports_path = Path(os.getenv("JALSURAKSHA_REPORT_STORE", str(ROOT / "data/reports/reports.json")))
    database_path = Path(os.getenv("JALSURAKSHA_SQLITE_PATH", str(ROOT / "data/reports/jalsuraksha.sqlite3")))
    storage_backend = os.getenv("JALSURAKSHA_STORAGE_BACKEND", "json").strip().lower()
    photos_path = Path(os.getenv("JALSURAKSHA_PHOTO_DIR", str(ROOT / "data/reports/photos")))
    half_life_minutes = float(os.getenv("JALSURAKSHA_REPORT_HALF_LIFE_MINUTES", "60"))
    cluster_radius_m = float(os.getenv("JALSURAKSHA_CLUSTER_RADIUS_M", "150"))
    cluster_window_minutes = int(os.getenv("JALSURAKSHA_CLUSTER_WINDOW_MINUTES", "120"))
    cluster_min_reporters = int(os.getenv("JALSURAKSHA_CLUSTER_MIN_REPORTERS", "3"))
    responder_token = os.getenv("JALSURAKSHA_RESPONDER_TOKEN", "responder-dev-key")
    max_photo_bytes = int(os.getenv("JALSURAKSHA_MAX_PHOTO_BYTES", str(8 * 1024 * 1024)))
    cors_origins = [s.strip() for s in os.getenv("JALSURAKSHA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()]

@lru_cache
def settings():
    return Settings()
