from collections import deque
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
import math
from app.config import settings
from app.services.reports import list_reports

SEVERITY = {"unknown": .35, "ankle": .45, "knee": .75, "waist_or_stalled_cars": 1.0}
ACTIVE = {"new", "corroborated", "verified"}

def distance_m(a_lat, a_lon, b_lat, b_lon):
    r = 6371000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat-a_lat), math.radians(b_lon-a_lon)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(max(0, 1-a)))

def influence(report, now=None):
    now = now or datetime.now(timezone.utc)
    age = max(0, (now-report.observed_at).total_seconds()/60)
    half = max(1, settings().half_life_minutes)
    return SEVERITY[report.depth.value] * math.exp(-math.log(2)*age/half)

def clusters(reports=None):
    now = datetime.now(timezone.utc)
    cfg = settings()
    rows = reports if reports is not None else list_reports()
    rows = [r for r in rows if r.status.value in ACTIVE and (now-r.observed_at).total_seconds() <= cfg.cluster_window_minutes*60]
    seen, output = set(), []
    for i in range(len(rows)):
        if i in seen: continue
        comp, q = [], deque([i]); seen.add(i)
        while q:
            k = q.popleft(); comp.append(rows[k])
            for j, candidate in enumerate(rows):
                if j not in seen and distance_m(rows[k].latitude, rows[k].longitude, candidate.latitude, candidate.longitude) <= cfg.cluster_radius_m:
                    seen.add(j); q.append(j)
        members = comp
        reporters = {r.reporter_id for r in members}
        newest = max(r.observed_at for r in members)
        score = min(1.0, sum(influence(r, now) for r in members)/max(1, len(reporters)))
        max_depth = max((r.depth.value for r in members), key=lambda x: SEVERITY[x])
        output.append({
            "id": str(uuid5(NAMESPACE_URL, "|".join(sorted(r.id for r in members)))),
            "latitude": sum(r.latitude for r in members)/len(members),
            "longitude": sum(r.longitude for r in members)/len(members),
            "report_count": len(members), "distinct_reporters": len(reporters),
            "report_ids": [r.id for r in members],
            "max_reported_depth": max_depth,
            "status": "corroborated" if len(reporters) >= cfg.cluster_min_reporters else "unconfirmed",
            "influence_score": round(score, 4), "newest_report_at": newest,
        })
    return output

def at_location(lat, lon, radius=150, active_rows=None, active_clusters=None):
    if active_rows is None:
        active_rows = [r for r in list_reports() if r.status.value in ACTIVE]
    if not active_rows:
        return {"nearby_report_count": 0, "distinct_reporters": 0, "influence_score": 0.0,
                "corroborated": False, "reports": []}
    rows = [r for r in active_rows if distance_m(lat, lon, r.latitude, r.longitude) <= radius]
    if active_clusters is None:
        active_clusters = clusters(active_rows)
    return {"nearby_report_count": len(rows), "distinct_reporters": len({r.reporter_id for r in rows}),
            "influence_score": round(min(1, sum(influence(r) for r in rows)), 4),
            "corroborated": any(c["status"] == "corroborated" and distance_m(lat, lon, c["latitude"], c["longitude"]) <= radius for c in active_clusters),
            "reports": [r.model_dump(mode="json") for r in rows]}
