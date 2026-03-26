from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import Channel, Post
from db.session import AsyncSessionLocal
from services.TGqueries import update_post_comments
from services.ingestion_core import IngestionContext, IngestionCore, IngestionOptions
from services.pipeline_runtime import (
    TELEGRAM_JOB_TYPES,
    _clamp_positive_int,
    _get_active_channels,
    _get_last_tg_message_id_for_channel,
    _rebuild_event_process_graphs,
    _resolve_setting_value,
    _schedule_post_jobs,
    build_tg_client,
    build_worker_id,
    collect_backlog_snapshot,
    configure_logging,
    count_incomplete_link_jobs,
    enqueue_daily_retention_jobs,
    get_telegram_poll_seconds,
    is_session_locked_error,
    retention_scheduler_enabled,
    run_telegram_jobs,
    run_telegram_link_jobs_until_idle,
    sleep_until_next_telegram_cycle,
    with_session_lock_retry,
)
from services.runtime_heartbeat import HEARTBEAT_INTERVAL_SECONDS, persist_runtime_heartbeat
from services.runtime_topology import TELEGRAM_PIPELINE_RUNTIME
from services.settings_defaults import get_default_setting
from services.settings_store import get_all_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InlineCommentCycleMetrics:
    processed_posts: int
    executed_jobs: int
    immediate_comment_attempts: int
    immediate_comment_successes: int
    immediate_comment_failures: int


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Telegram ingestion pipeline with immediate comment collection after each saved post."
    )
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


async def _process_channel_inline_comments(
    client,
    channel: Channel,
    *,
    since_utc: datetime,
    max_posts: int,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    comment_schedule_jitter_seconds: int,
) -> tuple[int, int, int, int]:
    logger.info("Parsing channel @%s since %s", channel.username, since_utc.isoformat())
    async with AsyncSessionLocal() as session:
        channel_last_tg_msg_id = await _get_last_tg_message_id_for_channel(session=session, channel_id=channel.id)

    core = IngestionCore(tg_client=client, session_factory=AsyncSessionLocal)
    options = IngestionOptions(
        since_utc=since_utc,
        max_posts=max_posts,
        min_tg_message_id_exclusive=channel_last_tg_msg_id,
        resolve_album_representative=True,
    )

    immediate_attempts = 0
    immediate_successes = 0
    immediate_failures = 0

    async def _on_post_saved(session, post: Post, ctx: IngestionContext) -> None:
        nonlocal immediate_attempts, immediate_successes, immediate_failures

        await _schedule_post_jobs(
            session,
            post=post,
            comment_first_delay_hours=comment_first_delay_hours,
            comment_interval_hours=comment_interval_hours,
            comment_window_hours=comment_window_hours,
            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
        )
        logger.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, ctx.message.id, channel.username)

        immediate_attempts += 1
        nested = await session.begin_nested()
        try:
            result = await update_post_comments(session, post.id, tg_client=client)
            status = str(result.get("status") or "unknown")
            if status in {"ok", "unchanged", "no_discussion"}:
                await nested.commit()
                immediate_successes += 1
            else:
                await nested.rollback()
                immediate_failures += 1
            logger.info(
                "Immediate comments post_id=%s tg_msg_id=%s channel=@%s status=%s result=%s",
                post.id,
                ctx.message.id,
                channel.username,
                status,
                result,
            )
        except Exception:
            await nested.rollback()
            immediate_failures += 1
            logger.exception(
                "Immediate comments failed marker=inline_comments_unexpected post_id=%s tg_msg_id=%s channel=@%s",
                post.id,
                ctx.message.id,
                channel.username,
            )

    async with client.operation_lock:
        result = await core.ingest_channel(channel=channel, options=options, on_post_saved=_on_post_saved)
    logger.info(
        "Finished @%s processed_posts=%s stopped_reason=%s immediate_attempts=%s immediate_successes=%s immediate_failures=%s",
        channel.username,
        result.processed_posts,
        result.stopped_reason,
        immediate_attempts,
        immediate_successes,
        immediate_failures,
    )
    return result.processed_posts, immediate_attempts, immediate_successes, immediate_failures


