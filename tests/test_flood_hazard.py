from app.services.flood_hazard import geojson, classify, features

def test_kml_is_loaded_and_categories_are_present():
    data = geojson()
    assert data["metadata"]["available"] is True
    assert data["metadata"]["return_period_years"] == 100
    assert data["metadata"]["category_counts"] == {"HIGH": 85, "MODERATE": 181, "LOW": 156}
    assert len(data["features"]) == 422

def test_hazard_classification_does_not_call_unmapped_safe():
    result = classify(0.0, 0.0)
    assert result["category"] in {"UNCLASSIFIED", "UNAVAILABLE"}
    assert result["mapped"] is False

def test_classification_at_known_high_polygon():
    rows = features()
    high = next(row for row in rows if row["category"] == "HIGH")
    lon, lat = high["geometry"].representative_point().x, high["geometry"].representative_point().y
    result = classify(lat, lon)
    assert result["category"] == "HIGH"
    assert result["mapped"] is True


def test_segment_classification_uses_intersection():
    from app.services.flood_hazard import classify_segment
    rows = features()
    high = next(row for row in rows if row["category"] == "HIGH")
    point = high["geometry"].representative_point()
    result = classify_segment(point.y, point.x, point.y + 0.0001, point.x + 0.0001)
    assert result["category"] == "HIGH"
    assert result["mapped"] is True
