"""List all roofer accounts."""

import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.roofer_account import RooferAccount


async def main():
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(
                    RooferAccount.email,
                    RooferAccount.company_name,
                    RooferAccount.phone_number,
                    RooferAccount.org_role,
                    RooferAccount.subscription_tier,
                    RooferAccount.is_active,
                    RooferAccount.created_at,
                ).order_by(RooferAccount.created_at)
            )
        ).all()

        print(f"{'Email':<35} {'Company':<22} {'Phone':<14} {'Role':<8} {'Tier':<6} {'Active':<7} {'Created'}")
        print("-" * 115)
        for email, company, phone, role, tier, active, created in rows:
            print(
                f"{email:<35} "
                f"{(company or '-'):<22} "
                f"{(phone or '-'):<14} "
                f"{(role or '-'):<8} "
                f"{tier:<6} "
                f"{'yes' if active else 'no':<7} "
                f"{created.strftime('%Y-%m-%d')}"
            )
        print(f"\nTotal: {len(rows)} accounts")


if __name__ == "__main__":
    asyncio.run(main())
