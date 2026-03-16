from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.pipeline_runtime import (
    AI_JOB_TYPES,
    build_worker_id,
    collect_backlog_snapshot,
    configure_logging,
    get_ai_poll_seconds,
    run_ai_cycle,
)
from services.runtime_heartbeat import HEARTBEAT_INTERVAL_SECONDS, persist_runtime_heartbeat
from services.runtime_topology import AI_PIPELINE_RUNTIME


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI reporting pipeline.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=None)
    parser.add_argument("--job-batch-size", type=int, default=None)
    parser.add_argument("--job-worker-concurrency", type=int, default=None)
    parser.add_argument("--post-report-age-hours", type=int, default=None)
    parser.add_argument("--scheduler-limit", type=int, default=None)
    return parser


async def main_async(args: argparse.Namespace) -> None:
    worker_id = build_worker_id("ai-pipeline")
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(worker_id=worker_id, jobs_provider=lambda: sorted(AI_JOB_TYPES))
    )
    try:
        await persist_runtime_heartbeat(
            runtime_name=AI_PIPELINE_RUNTIME.runtime_name,
            status="running",
            details={"worker_id": worker_id, "job_types": sorted(AI_JOB_TYPES), "pid": os.getpid()},
        )
        while True:
            cycle_started_at = datetime.now(timezone.utc)
            backlog_before = await collect_backlog_snapshot(allowed_types=AI_JOB_TYPES)
            queued, executed = await run_ai_cycle(
                worker_id=worker_id,
                job_batch_size_arg=args.job_batch_size,
                job_worker_concurrency_arg=args.job_worker_concurrency,
                post_report_age_hours_arg=args.post_report_age_hours,
                scheduler_limit_arg=args.scheduler_limit,
            )
            backlog_after = await collect_backlog_snapshot(allowed_types=AI_JOB_TYPES)
            logging.info(
                "AI cycle worker_id=%s queued_post_reports=%s executed_jobs=%s backlog_before=%s backlog_after=%s",
                worker_id,
                queued,
                executed,
                backlog_before,
                backlog_after,
            )
            if not args.daemon:
                return
            elapsed = (datetime.now(timezone.utc) - cycle_started_at).total_seconds()
            poll_seconds = await get_ai_poll_seconds(cli_override=args.poll_seconds)
            await asyncio.sleep(max(1, int(poll_seconds - elapsed)))
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await persist_runtime_heartbeat(
            runtime_name=AI_PIPELINE_RUNTIME.runtime_name,
            status="stopped",
            details={"worker_id": worker_id, "job_types": sorted(AI_JOB_TYPES), "pid": os.getpid()},
        )


async def _heartbeat_loop(*, worker_id: str, jobs_provider) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await persist_runtime_heartbeat(
            runtime_name=AI_PIPELINE_RUNTIME.runtime_name,
            status="running",
            details={"worker_id": worker_id, "job_types": jobs_provider(), "pid": os.getpid()},
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
