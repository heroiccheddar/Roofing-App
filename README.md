# RoofIQ

RoofIQ (called StormLeads in some filenames and config; it was the original name) is a roofing lead-intelligence prototype. It tells a roofing canvasser where to knock doors today. It combines storm activity with housing, demographic, hazard and market data, scores areas of Georgia, and serves those scores to a mobile-friendly map app that also tracks the leads a canvasser collects.

I built it for my brother-in-law's roofing company, and I chose the project as a test of Claude Code on a system with many datasets and several engines that feed one pipeline. It is a working prototype, not a finished product. The [Status and limitations](#status-and-limitations) section says what is and isn't solid.

## How it works

Data flows through four stages.

**1. Ingest.** The backend has 18 ingestion modules in `backend/app/ingestion/`. Live storm data comes from the National Weather Service active-alerts API (polled every 5 minutes) and the Storm Prediction Center's reports (every 6 hours). A deduplication job cross-checks the sources so that corroborated events score higher. Static and slow-moving context is loaded in bulk by scripts: US Census and ACS tract data, FEMA National Risk Index, FEMA disaster declarations and flood hazard, NOAA SWDI and NCEI historical hail and storm events, CDC Social Vulnerability Index, EPA EJScreen, USDA RUCA codes, USFS tree canopy, NASA POWER climate data, Census building permits, FHFA house price index, Redfin market data, and Microsoft building footprints.

**2. Score.** Three engines in `backend/app/scoring/` produce one score per H3 hexagon (resolution 7):

- The **base engine** scores every Georgia census tract on four sub-scores (roof condition, market quality, risk exposure, canvass efficiency), then re-normalizes across all zones so scores spread over 0 to 100. It refreshes daily.
- The **storm engine** runs every 10 minutes on newly arrived storm events. It clusters events to hexagons, computes a storm boost from hail size, wind speed, event count, corroboration and local risk context, and blends it with the base score: `composite = base × 0.80 + storm_boost × 0.20`. Storm boosts decay, and zones return to their base score after 14 days.
- The **roof-age engine** is a separate lead type that finds neighborhoods with aging housing stock, with or without a recent storm.

Scores map to bands: hot (70 and up), warm (50–69), cool (30–49) and skip (below 30). Each band carries a predicted conversion rate (12%, 7%, 3%, 1%). Those rates are model assumptions written into `weights.py`, not measured results. Calibrating them against real outcomes is planned in `VISION.md`.

**3. Recommend and route.** The "where should I go today?" endpoint ranks zones by `0.35 × score + 0.25 × proximity + 0.25 × freshness + 0.15 × storm`, where freshness rewards zones nobody has canvassed recently. Route planning uses OpenRouteService when an API key is set and falls back to a nearest-neighbour heuristic with haversine distances when it isn't.

**4. Field app.** A React progressive web app shows zones on a Mapbox map with score, distance and type filters. A canvasser can drop lead pins with one of six dispositions (not home, callback, interested, inspection set, contract signed, not interested), attach contact details and photos, log follow-ups, and see a pipeline board, calendar, analytics and a team leaderboard. Pin and feedback writes queue in IndexedDB when the phone is offline and sync when it reconnects.

An alert engine (`backend/app/services/alert_engine.py`) matches new high-scoring zones to each user's preferences, including minimum score and quiet hours, and sends email through AWS SES. An alert-history API and websocket stream sit alongside it. The engine is not yet called from the scheduled pipeline, so storm alerts are not sent automatically. SMS and push appear in the settings schema but are not implemented.

## Tech stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12+, FastAPI, async SQLAlchemy, Alembic (31 migrations), APScheduler (6 scheduled jobs), slowapi rate limiting, JWT auth with bcrypt |
| Data | PostgreSQL with PostGIS (GeoAlchemy2), H3, GeoPandas, Shapely, Rasterio; optional Upstash Redis cache |
| Frontend | React 18, TypeScript, Vite, Mapbox GL, TanStack Query, Zustand, Recharts, vite-plugin-pwa |
| Cloud | Fly.io (API, `backend/fly.toml`), Vercel (frontend), AWS S3 (photos) and SES (email) |

`backend/apprunner.yaml`, `frontend/amplify.yml` and `infra/cloudformation.yml` are from an earlier AWS deployment plan. The current deployment uses Fly.io and Vercel.

