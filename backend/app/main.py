"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    # TODO: Initialize APScheduler here in WP 3.6
    yield
    # Shutdown
    # TODO: Shutdown APScheduler here in WP 3.6


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


@app.get("/health")
async def health_check():
    """Health check endpoint for App Runner."""
    return {"status": "healthy", "service": "stormleads-api"}
