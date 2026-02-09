"""Data ingestion modules for external storm data sources."""

from app.ingestion.census_loader import load_census_data
from app.ingestion.nws_poller import poll_nws_alerts
from app.ingestion.spc_scraper import scrape_spc_reports
from app.ingestion.swdi_fetcher import fetch_swdi_mesh, fetch_swdi_for_warning
from app.ingestion.dedup import deduplicate_storm_events

__all__ = [
    "load_census_data",
    "poll_nws_alerts",
    "scrape_spc_reports",
    "fetch_swdi_mesh",
    "fetch_swdi_for_warning",
    "deduplicate_storm_events",
]
