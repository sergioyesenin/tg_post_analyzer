#!/usr/bin/env python3
"""
Backfill script to rebuild events and processes from all existing post_links.
Uses the same logic as the main pipeline (rebuild_events, rebuild_processes)
and processes the entire date range of posts.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.processes.build_processes import rebuild_processes
from services.pipeline_runtime_common import configure_logging
from sqlalchemy import select, func
from db.models import Post


async def get_full_date_range() -> tuple[datetime, datetime] | None:
    """Return (min_date, max_date) from posts table, or None if no posts."""
    async with AsyncSessionLocal() as session:
        stmt = select(func.min(Post.date), func.max(Post.date))
        result = await session.execute(stmt)
        min_date, max_date = result.one()
        if min_date is None or max_date is None:
            return None
        return min_date, max_date


async def backfill_full(
    dry_run: bool = False,
    rebuild_events_flag: bool = True,
    rebuild_processes_flag: bool = True,
) -> None:
    """Rebuild events and/or processes for all posts (based on post_links)."""
    date_range = await get_full_date_range()
    if date_range is None:
        logging.error("No posts found in database. Nothing to backfill.")
        return

    date_from, date_to = date_range
    logging.info("Processing full date range: %s to %s", date_from, date_to)

    if dry_run:
        logging.info("DRY RUN: would rebuild events and processes for the entire range")
        return

    async with AsyncSessionLocal() as session:
        if rebuild_events_flag:
            logging.info("Rebuilding events for all posts...")
            rebuilt_events = await rebuild_events(
                session,
                date_from=date_from,
                date_to=date_to,
                created_by="backfill-script",
            )
            await session.commit()
            logging.info("Rebuilt %s events", rebuilt_events)

        if rebuild_processes_flag:
            logging.info("Rebuilding processes for all events...")
            rebuilt_memberships = await rebuild_processes(
                session,
                date_from=date_from,
                date_to=date_to,
                created_by="backfill-script",
            )
            await session.commit()
            logging.info("Rebuilt %s process-event memberships", rebuilt_memberships)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill events and processes from all existing post_links."
    )
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    parser.add_argument("--skip-events", action="store_true", help="Skip rebuilding events")
    parser.add_argument("--skip-processes", action="store_true", help="Skip rebuilding processes")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    return parser.parse_args()


async def backfill_events_processes() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    await backfill_full(
        dry_run=args.dry_run,
        rebuild_events_flag=not args.skip_events,
        rebuild_processes_flag=not args.skip_processes,
    )


def main() -> None:
    asyncio.run(backfill_events_processes())


if __name__ == "__main__":
    main()