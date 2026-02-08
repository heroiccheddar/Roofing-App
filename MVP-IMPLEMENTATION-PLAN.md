# MVP Implementation Plan — StormLeads

**Stack:** Recommended MVP · $15–20/mo · FastAPI + Neon PostGIS + Railway
**Timeline:** 12 Weeks · Solo Developer Build

---

## Table of Contents

1. [Stack & Accounts Setup](#1-stack--accounts-setup)
2. [Phase 1: Foundation](#phase-1-foundation--weeks-12) — Weeks 1–2 · Database + data ingestion pipeline
3. [Phase 2: Brain](#phase-2-brain--weeks-34) — Weeks 3–4 · Scoring engine + lead zone generation
4. [Phase 3: Surface](#phase-3-surface--weeks-56) — Weeks 5–6 · API + React map dashboard
5. [Phase 4: Reach](#phase-4-reach--weeks-78) — Weeks 7–8 · Alerts (WebSocket + SMS + email) + auth
6. [Phase 5: Loop](#phase-5-loop--weeks-910) — Weeks 9–10 · Feedback PWA + canvass tracking
7. [Phase 6: Intelligence](#phase-6-intelligence--weeks-1112) — Weeks 11–12 · Calibration engine + admin tooling
8. [Launch Checklist](#launch-checklist)
9. [Deployment Pipeline](#deployment-pipeline)
10. [Timeline Summary](#timeline-summary)

---

## 1. Stack & Accounts Setup

### Accounts to Create (Do This First)

Sign up for all services before writing code. Most require only email verification. Total time: ~30 minutes.

| Service | Plan | Cost | What You Get |
|---------|------|------|--------------|
| **Neon** | Free → Launch | $0 → $5/mo | PostgreSQL 16 + PostGIS. Start free, upgrade to Launch when deploying to Railway. |
| **Railway** | Hobby | $5/mo | Container hosting with $5 usage credit. Git push deploys. |
| **Upstash** | Free | $0 | Serverless Redis. 256MB / 500K cmds/mo. HTTP-based. |
| **Cloudflare** | Free | $0 | Pages (frontend hosting) + Registrar (domain) + DNS. |
| **Mapbox** | Free | $0 | GL JS map rendering. 50K loads/mo. Get access token for frontend. |
| **Resend** | Free | $0 | Transactional email. 3K/mo. Domain verification required. |
| **Twilio** | Pay-as-you-go | ~$2-3/mo | SMS alerts. Buy one phone number ($1.15/mo) + per-message. |
| **Sentry** | Developer (free) | $0 | Error tracking. 5K events/mo. |
| **BetterStack** | Free | $0 | Uptime monitoring. 5 monitors, email alerts. |
| **GitHub** | Free | $0 | Monorepo. Railway + Cloudflare Pages both deploy from GitHub. |
| **Census API** | Free | $0 | API key for ACS data (demographics). Request at api.census.gov. |

### Repository Structure — Monorepo

Single GitHub repo. Railway deploys `/backend`, Cloudflare Pages deploys `/frontend`.

```
stormleads/
├── backend/                        # → Railway deploys this
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entry + APScheduler init
│   │   ├── config.py               # Pydantic Settings (env vars)
│   │   ├── database.py             # SQLAlchemy async engine + session
│   │   │
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── storm_event.py
│   │   │   ├── census_tract.py
│   │   │   ├── lead_zone.py
│   │   │   ├── canvass_session.py
│   │   │   ├── model_calibration.py
│   │   │   ├── roofer_account.py
│   │   │   └── alert_log.py
│   │   │
│   │   ├── ingestion/              # Data pipeline modules
│   │   │   ├── nws_poller.py       # 5-min NWS alerts poll
│   │   │   ├── spc_scraper.py      # 6-hr SPC storm reports CSV
│   │   │   ├── swdi_fetcher.py     # On-demand SWDI radar signatures
│   │   │   └── census_loader.py    # One-time ACS data load
│   │   │
│   │   ├── scoring/                # Core product logic
│   │   │   ├── engine.py           # Scoring algorithm (weights + formula)
│   │   │   ├── weights.py          # Weight definitions + versioning
│   │   │   ├── spatial.py          # PostGIS helpers (clustering, intersects)
│   │   │   └── decay.py            # Time decay function
│   │   │
│   │   ├── api/                    # FastAPI route modules
│   │   │   ├── auth.py             # Register, login, JWT
│   │   │   ├── zones.py            # Lead zone endpoints
│   │   │   ├── feedback.py         # Canvass session CRUD
│   │   │   ├── alerts.py           # WebSocket + alert history
│   │   │   ├── account.py          # Service area, preferences
│   │   │   └── internal.py         # Admin: calibration, model deploy
│   │   │
│   │   ├── scheduler/              # APScheduler job definitions
│   │   │   └── jobs.py             # Cron schedule for all background tasks
│   │   │
│   │   └── services/               # External integrations
│   │       ├── twilio_sms.py
│   │       ├── resend_email.py
│   │       └── redis_cache.py      # Upstash HTTP client
│   │
│   ├── alembic/                    # Database migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile                  # Railway uses this
│   ├── railway.toml                # Railway config
│   └── pytest.ini
│
├── frontend/                       # → Cloudflare Pages deploys this
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── MapView.tsx         # Mapbox GL JS wrapper
│   │   │   ├── ZonePanel.tsx       # Zone detail sidebar
│   │   │   ├── AlertFeed.tsx       # Real-time alert list
│   │   │   ├── FeedbackForm.tsx    # Canvass session submission
│   │   │   └── ScoreGauge.tsx      # Visual score display
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # Alert stream connection
│   │   │   └── useZones.ts         # Zone data fetching
│   │   ├── stores/
│   │   │   └── appStore.ts         # Zustand state
│   │   └── pages/
│   │       ├── Dashboard.tsx
│   │       ├── Login.tsx
│   │       ├── FeedbackHistory.tsx
│   │       └── Settings.tsx
│   ├── public/
│   │   ├── manifest.json           # PWA manifest
│   │   └── sw.js                   # Service worker (offline feedback)
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── scripts/                        # One-time setup + utilities
│   ├── load_census_data.py         # Bulk load ACS into census_tracts
│   ├── backfill_historical.py      # Load Storm Events DB for validation
│   └── seed_test_data.py           # Dev fixtures
│
├── .github/workflows/              # CI (optional, Railway has auto-deploy)
├── .env.example
└── README.md
```

### Environment Variables

All secrets live in Railway's env vars (backend) and Cloudflare Pages env vars (frontend). Never committed to repo. Create a `.env.example` as reference.

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

# ── Twilio ──
TWILIO_ACCOUNT_SID=ACxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxx
TWILIO_FROM_NUMBER=+1xxxxxxxxxx

# ── Resend ──
RESEND_API_KEY=re_xxxxxxxxxx
RESEND_FROM_EMAIL=alerts@stormleads.com

# ── Census ──
CENSUS_API_KEY=xxxxxxxxxx

# ── Sentry ──
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx

# ── Frontend (Cloudflare Pages env) ──
VITE_API_URL=https://api.stormleads.com
VITE_WS_URL=wss://api.stormleads.com
VITE_MAPBOX_TOKEN=pk.xxxxxxxxxx
```

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
geoalchemy2==0.15.*              # PostGIS column types + spatial functions
alembic==1.14.*

# ── Scheduling (replaces Celery for MVP) ──
apscheduler==3.10.*

# ── Spatial + Data ──
geopandas==1.0.*
h3==3.7.*                        # Uber H3 hexagonal indexing
shapely==2.0.*
httpx==0.28.*                    # Async HTTP client for NWS/SWDI/SPC

# ── Auth ──
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*

# ── External Services ──
twilio==9.*
resend==2.*
upstash-redis==1.*               # HTTP-based Redis client

# ── Monitoring ──
sentry-sdk[fastapi]==2.*

# ── Dev/Test ──
pytest==8.*
pytest-asyncio==0.24.*
```

---

## Phase 1: Foundation — Weeks 1–2

**Goal:** Storm events flowing into PostGIS and census demographics pre-loaded. All spatial queries verified working.
**Running cost:** $0 (Neon free tier, local dev).

### Week 1 — Database + Census

- [ ] **Create Neon project** with PostGIS extension enabled. Region: `us-east-2` (closest to NOAA servers). Enable `postgis` and `h3-pg` extensions.
- [ ] **Define SQLAlchemy models** for all 7 tables using GeoAlchemy2 for geometry columns. Start with `storm_events` and `census_tracts`.
- [ ] **Set up Alembic** for migrations. Initial migration creates schema with GIST indexes on all geometry columns, BRIN on timestamps.
- [ ] **Build census_loader.py** — fetch ACS 5-Year data (B25003 ownership, B25035 year built, B25077 home value, B01003 population) at tract level for target states. Use Census API + TIGER/Line shapefiles for tract boundaries.
- [ ] **Load census data** for 3-5 initial states (TX, OK, KS, CO, NE — the hail corridor). ~15K tracts. Verify spatial queries: `ST_Contains(tract.geometry, point)`.

### Week 2 — Ingestion Pipeline

- [ ] **Build nws_poller.py** — async httpx client polling `api.weather.gov/alerts/active?event=Severe Thunderstorm Warning` every 5 minutes. Parse warning polygon, extract hail/wind parameters, upsert into `storm_events`.
- [ ] **Build spc_scraper.py** — parse SPC filtered CSV (`spc.noaa.gov/climo/reports/today_hail.csv`). Extract lat/lon, hail size, time. Run every 6 hours.
- [ ] **Build swdi_fetcher.py** — query NCEI SWDI API for MESH (Maximum Expected Size of Hail) signatures when NWS warning triggers. This is the highest-fidelity hail data. Corroborate SPC reports with radar-derived probability.
- [ ] **Wire APScheduler** into FastAPI startup. Schedule NWS poll (5min), SPC scrape (6hr). SWDI runs on-demand when new NWS warning arrives in watched states.
- [ ] **Deduplication logic** — SPC, SWDI, and NWS may all report the same hail event. Match by timestamp window (±30 min) and spatial proximity (`ST_DWithin` 15km). Link corroborated events for higher confidence scoring.
- [ ] **Backfill validation** — load 30 days of Storm Events DB historical data. Verify ingestion pipeline produces events that match known storm outcomes.

### Phase 1 Milestone

```sql
SELECT * FROM storm_events
WHERE ST_DWithin(location, ST_MakePoint(-97.5, 35.5)::geography, 50000);
```
Returns real storm events with hail size and SWDI probability scores. Census tracts loaded with ownership/age/value demographics.

---

## Phase 2: Brain — Weeks 3–4

**Goal:** Storm events automatically scored and aggregated into lead zones with composite scores. The core product logic works end-to-end.
**Running cost:** $0 (still local + Neon free).

### Week 3 — Scoring Algorithm

- [ ] **Implement weights.py** — define `ModelVersion` dataclass with version string, damage weights (`hail_diameter: 0.40, wind_speed: 0.25, radar_confidence: 0.20, report_corroboration: 0.15`), lead quality weights, density weights. Hardcode v1.0.0. Include `to_snapshot()` for JSON serialization to `score_weights_snapshot` column.
- [ ] **Implement spatial.py** — PostGIS helper functions: find census tracts intersecting an event bounding box, cluster events using DBSCAN on coordinates (via H3 resolution 7 hex aggregation), calculate housing density from tract geometry area.
- [ ] **Implement decay.py** — time decay function `e^(-0.25 × hours_since_storm / 24)`. Pure function, takes event timestamp, returns multiplier 0.0–1.0. At 72 hours: ~0.50. At 168 hours (7 days): ~0.17.
- [ ] **Implement engine.py** — the composite scoring pipeline:
  1. Query new storm events not yet scored
  2. Spatial join events → census tracts via `ST_Contains`
  3. Aggregate events per H3 hex cell → `damage_prob` subscore
  4. Pull tract demographics → `lead_quality` subscore
  5. Compute cluster density + residential density → `density_bonus`
  6. Composite: `(damage × 0.50 + quality × 0.30 + density × 0.20) × decay`
  7. Insert into `lead_zones` with frozen weight snapshot + model version

### Scoring Formula

```
LEAD_SCORE = (DAMAGE_PROB × 0.50 + LEAD_QUALITY × 0.30 + DENSITY_BONUS × 0.20) × TIME_DECAY
```

**Score bands:** 80–100 hot, 60–79 warm, 40–59 cool, 0–39 skip.

### Week 4 — Lead Zone Generation + Validation

- [ ] **Zone generation trigger** — APScheduler job: after each ingestion cycle, run scoring engine on any unprocessed events. Generate/update lead_zones. Set `expires_at` to 14 days from storm date.
- [ ] **Zone boundary generation** — for each H3 hex cluster, compute convex hull of underlying census tract geometries. Store as `lead_zones.boundary`. Store H3 index and centroid for quick lookups.
- [ ] **Score band classification** — tag zones: hot (80–100), warm (60–79), cool (40–59), skip (0–39). This feeds the frontend color coding and alert thresholds.
- [ ] **Historical validation** — run scoring engine against 30 days of backfilled Storm Events data. Manually inspect: do the highest-scored zones correlate with known severe damage areas? Are there obviously wrong zones? Tune thresholds.
- [ ] **Zone refresh logic** — when new events arrive in an area with existing active zones, recalculate (don't duplicate). Update event_count, max_hail_diameter, re-run scoring. The zone is a living entity for 14 days.
- [ ] **Unit tests** for scoring formula, decay curve, weight snapshot serialization/deserialization, H3 hex aggregation, and zone expiry cleanup.

### Phase 2 Milestone

Scoring engine generates lead_zones from storm events. A 2.5" hail event in a 1970s-era suburban neighborhood with 85% homeownership scores 80+ (hot). A 1.0" hail event in a new-construction rental area scores 30 (skip). Score weights snapshot preserved on every zone.

---

## Phase 3: Surface — Weeks 5–6

**Goal:** A roofer can log in, see scored zones on a map, click for details. First deployment to Railway + Cloudflare Pages.
**Running cost:** ~$10/mo (Neon Launch $5 + Railway Hobby $5).

### Week 5 — REST API + Deploy Backend

- [ ] **Auth endpoints** — `POST /auth/register` (email, password, company name, service area as lat/lon/radius), `POST /auth/login` (returns JWT). bcrypt password hashing. Service area stored as `ST_Buffer(point, radius)` polygon.
- [ ] **Zone endpoints**:
  - `GET /zones` — paginated, filtered by service area intersection, min_score, sorted by composite_score desc
  - `GET /zones/{id}` — full detail with decay-adjusted score recalculated on read
  - `GET /zones/geojson` — GeoJSON FeatureCollection for map layer, params: bbox, min_score
  - `GET /zones/{id}/events` — raw storm events that contributed to this zone
  - `GET /zones/{id}/heatmap-tile/{z}/{x}/{y}` — vector tile endpoint for Mapbox GL rendering at scale
- [ ] **Redis caching layer** — cache GeoJSON responses in Upstash (TTL: 5 minutes). Cache zone detail (TTL: 1 minute). Invalidate on new scoring run.
- [ ] **Deploy to Railway** — connect GitHub repo, set root directory to `/backend`, configure env vars in Railway dashboard. Verify Dockerfile builds and `uvicorn` starts. Custom domain: `api.stormleads.com`.
- [ ] **Upgrade Neon to Launch** — $5/mo minimum. Configure connection pooling. Set `?sslmode=require` in DATABASE_URL. Railway → Neon connection verified.

### Week 6 — React Map Dashboard

- [ ] **Scaffold React + Vite + TypeScript**. Install `mapbox-gl`, `zustand`, `react-query` (TanStack Query for API caching).
- [ ] **MapView component** — Mapbox GL JS with GeoJSON source layer. Color-code zones: hot=red, warm=orange, cool=yellow, skip=gray. Clickable polygons. Zoom to roofer's service area on load.
- [ ] **ZonePanel component** — sidebar/drawer showing zone detail on click: composite score (big number), sub-scores (damage, quality, density), hail diameter, hours since storm, event count, time decay indicator. "Navigate" button opens Google Maps directions to zone centroid.
- [ ] **Dashboard page** — map takes 70% width, zone list panel on right. Filter controls: min score slider, hail size filter, sort options. Active zone count badge.
- [ ] **Login page** — simple email/password form. Store JWT in memory (not localStorage — PWA security). Redirect to dashboard on success.
- [ ] **Deploy to Cloudflare Pages** — connect GitHub, set build command `npm run build`, root `/frontend`, output `dist`. Custom domain: `app.stormleads.com`. Configure CORS on Railway backend to allow Cloudflare domain.
- [ ] **PWA manifest** — add `manifest.json` with app name, icons, theme color. Roofers can "Add to Home Screen" for app-like experience.

### Phase 3 Milestone

Live at `app.stormleads.com`. A roofer can register, log in, see a map with scored zones from real storm data, click zones for detail, and use score/hail filters. Backend polling NWS every 5 minutes and auto-generating new zones. **This is a demoable product.**

---

## Phase 4: Reach — Weeks 7–8

**Goal:** Roofers receive proactive alerts (SMS, email, push) when new high-scoring zones appear in their service area.
**Running cost:** ~$13–18/mo (add Twilio ~$2-3).

### Week 7 — Alert Engine + SMS/Email

- [ ] **Alert preferences endpoint** — `PUT /account/alert-preferences`. JSONB payload:
  ```json
  {
    "min_score": 70,
    "min_hail_inches": 1.5,
    "channels": ["sms", "email"],
    "quiet_hours": { "start": "22:00", "end": "07:00" }
  }
  ```
- [ ] **Alert matching logic** — after scoring engine generates/updates a zone, query all roofer_accounts where `ST_Intersects(account.service_area, zone.boundary)` AND `zone.composite_score >= account.alert_prefs.min_score`. Respect quiet hours using account timezone.
- [ ] **SMS alert via Twilio** — short, actionable message:
  ```
  🔴 HOT ZONE (Score: 87) — 2.5" hail in Plano, TX, 6 hrs ago.
  1970s homes, 82% owner-occupied.
  Open: app.stormleads.com/zone/abc123
  ```
  Log to `alert_log` with `sent_at`.
- [ ] **Email alert via Resend** — HTML email with mini-map image (Mapbox Static Images API — free tier covers this), score breakdown, and CTA link. Log to `alert_log`.
- [ ] **Rate limiting** — max 5 SMS per roofer per day. Max 10 email per roofer per day. Prevents alert fatigue during active storm sequences.

### Week 8 — WebSocket + Alert UX

- [ ] **WebSocket endpoint** — `WS /alerts/stream`. On connect, authenticate via JWT in query param. Subscribe roofer to their service area. When scoring engine creates a matching zone, push to connected clients. FastAPI native WebSocket support (no external broker needed at MVP scale).
- [ ] **AlertFeed component** — real-time feed on dashboard. New zones animate in. Click to zoom map to zone. Badge count of unread alerts. Sound notification option.
- [ ] **Alert history endpoint** — `GET /alerts/history`. Shows past alerts with status: sent, opened (track via email open pixel + link click tracking), acted_on (navigated to zone).
- [ ] **Alert tracking** — update `alert_log.opened_at` when roofer clicks email link or views zone from alert. Update `acted_on` when roofer opens zone detail from an alert notification. This is feedback loop data — measures which score thresholds drive action.
- [ ] **SMS as paid feature gate** — free tier gets email-only alerts. Pro tier ($X/mo) gets SMS. This ensures SMS costs are always covered by revenue. Implement simple `subscription_tier` check before Twilio send.

### Phase 4 Milestone

A roofer with SMS enabled receives a text within minutes of a high-scoring zone appearing in their service area. Dashboard shows real-time alert feed via WebSocket. Alert engagement is tracked for feedback loop. **This is a sellable product.**

---

## Phase 5: Loop — Weeks 9–10

**Goal:** Roofers can submit field outcomes (star rating, door count, damage observations, contracts). GPS auto-detects which zone they're in.
**Running cost:** unchanged ~$15-18/mo (feedback adds zero infra cost).

### Week 9 — Feedback API + Progressive Form

- [ ] **Feedback endpoints**:
  - `POST /zones/{id}/feedback` — accepts tiered payload:
    - **Tier 1 (required):** `{ rating: 4 }`
    - **Tier 2 (encouraged):** `{ rating: 4, doors_knocked: 40, doors_answered: 15, visible_damage_count: 8, homeowner_interested: 5 }`
    - **Tier 3 (incentivized):** adds `inspections_scheduled, contracts_signed, estimated_revenue, roof_type, competitor_presence`
  - `PUT /feedback/{session_id}` — update existing session. Critical: contracts often close days after canvassing. Roofer should be able to add `contracts_signed` and `estimated_revenue` after the fact.
  - `GET /feedback/my-history` — roofer's own canvass history with conversion rates.
- [ ] **FeedbackForm component** — progressive disclosure UI:
  1. Star rating (1-5) appears first — tap and done in 2 seconds
  2. "Add details?" expands to 4 number fields (doors/damage/interested/inspections)
  3. "Full report" expands to roof type selector, competitor presence dropdown, revenue field
  4. Submit at any tier — partial data is still valuable
- [ ] **Contextual prompt** — when roofer opens zone detail, show subtle "Been here? Leave feedback" prompt. Pre-fill zone ID. If GPS available, auto-detect nearest zone.

### Week 10 — Offline Support + GPS + History

- [ ] **Service worker** for offline feedback submission. Roofer in storm-damaged area may have poor connectivity. Queue feedback in IndexedDB, sync when online. Show "pending sync" indicator.
- [ ] **GPS zone detection** — use Geolocation API to get roofer's position. Query `GET /zones?near_lat=X&near_lon=Y&radius=5km` to find which zone they're in. Auto-suggest feedback for that zone. No manual zone selection needed.
- [ ] **Feedback history page** — `GET /feedback/my-history`. Show all canvass sessions with zone score at time of canvass, outcome data, and an editable link to update contracts/revenue later.
- [ ] **24-hour feedback nudge** — APScheduler job: 24 hours after a roofer views a zone detail (tracked in `alert_log.opened_at`), if no feedback exists for that zone+roofer, trigger a push notification or email: "Did you canvass [Zone Name]? Quick feedback improves your scores."
- [ ] **Gamification seed** — track feedback count per roofer. Display "Feedback accuracy score" (how closely their star ratings correlate with their own conversion rates). Top contributors badge. This is a hook for Tier 3 reporting — show roofers that detailed feedback unlocks better recommendations.

### Phase 5 Milestone

A roofer canvasses a zone, opens the PWA, taps 4 stars and enters "40 doors / 8 damage / 5 interested" in under 30 seconds. Data flows into canvass_sessions. Works offline. GPS auto-links to the right zone. **The feedback loop is open.**

---

## Phase 6: Intelligence — Weeks 11–12

**Goal:** Nightly batch job compares predictions to outcomes. Internal dashboard shows where the model is accurate vs. biased. Weight adjustment pipeline ready.
**Running cost:** unchanged ~$15-18/mo.

### Week 11 — Calibration Engine

- [ ] **Nightly calibration job** — APScheduler daily at 2 AM UTC. Join `lead_zones` ↔ `canvass_sessions` on `lead_zone_id`. Group by: model_version, region (state), hail_size_bucket (1.0–1.49, 1.5–1.99, 2.0–2.74, 2.75+). Calculate:
  - `avg_predicted_conversion` (from `lead_zones.predicted_conversion_rate`)
  - `avg_actual_conversion` (from `canvass_sessions.contracts_signed / doors_knocked`)
  - `prediction_bias` = predicted − actual
  - `avg_competitor_saturation` (from `canvass_sessions.competitor_presence`)
- [ ] **Insert into model_calibration** table with period and computed_at timestamp.
- [ ] **Bias alert** — when `abs(prediction_bias) > 0.02` for any region/hail bucket, log a warning. This is the trigger for weight adjustment. At MVP, this flags for manual review — not auto-adjusted.
- [ ] **Zone-level predicted conversion** — extend scoring engine to output `predicted_conversion_rate` on each lead_zone. For v1.0.0, use a simple lookup table: score 80-100 → 12% predicted conversion, 60-79 → 7%, 40-59 → 3%, 0-39 → 1%. Calibration data will refine this over time.

### Week 12 — Admin Dashboard + Roofer Analytics

- [ ] **Internal admin endpoints** (protected, admin account only):
  - `GET /internal/calibration/report` — predicted vs actual by region, hail bucket, model version. The core truth table.
  - `POST /internal/model/propose-weights` — given calibration data, compute suggested weight adjustments. Display diff: "hail_diameter weight: 0.40 → 0.43 (reason: 2"+ hail underestimated by 4% in TX)"
  - `POST /internal/model/deploy` — bump model_version, store new weights. All future zones use new weights. Old zones retain their snapshot.
- [ ] **Roofer analytics endpoint** — `GET /analytics/my-performance`. Personal stats: total zones canvassed, avg conversion rate, best performing hail size range, best performing score band, ROI per trip (revenue / trips). This is the feature that makes roofers want to submit feedback — it shows them their own data getting better.
- [ ] **Admin calibration view** — simple table in the React app (admin-only route). Shows model_calibration rows: hail bucket × region × bias × sample size. Color-code: green (bias < 0.01), yellow (0.01-0.02), red (> 0.02). This is the operational dashboard.
- [ ] **Roofer performance view** — page in the dashboard showing personal analytics. Charts: conversion rate by score band, conversion rate over time, revenue per trip trend.
- [ ] **Zone cleanup job** — APScheduler daily: delete or archive lead_zones past `expires_at` (14 days). Keep canvass_sessions permanently (training data). Keep model_calibration permanently.

### Phase 6 Milestone

After 2 weeks of real usage, the calibration table shows predicted vs. actual conversion rates by hail bucket and region. You can see where the model is accurate and where it's biased. Weight adjustment pipeline is ready for your first model version bump. Roofers can see their own performance analytics. **The feedback loop is closed.**

---

## Launch Checklist

### Infrastructure

- [ ] Neon Launch plan active — not free tier (avoid cold start / auto-pause issues)
- [ ] Railway Hobby plan active — custom domain `api.stormleads.com` with SSL
- [ ] Cloudflare Pages — custom domain `app.stormleads.com` with SSL
- [ ] Twilio phone number purchased — verified for SMS sending
- [ ] Resend domain verified — emails come from `@stormleads.com` not `@resend.dev`
- [ ] Sentry + BetterStack monitoring active — uptime alerts to your phone
- [ ] Database backups — Neon Launch includes daily backups with 24hr PITR. Verify it works.

### Product

- [ ] Ingestion running 24/7 for at least 1 week with no errors. NWS poll (5 min), SPC scrape (6 hr), SWDI on-trigger — all verified.
- [ ] Scoring engine validated against known storm events. Scores intuitively make sense when spot-checked by hand.
- [ ] SMS alerts delivered — test with your own phone. Verify delivery latency is under 5 minutes from storm event to SMS received.
- [ ] Feedback form works offline — airplane mode → submit → reconnect → data syncs.
- [ ] Service area works correctly — roofer only sees zones within their defined radius. Alert matching respects service area boundary.
- [ ] Zone expiry cleanup runs daily — old zones don't accumulate forever.
- [ ] Rate limits on auth endpoints — prevent brute-force login attempts.

### Business

- [ ] Pricing defined — free tier (email alerts, 1 state, basic map) vs. pro tier (SMS, multi-state, full analytics, priority alerts). Recommend starting at $49-99/mo for pro.
- [ ] Payment integration — Stripe Checkout session for pro tier upgrade. Don't overbuild — a Stripe link that sets `subscription_tier = 'pro'` on webhook is enough for MVP.
- [ ] Terms of service + privacy policy — basic pages. You're collecting location data and business data — need explicit consent.
- [ ] Landing page — on `stormleads.com`. Value prop, screenshot of map, pricing, signup CTA. Can be a simple Cloudflare Pages static site.

### What Can Wait (Do NOT Build for Launch)

- **NEXRAD raw radar processing** — SWDI gives you radar-derived hail data already. Raw NEXRAD is Phase 2.
- **ML model retraining** — manual weight tuning via admin panel is fine until you have 500+ feedback sessions.
- **GPS track upload** — nice-to-have. Manual zone selection + GPS auto-detect covers 90% of the UX.
- **Multi-language support** — English only at launch.
- **Mobile native app** — PWA is sufficient. Native app only if roofer adoption proves PWA is a friction point.
- **Team accounts** — single roofer accounts first. Multi-seat company accounts come with paying enterprise customers.

---

## Deployment Pipeline

### Git-Push Deploys (No CI/CD to Build)

Both Railway and Cloudflare Pages deploy automatically on push to `main`:

```bash
# Your entire deploy pipeline:
git add .
git commit -m "feat: add alert matching logic"
git push origin main

# Railway auto-detects /backend Dockerfile change → rebuilds → deploys
# Cloudflare Pages auto-detects /frontend change → npm build → deploys
# If only backend changed, only Railway deploys (and vice versa)

# Database migrations (run manually after deploy):
railway run alembic upgrade head
```

**Railway config** (`railway.toml`): set root directory to `/backend`, start command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health check on `/health`.

**Cloudflare Pages config**: build command `npm run build`, root directory `/frontend`, output directory `dist`. Add `_redirects` file with `/* /index.html 200` for SPA routing.

**Database migrations**: Alembic runs from Railway CLI (`railway run`) or via a one-off Railway service. Not automated — review and run manually since schema changes need care.

---

## Timeline Summary

| Phase | Weeks | What Ships | Running Cost | Key Risk |
|-------|-------|-----------|-------------|----------|
| **1. Foundation** | 1–2 | PostGIS schema + census data + storm ingestion pipeline | $0 | SWDI API availability / rate limits. Fallback: heavier reliance on SPC reports. |
| **2. Brain** | 3–4 | Scoring engine + lead zone generation with frozen weights | $0 | Scoring accuracy without ground truth. Mitigate: validate against Storm Events DB known outcomes. |
| **3. Surface** | 5–6 | REST API + React map dashboard + first deployment | ~$10 | Mapbox GL JS learning curve for custom GeoJSON styling. Mitigate: Mapbox examples are excellent. |
| **4. Reach** | 7–8 | SMS/email/WebSocket alerts + alert preferences | ~$13-18 | Twilio deliverability to roofer cell phones. Mitigate: test with multiple carriers early. |
| **5. Loop** | 9–10 | Feedback form + offline support + GPS zone detection | ~$15-18 | Roofer adoption of feedback. Mitigate: make Tier 1 (star rating) absurdly easy. Tie analytics access to feedback submission. |
| **6. Intelligence** | 11–12 | Calibration engine + admin dashboard + roofer analytics | ~$15-18 | Insufficient feedback data for meaningful calibration. Mitigate: expected — calibration becomes useful after 200+ sessions. The infrastructure is ready when data arrives. |

---

## Database Schema Reference

Seven core tables:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `storm_events` | Raw ingested storm data | location (POINT), hail_diameter, wind_speed, source, event_timestamp, warning_polygon |
| `census_tracts` | Pre-loaded demographics | geometry (MULTIPOLYGON), geoid, owner_occupied_pct, median_year_built, median_home_value |
| `lead_zones` | **Core product output** | boundary (POLYGON), composite_score, damage_prob, lead_quality, density_bonus, predicted_conversion_rate, score_weights_snapshot, model_version, expires_at |
| `canvass_sessions` | **Feedback loop core** | lead_zone_id (FK), roofer_account_id (FK), rating, doors_knocked, visible_damage_count, contracts_signed, estimated_revenue |
| `model_calibration` | **Feedback loop analytics** | model_version, region, hail_size_bucket, avg_predicted_conversion, avg_actual_conversion, prediction_bias, sample_size |
| `roofer_accounts` | User accounts | service_area (POLYGON), alert_preferences (JSONB), subscription_tier |
| `alert_log` | Notification tracking | roofer_account_id (FK), lead_zone_id (FK), channel, sent_at, opened_at, acted_on |

**Key indexes:** GIST on all geometry columns, BRIN on `storm_events.event_timestamp` and `lead_zones.created_at`, composite on `lead_zones(composite_score, expires_at)`.

---

## API Endpoints Reference

### Authentication & Account
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create roofer account + define service area |
| POST | `/api/v1/auth/login` | JWT token issuance |
| PUT | `/api/v1/account/service-area` | Update service polygon or radius |
| PUT | `/api/v1/account/alert-preferences` | Set min score, hail thresholds, notification channels |

### Lead Zones — Core Product
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/zones` | List active zones in roofer's service area. Params: min_score, hail_min, sort_by, page |
| GET | `/api/v1/zones/{id}` | Zone detail: all sub-scores, contributing events, census overlay, decay-adjusted score |
| GET | `/api/v1/zones/{id}/events` | Raw storm events that contributed to this zone |
| GET | `/api/v1/zones/geojson` | GeoJSON FeatureCollection for map layer. Params: bbox, min_score |
| GET | `/api/v1/zones/{id}/heatmap-tile/{z}/{x}/{y}` | Vector tile endpoint for Mapbox GL rendering at scale |

### Real-Time Alerts
| Method | Path | Description |
|--------|------|-------------|
| WS | `/api/v1/alerts/stream` | WebSocket: push new zones matching roofer's preferences in real-time |
| GET | `/api/v1/alerts/history` | Recent alert log for this account |

### Feedback (Feedback Loop)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/zones/{id}/feedback` | Submit canvass session. Accepts all tiers (star only, counts, full detail). |
| PUT | `/api/v1/feedback/{session_id}` | Update session — add contract count days later when deals close. |
| GET | `/api/v1/feedback/my-history` | Roofer's own canvass history with conversion rates. |
| GET | `/api/v1/analytics/my-performance` | Personal dashboard: avg conversion by zone score, best hail ranges, ROI per canvass trip. |

### Internal Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/internal/calibration/report` | Predicted vs actual by region, hail bucket, model version |
| POST | `/api/v1/internal/model/propose-weights` | Compute suggested weight adjustments from calibration data |
| POST | `/api/v1/internal/model/deploy` | Bump model_version with new weights |

---

## Feedback Loop Architecture

```
Storm Event
    │
    ▼
Scoring Engine ──── predicted_conversion ───▶ lead_zones
    │                                            │
    │                                            │ FK
    │                                            ▼
    │                                      canvass_sessions
    │                                            │
    │                                            │ nightly batch
    │                                            ▼
    │◄──── weight adjustment ◄──────── model_calibration
    │
    ▼
Bump model_version → new zones use updated weights
Old zones retain their frozen score_weights_snapshot
```

**Trigger for weight tuning:** `abs(prediction_bias) > 0.02` in any region/hail bucket.

**Predicted conversion lookup (v1.0.0):**
- Score 80–100 → 12% predicted conversion
- Score 60–79 → 7%
- Score 40–59 → 3%
- Score 0–39 → 1%

---

## Key Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **APScheduler over Celery** | APScheduler in-process | Saves ~$5-10/mo by avoiding second Railway service. Split to Celery at ~30 concurrent users. |
| **Neon over Supabase** | Neon Launch $5/mo | Supabase free tier auto-pauses after 7 days (dealbreaker for 24/7 storm monitoring). Supabase Pro is $25/mo. |
| **Upstash over self-hosted Redis** | Upstash free tier | HTTP-based, serverless. 256MB/500K cmds is plenty for API response caching at MVP scale. |
| **Cloudflare Pages over Vercel/Netlify** | Cloudflare Pages free | Unlimited bandwidth, 500 builds/mo, global CDN. Domain registrar in same ecosystem. |
| **Monorepo over multi-repo** | Single GitHub repo | Solo developer. Railway and Cloudflare Pages both support root directory config. Simpler to manage. |
| **JWT over session-based auth** | JWT with 72hr expiry | Stateless. No session store needed. PWA-friendly. Refresh token flow not needed at MVP scale. |
| **SMS as paid feature** | SMS gated behind Pro tier | SMS costs scale linearly with users ($0.0079/msg). Gating ensures costs are always covered by revenue. |
