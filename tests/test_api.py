def test_health(client):
    r=client.get("/api/v1/health")
    assert r.status_code==200 and r.json()["status"]=="ok"

def test_openapi(client):
    r=client.get("/openapi.json")
    assert r.status_code==200
    assert "/api/v1/routes/compare" in r.json()["paths"]

def test_report_lifecycle(client):
    payload={"latitude":13.0827,"longitude":80.2707,"depth":"knee","reporter_id":"test-device","description":"Water on road"}
    created=client.post("/api/v1/reports",json=payload)
    assert created.status_code==201,created.text
    report=created.json()
    assert report["status"]=="new"
    listed=client.get("/api/v1/reports")
    assert any(x["id"]==report["id"] for x in listed.json())
    patched=client.patch(f"/api/v1/reports/{report['id']}",json={"status":"resolved"})
    assert patched.status_code==200 and patched.json()["status"]=="resolved"

def test_invalid_coordinates(client):
    r=client.post("/api/v1/reports",json={"latitude":100,"longitude":0,"depth":"ankle","reporter_id":"x"})
    assert r.status_code==422

def test_route_is_explicit_when_graph_missing(client):
    r=client.post("/api/v1/routes/compare",json={"origin":{"latitude":13.08,"longitude":80.27},"destination":{"latitude":13.06,"longitude":80.25}})
    assert r.status_code==200
    assert r.json()["status"] in {"ok","unavailable","no_feasible_route"}
