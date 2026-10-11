"""
Tests for report validation, corroboration algorithm, authorization, and edge cases.
Covers all 10 cases specified in section 8G of the specification.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app

CHENNAI = {"latitude": 13.0827, "longitude": 80.2707}
NEARBY_OFFSET = 0.0005       # ~55m — within 150m radius
FAR_OFFSET = 0.01            # ~1.1km — outside 150m radius


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = settings()
    monkeypatch.setattr(cfg, "reports_path", tmp_path / "reports.json")
    monkeypatch.setattr(cfg, "photos_path", tmp_path / "photos")
    with TestClient(app) as c:
        yield c


def _report(reporter_id, lat=CHENNAI["latitude"], lon=CHENNAI["longitude"],
            depth="knee", observed_at=None):
    payload = {"latitude": lat, "longitude": lon, "depth": depth,
               "reporter_id": reporter_id}
    if observed_at:
        payload["observed_at"] = observed_at.isoformat()
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# 1. One report remains unverified / new
# ─────────────────────────────────────────────────────────────────────────────
def test_single_report_stays_new(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    assert r["status"] == "new"
    clusters = client.get("/api/v1/hazards/clusters").json()
    # The single cluster should be unconfirmed, not corroborated
    matching = [c for c in clusters if c["report_count"] == 1]
    assert matching, "Expected a cluster containing the single report"
    assert matching[0]["status"] == "unconfirmed"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Two independent reports within radius and window remain unverified
# ─────────────────────────────────────────────────────────────────────────────
def test_two_reporters_remain_unconfirmed(client):
    client.post("/api/v1/reports", json=_report("device-A"))
    client.post("/api/v1/reports", json=_report("device-B",
        lat=CHENNAI["latitude"] + NEARBY_OFFSET))
    clusters = client.get("/api/v1/hazards/clusters").json()
    assert clusters, "Expected at least one cluster"
    # Two distinct reporters — still below threshold of 3
    top = clusters[0]
    assert top["distinct_reporters"] == 2
    assert top["status"] == "unconfirmed"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Three distinct reporters meeting threshold → corroborated
# ─────────────────────────────────────────────────────────────────────────────
def test_three_reporters_become_corroborated(client):
    for i, dev in enumerate(["device-A", "device-B", "device-C"]):
        client.post("/api/v1/reports", json=_report(dev,
            lat=CHENNAI["latitude"] + i * NEARBY_OFFSET * 0.3))
    clusters = client.get("/api/v1/hazards/clusters").json()
    assert clusters, "Expected a cluster"
    top = clusters[0]
    assert top["distinct_reporters"] >= 3
    assert top["status"] == "corroborated"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Same reporter submitting multiple times does not satisfy threshold
# ─────────────────────────────────────────────────────────────────────────────
def test_same_reporter_does_not_corroborate(client):
    # Submit 3 reports all from the same reporter_id
    for _ in range(3):
        client.post("/api/v1/reports", json=_report("same-device"))
    clusters = client.get("/api/v1/hazards/clusters").json()
    assert clusters, "Expected a cluster"
    top = clusters[0]
    # distinct_reporters must be 1 — not 3
    assert top["distinct_reporters"] == 1
    assert top["status"] == "unconfirmed"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Reports outside the spatial radius do not corroborate each other
# ─────────────────────────────────────────────────────────────────────────────
def test_far_reports_do_not_join_cluster(client):
    client.post("/api/v1/reports", json=_report("device-A"))
    client.post("/api/v1/reports", json=_report("device-B",
        lat=CHENNAI["latitude"] + FAR_OFFSET))
    client.post("/api/v1/reports", json=_report("device-C",
        lat=CHENNAI["latitude"] + FAR_OFFSET * 2))
    clusters = client.get("/api/v1/hazards/clusters").json()
    # Each report should be in its own cluster, none corroborated
    for c in clusters:
        assert c["report_count"] == 1
        assert c["status"] == "unconfirmed"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reports outside the recency window do not satisfy the current threshold
# ─────────────────────────────────────────────────────────────────────────────
def test_old_reports_excluded_from_cluster(client, monkeypatch):
    cfg = settings()
    old_window = cfg.cluster_window_minutes
    monkeypatch.setattr(cfg, "cluster_window_minutes", 60)  # 1-hour window
    # Submit 3 reports with observed_at 2 hours ago
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    for dev in ["device-A", "device-B", "device-C"]:
        client.post("/api/v1/reports", json=_report(dev, observed_at=old_time))
    clusters = client.get("/api/v1/hazards/clusters").json()
    # None of the clusters should contain those old reports (they're outside window)
    # (If no active-window reports exist, clusters will be empty)
    for c in clusters:
        assert c["status"] != "corroborated", \
            "Old reports outside window should not generate corroborated cluster"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Expired (resolved/rejected) reports are not shown in active list
# ─────────────────────────────────────────────────────────────────────────────
def test_resolved_reports_excluded_from_default_list(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    report_id = r["id"]
    # Resolve the report
    client.patch(f"/api/v1/reports/{report_id}", json={"status": "resolved"})
    active = client.get("/api/v1/reports").json()
    assert not any(x["id"] == report_id for x in active), \
        "Resolved report should not appear in default (active) list"
    # But should appear with include_resolved=true
    all_reports = client.get("/api/v1/reports?include_resolved=true").json()
    assert any(x["id"] == report_id for x in all_reports), \
        "Resolved report should appear when include_resolved=true"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Invalid coordinates and invalid depth categories are rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_latitude_rejected(client):
    r = client.post("/api/v1/reports",
                    json={"latitude": 200, "longitude": 80.27,
                          "depth": "knee", "reporter_id": "x"})
    assert r.status_code == 422


def test_invalid_longitude_rejected(client):
    r = client.post("/api/v1/reports",
                    json={"latitude": 13.08, "longitude": 999,
                          "depth": "knee", "reporter_id": "x"})
    assert r.status_code == 422


def test_invalid_depth_rejected(client):
    r = client.post("/api/v1/reports",
                    json={"latitude": 13.08, "longitude": 80.27,
                          "depth": "completely_flooded", "reporter_id": "x"})
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 9a. Public users cannot mark reports verified (requires X-Responder-Token)
# ─────────────────────────────────────────────────────────────────────────────
def test_public_cannot_mark_verified(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    patch = client.patch(f"/api/v1/reports/{r['id']}", json={"status": "verified"})
    assert patch.status_code == 403, \
        "Public PATCH to verified should be forbidden without X-Responder-Token"


# ─────────────────────────────────────────────────────────────────────────────
# 9b. Public users cannot mark reports rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_public_cannot_mark_rejected(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    patch = client.patch(f"/api/v1/reports/{r['id']}", json={"status": "rejected"})
    assert patch.status_code == 403, \
        "Public PATCH to rejected should be forbidden without X-Responder-Token"


# ─────────────────────────────────────────────────────────────────────────────
# 9c. Responder with valid token can mark reports verified
# ─────────────────────────────────────────────────────────────────────────────
def test_responder_can_mark_verified(client):
    cfg = settings()
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    patch = client.patch(
        f"/api/v1/reports/{r['id']}",
        json={"status": "verified"},
        headers={"X-Responder-Token": cfg.responder_token}
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "verified"


# ─────────────────────────────────────────────────────────────────────────────
# 9d. Wrong token is still rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_wrong_token_is_rejected(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    patch = client.patch(
        f"/api/v1/reports/{r['id']}",
        json={"status": "verified"},
        headers={"X-Responder-Token": "wrong-token-xyz"}
    )
    assert patch.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 9e. Public users CAN mark reports resolved (non-privileged status)
# ─────────────────────────────────────────────────────────────────────────────
def test_public_can_mark_resolved(client):
    r = client.post("/api/v1/reports", json=_report("device-A")).json()
    patch = client.patch(f"/api/v1/reports/{r['id']}", json={"status": "resolved"})
    assert patch.status_code == 200
    assert patch.json()["status"] == "resolved"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Existing report lifecycle remains compatible
# ─────────────────────────────────────────────────────────────────────────────
def test_existing_lifecycle_still_works(client):
    payload = {"latitude": 13.06, "longitude": 80.25,
               "depth": "ankle", "reporter_id": "test-device-legacy",
               "description": "Water on road"}
    created = client.post("/api/v1/reports", json=payload)
    assert created.status_code == 201
    report = created.json()
    assert report["status"] == "new"
    listed = client.get("/api/v1/reports")
    assert any(x["id"] == report["id"] for x in listed.json())
    patched = client.patch(f"/api/v1/reports/{report['id']}",
                           json={"status": "resolved"})
    assert patched.status_code == 200 and patched.json()["status"] == "resolved"


# ─────────────────────────────────────────────────────────────────────────────
# New endpoints
# ─────────────────────────────────────────────────────────────────────────────
def test_susceptibility_bounds_endpoint(client):
    r = client.get("/api/v1/susceptibility/bounds")
    assert r.status_code == 200
    data = r.json()
    assert "bounds" in data
    bounds = data["bounds"]
    # [[south, west], [north, east]]
    assert len(bounds) == 2
    assert len(bounds[0]) == 2
    south, west = bounds[0]
    north, east = bounds[1]
    assert south < north
    assert west < east
    # Must be within Chennai region
    assert 12.0 < south < 14.0
    assert 79.0 < west < 81.0


def test_susceptibility_overlay_png(client):
    r = client.get("/api/v1/susceptibility/overlay.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_photo_serve_invalid_key(client):
    r = client.get("/api/v1/reports/photo/../../etc/passwd")
    assert r.status_code in (400, 404)


def test_hazard_clusters_returns_list(client):
    r = client.get("/api/v1/hazards/clusters")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_responder_overview(client):
    r = client.get("/api/v1/responder/overview")
    assert r.status_code == 200
    data = r.json()
    assert "total_reports" in data
    assert "active_reports" in data
    assert "corroborated_clusters" in data


def test_future_observed_at_rejected(client):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = client.post("/api/v1/reports", json={
        "latitude": 13.08, "longitude": 80.27,
        "depth": "knee", "reporter_id": "x",
        "observed_at": future
    })
    assert r.status_code == 422


def test_public_cannot_manually_set_corroborated(client):
    report = client.post("/api/v1/reports", json=_report("device-A")).json()
    response = client.patch(
        f"/api/v1/reports/{report['id']}", json={"status": "corroborated"}
    )
    assert response.status_code == 400
