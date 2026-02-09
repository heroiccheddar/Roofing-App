"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.auth import router as auth_router
from app.api.zones import router as zones_router
from app.scheduler.jobs import (
    job_poll_nws,
    job_scrape_spc,
    job_deduplicate,
    job_run_scoring,
    job_expire_zones,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup — register and start scheduled jobs
    scheduler.add_job(
        job_poll_nws,
        IntervalTrigger(minutes=5),
        id="nws_poll",
        name="NWS Active Alerts Poll",
        replace_existing=True,
    )
    scheduler.add_job(
        job_scrape_spc,
        IntervalTrigger(hours=6),
        id="spc_scrape",
        name="SPC Storm Reports Scrape",
        replace_existing=True,
    )
    scheduler.add_job(
        job_deduplicate,
        IntervalTrigger(minutes=30),
        id="dedup",
        name="Storm Event Deduplication",
        replace_existing=True,
    )
    scheduler.add_job(
        job_run_scoring,
        IntervalTrigger(minutes=10),
        id="scoring",
        name="Lead Zone Scoring",
        replace_existing=True,
    )
    scheduler.add_job(
        job_expire_zones,
        IntervalTrigger(hours=1),
        id="zone_expiry",
        name="Zone Expiry Cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "APScheduler started with 5 jobs: "
        "nws_poll (5m), spc_scrape (6h), dedup (30m), scoring (10m), zone_expiry (1h)"
    )

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down")


app = FastAPI(
    title="StormLeads API",
    description="Storm damage lead generation for roofers",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(zones_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint for App Runner."""
    return {"status": "healthy", "service": "stormleads-api"}
