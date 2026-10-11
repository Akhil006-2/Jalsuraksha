# JalSuraksha flood-hazard routing update

## What changed
- Added `data/raw/flood/chennai_flows_100yr.kml` from the downloaded OpenCity / Greater Chennai Corporation 100-year return-period resource.
- Added `/api/v1/flood-hazards` GeoJSON endpoint and `/api/v1/flood-hazards/at` point classification endpoint.
- Added status reporting for the KML source.
- The primary route now uses A* with a straight-line distance heuristic that lower-bounds the weighted remaining cost. K-shortest simple paths generate alternatives. Routing samples each road edge midpoint against the hazard polygons.
- Mapped HIGH zones are excluded on the first routing pass. If no route avoiding them exists, a fallback allows them with a severe penalty and a warning.
- MODERATE zones receive a strong cost penalty; LOW zones receive a smaller penalty.
- Added hazard segment counts and explicit route explanations/warnings to route results.
- Frontend can display the hazard polygons and distinguish HIGH, MODERATE, and LOW categories alongside the existing susceptibility overlay.
- JSON report storage and existing report endpoints are unchanged.

## Source interpretation and limits
The source has 422 placemarks (85 HIGH, 181 MODERATE, 156 LOW) and describes a 100-year return-period design hazard. It is not a live flood map and is not a complete inventory of all historic floods. Outside mapped polygons is UNCLASSIFIED, not safe. Travel time is still an approximation without live traffic, closures, rainfall, or sensor feeds.

## New endpoints
- `GET /api/v1/flood-hazards`: GeoJSON FeatureCollection with metadata and coverage bounds.
- `GET /api/v1/flood-hazards/at?latitude=...&longitude=...`: category for a point; reports UNCLASSIFIED when outside mapped polygons.
- `GET /api/v1/status`: includes the flood KML source status.

## Local requirements
Install backend requirements with `python -m pip install -r requirements-backend.txt`. The new spatial parser requires Shapely 2.x. Keep the existing road graph at `data/processed/roads/chennai.graphml` and susceptibility raster at `data/processed/susceptibility/chennai_flood_susceptibility_v1.tif`; they are not duplicated in this patch ZIP. Keep your existing `data/reports/reports.json` to preserve submitted reports.
