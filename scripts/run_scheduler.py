from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.session import AsyncSessionLocal
from services.pipeline_runtime import configure_logging
from services.runtime_heartbeat import HEARTBEAT_INTERVAL_SECONDS, persist_runtime_heartbeat
from services.scheduler_dispatch import retention_scheduler_enabled
from services.scheduler_runtime import build_scheduler, register_periodic_jobs
from services.settings_store import get_all_settings
from services.runtime_topology import SCHEDULER_RUNTIME


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run APScheduler-based control plane.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


async def main_async() -> None:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    #if not retention_scheduler_enabled(effective_settings):
    #    logging.info("Scheduler process is disabled by settings.")
    #    return

    scheduler = build_scheduler()
    register_periodic_jobs(scheduler, effective_settings=effective_settings)
    scheduler.start()
    job_ids = sorted(job.id for job in scheduler.get_jobs())
    try:
        await persist_runtime_heartbeat(
            runtime_name=SCHEDULER_RUNTIME.runtime_name,
            status="running",
            details={"jobs": job_ids, "pid": os.getpid()},
        )
    except Exception:
        scheduler.shutdown(wait=False)
        raise
    logging.info("Scheduler started with jobs=%s", job_ids)

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(job_ids_getter=lambda: sorted(job.id for job in scheduler.get_jobs())))
    try:
        await stop_event.wait()
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await persist_runtime_heartbeat(
            runtime_name=SCHEDULER_RUNTIME.runtime_name,
            status="stopped",
            details={"jobs": job_ids, "pid": os.getpid()},
        )
        scheduler.shutdown(wait=False)


async def _heartbeat_loop(*, job_ids_getter) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await persist_runtime_heartbeat(
            runtime_name=SCHEDULER_RUNTIME.runtime_name,
            status="running",
            details={"jobs": job_ids_getter(), "pid": os.getpid()},
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
