"""Compute percentile ranks for census tract features within a state."""
import argparse
import asyncio
import os
import sys

os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.ingestion.percentile_loader import compute_and_store_percentiles
from app.database import AsyncSessionLocal


async def main(state_fips: str):
    async with AsyncSessionLocal() as session:
        stats = await compute_and_store_percentiles(session, state_fips)
        print(f"Done: {stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="13", help="State FIPS (default: 13 = Georgia)")
    args = parser.parse_args()
    asyncio.run(main(args.state))
