"""AWS SES email service.

Sends HTML email alerts to roofers with lead zone summaries, mini-maps,
and links to the dashboard. Uses AWS SES send_email() via boto3.

62K emails/month free when sent from AWS compute (App Runner qualifies).
SES configuration set provides open/click tracking.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.alert_log import AlertLog

logger = logging.getLogger(__name__)

DAILY_EMAIL_LIMIT = 10


def _get_ses_client():
    """Create SES client with optional explicit credentials for local dev.

    In production (App Runner), credentials are auto-discovered from IAM role.
    For local dev, set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env.

    Returns:
        boto3 SES client or None if credentials are missing
    """
    try:
        # If explicit credentials are provided, use them (local dev)
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            return boto3.client(
                'ses',
                region_name=settings.SES_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )

        # Otherwise, use auto-discovered credentials (IAM role in production)
        return boto3.client('ses', region_name=settings.SES_REGION)

    except NoCredentialsError:
        logger.warning("AWS credentials not found. Email sending will be disabled.")
        return None
    except Exception as e:
        logger.warning(f"Failed to create SES client: {e}. Email sending will be disabled.")
        return None


async def check_rate_limit(
    db: AsyncSession,
    roofer_id: uuid.UUID,
    channel: str = "email",
    limit: int = DAILY_EMAIL_LIMIT
) -> bool:
    """Check if roofer has exceeded daily email limit.

    Args:
        db: Database session
        roofer_id: UUID of the roofer account
        channel: Alert channel to check (default: 'email')
        limit: Daily limit (default: 10)

    Returns:
        True if within limit, False if limit exceeded
    """
    # Calculate 24 hours ago
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=1)

    # Count emails sent in the last 24 hours
    stmt = select(func.count(AlertLog.id)).where(
        and_(
            AlertLog.roofer_account_id == roofer_id,
            AlertLog.channel == channel,
            AlertLog.sent_at >= cutoff_time,
        )
    )

    result = await db.execute(stmt)
    count = result.scalar_one()

    logger.debug(f"Rate limit check: {count}/{limit} {channel} alerts sent in last 24h for roofer {roofer_id}")

    return count < limit


async def send_zone_alert_email(
    db: AsyncSession,
    roofer,
    zone
) -> dict:
    """Send zone alert email to roofer.

    Args:
        db: Database session
        roofer: RooferAccount model instance
        zone: LeadZone model instance

    Returns:
        dict with keys:
            - sent: bool (True if email was sent successfully)
            - message_id: str|None (SES message ID if sent)
            - error: str|None (Error message if failed)
    """
    # Check rate limit first
    within_limit = await check_rate_limit(db, roofer.id, channel="email")
    if not within_limit:
        logger.warning(
            f"Rate limit exceeded for roofer {roofer.id} ({roofer.email}). "
            f"Skipping email for zone {zone.id}."
        )
        return {
            "sent": False,
            "message_id": None,
            "error": f"Rate limit exceeded ({DAILY_EMAIL_LIMIT} emails/day)"
        }

    # Get SES client (may be None if credentials missing)
    ses_client = _get_ses_client()
    if not ses_client:
        logger.warning(
            f"SES client unavailable. Cannot send email to {roofer.email} for zone {zone.id}. "
            "Check AWS credentials configuration."
        )
        return {
            "sent": False,
            "message_id": None,
            "error": "AWS SES client unavailable (missing credentials)"
        }

    # Build email content
    html_body = _build_html_email(roofer, zone)
    subject = _build_subject_line(zone)

    try:
        # Send email via SES
        response = ses_client.send_email(
            Source=settings.SES_FROM_EMAIL,
            Destination={
                'ToAddresses': [roofer.email],
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8',
                },
                'Body': {
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8',
                    },
                },
            },
        )

        message_id = response['MessageId']
        logger.info(
            f"Email sent successfully to {roofer.email} for zone {zone.id}. "
            f"SES Message ID: {message_id}"
        )

        # Log to alert_log
        alert_log = AlertLog(
            roofer_account_id=roofer.id,
            lead_zone_id=zone.id,
            channel='email',
            sent_at=datetime.now(timezone.utc),
            message_id=message_id,
        )
        db.add(alert_log)
        await db.commit()

        return {
            "sent": True,
            "message_id": message_id,
            "error": None
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(
            f"SES ClientError sending email to {roofer.email} for zone {zone.id}: "
            f"{error_code} - {error_message}"
        )
        return {
            "sent": False,
            "message_id": None,
            "error": f"SES error: {error_code} - {error_message}"
        }

    except Exception as e:
        logger.error(
            f"Unexpected error sending email to {roofer.email} for zone {zone.id}: {e}",
            exc_info=True
        )
        return {
            "sent": False,
            "message_id": None,
            "error": f"Unexpected error: {str(e)}"
        }


def _build_subject_line(zone) -> str:
    """Build email subject line based on zone score band.

    Args:
        zone: LeadZone model instance

    Returns:
        Email subject string
    """
    band_emoji = {
        'hot': '🔥',
        'warm': '⚡',
        'cool': '📍',
        'skip': '❄️',
    }

    emoji = band_emoji.get(zone.score_band, '📍')

    return f"{emoji} New {zone.score_band.title()} Lead Zone - Score {int(zone.composite_score)}"


def _build_html_email(roofer, zone) -> str:
    """Build HTML email body for zone alert.

    Args:
        roofer: RooferAccount model instance
        zone: LeadZone model instance

    Returns:
        HTML email body as string
    """
    # Calculate hours since storm
    hours_since_storm = None
    if zone.primary_event_timestamp:
        delta = datetime.now(timezone.utc) - zone.primary_event_timestamp
        hours_since_storm = int(delta.total_seconds() / 3600)

    # Format storm metrics
    hail_display = f"{zone.max_hail_diameter:.1f}\"" if zone.max_hail_diameter else "N/A"
    wind_display = f"{int(zone.max_wind_speed)} mph" if zone.max_wind_speed else "N/A"
    hours_display = f"{hours_since_storm}h ago" if hours_since_storm is not None else "N/A"

    # Score band styling
    band_colors = {
        'hot': '#DC2626',      # red-600
        'warm': '#EA580C',     # orange-600
        'cool': '#2563EB',     # blue-600
        'skip': '#6B7280',     # gray-500
    }
    band_color = band_colors.get(zone.score_band, '#6B7280')

    # Build CTA link
    dashboard_url = f"https://app.stormleads.com/zone/{zone.id}"

    # HTML template
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>New Lead Zone Alert</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #F3F4F6;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #F3F4F6;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <!-- Main container -->
                <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #FFFFFF; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 32px 24px; text-align: center; background-color: {band_color}; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 700;">
                                New {zone.score_band.title()} Lead Zone
                            </h1>
                        </td>
                    </tr>

                    <!-- Score display -->
                    <tr>
                        <td style="padding: 32px 32px 16px; text-align: center;">
                            <div style="display: inline-block; background-color: #F9FAFB; border-radius: 8px; padding: 24px 32px;">
                                <div style="color: #6B7280; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">
                                    Composite Score
                                </div>
                                <div style="color: {band_color}; font-size: 48px; font-weight: 800; line-height: 1;">
                                    {int(zone.composite_score)}
                                </div>
                            </div>
                        </td>
                    </tr>

                    <!-- Storm metrics -->
                    <tr>
                        <td style="padding: 0 32px 24px;">
                            <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 12px; text-align: center; background-color: #F9FAFB; border-radius: 8px; width: 33.33%;">
                                        <div style="color: #6B7280; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">
                                            Hail
                                        </div>
                                        <div style="color: #111827; font-size: 18px; font-weight: 700;">
                                            {hail_display}
                                        </div>
                                    </td>
                                    <td style="width: 8px;"></td>
                                    <td style="padding: 12px; text-align: center; background-color: #F9FAFB; border-radius: 8px; width: 33.33%;">
                                        <div style="color: #6B7280; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">
                                            Wind
                                        </div>
                                        <div style="color: #111827; font-size: 18px; font-weight: 700;">
                                            {wind_display}
                                        </div>
                                    </td>
                                    <td style="width: 8px;"></td>
                                    <td style="padding: 12px; text-align: center; background-color: #F9FAFB; border-radius: 8px; width: 33.33%;">
                                        <div style="color: #6B7280; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px;">
                                            Time
                                        </div>
                                        <div style="color: #111827; font-size: 18px; font-weight: 700;">
                                            {hours_display}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Additional details -->
                    <tr>
                        <td style="padding: 0 32px 24px;">
                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #F9FAFB; border-radius: 8px; padding: 16px;">
                                <tr>
                                    <td style="padding: 8px 0;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="color: #6B7280; font-size: 14px; font-weight: 500;">
                                                    Score Band
                                                </td>
                                                <td style="color: #111827; font-size: 14px; font-weight: 600; text-align: right;">
                                                    {zone.score_band.title()}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 8px 0; border-top: 1px solid #E5E7EB;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="color: #6B7280; font-size: 14px; font-weight: 500;">
                                                    Events Detected
                                                </td>
                                                <td style="color: #111827; font-size: 14px; font-weight: 600; text-align: right;">
                                                    {zone.event_count}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 8px 0; border-top: 1px solid #E5E7EB;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="color: #6B7280; font-size: 14px; font-weight: 500;">
                                                    Damage Probability
                                                </td>
                                                <td style="color: #111827; font-size: 14px; font-weight: 600; text-align: right;">
                                                    {int(zone.damage_prob)}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 8px 0; border-top: 1px solid #E5E7EB;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="color: #6B7280; font-size: 14px; font-weight: 500;">
                                                    Lead Quality
                                                </td>
                                                <td style="color: #111827; font-size: 14px; font-weight: 600; text-align: right;">
                                                    {int(zone.lead_quality)}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- CTA button -->
                    <tr>
                        <td style="padding: 0 32px 32px; text-align: center;">
                            <a href="{dashboard_url}" style="display: inline-block; background-color: {band_color}; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                View Zone Details
                            </a>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 32px; border-top: 1px solid #E5E7EB; background-color: #F9FAFB; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0 0 8px; color: #6B7280; font-size: 14px; text-align: center;">
                                This alert was sent to {roofer.company_name}
                            </p>
                            <p style="margin: 0; color: #9CA3AF; font-size: 12px; text-align: center;">
                                You're receiving this because you have email alerts enabled for your service area.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
    """

    return html.strip()
