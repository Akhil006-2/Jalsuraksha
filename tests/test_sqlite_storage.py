from datetime import timezone
from app.config import settings
from app.schemas.models import ReportCreate, Depth
from app.services.reports import create_report, list_reports, update_report
from app.schemas.models import ReportUpdate, Status

def test_sqlite_storage_roundtrip(tmp_path, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "storage_backend", "sqlite")
    monkeypatch.setattr(cfg, "database_path", tmp_path / "reports.sqlite3")
    created = create_report(ReportCreate(latitude=13.08, longitude=80.27, depth=Depth.knee, reporter_id="sqlite-test"))
    assert created.status == Status.new
    assert any(r.id == created.id for r in list_reports())
    updated = update_report(created.id, ReportUpdate(status=Status.resolved), actor="test")
    assert updated.status == Status.resolved
    assert not any(r.id == created.id for r in list_reports())
    assert (tmp_path / "reports.sqlite3").exists()
