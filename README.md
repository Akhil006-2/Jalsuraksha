# JalSuraksha — Chennai Flood Watch

JalSuraksha is a flood-awareness and flood-first route-comparison prototype for Chennai. It brings together a static flood-hazard map, a modelled flood-susceptibility raster, a road-network graph, community-submitted reports, and alternative-route analysis in a web application.

> **Deployment:** The current application is hosted on AWS EC2, with Nginx serving the frontend and proxying API requests to FastAPI. The configured report storage backend is JSON.

## Contents

- [Features](#features)
- [System architecture](#system-architecture)
- [Algorithms and how they work](#algorithms-and-how-they-work)
- [Data sources](#data-sources)
- [AWS deployment and SageMaker status](#aws-deployment-and-sagemaker-status)
- [Project layout](#project-layout)
- [Run locally](#run-locally)
- [API endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Limitations and responsible use](#limitations-and-responsible-use)

## Features

- Displays mapped flood-hazard polygons as a separately toggleable map layer.
- Displays the static susceptibility raster as a georeferenced overlay.
- Classifies a point against available flood-hazard polygons.
- Compares candidate road routes and explains the mapped hazard categories encountered.
- Accepts community reports and groups nearby, recent observations for corroboration.
- Provides report and responder-oriented API endpoints.
- Uses JSON files for report persistence in the current deployment.

## System architecture

```text
                    User / Browser
                          |
                 React + TypeScript UI
                  Leaflet / OSM map
                          |
                    HTTP requests
                          |
                   Nginx on AWS EC2
                 /                    \
        Static frontend files       /api requests
                                          |
                                    FastAPI backend
                                          |
             +----------------------------+---------------------------+
             |               |              |             |           |
        Flood KML       Susceptibility   Road graph    Reports JSON  Hazard
        polygons        GeoTIFF          GraphML       + photos      clusters
             |               |              |             |           |
             +---------------+--------------+-------------+-----------+
                                          |
                             Route comparison and API results
```

The frontend is a React, TypeScript, Vite, and Leaflet application. The backend is a FastAPI application. Nginx serves the built frontend and forwards `/api/` requests to the backend service.

## Algorithms and how they work

### 1. XGBoost flood-susceptibility modelling

The susceptibility raster is generated from an XGBoost model and saved as a GeoTIFF. XGBoost is a gradient-boosted decision-tree method: it builds trees sequentially, with later trees improving the objective based on errors made by earlier trees. Input features are combined to produce a relative susceptibility score for each modelled raster cell.

The backend serves the raster as a map overlay and exposes its geographic bounds. **The score is not a calibrated flood probability, a live flood measurement, or a guarantee that a location will or will not flood.** The raster only covers its current study-area footprint.

### 2. Flood-first road routing with A*

The route comparison service uses the Chennai road graph stored in `chennai.graphml`. The documented routing approach is:

1. Map the origin and destination to the road network.
2. Intersect road segments with the supplied static flood-hazard polygons.
3. Run A* search using straight-line distance as the heuristic.
4. In the preferred pass, remove road segments that intersect mapped **HIGH** hazard zones.
5. If no path avoiding those mapped HIGH zones exists in the selected routing corridor, allow a warned fallback route.
6. Generate additional candidates by rerunning A* with penalties on edges used by previous candidates.
7. Return route geometries, relative route metrics, hazard-segment counts, and caveats.

A* prioritizes paths using the accumulated path cost plus a heuristic estimate of the remaining distance. In this implementation, the heuristic is straight-line distance, and weighted edge costs are at least the physical edge length, so the heuristic remains admissible under the documented cost setup.

The alternatives are useful candidates, **not an exhaustive set of mathematically optimal K-shortest paths**. A route result does not prove that a road is currently passable or safe.

### 3. Static flood-hazard classification

The backend loads the `Chennai Flows 100 Years Return Period` KML source and exposes its polygons through the flood-hazard API. The map can display the mapped HIGH, MODERATE, and LOW categories. Point queries classify a coordinate relative to the available mapped features.

Locations outside the mapped polygons are treated as **UNCLASSIFIED**, not flood-free. This layer represents a static return-period scenario; it is not a live inundation feed.

### 4. Spatial and temporal report corroboration

The clustering service groups recent active community reports using geographic proximity and a configurable time window. A cluster is marked `corroborated` when it reaches the configured threshold of distinct reporter tokens.

The default configuration is a 150 m radius, a 120-minute window, and three distinct reporter tokens. The report influence half-life defaults to 60 minutes. These are configurable parameters, not proof of independent human identities: a person can create multiple tokens, and tokens can be shared.

### 5. Route cost and travel-time estimates

Candidate routes use the prototype's route-cost logic, including static susceptibility and recent report influence. Travel durations are rough estimates based on travel mode; they do not use live traffic or verified road-closure information. The API reports hazard-segment categories to help explain the comparison, rather than certifying a route as safe.

## Data sources

| Data / artifact | Role in JalSuraksha |
|---|---|
| OpenCity / Greater Chennai Corporation 100-year flood-flow KML | Static flood-hazard polygons used for map display, point classification, and route-segment intersection |
| Chennai OpenStreetMap road graph (`chennai.graphml`) | Road network for route comparison |
| XGBoost susceptibility GeoTIFF | Static relative susceptibility overlay for its available study area |
| Community-submitted reports | Recent observations used in report views and spatial/temporal corroboration |
| OpenStreetMap map tiles | Base map displayed through Leaflet; attribution and tile-use policies apply |

The application status endpoint reports the current raster's CRS, dimensions, resolution, and bounds, along with whether the road graph and flood KML are available.

## AWS deployment and SageMaker status

### Current AWS hosting

The deployed application uses:

- **Amazon EC2:** runs the application host.
- **Nginx:** serves the production-built frontend and proxies `/api/` requests.
- **FastAPI + Uvicorn:** serves the backend API on the local host interface.
- **JSON file storage:** persists reports at the configured path.
- **Local geospatial files:** the road graph, susceptibility GeoTIFF, and flood-hazard KML are stored on the EC2 instance.

The currently verified public demo URL is `http://13.127.225.236/`. Configure HTTPS and production security controls before using the service beyond a demo.

### Amazon SageMaker and the ML algorithm

The susceptibility model is based on **XGBoost**, a gradient-boosted decision-tree algorithm. The generated GeoTIFF is served by the application as a static raster overlay.

**Amazon SageMaker online inference is not currently configured.** The live API status reports `sagemaker_online_endpoint` as `configured: false`. Therefore, do not describe the current deployed application as making live predictions through a SageMaker endpoint.

SageMaker could be used in a future version to manage XGBoost training and/or host a real-time inference endpoint. That would require packaging the model and preprocessing steps, configuring the endpoint and IAM permissions, and integrating the backend with the endpoint. Until this integration is implemented and verified, the application uses its available static susceptibility raster rather than a live SageMaker inference service.

## Project layout

```text
JalSuraksha/
├── app/                              # FastAPI application and backend services
├── frontend/                         # React + TypeScript + Vite + Leaflet UI
├── data/
│   ├── raw/
│   │   └── flood/                    # Source flood-hazard KML
│   ├── processed/
│   │   ├── roads/
│   │   │   └── chennai.graphml       # Road-network graph
│   │   └── susceptibility/           # Susceptibility GeoTIFF/model artifacts
│   └── reports/                      # JSON reports and uploaded photos
├── scripts/                          # Training, geospatial, and utility scripts
├── tests/                            # Backend tests
├── openapi/
│   └── openapi.json                  # Exported API schema
├── requirements-backend.txt          # Python backend dependencies
├── pytest.ini                        # Test discovery configuration
└── README.md
```

Actual files may vary by deployment bundle; the deployed server also has environment configuration and systemd/Nginx service files outside the repository.

## Run locally

### Prerequisites

- Python and a virtual environment
- Node.js and npm
- The required data files listed in the project layout

### Backend (Windows PowerShell)

Run from the repository root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-backend.txt
$env:JALSURAKSHA_STORAGE_BACKEND = "json"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If the virtual environment already exists, activate it rather than recreating it.

Backend API documentation: <http://127.0.0.1:8000/docs>

### Frontend

Open a second PowerShell terminal:

```powershell
Set-Location .\frontend
Copy-Item .env.example .env -ErrorAction SilentlyContinue
npm ci
npm run dev
```

Open the URL printed by Vite, normally <http://127.0.0.1:5173>. The Vite development proxy forwards `/api` requests to FastAPI. If your frontend setup requires an explicit API base URL, configure `VITE_API_BASE_URL` in `frontend/.env`.

### Build the frontend

From the `frontend/` directory:

```powershell
npm run build
```

### Tests and OpenAPI export

From the repository root with the backend environment activated:

```powershell
python -m pytest -q
python scripts/export_openapi.py
```

Normal pytest discovery is limited to `tests/`; exploratory scripts under `scripts/` that contact external services are not automatically run as tests.

## API endpoints

The deployed API currently exposes the following routes:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/status` | Component and data availability status |
| `GET` | `/api/v1/flood-hazards` | Flood-hazard GeoJSON |
| `GET` | `/api/v1/flood-hazards/at` | Point query against mapped flood hazards |
| `GET` | `/api/v1/susceptibility` | Susceptibility query |
| `GET` | `/api/v1/susceptibility/overlay.png` | Georeferenced raster overlay image |
| `GET` | `/api/v1/susceptibility/bounds` | Raster bounds for map display |
| `POST` | `/api/v1/routes/compare` | Compare candidate routes |
| `GET` | `/api/v1/reports` | List reports |
| `POST` | `/api/v1/reports` | Submit a report |
| `GET` | `/api/v1/reports/{report_id}` | Retrieve a report |
| `PATCH` | `/api/v1/reports/{report_id}` | Update a report under the configured authorization rules |
| `POST` | `/api/v1/reports/photo` | Upload a report photo |
| `GET` | `/api/v1/reports/photo/{photo_key}` | Retrieve an authorized report photo |
| `GET` | `/api/v1/hazards/clusters` | Retrieve report clusters |
| `GET` | `/api/v1/hazards/at` | Query hazards/reports at a location |
| `GET` | `/api/v1/responder/overview` | Responder overview |
| `GET` | `/api/v1/responder/pump-priorities` | Responder pump-priority view |

Interactive API documentation is available at `/docs` when the backend is reachable.

## Configuration

Relevant environment variables include:

| Variable | Purpose |
|---|---|
| `JALSURAKSHA_STORAGE_BACKEND` | Storage backend; `json` is the current deployment setting |
| `JALSURAKSHA_REPORT_STORE` | Path to the JSON report store |
| `JALSURAKSHA_PHOTO_DIR` | Directory for uploaded photos |
| `JALSURAKSHA_RASTER` | Path to the susceptibility GeoTIFF |
| `JALSURAKSHA_ROAD_GRAPH` | Path to the road graph |
| `JALSURAKSHA_FLOOD_HAZARD_KML` | Path to the static flood-hazard KML |
| `JALSURAKSHA_RESPONDER_TOKEN` | Secret used for responder-authorized actions |
| `JALSURAKSHA_CORS_ORIGINS` | Allowed browser origins |
| `JALSURAKSHA_CLUSTER_RADIUS_M` | Spatial clustering radius; default 150 m |
| `JALSURAKSHA_CLUSTER_WINDOW_MINUTES` | Report recency window; default 120 minutes |
| `JALSURAKSHA_CLUSTER_MIN_REPORTERS` | Distinct reporter-token threshold; default 3 |
| `JALSURAKSHA_REPORT_HALF_LIFE_MINUTES` | Report influence half-life; default 60 minutes |
| `JALSURAKSHA_MAX_PHOTO_BYTES` | Maximum accepted photo size |

Never commit production secrets to source control. Do not use the default development responder token in a deployed environment.

## Limitations and responsible use

1. **Static and incomplete hazard coverage:** the flood KML is a static 100-year-return-period scenario, and the susceptibility raster covers only its existing study-area footprint. Neither is a live flood observation or a calibrated probability. Locations outside mapped polygons are unclassified, not confirmed flood-free.
2. **No live operational feeds or safety guarantee:** the current deployment does not have a configured live sensor feed, live traffic, verified road closures, or a configured SageMaker online endpoint. Route alternatives and travel times are prototype estimates and must not be used as the sole basis for emergency decisions.

Additional production work is required for strong authentication and authorization, rate limiting, secure and durable photo storage, backups, audit and retention policies, monitoring, and validation with trusted local data and relevant authorities. Use a single application process while relying on local JSON writes; JSON storage is not suitable for concurrent multi-instance deployment.

OpenStreetMap tiles require attribution and compliance with the tile provider's usage policy.
