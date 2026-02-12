"""
Alert Matching Engine

Connects the scoring pipeline to notification channels. After lead zones are scored,
this engine:
1. Finds roofers whose service area intersects the zone
2. Filters by alert preferences (min_score, min_hail, quiet_hours)
3. Prevents duplicate alerts
4. Dispatches via email (SES) and WebSocket
"""

import logging
from datetime import datetime, time, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Intersects

from app.models.lead_zone import LeadZone
from app.models.roofer_account import RooferAccount
from app.models.alert_log import AlertLog
from app.services.ses_email import send_zone_alert_email
from app.api.alerts import manager as websocket_manager

logger = logging.getLogger(__name__)


async def process_zone_alerts(db: AsyncSession, zone_ids: list[UUID]) -> dict:
    """
    Main entry point for alert processing. Called after scoring pipeline creates/updates zones.

    Args:
        db: Database session
        zone_ids: List of lead zone UUIDs to process

    Returns:
        Stats dict with zones_processed, alerts_sent, errors counts
    """
    stats = {
        "zones_processed": 0,
        "alerts_sent": 0,
        "errors": 0
    }

    if not zone_ids:
        logger.info("No zones to process for alerts")
        return stats

    logger.info(f"Processing alerts for {len(zone_ids)} zones")

    # Fetch all zones in one query
    stmt = select(LeadZone).where(
        and_(
            LeadZone.id.in_(zone_ids),
            LeadZone.active == True
        )
    )
    result = await db.execute(stmt)
    zones = result.scalars().all()

    if not zones:
        logger.warning(f"No active zones found for provided IDs")
        return stats

    # Process each zone
    for zone in zones:
        try:
            zone_stats = await match_and_notify(db, zone)
            stats["zones_processed"] += 1
            stats["alerts_sent"] += zone_stats.get("notified", 0)
            logger.info(
                f"Zone {zone.id}: matched={zone_stats['matched']}, "
                f"notified={zone_stats['notified']}, skipped={zone_stats['skipped']}"
            )
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error processing zone {zone.id}: {e}", exc_info=True)

    logger.info(
        f"Alert processing complete: {stats['zones_processed']} zones, "
        f"{stats['alerts_sent']} alerts sent, {stats['errors']} errors"
    )

    return stats


async def match_and_notify(db: AsyncSession, zone: LeadZone) -> dict:
    """
    Match roofers to a zone and send notifications.

    Finds roofers whose service area intersects the zone, applies preference
    filters, and dispatches alerts.

    Args:
        db: Database session
        zone: LeadZone to match against

    Returns:
        Stats dict with matched, notified, skipped counts
    """
    stats = {
        "matched": 0,
        "notified": 0,
        "skipped": 0
    }

    # Find roofers whose service area intersects the zone boundary
    stmt = select(RooferAccount).where(
        and_(
            RooferAccount.is_active == True,
            ST_Intersects(RooferAccount.service_area, zone.boundary)
        )
    )

    result = await db.execute(stmt)
    matching_roofers = result.scalars().all()

    stats["matched"] = len(matching_roofers)

    if not matching_roofers:
        logger.debug(f"No roofers matched for zone {zone.id}")
        return stats

    logger.info(f"Found {len(matching_roofers)} roofers for zone {zone.id}")

    # Process each matching roofer
    for roofer in matching_roofers:
        try:
            # Check if roofer should receive alert based on preferences
            if not should_alert_roofer(roofer, zone):
                stats["skipped"] += 1
                logger.debug(
                    f"Skipping roofer {roofer.id} for zone {zone.id} "
                    f"(preferences not met)"
                )
                continue

            # Dispatch alerts through enabled channels
            dispatch_result = await dispatch_alert(db, roofer, zone)

            # Count as notified if any channel succeeded
            if dispatch_result.get("email", {}).get("sent") or dispatch_result.get("websocket"):
                stats["notified"] += 1
                logger.info(
                    f"Notified roofer {roofer.id} for zone {zone.id} "
                    f"via {_summarize_dispatch(dispatch_result)}"
                )
            else:
                stats["skipped"] += 1
                logger.warning(
                    f"Failed to notify roofer {roofer.id} for zone {zone.id} "
                    f"(all channels failed or duplicate)"
                )

        except Exception as e:
            stats["skipped"] += 1
            logger.error(
                f"Error notifying roofer {roofer.id} for zone {zone.id}: {e}",
                exc_info=True
            )

    return stats


def should_alert_roofer(roofer: RooferAccount, zone: LeadZone) -> bool:
    """
    Check if a roofer should receive an alert for this zone based on preferences.

    Checks:
    - Minimum composite score threshold
    - Minimum hail diameter threshold
    - Quiet hours (if current time is in quiet period)

    Args:
        roofer: RooferAccount with alert_preferences
        zone: LeadZone with scoring data

    Returns:
        True if alert should be sent, False otherwise
    """
    prefs = roofer.alert_preferences or {}

    # Check minimum score threshold
    min_score = prefs.get("min_score", 0.0)
    if zone.composite_score < min_score:
        logger.debug(
            f"Roofer {roofer.id}: zone score {zone.composite_score} "
            f"below threshold {min_score}"
        )
        return False

    # Check minimum hail diameter threshold
    min_hail = prefs.get("min_hail_inches", 0.0)
    if min_hail > 0 and (zone.max_hail_diameter is None or zone.max_hail_diameter < min_hail):
        logger.debug(
            f"Roofer {roofer.id}: zone hail {zone.max_hail_diameter} "
            f"below threshold {min_hail}"
        )
        return False

    # Check quiet hours
    quiet_hours = prefs.get("quiet_hours")
    if quiet_hours and _is_quiet_hours(quiet_hours):
        logger.debug(f"Roofer {roofer.id}: currently in quiet hours")
        return False

    return True


