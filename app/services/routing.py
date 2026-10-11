import math
import networkx as nx
from app.config import settings
from app.services.hazards import at_location, distance_m
from app.services.susceptibility import sample
from app.services.flood_hazard import classify_segments

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
        margin = 0.025
        min_lat = min(payload.origin.latitude, payload.destination.latitude) - margin
        max_lat = max(payload.origin.latitude, payload.destination.latitude) + margin
        min_lon = min(payload.origin.longitude, payload.destination.longitude) - margin
        max_lon = max(payload.origin.longitude, payload.destination.longitude) + margin

        def build_weighted(use_bbox=True, exclude_high=True):
            weighted = nx.DiGraph()
            weighted.add_nodes_from(graph.nodes(data=True))
            candidates = []
            segment_coords = []
            for u, v, data in graph.edges(data=True):
                cu, cv = _coords(graph.nodes[u]), _coords(graph.nodes[v])
                if not cu or not cv:
                    continue
                if use_bbox and not (min_lat <= cu[0] <= max_lat and min_lon <= cu[1] <= max_lon):
                    continue
                try:
                    length = float(data.get("length", 0))
                except (TypeError, ValueError):
                    length = 0
                if length <= 0:
                    length = distance_m(*cu, *cv)
                candidates.append((u, v, data, cu, cv, length))
                segment_coords.append((cu[0], cu[1], cv[0], cv[1]))
            flood_categories = classify_segments(segment_coords)
            for (u, v, data, cu, cv, length), flood_category in zip(candidates, flood_categories):
                lat, lon = (cu[0]+cv[0])/2, (cu[1]+cv[1])/2
                hazard = at_location(lat, lon, 60, active_rows=active_reports, active_clusters=active_clusters)
                if hazard["corroborated"] and hazard["nearby_report_count"] and hazard["influence_score"] >= .35:
                    continue
                if payload.avoid_uncertain_hazards and hazard["nearby_report_count"] and hazard["influence_score"] >= .2:
                    continue
                risk = sample(lat, lon)
                if risk is None:
                    risk = .5
                flood_penalty = {"HIGH": 80.0, "MODERATE": 12.0, "LOW": 2.0, "UNCLASSIFIED": 1.0, "UNAVAILABLE": 1.0}.get(flood_category, 1.0)
                cost = length * (1 + 2*risk + 5*hazard["influence_score"] + flood_penalty)
                if not weighted.has_edge(u, v) or cost < weighted[u][v]["weight"]:
                    weighted.add_edge(u, v, weight=cost, length=length, risk=risk,
                                      hazard=hazard["influence_score"], hazard_count=hazard["nearby_report_count"],
                                      corroborated=hazard["corroborated"], flood_category=flood_category)
            return weighted

        weighted = build_weighted(use_bbox=True, exclude_high=False)
        # Exclude high-hazard segments for the preferred routing pass without
        # recomputing all spatial overlays. If the corridor itself is disconnected,
        # expand once to the full road graph.
        safe_weighted = weighted.copy()
        safe_weighted.remove_edges_from([(u, v) for u, v, d in safe_weighted.edges(data=True)
                                         if d.get("flood_category") == "HIGH"])
        high_zone_fallback = False
        if nx.has_path(safe_weighted, start, end):
            weighted = safe_weighted
        elif nx.has_path(weighted, start, end):
            # Explicitly warned fallback: allow HIGH-zone roads only when avoidance
            # disconnects the graph. Their cost remains severe.
            high_zone_fallback = True
        else:
            return {"status": "no_feasible_route", "routes": [], "message": "No connected road route exists in the configured graph."}

        def heuristic(a, b):
            ca, cb = _coords(weighted.nodes[a]), _coords(weighted.nodes[b])
            return distance_m(ca[0], ca[1], cb[0], cb[1]) if ca and cb else 0.0

        # A* gives the primary route. The straight-line distance heuristic is
        # admissible because every edge cost is at least its physical length.
        primary = nx.astar_path(weighted, start, end, heuristic=heuristic, weight="weight")
        candidate_paths = [primary]
        # Bounded alternative generation: rerun A* while penalizing edges used by
        # previous candidates. This is substantially cheaper than enumerating all
        # simple paths on a city-scale graph, and encourages meaningfully different
        # options without pretending they are mathematically exhaustive K-shortest paths.
        for _ in range(1, payload.alternatives):
            used_edges = {(u, v) for path in candidate_paths for u, v in zip(path, path[1:])}
            def diversified_weight(u, v, data):
                base = float(data.get("weight", data.get("length", 1.0)))
                return base * (3.0 if (u, v) in used_edges else 1.0)
            try:
                candidate = nx.astar_path(weighted, start, end, heuristic=heuristic, weight=diversified_weight)
            except nx.NetworkXNoPath:
                break
            if candidate in candidate_paths:
                break
            candidate_paths.append(candidate)

        output = []
        for idx, path in enumerate(candidate_paths[:payload.alternatives]):
            length = sum(weighted[u][v]["length"] for u, v in zip(path, path[1:]))
            edges = [weighted[u][v] for u, v in zip(path, path[1:])]
            risks = [e["risk"] for e in edges]
            hazard_scores = [e.get("hazard", 0.0) for e in edges]
            hazard_edges = sum(1 for e in edges if e.get("hazard_count", 0))
            corroborated_edges = sum(1 for e in edges if e.get("corroborated", False))
            flood_counts = {category: sum(1 for e in edges if e.get("flood_category") == category)
                            for category in ("HIGH", "MODERATE", "LOW", "UNCLASSIFIED", "UNAVAILABLE")}
            mean_risk = (sum(risks) / len(risks)) if risks else None
            mean_hazard = (sum(hazard_scores) / len(hazard_scores)) if hazard_scores else 0.0
            coords = [_coords(weighted.nodes[n]) for n in path]
            coords = [c for c in coords if c]
            explanation = [
                f"Relative susceptibility along sampled route: {mean_risk:.2f} on a 0–1 relative scale." if mean_risk is not None else "Susceptibility data unavailable for this route.",
                f"{hazard_edges} of {len(edges)} road segments have nearby active community reports.",
                f"{corroborated_edges} road segments intersect the current corroborated-hazard avoidance radius.",
                "Mapped flood-zone segments: " + ", ".join(f"{k}={v}" for k,v in flood_counts.items()) + ".",
                "Route ranking combines distance, static relative susceptibility, mapped flood design hazard, and recent report influence.",
                "Historical rainfall is city-wide in the available dataset, not route-specific, so it is not used to claim that one road had lower historical rainfall.",
                "The susceptibility model is trained against a limited historical flood target; scores are not calibrated probabilities.",
            ]
            output.append({
                "route_id": f"candidate-{idx+1}", "distance_m": round(length, 1),
                "estimated_minutes": round(length/1000/SPEED[payload.vehicle.value]*60, 1),
                "relative_susceptibility_exposure": round(mean_risk, 4) if mean_risk is not None else None,
                "hazard_warnings": (["No route avoiding mapped HIGH hazard zones was found; this alternative may cross HIGH design-hazard areas."] if high_zone_fallback else []) + ["No live traffic, rainfall, sensor, or official road-closure feed is connected; travel time is approximate.", "UNCLASSIFIED roads are not confirmed flood-free."],
                "mapped_flood_segments": flood_counts,
                "uses_high_hazard_fallback": high_zone_fallback,
                "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in coords]},
                "explanation": explanation,
            })
        return {"status": "ok" if output else "no_feasible_route", "routes": output, "message": "Candidates are decision support, not a safety guarantee."}
    except (nx.NetworkXException, ValueError, TypeError, KeyError):
        return {"status": "unavailable", "routes": [], "message": "Routing could not process the configured graph."}
