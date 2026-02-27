"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.api.auth import router as auth_router
from app.api.zones import router as zones_router
from app.api.feedback import router as feedback_router
from app.api.account import router as account_router
from app.api.alerts import router as alerts_router
from app.api.canvass import router as canvass_router
from app.api.recommend import router as recommend_router
from app.api.route import router as route_router
from app.api.leads import router as leads_router
from app.api.properties import router as properties_router
from app.api.org import router as org_router
from app.api.metrics import router as metrics_router
from app.api.photos import router as photos_router
from app.scheduler.jobs import (
    job_poll_nws,
    job_scrape_spc,
    job_deduplicate,
    job_run_storm_scoring,
    job_run_base_scoring,
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
        job_run_storm_scoring,
        IntervalTrigger(minutes=10),
        id="storm_scoring",
        name="Storm Event Rescore",
        replace_existing=True,
    )
    scheduler.add_job(
        job_run_base_scoring,
        CronTrigger(hour=2, minute=0),
        id="base_scoring",
        name="Daily Base Score Refresh",
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
        "APScheduler started with 6 jobs: "
        "nws_poll (5m), spc_scrape (6h), dedup (30m), "
        "storm_scoring (10m), base_scoring (daily 02:00 UTC), zone_expiry (1h)"
    )

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down")


app = FastAPI(
    title="RoofIQ API",
    description="Roofing lead intelligence platform",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — explicit methods and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    return response


# API routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(zones_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(canvass_router, prefix="/api/v1")
app.include_router(recommend_router, prefix="/api/v1")
app.include_router(route_router, prefix="/api/v1")
app.include_router(leads_router, prefix="/api/v1")
app.include_router(properties_router, prefix="/api/v1")
app.include_router(org_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(photos_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint for App Runner."""
    return {"status": "healthy", "service": "roofiq-api"}
