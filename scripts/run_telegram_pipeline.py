from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.orchestration import (
    TELEGRAM_JOB_TYPES,
    run_telegram_cycle,
)
from services.orchestration import (
    is_session_locked_error,
    with_session_lock_retry,
    build_tg_client,
    build_worker_id,
    collect_backlog_snapshot,
    configure_logging,
    get_telegram_poll_seconds,
    sleep_until_next_telegram_cycle,
)
from services.runtime_heartbeat import HEARTBEAT_INTERVAL_SECONDS, persist_runtime_heartbeat
from services.runtime_topology import TELEGRAM_PIPELINE_RUNTIME


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Telegram ingestion, comments and linking pipeline.")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--max-posts-per-channel", type=int, default=None)
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--session-suffix", type=str, default="")
    parser.add_argument("--unique-session-per-run", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=None)
    parser.add_argument("--job-batch-size", type=int, default=None)
    parser.add_argument("--comment-first-delay-hours", type=int, default=None)
    parser.add_argument("--comment-interval-hours", type=int, default=None)
    parser.add_argument("--comment-window-hours", type=int, default=None)
    parser.add_argument("--retention-days", type=int, default=None)
    parser.add_argument("--archive-batch-size", type=int, default=None)
    parser.add_argument("--skip-rebuild-graphs", action="store_true")
    return parser


async def main_async(args: argparse.Namespace) -> None:
    client = build_tg_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    worker_id = build_worker_id("tg-pipeline")
    await with_session_lock_retry(lambda: client.start(), op_name="client.start")
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(worker_id=worker_id, jobs_provider=lambda: sorted(TELEGRAM_JOB_TYPES))
    )
    try:
        await persist_runtime_heartbeat(
            runtime_name=TELEGRAM_PIPELINE_RUNTIME.runtime_name,
            status="running",
            details={"worker_id": worker_id, "job_types": sorted(TELEGRAM_JOB_TYPES), "pid": os.getpid()},
        )
        while True:
            cycle_started_at = datetime.now(timezone.utc)
            backlog_before = await collect_backlog_snapshot(allowed_types=TELEGRAM_JOB_TYPES)
            metrics = await run_telegram_cycle(
                client=client,
                days=args.days,
                max_posts_per_channel_arg=args.max_posts_per_channel,
                comment_first_delay_hours_arg=args.comment_first_delay_hours,
                comment_interval_hours_arg=args.comment_interval_hours,
                comment_window_hours_arg=args.comment_window_hours,
                job_batch_size_arg=args.job_batch_size,
                retention_days_arg=args.retention_days,
                archive_batch_size_arg=args.archive_batch_size,
                skip_rebuild_graphs=args.skip_rebuild_graphs,
                worker_id=worker_id,
            )
            backlog_after = await collect_backlog_snapshot(allowed_types=TELEGRAM_JOB_TYPES)
            logging.info(
                "Telegram cycle worker_id=%s processed_posts=%s executed_jobs=%s backlog_before=%s backlog_after=%s",
                worker_id,
                metrics.processed_posts,
                metrics.executed_jobs,
                backlog_before,
                backlog_after,
            )
            if not args.daemon:
                return
            elapsed = (datetime.now(timezone.utc) - cycle_started_at).total_seconds()
            poll_seconds = await get_telegram_poll_seconds(cli_override=args.poll_seconds)
            await sleep_until_next_telegram_cycle(
                target_seconds=max(1, int(poll_seconds - elapsed)),
            )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await persist_runtime_heartbeat(
            runtime_name=TELEGRAM_PIPELINE_RUNTIME.runtime_name,
            status="stopped",
            details={"worker_id": worker_id, "job_types": sorted(TELEGRAM_JOB_TYPES), "pid": os.getpid()},
        )
        try:
            await with_session_lock_retry(lambda: client.disconnect(), op_name="client.disconnect")
        except sqlite3.OperationalError as exc:
            if is_session_locked_error(exc):
                logging.warning("Telethon session is locked during disconnect, ignored: %r", exc)
            else:
                raise


async def _heartbeat_loop(*, worker_id: str, jobs_provider) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await persist_runtime_heartbeat(
            runtime_name=TELEGRAM_PIPELINE_RUNTIME.runtime_name,
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
