# StormLeads — Proof of Concept Build Plan v3.0

**Goal:** Prove that the scoring algorithm produces actionable lead zones before investing in alerts, feedback loops, or monetization features.
**Stack:** FastAPI + Neon PostGIS + AWS App Runner + React/Mapbox
**Cost:** ~$6-8/mo (Neon $5 + App Runner ~$1-3 at low traffic)
**Timeline:** 6 Weeks · Solo Developer Build
**Accounts:** AWS, Neon, Upstash, GitHub, Mapbox, Census Bureau

---

## Table of Contents

1. [What We're Building (And What We're Not)](#1-what-were-building-and-what-were-not)
2. [Stack & Setup](#2-stack--setup)
3. [Phase 1: Foundation](#phase-1-foundation--weeks-12) — Database + storm data pipeline
4. [Phase 2: Brain](#phase-2-brain--weeks-34) — Scoring engine + lead zone generation
5. [Phase 3: Surface](#phase-3-surface--weeks-56) — API + map dashboard
6. [Deployment Pipeline](#deployment-pipeline)
7. [Field Validation Plan](#field-validation-plan)
8. [What Comes After POC](#what-comes-after-poc)

---

## 1. What We're Building (And What We're Not)

### The POC Question

> "Does our scoring algorithm correctly identify neighborhoods where a roofer should knock doors?"

Everything in this plan exists to answer that question. If the answer is yes, we build alerts, feedback loops, and monetization. If the answer is no, we've spent $30 total and 6 weeks — not 12 weeks and a pile of unused infrastructure.

### What Ships

A web app where a roofer logs in, sees a map of scored neighborhoods based on recent storm activity, and can click any zone to see why it scored the way it did. The roofer checks it manually — like checking the weather — and decides whether to go canvass. There is a simple feedback form on each zone so roofers can report back what they found.

### What's Explicitly Deferred

| Feature | Why It Can Wait |
|---------|----------------|
| SMS/email alerts | Proves nothing about scoring accuracy. Add after field validation. |
| WebSocket real-time push | Same — just refresh the page. |
| Calibration engine | Needs 200+ feedback sessions. Not useful for months. |
| Admin weight tuning dashboard | Manual SQL updates are fine for POC tuning. |
| Stripe payment integration | No point charging until we know the product works. |
| PWA offline support | Nice-to-have. Roofers have cell service in suburbs. |
| Service worker | Deferred with offline support. |
| Gamification / nudges | Zero users to gamify. |
| Landing page / marketing site | Build when there's something to sell. |
| Custom domain | Use default AWS URLs until ready for real users. Optional to add anytime. |

### POC Success Criteria

Before building Phase 4+ (alerts, feedback loop, monetization), validate ALL of these:

1. **Ingestion reliability** — storm data pipeline runs 7+ days with no missed events or crashes.
2. **Scoring face validity** — hot zones (80+) consistently land on neighborhoods with visible roof damage. Cool/skip zones are genuinely low-opportunity.
3. **Roofer signal** — at least 2-3 roofers (can be friends/contacts in the industry) confirm "yes, I would drive to this zone" when shown a hot-scored zone, or "this is accurate" after canvassing one.
4. **Time-to-value** — zones appear within 30 minutes of a storm event, not hours.
5. **Geographic accuracy** — zone boundaries make sense on the ground. Not too wide (entire city), not too narrow (single block).

---

## 2. Stack & Setup

### Accounts to Create

| # | Account | What to Do | Cost |
|---|---------|-----------|------|
| 1 | **AWS** | Create account → enable MFA → create IAM user for CLI → install AWS CLI. Enable App Runner, Amplify, CloudWatch, ECR. | ~$1-3/mo |
| 2 | **Neon** | Sign up → create project in `us-east-2` → enable `postgis` + `h3-pg` extensions. Start free, upgrade to Launch ($5/mo) at deployment. | $5/mo |
| 3 | **Upstash** | Sign up → create Redis database in `us-east-1` (AWS) → copy REST URL and token. | $0 |
| 4 | **GitHub** | Create repo `stormleads`. App Runner and Amplify deploy from here. | $0 |
| 5 | **Mapbox** | Sign up → copy default public access token. | $0 |
| 6 | **Census API** | Request key at `api.census.gov/data/key_signup.html`. Instant email approval. | $0 |

**Total: ~$6-8/mo.** No SES, SNS, Route 53, or Stripe needed for POC.

### Cost Breakdown

| Service | What It Powers | Monthly Cost |
|---------|---------------|-------------|
| **Neon Launch** | PostGIS database (storms, census, zones) | $5.00 |
| **App Runner** | FastAPI + APScheduler (0.25 vCPU / 0.5 GB) | ~$1-3 |
| **Amplify Hosting** | React dashboard (free tier) | $0 |
| **CloudWatch** | Logs + 1 health check alarm (free tier) | $0 |
| **ECR** | Container image storage | ~$0.10 |
| **Upstash Redis** | GeoJSON response caching (free tier) | $0 |
| **Mapbox GL JS** | Map rendering (free tier) | $0 |
| | **Total** | **~$6-8/mo** |

### Repository Structure

Stripped-down monorepo. No alert services, no SMS/email integrations, no service worker.

```
stormleads/
├── backend/                        # → AWS App Runner
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI + APScheduler init
│   │   ├── config.py               # Pydantic Settings
│   │   ├── database.py             # SQLAlchemy async engine + session
│   │   │
│   │   ├── models/                 # SQLAlchemy ORM (5 tables for POC)
│   │   │   ├── __init__.py
│   │   │   ├── storm_event.py
│   │   │   ├── census_tract.py
│   │   │   ├── lead_zone.py
│   │   │   ├── roofer_account.py
│   │   │   └── zone_feedback.py    # Simple feedback (rating + notes)
│   │   │
│   │   ├── ingestion/              # Data pipeline
│   │   │   ├── __init__.py
│   │   │   ├── nws_poller.py       # 5-min NWS alerts poll
│   │   │   ├── spc_scraper.py      # 6-hr SPC storm reports
│   │   │   ├── swdi_fetcher.py     # On-demand SWDI radar data
│   │   │   └── census_loader.py    # One-time ACS bulk load
│   │   │
│   │   ├── scoring/                # Core product logic
│   │   │   ├── __init__.py
│   │   │   ├── engine.py           # Composite scoring pipeline
│   │   │   ├── weights.py          # v1.0.0 hardcoded weights
│   │   │   ├── spatial.py          # PostGIS helpers + H3 clustering
│   │   │   └── decay.py            # Time decay function
│   │   │
│   │   ├── api/                    # FastAPI routes
│   │   │   ├── __init__.py
│   │   │   ├── auth.py             # Register + login (JWT)
│   │   │   ├── zones.py            # Zone list, detail, GeoJSON
│   │   │   └── feedback.py         # Simple zone feedback
│   │   │
│   │   ├── scheduler/
│   │   │   ├── __init__.py
│   │   │   └── jobs.py             # APScheduler job definitions
│   │   │
│   │   └── services/
│   │       ├── __init__.py
│   │       └── redis_cache.py      # Upstash HTTP client
│   │
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── pytest.ini
│
├── frontend/                       # → AWS Amplify
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── MapView.tsx         # Mapbox GL JS map
│   │   │   ├── ZonePanel.tsx       # Zone detail drawer
│   │   │   ├── ZoneList.tsx        # Sortable/filterable list
│   │   │   ├── ScoreBadge.tsx      # Color-coded score display
│   │   │   └── FeedbackForm.tsx    # Simple rating + text
│   │   ├── hooks/
│   │   │   └── useZones.ts         # Zone data fetching
│   │   ├── stores/
│   │   │   └── appStore.ts         # Zustand state
│   │   └── pages/
│   │       ├── Dashboard.tsx       # Main map + zone panel
│   │       └── Login.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── amplify.yml
│   └── tsconfig.json
│
├── scripts/
│   ├── load_census_data.py         # Bulk ACS loader
│   ├── backfill_historical.py      # 30-day Storm Events DB
│   └── seed_test_data.py           # Dev fixtures
│
├── .env.example
└── README.md
```

### Environment Variables

```bash
# ── Database (Neon) ──
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xyz.us-east-2.aws.neon.tech/stormleads?sslmode=require

# ── Redis (Upstash) ──
UPSTASH_REDIS_URL=https://usw2-xyz.upstash.io
UPSTASH_REDIS_TOKEN=AXxxxxxxxxxxxx

# ── Auth ──
JWT_SECRET=(generate: openssl rand -hex 32)
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=72

# ── AWS (only needed for local dev — App Runner uses IAM role) ──
AWS_REGION=us-east-2
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxx       # local dev only
AWS_SECRET_ACCESS_KEY=xxxxxxxxxx       # local dev only

# ── Census ──
CENSUS_API_KEY=xxxxxxxxxx

# ── Frontend (Amplify env vars) ──
VITE_API_URL=https://xxxxxxxxxx.us-east-2.awsapprunner.com
VITE_MAPBOX_TOKEN=pk.xxxxxxxxxx
```

No SES, SNS, or Twilio vars needed. If you add a custom domain later, update `VITE_API_URL` to `https://api.stormleads.com`.

### Core Python Dependencies

```
# backend/requirements.txt

# ── Framework ──
fastapi[standard]==0.115.*
uvicorn[standard]==0.34.*
pydantic-settings==2.*

# ── Database ──
sqlalchemy[asyncio]==2.0.*
asyncpg==0.30.*
geoalchemy2==0.15.*
alembic==1.14.*

# ── Scheduling ──
apscheduler==3.10.*

# ── Spatial + Data ──
geopandas==1.0.*
h3==3.7.*
shapely==2.0.*
httpx==0.28.*

# ── Auth ──
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*

# ── External Services ──
upstash-redis==1.*

# ── Monitoring ──
watchtower==3.*                  # CloudWatch Logs handler

# ── Dev/Test ──
pytest==8.*
pytest-asyncio==0.24.*
```

No `boto3` needed for POC (no SES/SNS). `watchtower` is optional — standard Python `logging` to stdout works fine since App Runner captures stdout to CloudWatch automatically.

### Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
EXPOSE 8080
```

### Amplify Build Config

```yaml
# frontend/amplify.yml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: dist
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
```

---

## Phase 1: Foundation — Weeks 1–2

**Goal:** Storm events flowing into PostGIS and census demographics loaded. All spatial queries verified.
**Running cost:** $0 (Neon free tier, local dev only).

### Database Schema (5 tables for POC)

The full product has 7 tables. For POC, we skip `canvass_sessions` (detailed feedback), `model_calibration` (needs 200+ sessions), and `alert_log` (no alerts). We add a simple `zone_feedback` table instead.

```sql
-- 1. storm_events — raw ingested storm data
CREATE TABLE storm_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(20) NOT NULL,           -- 'nws', 'spc', 'swdi'
    external_id VARCHAR(100),              -- source's ID for dedup
    event_timestamp TIMESTAMPTZ NOT NULL,
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    warning_polygon GEOGRAPHY(POLYGON, 4326),
    hail_diameter_inches FLOAT,
    wind_speed_mph FLOAT,
    radar_confidence FLOAT,                -- SWDI MESH probability 0-1
    corroborated_event_id UUID REFERENCES storm_events(id),
    raw_data JSONB,                        -- full source payload
    processed BOOLEAN DEFAULT FALSE,       -- scoring engine flag
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_storm_events_location ON storm_events USING GIST (location);
CREATE INDEX idx_storm_events_timestamp ON storm_events USING BRIN (event_timestamp);
CREATE INDEX idx_storm_events_unprocessed ON storm_events (processed) WHERE processed = FALSE;

-- 2. census_tracts — pre-loaded demographics
CREATE TABLE census_tracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geoid VARCHAR(11) UNIQUE NOT NULL,     -- FIPS code
    state_fips VARCHAR(2) NOT NULL,
    geometry GEOGRAPHY(MULTIPOLYGON, 4326) NOT NULL,
    owner_occupied_pct FLOAT,              -- B25003
    median_year_built INTEGER,             -- B25035
    median_home_value INTEGER,             -- B25077
    total_population INTEGER,              -- B01003
    total_housing_units INTEGER,
    land_area_sq_km FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_census_tracts_geometry ON census_tracts USING GIST (geometry);
CREATE INDEX idx_census_tracts_state ON census_tracts (state_fips);

-- 3. lead_zones — scored neighborhoods (core product output)
CREATE TABLE lead_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    boundary GEOGRAPHY(POLYGON, 4326) NOT NULL,
    centroid GEOGRAPHY(POINT, 4326) NOT NULL,
    h3_index VARCHAR(20),                  -- H3 resolution 7 hex ID
    composite_score FLOAT NOT NULL,        -- 0-100
    score_band VARCHAR(10) NOT NULL,       -- 'hot', 'warm', 'cool', 'skip'
    damage_prob FLOAT NOT NULL,            -- 0-100 subscore
    lead_quality FLOAT NOT NULL,           -- 0-100 subscore
    density_bonus FLOAT NOT NULL,          -- 0-100 subscore
    time_decay FLOAT NOT NULL,             -- 0.0-1.0 multiplier at creation
    max_hail_diameter FLOAT,
    max_wind_speed FLOAT,
    event_count INTEGER DEFAULT 1,
    earliest_event TIMESTAMPTZ NOT NULL,
    latest_event TIMESTAMPTZ NOT NULL,
    predicted_conversion_rate FLOAT,       -- lookup table for POC
    score_weights_snapshot JSONB NOT NULL,  -- frozen v1.0.0 weights
    model_version VARCHAR(20) NOT NULL,    -- 'v1.0.0'
    contributing_event_ids UUID[] NOT NULL, -- array of storm_event IDs
    contributing_tract_ids UUID[],         -- array of census_tract IDs
    expires_at TIMESTAMPTZ NOT NULL,       -- 14 days from latest_event
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_lead_zones_boundary ON lead_zones USING GIST (boundary);
CREATE INDEX idx_lead_zones_score ON lead_zones (composite_score DESC);
CREATE INDEX idx_lead_zones_active ON lead_zones (expires_at) WHERE expires_at > NOW();
CREATE INDEX idx_lead_zones_band ON lead_zones (score_band);

-- 4. roofer_accounts — user accounts
CREATE TABLE roofer_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    service_area GEOGRAPHY(POLYGON, 4326), -- ST_Buffer(center, radius)
    service_area_center GEOGRAPHY(POINT, 4326),
    service_area_radius_km FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. zone_feedback — simple POC feedback (replaces full canvass_sessions)
CREATE TABLE zone_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_zone_id UUID NOT NULL REFERENCES lead_zones(id),
    roofer_account_id UUID NOT NULL REFERENCES roofer_accounts(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    visible_damage BOOLEAN,
    notes TEXT,                             -- free-text field observations
    zone_score_at_feedback FLOAT,          -- snapshot of zone score
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(lead_zone_id, roofer_account_id) -- one feedback per roofer per zone
);
```

### Week 1 — Database + Census Data

- [ ] **Create Neon project** — region `us-east-2`, enable `postgis` and `h3-pg` extensions. Stay on free tier during development.
- [ ] **Define SQLAlchemy models** for all 5 tables using GeoAlchemy2 geometry columns. Each model in its own file under `app/models/`.
- [ ] **Set up Alembic** — initial migration creates schema with all indexes above. Verify migration runs cleanly against Neon.
- [ ] **Build `census_loader.py`** — fetch ACS 5-Year data at tract level:
  - B25003: Owner-occupied vs renter (homeownership rate)
  - B25035: Median year structure built (roof age proxy)
  - B25077: Median home value (willingness/ability to pay)
  - B01003: Total population
  - TIGER/Line shapefiles for tract boundary geometries
  - Use Census API + `geopandas` to join tabular data with geometries
- [ ] **Load initial states** — TX, OK, KS, CO, NE (hail corridor). ~15K tracts. This covers the highest-probability storm region for initial validation.
- [ ] **Verify spatial queries work:**
  ```sql
  -- Find tracts near a point
  SELECT geoid, owner_occupied_pct, median_year_built
  FROM census_tracts
  WHERE ST_DWithin(geometry, ST_MakePoint(-96.77, 32.78)::geography, 25000);
  
  -- Confirm PostGIS index is being used
  EXPLAIN ANALYZE SELECT ...;
  ```

### Week 2 — Storm Data Ingestion

- [ ] **Build `nws_poller.py`** — async httpx polling `api.weather.gov/alerts/active` every 5 minutes.
  - Filter: `event=Severe Thunderstorm Warning` (hail-producing storms)
  - Parse GeoJSON warning polygon → `warning_polygon` column
  - Extract hail size from `parameters.maxHailSize` or description text
  - Extract wind speed from `parameters.maxWindGust`
  - Upsert using NWS alert ID as `external_id` (avoid duplicates on re-poll)
  - Mark existing alerts as expired when NWS removes them

- [ ] **Build `spc_scraper.py`** — parse SPC daily CSV every 6 hours.
  - URL: `spc.noaa.gov/climo/reports/today_hail.csv` (rotates daily)
  - Also check `yesterday_hail.csv` for overlap coverage
  - Fields: time, lat, lon, size (inches), county, state
  - Insert as `source='spc'` storm events
  - Only insert if hail size ≥ 1.0" (below that, minimal roof damage)

- [ ] **Build `swdi_fetcher.py`** — query NCEI SWDI API on-demand.
  - Trigger: when `nws_poller` inserts a new warning with hail ≥ 1.0"
  - Query SWDI for MESH (Maximum Expected Size of Hail) data in the warning polygon's bounding box
  - MESH gives radar-derived hail probability — higher fidelity than ground reports
  - Store `radar_confidence` as MESH probability (0.0–1.0)
  - This corroborates NWS/SPC reports with actual radar signatures

- [ ] **Wire APScheduler into FastAPI startup** (`app/main.py`):
  ```python
  @app.on_event("startup")
  async def start_scheduler():
      scheduler = AsyncIOScheduler()
      scheduler.add_job(poll_nws, 'interval', minutes=5)
      scheduler.add_job(scrape_spc, 'interval', hours=6)
      scheduler.add_job(cleanup_expired_zones, 'cron', hour=2)  # daily 2 AM UTC
      scheduler.start()
  ```

- [ ] **Deduplication logic** — when inserting from any source, check for existing events within ±30 minutes AND `ST_DWithin(location, existing.location, 15000)` (15km). If match found, link via `corroborated_event_id` and take the max hail size. Corroborated events get a scoring boost.

- [ ] **Backfill 30 days** — run `scripts/backfill_historical.py` to load Storm Events DB CSV for the past month. This gives the scoring engine data to validate against in Phase 2.

- [ ] **Verify pipeline end-to-end** — run locally for 24 hours. Confirm:
  - NWS polls return data (or empty if no active storms — that's fine)
  - SPC CSV parses correctly
  - Deduplication catches overlaps
  - `storm_events` table grows with real data
  - No memory leaks in the polling loop

### Phase 1 Milestone

```sql
-- Real storm events are in the database
SELECT source, COUNT(*), AVG(hail_diameter_inches)
FROM storm_events
GROUP BY source;

-- Census tracts are queryable by geography
SELECT COUNT(*) FROM census_tracts WHERE state_fips = '48'; -- Texas
```

Storm events flowing in from 3 federal sources. Census demographics loaded for 5 states. All spatial queries return results with sub-second response times.

---

## Phase 2: Brain — Weeks 3–4

**Goal:** Storm events automatically scored into lead zones. The scoring formula produces results that pass a gut check.
**Running cost:** $0 (still local dev + Neon free tier).

### Week 3 — Scoring Algorithm

- [ ] **Implement `weights.py`** — v1.0.0 hardcoded weights:

  ```python
  @dataclass
  class ModelWeights:
      version: str = "v1.0.0"
      
      # Component weights (must sum to 1.0)
      damage_weight: float = 0.50
      quality_weight: float = 0.30
      density_weight: float = 0.20
      
      # Damage sub-weights
      hail_diameter: float = 0.40        # bigger hail = more damage
      wind_speed: float = 0.25           # wind compounds hail damage
      radar_confidence: float = 0.20     # MESH probability
      report_corroboration: float = 0.15 # multiple sources = higher confidence
      
      # Lead quality sub-weights
      homeownership: float = 0.40        # owners replace roofs, renters don't
      roof_age: float = 0.35             # older roofs = more vulnerable
      home_value: float = 0.25           # higher value = bigger jobs
      
      def to_snapshot(self) -> dict:
          """Freeze weights as JSON for lead_zone record."""
          return asdict(self)
  ```

- [ ] **Implement `decay.py`** — exponential time decay:
  ```python
  def time_decay(hours_since_storm: float) -> float:
      """
      e^(-0.25 × hours/24)
      
      At 0 hours:   1.00 (full value)
      At 24 hours:  0.78
      At 48 hours:  0.61
      At 72 hours:  0.47
      At 168 hours: 0.17 (7 days — zone is fading)
      """
      return math.exp(-0.25 * hours_since_storm / 24)
  ```

- [ ] **Implement `spatial.py`** — PostGIS helper functions:
  - `find_intersecting_tracts(event_bbox)` — find census tracts that intersect a storm event's bounding box or warning polygon
  - `cluster_events_h3(events, resolution=7)` — group nearby events into H3 hex cells (~5.16 km² each). Each hex becomes a potential lead zone.
  - `compute_zone_boundary(tract_geometries)` — convex hull of underlying tract geometries for the zone boundary
  - `housing_density(tract)` — `total_housing_units / land_area_sq_km`

- [ ] **Implement `engine.py`** — the composite scoring pipeline. This is the core product logic:

  ```
  For each unprocessed storm event cluster:
  
  1. SPATIAL JOIN — find census tracts intersecting event locations
  2. AGGREGATE — group events by H3 hex (resolution 7)
  3. DAMAGE_PROB (0-100):
     - Normalize hail_diameter: 1.0" → 20, 2.0" → 60, 3.0" → 100
     - Normalize wind_speed: 58mph → 20, 80mph → 60, 100mph+ → 100
     - Factor in radar_confidence (SWDI MESH probability)
     - Corroboration bonus: +15 if event confirmed by 2+ sources
     - Weighted sum using damage sub-weights
  4. LEAD_QUALITY (0-100):
     - Homeownership: 90%+ → 100, 50% → 50, <30% → 10
     - Roof age: built before 1990 → 100, 1990-2010 → 60, after 2010 → 20
     - Home value: >$300K → 100, $200K → 70, <$100K → 20
     - Weighted sum using quality sub-weights
  5. DENSITY_BONUS (0-100):
     - Housing density score: >500 units/km² → 100, 200 → 50, <50 → 10
     - Suburban sweet spot bonus: +20 if density 200-800 (dense suburbs, not urban/rural)
  6. COMPOSITE = (DAMAGE × 0.50 + QUALITY × 0.30 + DENSITY × 0.20) × TIME_DECAY
  7. INSERT lead_zone with all scores + frozen weight snapshot
  ```

### Week 4 — Zone Generation + Validation

- [ ] **Zone generation job** — APScheduler runs scoring after each ingestion cycle:
  1. Query `storm_events WHERE processed = FALSE`
  2. Run scoring pipeline
  3. For each H3 hex cluster with score > 0:
     - Check if active zone exists for this hex → update (recalculate) vs insert (new zone)
     - Set `score_band`: hot (80-100), warm (60-79), cool (40-59), skip (0-39)
     - Set `expires_at` to 14 days from `latest_event`
     - Freeze `score_weights_snapshot` as JSON
  4. Mark source events as `processed = TRUE`

- [ ] **Predicted conversion rate** — simple lookup table for POC:
  | Score Band | Predicted Conversion |
  |-----------|---------------------|
  | Hot (80-100) | 12% |
  | Warm (60-79) | 7% |
  | Cool (40-59) | 3% |
  | Skip (0-39) | 1% |

  These are rough estimates. Real calibration comes later with field data.

- [ ] **Zone refresh logic** — when new events arrive near an existing active zone:
  - Don't create a duplicate — update the existing zone
  - Recalculate `composite_score` with all contributing events
  - Update `event_count`, `max_hail_diameter`, `latest_event`
  - Extend `expires_at` if new event is more recent

- [ ] **Zone expiry cleanup** — daily job at 2 AM UTC: delete zones past `expires_at`.

- [ ] **Historical validation** — run scoring engine against 30 days of backfilled data. Manually inspect results:
  - Do hot zones land on areas that had known severe damage?
  - Do skip zones correctly avoid low-opportunity areas?
  - Are zone boundaries sensible (not too wide, not too narrow)?
  - Adjust scoring thresholds and normalization curves based on gut checks
  - Document any tuning decisions for later reference

- [ ] **Unit tests:**
  - `test_decay.py` — verify decay curve values at known time points
  - `test_weights.py` — snapshot serialization/deserialization roundtrip
  - `test_scoring.py` — known inputs produce expected score ranges
  - `test_spatial.py` — H3 aggregation, tract intersection, boundary generation
  - `test_zone_lifecycle.py` — create, update, expire, cleanup

### Phase 2 Milestone

Run scoring on backfilled data. Verify manually:
- 2.5" hail in 1970s-era suburb, 85% homeownership → scores 80+ (hot) ✓
- 1.0" hail in new-construction rental complex → scores 30 (skip) ✓
- Same storm area, 72 hours later → score decayed by ~50% ✓
- Zone boundary wraps 3-5 census tracts, not an entire metro area ✓

---

## Phase 3: Surface — Weeks 5–6

**Goal:** Deploy. A roofer logs in and sees scored zones on a map. Simple feedback form lets them report what they found.
**Running cost:** ~$6-8/mo (Neon Launch $5 + App Runner ~$1-3).

### Week 5 — REST API + Backend Deploy

- [ ] **Health check endpoint:**
  ```python
  @app.get("/health")
  async def health():
      return {"status": "ok", "version": "0.1.0"}
  ```

- [ ] **Auth endpoints:**
  - `POST /api/v1/auth/register` — email, password, company_name, service area (lat, lon, radius_km). Hash password with bcrypt. Store service area as `ST_Buffer(ST_MakePoint(lon, lat)::geography, radius_km * 1000)`.
  - `POST /api/v1/auth/login` — returns JWT (72hr expiry). Include `roofer_id` in token payload.

- [ ] **Zone endpoints:**
  - `GET /api/v1/zones` — list active zones intersecting roofer's service area. Params: `min_score` (default 40), `sort_by` (score|recency), `page`, `per_page`. Returns summary: id, score, band, hail size, hours since storm, centroid lat/lon.
  - `GET /api/v1/zones/{id}` — full zone detail. Recalculate time decay on read (score shown is always current). Include all sub-scores, contributing events, census overlay stats.
  - `GET /api/v1/zones/geojson` — GeoJSON FeatureCollection for Mapbox. Params: `bbox` (map viewport), `min_score`. Each feature includes `composite_score`, `score_band`, and `max_hail_diameter` as properties for map styling.

- [ ] **Feedback endpoints:**
  - `POST /api/v1/zones/{id}/feedback` — `{ rating: 1-5, visible_damage: true/false, notes: "string" }`. Snapshots `zone_score_at_feedback`. One feedback per roofer per zone (upsert).
  - `GET /api/v1/zones/{id}/feedback` — list feedback for a zone (admin use).

- [ ] **Redis caching** — cache GeoJSON endpoint in Upstash (TTL 5 min). Cache zone detail (TTL 1 min). Invalidate both when scoring engine generates new zones.

- [ ] **Deploy to AWS App Runner:**
  1. Push code to GitHub `main` branch
  2. AWS Console → App Runner → Create Service
  3. Source: GitHub repository, branch `main`, source directory `/backend`
  4. Deployment: automatic on push
  5. Instance: 0.25 vCPU / 0.5 GB RAM (smallest available)
  6. Port: 8080
  7. Health check: HTTP GET `/health`
  8. Auto-scaling: min 1, max 2 (keep 1 always-on for storm monitoring)
  9. Set environment variables: `DATABASE_URL`, `UPSTASH_REDIS_URL`, `UPSTASH_REDIS_TOKEN`, `JWT_SECRET`, `CENSUS_API_KEY`
  10. Note the generated URL: `https://xxxxxxxxxx.us-east-2.awsapprunner.com`

- [ ] **Upgrade Neon to Launch** ($5/mo). Enable connection pooling. Verify App Runner connects to Neon with `?sslmode=require`.

- [ ] **Run database migration** from local machine:
  ```bash
  DATABASE_URL=postgresql+asyncpg://... alembic upgrade head
  ```

- [ ] **Load census data into production** — run `scripts/load_census_data.py` against the Neon production database.

- [ ] **Verify ingestion is running** — check CloudWatch logs (App Runner ships stdout automatically). Confirm NWS poll and SPC scrape are executing on schedule.

### Week 6 — React Dashboard

- [ ] **Scaffold frontend** — `npm create vite@latest frontend -- --template react-ts`. Install dependencies:
  ```bash
  npm install mapbox-gl @types/mapbox-gl zustand @tanstack/react-query axios
  ```

- [ ] **Login page** — email/password form. Store JWT in memory (React state, not localStorage). Redirect to Dashboard on success. Show error on invalid credentials.

- [ ] **Dashboard page layout:**
  ```
  ┌─────────────────────────────────────────────────────────┐
  │  StormLeads POC    [Filters: Min Score ▼] [Sort ▼]  🔄  │
  ├───────────────────────────────────┬─────────────────────┤
  │                                   │  Zone List          │
  │                                   │  ┌───────────────┐  │
  │          Mapbox GL JS             │  │ 🔴 Score: 87   │  │
  │          Map View                 │  │ Plano, TX      │  │
  │                                   │  │ 2.5" hail, 6h  │  │
  │          (colored zone            │  ├───────────────┤  │
  │           polygons)               │  │ 🟠 Score: 72   │  │
  │                                   │  │ Frisco, TX     │  │
  │                                   │  │ 1.75" hail, 3h │  │
  │                                   │  ├───────────────┤  │
  │                                   │  │ 🟡 Score: 55   │  │
  │                                   │  │ McKinney, TX   │  │
  │                                   │  │ 1.0" hail, 12h │  │
  │                                   │  └───────────────┘  │
  └───────────────────────────────────┴─────────────────────┘
  ```
  Map takes ~70% width. Zone list panel on right. Responsive — stack vertically on mobile.

- [ ] **MapView component** — Mapbox GL JS with GeoJSON source:
  - Fetch `/api/v1/zones/geojson` on load and when viewport changes
  - Fill color by score band: hot=`#ef4444`, warm=`#f97316`, cool=`#eab308`, skip=`#9ca3af`
  - Fill opacity: 0.4 (semi-transparent so street map shows through)
  - Stroke: 2px, same color at full opacity
  - Click polygon → select zone → show detail in ZonePanel
  - Zoom to roofer's service area on initial load (from JWT/account data)

- [ ] **ZonePanel component** — drawer/sidebar showing selected zone detail:
  - Big number: composite score with color badge
  - Sub-scores: damage probability, lead quality, density bonus (smaller)
  - Storm info: max hail size, max wind speed, event count, hours since storm
  - Census overlay: homeownership %, median year built, median home value
  - Time decay indicator: "Score was 92 at time of storm, now 87 (decaying)"
  - **Navigate button** — opens Google Maps directions to zone centroid
  - **Feedback section** — inline form: star rating (1-5), "visible damage?" toggle, notes text field, submit button

- [ ] **ZoneList component** — scrollable list of zones:
  - Score badge (color-coded), location description, hail size, time since storm
  - Click to select → map zooms to zone + ZonePanel opens
  - Filter: min score slider (0-100, default 40)
  - Sort: by score (default) or by recency

- [ ] **Auto-refresh** — poll `/api/v1/zones` every 5 minutes via `react-query` with `refetchInterval`. Subtle "Updated just now" indicator. Manual refresh button.

- [ ] **Deploy to AWS Amplify:**
  1. AWS Console → Amplify → New App → GitHub
  2. Repository: `stormleads`, branch: `main`
  3. App root: `/frontend`
  4. Framework auto-detected: Vite
  5. Environment variables: `VITE_API_URL` = App Runner URL, `VITE_MAPBOX_TOKEN`
  6. Configure rewrite rule: `/<*>` → `/index.html` (200) for SPA routing
  7. Note generated URL: `https://main.xxxxxxxxxx.amplifyapp.com`

- [ ] **Configure CORS on backend** — allow Amplify domain origin. Add middleware:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://main.xxxxxxxxxx.amplifyapp.com"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- [ ] **Smoke test the full flow:**
  1. Register a test account with service area around Dallas, TX
  2. Log in → see map centered on service area
  3. Zones from backfilled/live data appear as colored polygons
  4. Click a zone → detail panel shows scores and census data
  5. Submit feedback on a zone → confirm it saves
  6. Wait for NWS poll → confirm new zones appear after refresh

### Phase 3 Milestone

Live web app. A roofer registers, logs in, sees scored zones on a map with real storm data, clicks for detail, and can leave simple feedback. Backend is polling NWS every 5 minutes and generating new zones automatically. The app URL is a default AWS domain — no custom domain needed yet.

**The POC is deployed. Time to validate in the field.**

---

## Deployment Pipeline

### Git-Push Deploys

```bash
# Everything deploys on push to main:
git add .
git commit -m "feat: add zone detail endpoint"
git push origin main

# App Runner: detects /backend change → Docker build → deploy (~3-5 min)
# Amplify: detects /frontend change → npm build → deploy (~1-2 min)
```

**App Runner settings:** source directory `/backend`, auto-deploy on, 0.25 vCPU / 0.5 GB, min 1 instance, max 2, health check `GET /health`.

**Amplify settings:** app root `/frontend`, build per `amplify.yml`, rewrite `/<*>` → `/index.html` (200).

### Database Migrations

```bash
# From local machine:
cd backend
export DATABASE_URL=postgresql+asyncpg://user:pass@ep-xyz.neon.tech/stormleads?sslmode=require
alembic upgrade head
```

Not automated — run manually after deploying backend changes that include new migrations. Review migration SQL before running against production.

### Local Development

```bash
# Terminal 1: Backend
cd backend
export DATABASE_URL=postgresql+asyncpg://...  # Neon connection string
export UPSTASH_REDIS_URL=https://...
export UPSTASH_REDIS_TOKEN=...
export JWT_SECRET=dev-secret-change-me
export CENSUS_API_KEY=...
uvicorn app.main:app --reload --port 8080

# Terminal 2: Frontend
cd frontend
export VITE_API_URL=http://localhost:8080
export VITE_MAPBOX_TOKEN=pk.xxx
npm run dev
```

Local dev connects to real Neon and Upstash — no local database to manage.

---

## Field Validation Plan

### How to Test (Weeks 7-8, Post-Deploy)

With the POC running, spend 2 weeks validating before building more features.

**Step 1: Solo spot-checking (Week 7)**
- Monitor the app daily. When a storm hits a loaded state, check the zones it generates.
- Drive to 2-3 hot-scored zones if any are within range. Do you see roof damage? Are there other roofers already there?
- Check cool/skip zones — are they genuinely low-value? Or is the algorithm missing something?
- Document every observation. Screenshot zones + what you found on the ground.

**Step 2: Roofer feedback (Week 8)**
- Share the app with 2-3 roofers you know or can find (roofing company owners, storm chasers).
- Ask them to use it during an active storm week. Give them test accounts.
- Key questions:
  - "Would you drive to this hot zone based on what you see here?"
  - "Is anything missing that would make this more useful?"
  - "How does this compare to how you currently find storm leads?"
- Collect their feedback (both in-app ratings and verbal).

### What to Look For

| Signal | Good Sign | Bad Sign |
|--------|-----------|----------|
| Hot zone accuracy | Roofer finds visible damage, interested homeowners | Zone is in an area with no damage, or all new roofs |
| Skip zone accuracy | Low-value area, rentals, no damage | Actually had great leads that the algorithm missed |
| Timing | Zones appear within 30 min of storm | Zones take hours or miss storms entirely |
| Geography | Boundaries cover 3-5 neighborhoods | Boundaries cover entire city or single block |
| Census data relevance | Homeownership/age predictions match reality | High-ownership zone is actually all rentals |
| Competitive insight | Roofer is first to an area | 10 other roofers are already there |

### Decision Gate

After 2 weeks of field validation:

**If scoring works** (hot zones correlate with real opportunity):
→ Proceed to Phase 4: alerts, feedback loop, monetization. The algorithm is the hard part — everything else is engineering.

**If scoring is directionally right but needs tuning:**
→ Adjust weights, normalization curves, or scoring thresholds. Run another 2-week validation cycle. Don't add features on top of a broken algorithm.

**If scoring is fundamentally off:**
→ Investigate root cause. Is it data quality (NWS/SPC not granular enough)? Is it the census proxy (homeownership doesn't predict opportunity)? Is it geographic (H3 hex too coarse/fine)? Fix the foundation before building upward.

---

## What Comes After POC

Once field validation passes, the full product roadmap re-engages. Here's the priority order, each unlocked by the previous:

### Phase 4: Alerts (Weeks 9-10)
Add AWS SES (email) and SNS (SMS) to push alerts when new hot zones appear in a roofer's service area. This turns the product from "check it manually" to "it tells you." Requires SES production access (request during Phase 3 so it's ready).

### Phase 5: Feedback Loop (Weeks 11-12)
Replace the simple `zone_feedback` table with full `canvass_sessions` (doors knocked, contracts signed, revenue). Add GPS zone detection. Add offline support via service worker. This is the data collection infrastructure for model improvement.

### Phase 6: Intelligence (Weeks 13-14)
Nightly calibration job comparing predicted vs actual conversion. Admin dashboard for weight tuning. Roofer analytics page. This is the compounding moat — the product gets better with every user.

### Phase 7: Monetization (Week 15+)
Stripe integration. Free tier (email alerts, 1 state) vs Pro tier ($49-99/mo, SMS, multi-state, analytics). Landing page. Marketing.

Each phase is a clean 2-week sprint. Each one only makes sense if the previous phase validated. This plan gets you to the first decision gate in 6 weeks for under $50 total spend.

---

## API Endpoints Reference (POC)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check for App Runner |
| POST | `/api/v1/auth/register` | Create roofer account + service area |
| POST | `/api/v1/auth/login` | JWT token issuance (72hr expiry) |
| GET | `/api/v1/zones` | List active zones in service area. Params: min_score, sort_by, page |
| GET | `/api/v1/zones/{id}` | Zone detail with live-decayed score + sub-scores + census data |
| GET | `/api/v1/zones/geojson` | GeoJSON FeatureCollection for map. Params: bbox, min_score |
| POST | `/api/v1/zones/{id}/feedback` | Submit rating (1-5) + visible_damage + notes |
| GET | `/api/v1/zones/{id}/feedback` | List feedback for a zone |

**8 endpoints. That's the entire POC API.**

---

## Database Schema Reference (POC)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `storm_events` | Raw ingested storm data | location (POINT), hail_diameter, wind_speed, radar_confidence, source, event_timestamp, warning_polygon, processed |
| `census_tracts` | Pre-loaded demographics | geometry (MULTIPOLYGON), geoid, owner_occupied_pct, median_year_built, median_home_value |
| `lead_zones` | **Core product output** | boundary (POLYGON), composite_score, score_band, damage_prob, lead_quality, density_bonus, time_decay, max_hail_diameter, score_weights_snapshot, model_version, expires_at |
| `roofer_accounts` | User accounts | email, password_hash, service_area (POLYGON) |
| `zone_feedback` | Simple field validation data | lead_zone_id (FK), rating (1-5), visible_damage, notes, zone_score_at_feedback |

**5 tables. 8 endpoints. 3 accounts. ~$7/mo. 6 weeks to field validation.**

---

## Scoring Formula Reference

```
LEAD_SCORE = (DAMAGE_PROB × 0.50 + LEAD_QUALITY × 0.30 + DENSITY_BONUS × 0.20) × TIME_DECAY

Where:
  DAMAGE_PROB  = f(hail_diameter, wind_speed, radar_confidence, corroboration)
  LEAD_QUALITY = f(homeownership_pct, median_year_built, median_home_value)
  DENSITY_BONUS = f(housing_units_per_km², suburban_sweet_spot)
  TIME_DECAY   = e^(-0.25 × hours_since_storm / 24)

Score bands:
  80-100  HOT   🔴  — High damage + high-quality leads. Go now.
  60-79   WARM  🟠  — Moderate opportunity. Worth a drive if nearby.
  40-59   COOL  🟡  — Low confidence. Check if nothing better available.
  0-39    SKIP  ⚫  — Not worth the trip.
```

---

## Key Architecture Decisions (POC)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **POC-first approach** | Validate scoring before building features | Alerts, feedback loops, and payments are worthless if the algorithm doesn't work. |
| **5 tables, not 7** | Drop canvass_sessions, model_calibration, alert_log | Not needed until post-POC phases. Simple zone_feedback covers field validation. |
| **8 endpoints, not 20+** | Auth, zones, feedback only | No alert, analytics, admin, or payment endpoints. Add after validation. |
| **No custom domain** | Use default AWS URLs | Saves Route 53 cost + DNS config. Add `stormleads.com` when ready for real users. |
| **No SES/SNS** | No email or SMS | Zero alerting infrastructure. Roofers check the app manually. |
| **No service worker** | No offline support | Roofers have cell service in suburbs. Defer until feedback proves it's needed. |
| **No Stripe** | No payment processing | Nothing to charge for until the product proves value. |
| **Simple feedback** | Rating + notes, not full canvass tracking | Enough to validate scoring accuracy. Full feedback loop comes in Phase 5. |
| **Neon over RDS** | Neon Launch $5/mo | No free tier cliff. PostGIS + PITR included. |
| **Upstash over ElastiCache** | Upstash free tier | $0 vs $13/mo. HTTP-based, zero config. |
| **App Runner over ECS** | Simplest AWS compute | Git-push deploys, no VPC, no task definitions. |
| **APScheduler in-process** | Background jobs in same container | No second service. Split later if needed. |
