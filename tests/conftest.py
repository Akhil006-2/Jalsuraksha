import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg=settings()
    monkeypatch.setattr(cfg,"reports_path",tmp_path/"reports.json")
    monkeypatch.setattr(cfg,"photos_path",tmp_path/"photos")
    with TestClient(app) as c:
        yield c
