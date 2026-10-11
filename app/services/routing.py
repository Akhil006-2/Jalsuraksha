import math
import networkx as nx
from app.config import settings
from app.services.hazards import at_location, distance_m
from app.services.susceptibility import sample

from functools import lru_cache

SPEED = {"pedestrian": 4.5, "two_wheeler": 22, "sedan": 25, "ambulance": 28, "emergency_vehicle": 28}

@lru_cache(maxsize=1)
def _graph():
    path = settings().graph_path
    if not path.exists(): return None
    try: return nx.read_graphml(path)
    except Exception: return None

def _coords(data):
    try: return float(data.get("y", data.get("lat"))), float(data.get("x", data.get("lon")))
    except (TypeError, ValueError): return None

@lru_cache(maxsize=1)
def _node_index():
    graph = _graph()
    if graph is None:
        return None
    from scipy.spatial import cKDTree
    ids, coords = [], []
    for node, data in graph.nodes(data=True):
        c = _coords(data)
        if c:
            ids.append(node)
            # cKDTree operates in local degrees for this compact Chennai region.
            coords.append((c[0], c[1]))
    if not coords:
        return None
    return ids, cKDTree(coords), coords

def _nearest(graph, lat, lon):
    index = _node_index()
    if index is None:
        return None
    ids, tree, coords = index
    _, ix = tree.query((lat, lon), k=1)
    node = ids[int(ix)]
    c = coords[int(ix)]
    return node if distance_m(lat, lon, c[0], c[1]) <= 5000 else None


def compare(payload):
    graph = _graph()
    if graph is None:
        return {"status": "unavailable", "routes": [], "message": "No validated road graph is configured; no route was invented."}
    try:
        from app.services.reports import list_reports
        from app.services.hazards import clusters, ACTIVE

        start = _nearest(graph, payload.origin.latitude, payload.origin.longitude)
        end = _nearest(graph, payload.destination.latitude, payload.destination.longitude)
        if start is None or end is None:
            return {"status": "no_feasible_route", "routes": [], "message": "Origin or destination is outside road graph coverage."}

        active_reports = [r for r in list_reports() if r.status.value in ACTIVE]
        active_clusters = clusters(active_reports) if active_reports else []

        # Determine spatial bounding box with buffer to avoid scanning unrelated edges
        margin = 0.05
        min_lat = min(payload.origin.latitude, payload.destination.latitude) - margin
        max_lat = max(payload.origin.latitude, payload.destination.latitude) + margin
        min_lon = min(payload.origin.longitude, payload.destination.longitude) - margin
        max_lon = max(payload.origin.longitude, payload.destination.longitude) + margin

        def build_weighted(use_bbox=True):
            weighted = nx.DiGraph()
            weighted.add_nodes_from(graph.nodes(data=True))
            edges = graph.edges(data=True)
            for u, v, data in edges:
                cu, cv = _coords(graph.nodes[u]), _coords(graph.nodes[v])
                if not cu or not cv: continue
                if use_bbox:
                    if not (min_lat <= cu[0] <= max_lat and min_lon <= cu[1] <= max_lon):
                        continue
                try: length = float(data.get("length", 0))
                except (TypeError, ValueError): length = 0
                if length <= 0: length = distance_m(*cu, *cv)
                lat, lon = (cu[0]+cv[0])/2, (cu[1]+cv[1])/2
                hazard = at_location(lat, lon, 60, active_rows=active_reports, active_clusters=active_clusters)
                # Conservative: severe depth plus corroboration is excluded. Optionally avoid
                # fresh uncertain reports with meaningful influence.
                if hazard["corroborated"] and hazard["nearby_report_count"] and hazard["influence_score"] >= .35:
                    continue
                if payload.avoid_uncertain_hazards and hazard["nearby_report_count"] and hazard["influence_score"] >= .2:
                    continue
                risk = sample(lat, lon)
                if risk is None: risk = .5
                cost = length * (1 + 2*risk + 5*hazard["influence_score"])
                if not weighted.has_edge(u, v) or cost < weighted[u][v]["weight"]:
                    weighted.add_edge(u, v, weight=cost, length=length, risk=risk, hazard=hazard["influence_score"], hazard_count=hazard["nearby_report_count"], corroborated=hazard["corroborated"])
            return weighted

        weighted = build_weighted(use_bbox=True)
        if not nx.has_path(weighted, start, end):
            # If bbox did not connect, fall back to global graph
            weighted = build_weighted(use_bbox=False)
            if not nx.has_path(weighted, start, end):
                return {"status": "no_feasible_route", "routes": [], "message": "No connected route remains under the current hazard policy."}

        output = []
        for idx, path in enumerate(nx.shortest_simple_paths(weighted, start, end, weight="weight")):
            if idx >= payload.alternatives: break
            length = sum(weighted[u][v]["length"] for u, v in zip(path, path[1:]))
            edges = [weighted[u][v] for u, v in zip(path, path[1:])]
            risks = [e["risk"] for e in edges]
            hazard_scores = [e.get("hazard", 0.0) for e in edges]
            hazard_edges = sum(1 for e in edges if e.get("hazard_count", 0))
            corroborated_edges = sum(1 for e in edges if e.get("corroborated", False))
            mean_risk = (sum(risks) / len(risks)) if risks else None
            mean_hazard = (sum(hazard_scores) / len(hazard_scores)) if hazard_scores else 0.0
            coords = [_coords(weighted.nodes[n]) for n in path]
            coords = [c for c in coords if c]
            explanation = [
                f"Relative susceptibility along sampled route: {mean_risk:.2f} on a 0–1 relative scale." if mean_risk is not None else "Susceptibility data unavailable for this route.",
                f"{hazard_edges} of {len(edges)} road segments have nearby active community reports.",
                f"{corroborated_edges} road segments intersect the current corroborated-hazard avoidance radius.",
                "Route ranking combines road distance, static relative susceptibility, and recent report influence.",
                "Historical rainfall is city-wide in the available dataset, not route-specific, so it is not used to claim that one road had lower historical rainfall.",
                "The susceptibility model is trained against a limited historical flood target; scores are not calibrated probabilities.",
            ]
            output.append({
                "route_id": f"candidate-{idx+1}", "distance_m": round(length, 1),
                "estimated_minutes": round(length/1000/SPEED[payload.vehicle.value]*60, 1),
                "relative_susceptibility_exposure": round(mean_risk, 4) if mean_risk is not None else None,
                "hazard_warnings": ["No live traffic, rainfall, sensor, or official road-closure feed is connected; travel time is approximate."],
                "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]},
                "explanation": explanation,
            })
        return {"status": "ok" if output else "no_feasible_route", "routes": output, "message": "Candidates are decision support, not a safety guarantee."}
    except (nx.NetworkXException, ValueError, TypeError, KeyError):
        return {"status": "unavailable", "routes": [], "message": "Routing could not process the configured graph."}