def _is_quiet_hours(quiet_hours: dict) -> bool:
    """
    Check if current UTC time falls within roofer's quiet hours.

    Quiet hours are expected as {"start": "HH:MM", "end": "HH:MM"} in 24-hour format.
    For MVP, we compare against UTC time directly. In production, this should use
    the roofer's timezone.

    Args:
        quiet_hours: Dict with start and end time strings

    Returns:
        True if currently in quiet hours, False otherwise
    """
    try:
        start_str = quiet_hours.get("start")
        end_str = quiet_hours.get("end")

        if not start_str or not end_str:
            return False

        # Parse time strings (HH:MM format)
        start_hour, start_min = map(int, start_str.split(":"))
        end_hour, end_min = map(int, end_str.split(":"))

        start_time = time(start_hour, start_min)
        end_time = time(end_hour, end_min)

        # Get current UTC time
        now = datetime.now(timezone.utc).time()

        # Handle quiet hours that span midnight
        if start_time <= end_time:
            # Normal case: 22:00 to 23:59
            return start_time <= now <= end_time
        else:
            # Spans midnight: 22:00 to 07:00
            return now >= start_time or now <= end_time

    except (ValueError, AttributeError) as e:
        logger.warning(f"Invalid quiet_hours format: {quiet_hours} - {e}")
        return False


async def has_existing_alert(
    db: AsyncSession,
    roofer_id: UUID,
    zone_id: UUID,
    channel: str
) -> bool:
    """
    Check if an alert has already been sent for this roofer+zone+channel combination.

    Prevents duplicate notifications.

    Args:
        db: Database session
        roofer_id: Roofer account UUID
        zone_id: Lead zone UUID
        channel: Channel name ('email' or 'websocket')

    Returns:
        True if alert exists, False otherwise
    """
    stmt = select(AlertLog).where(
        and_(
            AlertLog.roofer_account_id == roofer_id,
            AlertLog.lead_zone_id == zone_id,
            AlertLog.channel == channel
        )
    ).limit(1)

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    return existing is not None


async def dispatch_alert(
    db: AsyncSession,
    roofer: RooferAccount,
    zone: LeadZone
) -> dict:
    """
    Dispatch alert through enabled channels.

    Sends alerts via:
    - Email (if "email" in channels and not duplicate)
    - WebSocket (always attempt if user connected)

    Logs all successful sends to alert_log.

    Args:
        db: Database session
        roofer: RooferAccount to notify
        zone: LeadZone data for notification

    Returns:
        Dict with results: {"email": {...}, "websocket": bool}
    """
    results = {
        "email": None,
        "websocket": False
    }

    prefs = roofer.alert_preferences or {}
    channels = prefs.get("channels", ["email"])

    # Send email if enabled
    if "email" in channels:
        try:
            # Check for duplicate
            if await has_existing_alert(db, roofer.id, zone.id, "email"):
                logger.debug(
                    f"Skipping duplicate email alert for roofer {roofer.id}, "
                    f"zone {zone.id}"
                )
                results["email"] = {"sent": False, "duplicate": True}
            else:
                # Send email (ses_email service handles logging to alert_log)
                email_result = await send_zone_alert_email(db, roofer, zone)
                results["email"] = email_result

        except Exception as e:
            logger.error(
                f"Error sending email to roofer {roofer.id} for zone {zone.id}: {e}",
                exc_info=True
            )
            results["email"] = {"sent": False, "error": str(e)}

    # Send WebSocket notification (always attempt)
    try:
        # Check for duplicate
        if await has_existing_alert(db, roofer.id, zone.id, "websocket"):
            logger.debug(
                f"Skipping duplicate websocket alert for roofer {roofer.id}, "
                f"zone {zone.id}"
            )
        else:
            # Prepare WebSocket payload
            ws_data = {
                "type": "lead_zone_alert",
                "zone_id": str(zone.id),
                "score": zone.composite_score,
                "score_band": zone.score_band,
                "max_hail": zone.max_hail_diameter,
                "max_wind": zone.max_wind_speed,
                "event_count": zone.event_count,
                "timestamp": zone.primary_event_timestamp.isoformat() if zone.primary_event_timestamp else None
            }

            # Attempt to send (will only succeed if user is connected)
            await websocket_manager.send_to_user(str(roofer.id), ws_data)
            results["websocket"] = True

            # Log WebSocket alert
            alert_log = AlertLog(
                roofer_account_id=roofer.id,
                lead_zone_id=zone.id,
                channel="websocket",
                sent_at=datetime.now(timezone.utc)
            )
            db.add(alert_log)
            await db.commit()

            logger.debug(f"Sent WebSocket alert to roofer {roofer.id}")

    except Exception as e:
        logger.error(
            f"Error sending WebSocket to roofer {roofer.id} for zone {zone.id}: {e}",
            exc_info=True
        )
        results["websocket"] = False

    return results


def _summarize_dispatch(dispatch_result: dict) -> str:
    """
    Summarize dispatch results for logging.

    Args:
        dispatch_result: Result dict from dispatch_alert

    Returns:
        Human-readable summary string
    """
    channels = []

    if dispatch_result.get("email", {}).get("sent"):
        channels.append("email")

    if dispatch_result.get("websocket"):
        channels.append("websocket")

    return ", ".join(channels) if channels else "none"