async def run_inline_comment_cycle(
    *,
    client,
    days: int,
    max_posts_per_channel_arg: int,
    comment_first_delay_hours_arg: int,
    comment_interval_hours_arg: int,
    comment_window_hours_arg: int,
    job_batch_size_arg: int,
    retention_days_arg: int,
    archive_batch_size_arg: int,
    skip_rebuild_graphs: bool,
    worker_id: str,
) -> InlineCommentCycleMetrics:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    ingest_settings = effective_settings.get("ingest", {})
    jobs_settings = effective_settings.get("jobs", {})
    retention_settings = effective_settings.get("retention", {})
    lookback_days = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("lookback_days"),
            cli_value=days,
            fallback=get_default_setting("ingest", "lookback_days"),
        )
    )
    since_utc = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    max_posts_per_channel = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("max_posts_per_channel"),
            cli_value=max_posts_per_channel_arg,
            fallback=get_default_setting("ingest", "max_posts_per_channel"),
        )
    )
    comment_first_delay_hours = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("comment_first_delay_hours"),
            cli_value=comment_first_delay_hours_arg,
            fallback=get_default_setting("ingest", "comment_first_delay_hours"),
        )
    )
    comment_interval_hours = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("comment_interval_hours"),
            cli_value=comment_interval_hours_arg,
            fallback=get_default_setting("ingest", "comment_interval_hours"),
        )
    )
    comment_window_hours = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("comment_window_hours"),
            cli_value=comment_window_hours_arg,
            fallback=get_default_setting("ingest", "comment_window_hours"),
        )
    )
    comment_schedule_jitter_seconds = int(
        _resolve_setting_value(
            settings_value=ingest_settings.get("comment_schedule_jitter_seconds"),
            cli_value=None,
            fallback=get_default_setting("ingest", "comment_schedule_jitter_seconds"),
        )
    )
    job_batch_size = int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("job_batch_size"),
            cli_value=job_batch_size_arg,
            fallback=get_default_setting("jobs", "job_batch_size"),
        )
    )
    collect_comments_quota_per_run = int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("collect_comments_quota_per_run"),
            cli_value=None,
            fallback=get_default_setting("jobs", "collect_comments_quota_per_run"),
        )
    )
    done_retention_days = int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("done_retention_days"),
            cli_value=None,
            fallback=get_default_setting("jobs", "done_retention_days"),
        )
    )
    dead_letter_retention_days = int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("dead_letter_retention_days"),
            cli_value=None,
            fallback=get_default_setting("jobs", "dead_letter_retention_days"),
        )
    )
    cleanup_batch_size = int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("cleanup_batch_size"),
            cli_value=None,
            fallback=get_default_setting("jobs", "cleanup_batch_size"),
        )
    )
    job_worker_concurrency = _clamp_positive_int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("job_worker_concurrency"),
            cli_value=None,
            fallback=get_default_setting("jobs", "job_worker_concurrency"),
        ),
        default=2,
        minimum=1,
        maximum=16,
    )
    retention_days = int(
        _resolve_setting_value(
            settings_value=retention_settings.get("retention_days"),
            cli_value=retention_days_arg,
            fallback=get_default_setting("retention", "retention_days"),
        )
    )
    archive_batch_size = int(
        _resolve_setting_value(
            settings_value=retention_settings.get("archive_batch_size"),
            cli_value=archive_batch_size_arg,
            fallback=get_default_setting("retention", "archive_batch_size"),
        )
    )

    channels = await _get_active_channels()
    total_processed_posts = 0
    immediate_attempts = 0
    immediate_successes = 0
    immediate_failures = 0
    if not channels:
        logger.warning("No active channels found.")
    else:
        for channel in channels:
            try:
                processed, attempts, successes, failures = await _process_channel_inline_comments(
                    client,
                    channel,
                    since_utc=since_utc,
                    max_posts=max_posts_per_channel,
                    comment_first_delay_hours=comment_first_delay_hours,
                    comment_interval_hours=comment_interval_hours,
                    comment_window_hours=comment_window_hours,
                    comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
                )
                total_processed_posts += processed
                immediate_attempts += attempts
                immediate_successes += successes
                immediate_failures += failures
            except Exception as exc:
                logger.exception(
                    "Inline channel processing failed marker=inline_channel_unexpected channel_id=%s channel_username=%s err=%r",
                    channel.id,
                    channel.username,
                    exc,
                )

    link_jobs_executed = await run_telegram_link_jobs_until_idle(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        job_worker_concurrency=job_worker_concurrency,
    )
    incomplete_link_jobs = await count_incomplete_link_jobs()

    if not skip_rebuild_graphs and incomplete_link_jobs > 0:
        logger.info(
            "Skip rebuild: build_post_links queue is not drained yet incomplete_link_jobs=%s",
            incomplete_link_jobs,
        )
    elif not skip_rebuild_graphs and (total_processed_posts > 0 or link_jobs_executed > 0):
        await _rebuild_event_process_graphs(date_from=since_utc, date_to=datetime.now(timezone.utc))
    elif not skip_rebuild_graphs:
        logger.info("Skip rebuild: no new posts or completed link jobs in this cycle.")

    if not retention_scheduler_enabled(effective_settings):
        async with AsyncSessionLocal() as session:
            await enqueue_daily_retention_jobs(
                session,
                effective_settings=effective_settings,
                now=datetime.now(timezone.utc),
                retention_days=retention_days,
                archive_batch_size=archive_batch_size,
                done_retention_days=done_retention_days,
                dead_letter_retention_days=dead_letter_retention_days,
                cleanup_batch_size=cleanup_batch_size,
            )

    executed_jobs = await run_telegram_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        collect_comments_quota_per_run=collect_comments_quota_per_run,
        tg_client=client,
        job_worker_concurrency=job_worker_concurrency,
    )
    return InlineCommentCycleMetrics(
        processed_posts=total_processed_posts,
        executed_jobs=link_jobs_executed + executed_jobs,
        immediate_comment_attempts=immediate_attempts,
        immediate_comment_successes=immediate_successes,
        immediate_comment_failures=immediate_failures,
    )


async def _heartbeat_loop(*, worker_id: str, jobs_provider) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        await persist_runtime_heartbeat(
            runtime_name=TELEGRAM_PIPELINE_RUNTIME.runtime_name,
            status="running",
            details={"worker_id": worker_id, "job_types": jobs_provider(), "pid": os.getpid()},
        )


async def main_async(args: argparse.Namespace) -> None:
    client = build_tg_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    worker_id = build_worker_id("tg-inline-comments")
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
            metrics = await run_inline_comment_cycle(
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
                "Inline Telegram cycle worker_id=%s processed_posts=%s executed_jobs=%s "
                "immediate_comment_attempts=%s immediate_comment_successes=%s immediate_comment_failures=%s "
                "backlog_before=%s backlog_after=%s",
                worker_id,
                metrics.processed_posts,
                metrics.executed_jobs,
                metrics.immediate_comment_attempts,
                metrics.immediate_comment_successes,
                metrics.immediate_comment_failures,
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
