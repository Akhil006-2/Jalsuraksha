import json, threading, sqlite3
from datetime import datetime, timezone
from uuid import uuid4
from app.config import settings
from app.schemas.models import Report, ReportCreate, ReportUpdate, Status

_lock = threading.RLock()

def _db():
    cfg = settings()
    cfg.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.database_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
        depth TEXT NOT NULL, reporter_id TEXT NOT NULL, description TEXT,
        photo_key TEXT, observed_at TEXT NOT NULL, received_at TEXT NOT NULL,
        status TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_observed ON reports(observed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_at TEXT NOT NULL,
        report_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
        details TEXT)""")
    return conn

def _read():
    cfg = settings()
    if cfg.storage_backend == "sqlite":
        with _lock, _db() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY received_at")]
    path = cfg.reports_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")
    with _lock:
        return json.loads(path.read_text(encoding="utf-8"))

def _write(rows):
    cfg = settings()
    if cfg.storage_backend == "sqlite":
        with _lock, _db() as conn:
            conn.execute("DELETE FROM reports")
            conn.executemany("""INSERT INTO reports
                (id,latitude,longitude,depth,reporter_id,description,photo_key,observed_at,received_at,status)
                VALUES (:id,:latitude,:longitude,:depth,:reporter_id,:description,:photo_key,:observed_at,:received_at,:status)""", rows)
        return
    path = cfg.reports_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with _lock:
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        tmp.replace(path)

def _audit(report_id, action, actor, details=None):
    cfg = settings()
    event = {"event_at": datetime.now(timezone.utc).isoformat(), "report_id": report_id,
             "action": action, "actor": actor, "details": details}
    if cfg.storage_backend == "sqlite":
        with _lock, _db() as conn:
            conn.execute("INSERT INTO audit_log(event_at,report_id,action,actor,details) VALUES (?,?,?,?,?)",
                         (event["event_at"], report_id, action, actor, json.dumps(details or {})))
    else:
        path = cfg.reports_path.parent / "audit.jsonl"
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\\n")

def list_reports(include_resolved=False):
    rows = _read()
    if not include_resolved:
        rows = [r for r in rows if r["status"] not in ("resolved", "rejected")]
    return [Report.model_validate(r) for r in rows]

def get_report(report_id):
    for r in _read():
        if r["id"] == report_id:
            return Report.model_validate(r)
    return None

def create_report(payload: ReportCreate):
    now = datetime.now(timezone.utc)
    observed = payload.observed_at or now
    if (observed - now).total_seconds() > 300:
        raise ValueError("observed_at cannot be more than five minutes in the future")
    row = {
        "id": str(uuid4()), "latitude": payload.latitude, "longitude": payload.longitude,
        "depth": payload.depth.value, "reporter_id": payload.reporter_id,
        "description": payload.description, "photo_key": payload.photo_key,
        "observed_at": observed.isoformat(), "received_at": now.isoformat(),
        "status": Status.new.value,
    }
    if settings().storage_backend == "sqlite":
        with _lock, _db() as conn:
            conn.execute("""INSERT INTO reports
                (id,latitude,longitude,depth,reporter_id,description,photo_key,observed_at,received_at,status)
                VALUES (:id,:latitude,:longitude,:depth,:reporter_id,:description,:photo_key,:observed_at,:received_at,:status)""", row)
        _audit(row["id"], "report_created", "community", {"depth": row["depth"]})
    else:
        rows = _read()
        rows.append(row)
        _write(rows)
        _audit(row["id"], "report_created", "community", {"depth": row["depth"]})
    return Report.model_validate(row)

def update_report(report_id, payload: ReportUpdate, actor="system"):
    rows = _read()
    for r in rows:
        if r["id"] == report_id:
            old_status = r["status"]
            if payload.status is not None:
                r["status"] = payload.status.value
            if payload.description is not None:
                r["description"] = payload.description
            _write(rows)
            if old_status != r["status"]:
                _audit(report_id, "status_changed", actor, {"from": old_status, "to": r["status"]})
            return Report.model_validate(r)
    return None
