# RoofIQ Product Vision

## Mission
Give a roofer the ability to show up at the right door, at the right time, with confidence that the homeowner needs a roof.

## Current State (v0.1 - Foundation)
- 20+ data source scoring engine (census, FEMA, NWS, climate, market data)
- 31,875 scored H3 zones covering Georgia
- Real-time storm event tracking with auto-rescoring
- Map-based zone browser with score/distance/type filters
- Basic canvassing tracker and feedback system
- Auth, service area, alert preferences

## Phase 1: Field-Ready MVP
**Goal**: Make this useful enough that your brother-in-law opens it every morning before heading out.

### 1A. Mobile Canvassing Experience
- **PWA install**: Add service worker + manifest so it works as a home-screen app on iPhone/Android
- **Daily route planner**: Select 3-5 zones, get an optimized driving route (Mapbox Directions API)
- **Street-level view**: When zoomed into a zone, show individual streets and parcels with score indicators
- **Quick-tap feedback**: After visiting a zone, one-tap star rating + "saw damage" toggle from the map — no navigation to a separate form
- **Offline mode**: Cache the day's route and zone data so the app works in areas with poor signal

### 1B. Smarter Zone Recommendations
- **"Where should I go today?"**: A single recommendation engine that weighs score, distance from home, time of day (morning = farther drive OK), and zones not yet visited
- **Zone staleness**: Track when zones were last visited by anyone. Deprioritize recently-canvassed zones automatically
- **Storm chasing mode**: After a storm event, surface a curated "storm run" — the 5-10 highest-boost zones within driving range, ordered as a route

### 1C. Quality-of-Life Polish
- **Display names for all zones**: Backfill the 26,000+ zones missing display_name via batch geocoding
- **Notifications**: Push notification when a new storm hits within service area (replace WebSocket-only approach with FCM/APNs)
- **Dark mode**: Roofers use the app in bright sunlight — need a high-contrast option
- **Loading states and error handling**: Current UI has minimal feedback on loading/errors

---

## Phase 2: Scoring Intelligence
**Goal**: The score actually predicts conversion — roofers trust it because zones rated "hot" produce signed contracts.

### 2A. Feedback-Driven Model Calibration
- **Outcome tracking**: Extend canvass sessions with outcome fields: `inspection_completed`, `contract_signed`, `revenue_actual`
- **Conversion funnel**: Zone score at time of visit -> doors knocked -> interested -> inspection -> contract. Track full funnel
- **Score calibration loop**: Monthly job compares predicted conversion rate (from score band) against actual outcomes. Log drift and flag when recalibration is needed
- **Feature importance audit**: After 100+ canvass sessions with outcomes, run feature importance analysis to validate which of the 20 data sources actually correlate with conversions

### 2B. Property-Level Intelligence
- **County assessor integration**: Pull parcel-level data (year built, roof type, last sale date, assessed value) for Georgia counties
- **Permit cross-reference**: Flag addresses with recent roofing permits (likely already replaced — skip)
- **Roof age estimation**: Combine year-built + last permit + satellite age indicators for per-property roof age
- **Street-level scoring**: Aggregate parcel data to street segments so the roofer knows which side of which street to work

### 2C. Satellite / Aerial Imagery (Stretch)
- **Nearmap or EagleView integration**: Detect visible roof damage, measure roof area, identify material type
- **Before/after storm comparison**: Flag properties where roof appearance changed after a storm event
- **Cost estimation**: Roof area x material type x local labor rates = rough estimate for the roofer to reference

---

## Phase 3: SaaS Foundation
**Goal**: A second roofing company can sign up, configure their service area, and get value on day one — without any manual setup.

### 3A. Multi-Tenant Infrastructure
- **Company accounts**: One company -> many users (owner, salespeople, canvassers) with role-based access
- **Territory management**: Define non-overlapping territories per salesperson. Zone recommendations respect territory boundaries
- **Shared canvass history**: Company-wide visibility into which zones have been visited and by whom

### 3B. Onboarding Flow
- **Service area wizard**: Draw a polygon on the map or enter a zip code list to define coverage
- **Home base setup**: Drop a pin for office/warehouse location (used for distance calculations)
- **Preference calibration**: Short quiz about company focus (storm chasers vs. retail vs. insurance) to tune initial filter defaults

### 3C. Subscription & Billing
- **Free tier**: View scores for up to 50 zones, no route planning, no canvass tracking
- **Pro tier ($X/user/month)**: Full access — unlimited zones, route planning, canvass tracking, storm alerts, export
- **Stripe integration**: Self-serve signup, billing portal, usage metering
- **Usage limits enforcement**: Query-level checks on subscription tier

### 3D. Analytics Dashboard
- **Company-wide metrics**: Zones visited, doors knocked, contracts signed, revenue, conversion rate by score band
- **Roofer leaderboard**: Activity metrics per team member
- **ROI calculator**: "RoofIQ helped you find X contracts worth $Y this month"
- **Score accuracy report**: How well do scores predict your actual outcomes?

---

## Phase 4: Scale & Expand (Future)
**Goal**: Expand beyond Georgia and add premium data sources.

- **Multi-state rollout**: Census + FEMA + NWS data is national. Re-run ingestion pipeline for target states (TX, FL, CO, AL, OK first)
- **State-specific tuning**: Different states have different building codes, weather patterns, and market dynamics. Per-state model weights
- **CRM integration**: Sync zone/lead data with ServiceTitan, JobNimbus, AccuLynx (common roofing CRMs)
- **Insurance claim data**: Partner with data providers for actual claim history (strongest signal for roof replacement need)
- **API access**: Let power users pull zone data into their own tools
- **White-label option**: Rebrandable version for roofing franchises

---

## Technical Principles

1. **Mobile-first**: Every feature must work on a phone in the field. If it doesn't work on mobile, it doesn't ship
2. **Score trust**: Never show a score without the ability to explain it. Every number traces back to a data source
3. **Feedback closes the loop**: Every piece of field data (ratings, outcomes, damage sightings) feeds back into the model
4. **Georgia is the lab**: Perfect the product for one state before scaling. Multi-state is an operational problem, not a technical one
5. **Simple beats clever**: A roofer needs to open the app, see where to go, and start knocking. Complexity lives in the backend, never in the UX

---

## Success Metrics

### Phase 1 (Field-Ready MVP)
- Brother-in-law uses it 5+ days/week
- Average 3+ zones visited per day via the app
- "Where should I go today?" recommendation used instead of gut instinct

### Phase 2 (Scoring Intelligence)
- 200+ canvass sessions with outcome data logged
- Predicted vs. actual conversion rate within 3% per score band
- At least 2 data sources identified as non-predictive and removed/downweighted

### Phase 3 (SaaS Foundation)
- 3+ paying roofing companies onboarded
- Self-serve signup works without manual intervention
- Monthly churn < 10%

### Phase 4 (Scale)
- 3+ states fully scored and active
- CRM integration used by 50%+ of pro users
