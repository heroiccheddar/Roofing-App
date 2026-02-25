"""Zone data freshness computation.

Computes a freshness status for each zone based on existing timestamp fields.
No new database columns needed — purely derived from LeadZone timestamps.
"""

from datetime import datetime, timezone
from typing import Literal

FreshnessStatus = Literal["fresh", "aging", "stale"]


def compute_freshness(
    has_active_storm: bool,
    primary_event_timestamp: datetime | None,
    base_scored_at: datetime | None,
    updated_at: datetime,
    current_time: datetime | None = None,
) -> dict:
    """Compute zone freshness status from existing timestamp fields.

    Returns dict with keys:
        status: "fresh" | "aging" | "stale"
        age_days: float (days since the primary reference timestamp)
        label: str (human-readable, e.g. "Storm 2d ago" or "Scored 45d ago")
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    if has_active_storm and primary_event_timestamp:
        # Storm zone: freshness driven by storm recency
        ref_time = primary_event_timestamp
        age_days = (current_time - ref_time).total_seconds() / 86400

        if age_days < 3:
            status: FreshnessStatus = "fresh"
        elif age_days < 7:
            status = "aging"
        else:
            status = "stale"

        label = _format_storm_label(age_days)
    else:
        # Base zone: freshness driven by scoring recency
        ref_time = base_scored_at or updated_at
        age_days = (current_time - ref_time).total_seconds() / 86400

        if age_days < 30:
            status = "fresh"
        elif age_days < 90:
            status = "aging"
        else:
            status = "stale"

        label = _format_base_label(age_days)

    return {
        "status": status,
        "age_days": round(age_days, 1),
        "label": label,
    }


def _format_storm_label(age_days: float) -> str:
    if age_days < 1:
        hours = age_days * 24
        return f"Storm {hours:.0f}h ago"
    return f"Storm {age_days:.0f}d ago"


def _format_base_label(age_days: float) -> str:
    if age_days < 1:
        return "Scored today"
    elif age_days < 30:
        return f"Scored {age_days:.0f}d ago"
    elif age_days < 365:
        months = age_days / 30
        return f"Scored {months:.0f}mo ago"
    else:
        return f"Scored {age_days / 365:.1f}yr ago"