## Repository layout

```
backend/
  app/api/         16 routers under /api/v1 (zones, recommendations, route, leads, canvass, photos, analytics, ...)
  app/ingestion/   data loaders and pollers
  app/scoring/     base, storm and roof-age engines, weights, decay, freshness, H3 spatial helpers
  app/scheduler/   scheduled jobs
  app/models/      SQLAlchemy models
  alembic/         migrations
  scripts/         bulk loaders, backfills, seed scripts
  tests/           pytest suite
frontend/src/      pages, components, hooks, API client, Zustand store
infra/             legacy CloudFormation template
VISION.md          product roadmap and success metrics
MVP-IMPLEMENTATION-PLAN*.md   the three planning iterations
CLAUDE.md          development rules used when building with Claude Code
```

## Running it locally

You need Python 3.12+, Node 18+ and a PostgreSQL database with PostGIS available. The first migration runs `CREATE EXTENSION IF NOT EXISTS postgis`.

**Backend**

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # set DATABASE_URL and JWT_SECRET at minimum
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`DATABASE_URL` and `JWT_SECRET` are required. Everything else is optional and the related feature degrades without it (Redis cache, Mapbox geocoding, OpenRouteService routing, Google Solar roof data, S3 photos, SES email). Set `TARGET_STATES` to choose which states are monitored (default `GA`). Health check: `GET /health`.

**Load data** (from `backend/`, with a Census API key in `.env`):

```bash
python -m scripts.seed_database --census-only    # census tracts
python -m scripts.seed_database --storms-only    # storm events, dedup, scoring
python -m scripts.seed_synthetic_data            # clearly tagged fake storms for testing
python -m scripts.seed_demo_pins                 # fake demo lead pins for every account
```

The enrichment datasets each have a loader in `backend/scripts/` (for example `load_nri_data`, `load_fema_disasters`, `load_redfin`). Run `python -m scripts.compute_percentiles` after loading them.

**Frontend**

```bash
cd frontend
npm ci
cp .env.example .env           # set VITE_API_URL and VITE_MAPBOX_TOKEN
npm run dev
```

`npm run build` type-checks and produces the production build, including the service worker.

## Testing

The backend has 225 test functions (262 cases after parametrization) in `backend/tests/`, run with `pytest` from `backend/`. Current results: **217 pass, 36 fail and 9 error.**

- **Passing:** the base engine, time decay, freshness, roof-age scoring and H3 spatial helpers all pass in full (122 tests), plus most of the storm engine, weights and SWDI fetcher tests.
- **Failing, and why:** the failures are tests that were not updated after the scoring model moved to version 9. The score-band tests still expect the older thresholds (hot at 80, not 70), one test asserts model version 7.0.0, a fixture builds `ModelVersion` without two fields it now requires, and the storm-engine test mocks don't supply the newer enrichment fields. Two SWDI fetcher tests also fail for reasons not yet investigated.
- **Not covered:** there are no API-level tests, no frontend tests and no CI workflow (`.github/workflows` is empty), and `npm run lint` has no ESLint configuration to run against.

Most of the existing tests check scoring math in isolation. Whether the full pipeline behaves correctly against a real PostGIS database has not been verified by automated tests.

## Status and limitations

- **Georgia only.** The base engine is hard-wired to Georgia census tracts. `VISION.md` describes the multi-state plan.
- **Scores are not yet validated.** The weights and conversion rates are informed assumptions. The calibration loop that compares predicted and actual outcomes (Phase 2 in `VISION.md`) isn't built yet.
- **Single-tenant in practice.** The organization model exists, but billing, territory management and an onboarding flow are roadmap items.
- **Alerts are not wired in.** See the alert engine note above.
- **Test suite needs repair** as described above.
- **Naming is inconsistent**: RoofIQ in the UI and docs, StormLeads in some config, package names and the Fly.io app name.

## How it was built

The project was built with Claude Code. `CLAUDE.md` holds the rules that kept it consistent: size and rate-limit planning before any data script is written, batched database commits to stay inside a small Fly.io machine, and a shared contract (column names, endpoint signatures, TypeScript types, store shape) defined before work on large features is split into parallel streams that never touch the same file.
