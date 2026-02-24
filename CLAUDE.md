# CLAUDE.md

## Project

RoofIQ — a general roofing lead intelligence platform with storm alerts, built on FastAPI + React + PostgreSQL/PostGIS. Backend deployed on Fly.io, frontend on Vercel.

## Development Rules

### Data Scripts & Pipelines

- Before writing any script that calls an external API or writes to the database, identify the rate limit, memory constraint, and expected row count. Design the script around those limits from the start — do not add batching or rate limiting as an afterthought.
- Bulk API calls (e.g., Mapbox geocoding, NWS polling) MUST include a `skip_*` parameter so the operation can be bypassed during large batch runs. Default to skipping when row count > 1,000.
- Database writes MUST use batch commits (every 500 rows) to bound memory on the 256MB Fly.io machine.
- Scripts expected to run > 2 minutes MUST log progress to a file and support detached execution (`nohup`). SSH sessions to Fly.io timeout.

### Feature Development

- Any feature touching 4+ files across backend and frontend MUST be planned with parallel agents. Split into independent workstreams where no two agents write to the same file.
- Before launching parallel agents, explicitly define the shared contract in the plan: new column names, API endpoint signatures, TypeScript types, and Zustand store shape. Agents reference this contract — not each other's files.
- Each agent's file set must be listed in the plan. If a file appears in two agents' lists, restructure the split until there is zero overlap.
