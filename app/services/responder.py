from datetime import datetime, timezone
from app.services.reports import list_reports
from app.services.hazards import clusters, SEVERITY

def pump_priorities():
    ranked=[]
    for c in clusters():
        severity=SEVERITY[c["max_reported_depth"]]
        score=100*(.45*severity+.35*c["influence_score"]+.20*min(1,c["report_count"]/3))
        ranked.append({"cluster_id":c["id"],"priority_score":round(score,2),
            "report_count":c["report_count"],"severity_component":round(severity,3),
            "freshness_component":c["influence_score"],"critical_facility_component":0.0,
            "explanation":["Preliminary decision-support ranking only.",
            "Uses reported depth, freshness-adjusted influence, and report count.",
            "Does not include traffic, facilities, drainage feasibility, or field verification."]})
    return sorted(ranked,key=lambda x:x["priority_score"],reverse=True)

def overview():
    rows=list_reports(include_resolved=True)
    active=[r for r in rows if r.status.value not in ("resolved","rejected")]
    cs=clusters(active)
    return {"generated_at":datetime.now(timezone.utc),"total_reports":len(rows),"active_reports":len(active),
        "corroborated_clusters":sum(c["status"]=="corroborated" for c in cs),
        "unconfirmed_clusters":sum(c["status"]=="unconfirmed" for c in cs),
        "critical_cutoffs":[],"critical_cutoffs_note":"Requires validated road graph and facility connectivity data.",
        "pump_priorities":pump_priorities()}
