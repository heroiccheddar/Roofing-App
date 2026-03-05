"""Seed 5 demo lead pins for every roofer account.

Creates realistic sample pins with varied dispositions, contacts, lead sources,
and deal values so new users can see the app populated immediately.

Pins are placed in a small cluster around Atlanta, GA (default) with recognizable
demo addresses. Each pin has a unique note identifying it as demo data.

Usage:
    python -m scripts.seed_demo_pins

    # Remove all demo pins
    python -m scripts.seed_demo_pins --cleanup
"""

import argparse
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from geoalchemy2 import WKTElement
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.lead_pin import LeadPin
from app.models.roofer_account import RooferAccount

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEMO_NOTE_TAG = "[DEMO PIN]"

DEMO_PINS = [
    {
        "address": "142 Peachtree St NW, Atlanta, GA 30303",
        "lat": 33.7590,
        "lon": -84.3880,
        "disposition": "interested",
        "lead_source": "door_knock",
        "contact_name": "James Mitchell",
        "contact_phone": "555-0101",
        "contact_email": "j.mitchell@example.com",
        "estimated_value": 8500,
        "notes": f"{DEMO_NOTE_TAG} Homeowner noticed missing shingles after last storm. Wants an inspection this week.",
    },
    {
        "address": "2890 Roswell Rd, Marietta, GA 30062",
        "lat": 33.9526,
        "lon": -84.5499,
        "disposition": "callback",
        "lead_source": "storm_canvass",
        "contact_name": "Sarah Chen",
        "contact_phone": "555-0102",
        "contact_email": None,
        "estimated_value": 12000,
        "callback_hours_from_now": 48,
        "notes": f"{DEMO_NOTE_TAG} Hail damage visible on north-facing slope. Callback scheduled to discuss insurance claim.",
    },
    {
        "address": "1055 Howell Mill Rd NW, Atlanta, GA 30318",
        "lat": 33.7845,
        "lon": -84.4120,
        "disposition": "inspection_set",
        "lead_source": "referral",
        "contact_name": "Marcus Johnson",
        "contact_phone": "555-0103",
        "contact_email": "marcus.j@example.com",
        "estimated_value": 15200,
        "notes": f"{DEMO_NOTE_TAG} Referred by neighbor at 1049 Howell Mill. Roof is 18 years old, ready to replace.",
    },
    {
        "address": "4400 Ashford Dunwoody Rd, Atlanta, GA 30346",
        "lat": 33.9230,
        "lon": -84.3410,
        "disposition": "not_home",
        "lead_source": "door_knock",
        "contact_name": None,
        "contact_phone": None,
        "contact_email": None,
        "estimated_value": None,
        "notes": f"{DEMO_NOTE_TAG} No answer. Visible wind damage on ridge cap. Left door hanger.",
    },
    {
        "address": "675 Ponce De Leon Ave NE, Atlanta, GA 30308",
        "lat": 33.7725,
        "lon": -84.3655,
        "disposition": "contract_signed",
        "lead_source": "website",
        "contact_name": "Linda Park",
        "contact_phone": "555-0105",
        "contact_email": "linda.park@example.com",
        "estimated_value": 22000,
        "notes": f"{DEMO_NOTE_TAG} Full tear-off and reroof. Signed on first visit. Insurance approved.",
    },
]


async def seed_pins() -> None:
    """Insert 5 demo pins for every roofer account."""
    async with AsyncSessionLocal() as session:
        # Get all accounts
        result = await session.execute(select(RooferAccount.id, RooferAccount.email))
        accounts = result.all()

        if not accounts:
            logger.warning("No roofer accounts found. Nothing to seed.")
            return

        logger.info("Found %d roofer accounts. Seeding %d demo pins each.", len(accounts), len(DEMO_PINS))

        now = datetime.now(tz=timezone.utc)
        total = 0

        for acct_id, email in accounts:
            # Check if demo pins already exist for this account
            existing = await session.execute(
                select(LeadPin.id).where(
                    LeadPin.roofer_account_id == acct_id,
                    LeadPin.notes.contains(DEMO_NOTE_TAG),
                )
            )
            if existing.first():
                logger.info("  %s — already has demo pins, skipping.", email)
                continue

            for i, pin_data in enumerate(DEMO_PINS):
                callback_date = None
                if pin_data.get("callback_hours_from_now"):
                    callback_date = now + timedelta(hours=pin_data["callback_hours_from_now"])

                pin = LeadPin(
                    id=uuid.uuid4(),
                    roofer_account_id=acct_id,
                    location=WKTElement(f"POINT({pin_data['lon']} {pin_data['lat']})", srid=4326),
                    address=pin_data["address"],
                    disposition=pin_data["disposition"],
                    lead_source=pin_data["lead_source"],
                    contact_name=pin_data["contact_name"],
                    contact_phone=pin_data["contact_phone"],
                    contact_email=pin_data["contact_email"],
                    estimated_value=pin_data["estimated_value"],
                    callback_date=callback_date,
                    notes=pin_data["notes"],
                    created_at=now - timedelta(hours=(len(DEMO_PINS) - i) * 12),
                )
                session.add(pin)
                total += 1

            logger.info("  %s — added %d demo pins.", email, len(DEMO_PINS))

        await session.commit()
        logger.info("Done. Inserted %d demo pins total.", total)


async def cleanup() -> None:
    """Remove all demo pins (identified by DEMO_NOTE_TAG in notes)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(LeadPin).where(LeadPin.notes.contains(DEMO_NOTE_TAG))
        )
        await session.commit()
        logger.info("Removed %d demo pins.", result.rowcount)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo lead pins for all accounts")
    parser.add_argument("--cleanup", action="store_true", help="Remove all demo pins")
    args = parser.parse_args()

    if args.cleanup:
        asyncio.run(cleanup())
    else:
        asyncio.run(seed_pins())


if __name__ == "__main__":
    main()
