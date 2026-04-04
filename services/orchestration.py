from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from client.telegram import is_session_locked_error, with_session_lock_retry
from db.models import Channel, Post
from db.session import AsyncSessionLocal
from services.TGqueries import update_post_comments
from services.ingestion_core import IngestionContext, IngestionCore, IngestionOptions
from services.pipeline_runtime import (
    AI_JOB_TYPES,
    PRIORITY_BUILD_POST_LINKS,
    TELEGRAM_JOB_TYPES,
    count_incomplete_link_jobs,
    enqueue_comment_refresh_job,
    enqueue_event_report_job,
    enqueue_post_link_job,
    enqueue_post_report_batch_job,
    enqueue_post_report_job,
    enqueue_process_report_job,
    enqueue_rebuild_events_job,
    enqueue_rebuild_processes_job,
    run_ai_cycle,
    run_telegram_cycle,
    run_telegram_jobs,
    run_telegram_link_jobs_until_idle,
)
from services.pipeline_runtime_common import (
    build_tg_client,
    build_worker_id,
    clamp_positive_int,
    collect_backlog_snapshot,
    configure_logging,
    get_ai_poll_seconds,
    get_telegram_poll_seconds,
    resolve_setting_value,
    sleep_until_next_telegram_cycle,
)
from services.pipeline_runtime_support import (
    collect_comments_job_priority,
    get_active_channels,
    get_last_tg_message_id_for_channel,
    rebuild_event_process_graphs,
    schedule_post_jobs,
)
from services.scheduler_dispatch import enqueue_daily_retention_jobs, retention_scheduler_enabled
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
        channel_last_tg_msg_id = await get_last_tg_message_id_for_channel(session=session, channel_id=channel.id)

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

        await schedule_post_jobs(
            session,
            post=post,
            comment_first_delay_hours=comment_first_delay_hours,
            comment_interval_hours=comment_interval_hours,
            comment_window_hours=comment_window_hours,
            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
            priority_build_post_links=PRIORITY_BUILD_POST_LINKS,
            collect_comments_job_priority_fn=collect_comments_job_priority,
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
        resolve_setting_value(
            settings_value=ingest_settings.get("lookback_days"),
            cli_value=days,
            fallback=get_default_setting("ingest", "lookback_days"),
        )
    )
    since_utc = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    max_posts_per_channel = int(
        resolve_setting_value(
            settings_value=ingest_settings.get("max_posts_per_channel"),
            cli_value=max_posts_per_channel_arg,
            fallback=get_default_setting("ingest", "max_posts_per_channel"),
        )
    )
    comment_first_delay_hours = int(
        resolve_setting_value(
            settings_value=ingest_settings.get("comment_first_delay_hours"),
            cli_value=comment_first_delay_hours_arg,
            fallback=get_default_setting("ingest", "comment_first_delay_hours"),
        )
    )
    comment_interval_hours = int(
        resolve_setting_value(
            settings_value=ingest_settings.get("comment_interval_hours"),
            cli_value=comment_interval_hours_arg,
            fallback=get_default_setting("ingest", "comment_interval_hours"),
        )
    )
    comment_window_hours = int(
        resolve_setting_value(
            settings_value=ingest_settings.get("comment_window_hours"),
            cli_value=comment_window_hours_arg,
            fallback=get_default_setting("ingest", "comment_window_hours"),
        )
    )
    comment_schedule_jitter_seconds = int(
        resolve_setting_value(
            settings_value=ingest_settings.get("comment_schedule_jitter_seconds"),
            cli_value=None,
            fallback=get_default_setting("ingest", "comment_schedule_jitter_seconds"),
        )
    )
    job_batch_size = int(
        resolve_setting_value(
            settings_value=jobs_settings.get("job_batch_size"),
            cli_value=job_batch_size_arg,
            fallback=get_default_setting("jobs", "job_batch_size"),
        )
    )
    collect_comments_quota_per_run = int(
        resolve_setting_value(
            settings_value=jobs_settings.get("collect_comments_quota_per_run"),
            cli_value=None,
            fallback=get_default_setting("jobs", "collect_comments_quota_per_run"),
        )
    )
    done_retention_days = int(
        resolve_setting_value(
            settings_value=jobs_settings.get("done_retention_days"),
            cli_value=None,
            fallback=get_default_setting("jobs", "done_retention_days"),
        )
    )
    dead_letter_retention_days = int(
        resolve_setting_value(
            settings_value=jobs_settings.get("dead_letter_retention_days"),
            cli_value=None,
            fallback=get_default_setting("jobs", "dead_letter_retention_days"),
        )
    )
    cleanup_batch_size = int(
        resolve_setting_value(
            settings_value=jobs_settings.get("cleanup_batch_size"),
            cli_value=None,
            fallback=get_default_setting("jobs", "cleanup_batch_size"),
        )
    )
    job_worker_concurrency = clamp_positive_int(
        resolve_setting_value(
            settings_value=jobs_settings.get("job_worker_concurrency"),
            cli_value=None,
            fallback=get_default_setting("jobs", "job_worker_concurrency"),
        ),
        default=2,
        minimum=1,
        maximum=16,
    )
    retention_days = int(
        resolve_setting_value(
            settings_value=retention_settings.get("retention_days"),
            cli_value=retention_days_arg,
            fallback=get_default_setting("retention", "retention_days"),
        )
    )
    archive_batch_size = int(
        resolve_setting_value(
            settings_value=retention_settings.get("archive_batch_size"),
            cli_value=archive_batch_size_arg,
            fallback=get_default_setting("retention", "archive_batch_size"),
        )
    )

    channels = await get_active_channels()
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
        await rebuild_event_process_graphs(
            date_from=since_utc,
            date_to=datetime.now(timezone.utc),
            created_by="telegram-pipeline",
        )
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


__all__ = [
    "AI_JOB_TYPES",
    "TELEGRAM_JOB_TYPES",
    "build_tg_client",
    "build_worker_id",
    "collect_backlog_snapshot",
    "configure_logging",
    "enqueue_comment_refresh_job",
    "enqueue_event_report_job",
    "enqueue_post_link_job",
    "enqueue_post_report_batch_job",
    "enqueue_post_report_job",
    "enqueue_process_report_job",
    "enqueue_rebuild_events_job",
    "enqueue_rebuild_processes_job",
    "get_ai_poll_seconds",
    "get_telegram_poll_seconds",
    "is_session_locked_error",
    "run_ai_cycle",
    "run_inline_comment_cycle",
    "run_telegram_cycle",
    "sleep_until_next_telegram_cycle",
    "with_session_lock_retry",
]
