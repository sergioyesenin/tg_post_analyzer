from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.reporter import TgReportProject
from client.telegram import (
    TelegramClientHandle,
    build_telegram_client,
    is_session_locked_error,
    with_session_lock_retry,
)
from db.models import Channel, Job, JobDeadLetter, Post, Report
from db.session import AsyncSessionLocal
from services.archive import run_archive_retention
from services.auth import write_audit_log
from services.channel_management import resolve_and_upsert_channel
from services.events.build_events import rebuild_events
from services.ingestion_core import IngestionCore, IngestionContext, IngestionOptions
from services.jobs import (
    JobType,
    defer_locked_job,
    enqueue_job,
    fetch_and_lock_jobs,
    get_job_result,
    mark_job_done,
    mark_job_failed,
    requeue_job,
    set_job_result,
)
from services.jobs_retention import run_jobs_retention
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes
from services.reporting import build_event_report_draft, build_post_report, build_process_report_draft
from services.scheduler_dispatch import enqueue_daily_retention_jobs, retention_scheduler_enabled
from services.settings_defaults import get_default_setting
from services.settings_store import get_all_settings, report_config_from_settings
from services.TGqueries import update_post_comments

logger = logging.getLogger(__name__)

PRIORITY_API_REPORT = 1
PRIORITY_API_COMMENT_REFRESH = 1
PRIORITY_API_POST_REPORT = 1
PRIORITY_API_POST_REPORT_BATCH = 5
PRIORITY_BUILD_POST_LINKS = 4
PRIORITY_BUILD_POST_REPORT = 40
PRIORITY_ARCHIVE_RETENTION = 95
PRIORITY_JOBS_RETENTION = 96

TELEGRAM_JOB_TYPES = {
    JobType.ADD_CHANNEL,
    JobType.COLLECT_COMMENTS,
    JobType.REFRESH_COMMENTS,
    JobType.BUILD_POST_LINKS,
    JobType.ARCHIVE_RETENTION,
    JobType.JOBS_RETENTION,
}

AI_JOB_TYPES = {
    JobType.BUILD_POST_REPORT,
    JobType.BUILD_POST_REPORT_BATCH,
    JobType.BUILD_EVENT_REPORT,
    JobType.BUILD_PROCESS_REPORT,
}

SKIP_CHANNEL_IDS: dict[int, str] = {}


@dataclass(frozen=True)
class TelegramCycleMetrics:
    processed_posts: int
    executed_jobs: int


TelegramPipelineClient = TelegramClientHandle


def _clamp_positive_int(value: int | None, *, default: int, minimum: int = 1, maximum: int = 64) -> int:
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(maximum, parsed))


def _resolve_setting_value(*, settings_value, cli_value, fallback):
    if settings_value is not None:
        return settings_value
    if cli_value is not None:
        return cli_value
    return fallback


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


def build_worker_id(prefix: str) -> str:
    return f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def _persist_job_failure_after_exception(
    session: AsyncSession,
    *,
    job_id: int,
    error: str,
    retry_base_seconds: int = 30,
    retry_max_seconds: int = 3600,
) -> bool:
    try:
        await session.rollback()
    except Exception:
        logger.exception("Failed to rollback aborted transaction for job_id=%s", job_id)

    db_job = await session.get(Job, job_id)
    if db_job is None:
        logger.warning("Unable to persist failure state: job_id=%s no longer exists", job_id)
        return False

    try:
        await mark_job_failed(
            session,
            job=db_job,
            error=error,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )
        await session.commit()
        return True
    except Exception:
        await session.rollback()
        logger.exception("Failed to persist failure state for job_id=%s", job_id)
        return False


def build_tg_client(*, session_suffix: str, unique_session_per_run: bool) -> TelegramPipelineClient:
    return build_telegram_client(
        session_suffix=session_suffix,
        unique_session_per_run=unique_session_per_run,
    )


async def collect_backlog_snapshot(*, allowed_types: set[str] | None = None) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        stmt = select(Job.status, func.count()).group_by(Job.status)
        if allowed_types:
            stmt = stmt.where(Job.type.in_(allowed_types))
        rows = (await session.execute(stmt)).all()

        pending_stmt = select(func.min(func.coalesce(Job.retry_at, Job.run_at))).where(Job.status == "pending")
        if allowed_types:
            pending_stmt = pending_stmt.where(Job.type.in_(allowed_types))
        pending_oldest = await session.scalar(pending_stmt)

        dead_stmt = select(func.count()).select_from(JobDeadLetter)
        if allowed_types:
            dead_stmt = dead_stmt.where(JobDeadLetter.type.in_(allowed_types))
        dead_letters = int((await session.scalar(dead_stmt)) or 0)

    counts = {str(status): int(count) for status, count in rows}
    pending_lag_seconds = 0
    if pending_oldest is not None:
        pending_lag_seconds = max(0, int((now_utc - pending_oldest).total_seconds()))
    return {
        "pending": int(counts.get("pending", 0)),
        "running": int(counts.get("running", 0)),
        "done": int(counts.get("done", 0)),
        "failed": int(counts.get("failed", 0)),
        "dead_letters": dead_letters,
        "pending_lag_seconds": pending_lag_seconds,
    }


async def has_due_priority_job(*, allowed_types: set[str], max_priority: int) -> bool:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Job.id)
            .where(Job.status == "pending")
            .where(Job.type.in_(allowed_types))
            .where(Job.priority <= max_priority)
            .where(func.coalesce(Job.retry_at, Job.run_at) <= now_utc)
            .limit(1)
        )
        job_id = await session.scalar(stmt)
    return job_id is not None


async def get_telegram_poll_seconds(*, cli_override: int | None, default: int | None = None) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    ingest_settings = effective_settings.get("ingest", {})
    resolved = _resolve_setting_value(
        settings_value=ingest_settings.get("poll_seconds"),
        cli_value=cli_override,
        fallback=get_default_setting("ingest", "poll_seconds") if default is None else default,
    )
    return max(5, int(resolved))


async def get_ai_poll_seconds(*, cli_override: int | None, default: int | None = None) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    jobs_settings = effective_settings.get("jobs", {})
    resolved = _resolve_setting_value(
        settings_value=jobs_settings.get("ai_poll_seconds"),
        cli_value=cli_override,
        fallback=get_default_setting("jobs", "ai_poll_seconds") if default is None else default,
    )
    return max(5, int(resolved))


async def sleep_until_next_telegram_cycle(*, target_seconds: int, wake_priority_threshold: int = PRIORITY_API_COMMENT_REFRESH) -> None:
    remaining = max(1, int(target_seconds))
    while remaining > 0:
        if await has_due_priority_job(
            allowed_types={JobType.REFRESH_COMMENTS},
            max_priority=wake_priority_threshold,
        ):
            return
        chunk = min(1, remaining)
        await asyncio.sleep(chunk)
        remaining -= chunk


async def enqueue_comment_refresh_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int = PRIORITY_API_COMMENT_REFRESH,
    source: str = "api",
) -> Job | None:
    return await enqueue_job(
        session,
        job_type=JobType.REFRESH_COMMENTS,
        payload={"post_id": post_id, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=8,
        dedupe_key=None,
    )


async def enqueue_event_report_job(
    session: AsyncSession,
    *,
    event_id: int,
    priority: int = PRIORITY_API_REPORT,
    source: str = "api",
) -> Job | None:
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_EVENT_REPORT,
        payload={"event_id": event_id, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=None,
    )


async def enqueue_process_report_job(
    session: AsyncSession,
    *,
    process_id: int,
    priority: int = PRIORITY_API_REPORT,
    source: str = "api",
) -> Job | None:
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_PROCESS_REPORT,
        payload={"process_id": process_id, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=None,
    )


async def enqueue_post_report_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int = PRIORITY_API_POST_REPORT,
    source: str = "api",
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT,
        payload={"post_id": post_id, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=dedupe_key,
    )


async def enqueue_post_report_batch_job(
    session: AsyncSession,
    *,
    filters: dict,
    priority: int = PRIORITY_API_POST_REPORT_BATCH,
    source: str = "api",
) -> Job | None:
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT_BATCH,
        payload={"filters": filters, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=3,
        dedupe_key=None,
    )


async def schedule_due_post_report_jobs(*, min_age_hours: int, limit: int) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(min_age_hours)))
    queued = 0
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Post.id)
            .outerjoin(Report, Report.post_id == Post.id)
            .where(Post.date <= threshold)
            .where(Post.last_comments_scan_at.is_not(None))
            .where(Report.id.is_(None))
            .order_by(Post.date.asc(), Post.id.asc())
            .limit(limit)
        )
        post_ids = [int(row[0]) for row in (await session.execute(stmt)).all()]
        now_utc = datetime.now(timezone.utc)
        for post_id in post_ids:
            job = await enqueue_job(
                session,
                job_type=JobType.BUILD_POST_REPORT,
                payload={"post_id": post_id, "source": "scheduler"},
                run_at=now_utc,
                priority=PRIORITY_BUILD_POST_REPORT,
                max_attempts=5,
                dedupe_key=f"build_post_report:{post_id}",
            )
            if job is not None:
                queued += 1
        await session.commit()
    return queued


async def dispatch_post_report_batch(
    session: AsyncSession,
    *,
    filters: dict,
) -> dict:
    channel_ids = [int(value) for value in (filters.get("channel_ids") or [])]
    categories = [str(value) for value in (filters.get("categories") or []) if str(value).strip()]
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    min_comments = filters.get("min_comments")
    limit = max(1, min(500, int(filters.get("limit") or 100)))

    stmt = (
        select(Post.id)
        .join(Channel, Channel.id == Post.channel_id)
        .order_by(Post.date.desc(), Post.id.desc())
    )
    conditions = []
    if channel_ids:
        conditions.append(Post.channel_id.in_(channel_ids))
    if categories:
        conditions.append(Channel.category.in_(categories))
    if date_from is not None:
        conditions.append(Post.date >= datetime.fromisoformat(str(date_from)))
    if date_to is not None:
        conditions.append(Post.date <= datetime.fromisoformat(str(date_to)))
    if min_comments is not None:
        conditions.append(Post.comments_count >= int(min_comments))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    post_ids = [int(row[0]) for row in (await session.execute(stmt.limit(limit))).all()]
    queued_job_ids: list[int] = []
    skipped_post_ids: list[int] = []
    for post_id in post_ids:
        job = await enqueue_post_report_job(
            session,
            post_id=post_id,
            priority=PRIORITY_BUILD_POST_REPORT,
            source="batch",
            dedupe_key=f"build_post_report:{post_id}",
        )
        if job is None:
            skipped_post_ids.append(post_id)
            continue
        queued_job_ids.append(int(job.id))

    return {
        "status": "queued",
        "matched_posts": len(post_ids),
        "queued_jobs": len(queued_job_ids),
        "skipped_existing": len(skipped_post_ids),
        "post_ids": post_ids,
        "job_ids": queued_job_ids,
        "filters": filters,
    }


async def _get_active_channels() -> list[Channel]:
    async with AsyncSessionLocal() as session:
        stmt = select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id.asc())
        return list((await session.execute(stmt)).scalars().all())


async def _get_last_tg_message_id_for_channel(*, session: AsyncSession, channel_id: int) -> int:
    stmt = select(func.max(Post.tg_message_id)).where(Post.channel_id == channel_id)
    last_value = (await session.execute(stmt)).scalar_one_or_none()
    if isinstance(last_value, int) and last_value > 0:
        return last_value
    return 0


def _collect_comments_job_priority(*, post: Post, scan_index: int) -> int:
    priority = 20
    if scan_index == 0:
        priority -= 2
    elif scan_index == 1:
        priority -= 1

    comments = int(post.comments_count or 0)
    if comments >= 100:
        priority -= 4
    elif comments >= 50:
        priority -= 3
    elif comments >= 20:
        priority -= 2
    elif comments >= 5:
        priority -= 1

    views = int(post.views or 0)
    if views >= 5000:
        priority -= 2
    elif views >= 1000:
        priority -= 1

    if isinstance(post.involvement, (int, float)):
        if post.involvement >= 0.20:
            priority -= 2
        elif post.involvement >= 0.10:
            priority -= 1

    return max(5, min(90, priority))


def split_jobs_for_telegram_worker(jobs: list[Job]) -> tuple[list[Job], list[Job]]:
    comment_jobs: list[Job] = []
    other_jobs: list[Job] = []
    for job in jobs:
        if job.type in {JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS}:
            comment_jobs.append(job)
        else:
            other_jobs.append(job)
    return comment_jobs, other_jobs


async def _schedule_post_jobs(
    session: AsyncSession,
    *,
    post: Post,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    comment_schedule_jitter_seconds: int,
) -> None:
    await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_LINKS,
        payload={"post_id": post.id},
        run_at=datetime.now(timezone.utc),
        priority=PRIORITY_BUILD_POST_LINKS,
        max_attempts=5,
        dedupe_key=f"build_post_links:{post.id}",
    )

    first_comment_at = post.date + timedelta(hours=comment_first_delay_hours)
    comment_until = post.date + timedelta(hours=comment_window_hours)
    current = first_comment_at
    scan_index = 0
    while current <= comment_until:
        jitter_seconds = random.randint(0, max(0, int(comment_schedule_jitter_seconds)))
        scheduled_at = current + timedelta(seconds=jitter_seconds)
        ts = int(scheduled_at.timestamp())
        await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": post.id, "scan_index": scan_index, "source": "scheduler"},
            run_at=scheduled_at,
            priority=_collect_comments_job_priority(post=post, scan_index=scan_index),
            max_attempts=8,
            dedupe_key=f"collect_comments:{post.id}:{ts}",
        )
        current = current + timedelta(hours=comment_interval_hours)
        scan_index += 1


async def _process_channel(
    client: TelegramPipelineClient,
    channel: Channel,
    *,
    since_utc: datetime,
    max_posts: int,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    comment_schedule_jitter_seconds: int,
) -> int:
    if channel.id in SKIP_CHANNEL_IDS:
        logger.info("Skip channel id=%s (@%s): excluded by config", channel.id, channel.username)
        return 0

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

    async def _on_post_saved(session: AsyncSession, post: Post, ctx: IngestionContext) -> None:
        await _schedule_post_jobs(
            session,
            post=post,
            comment_first_delay_hours=comment_first_delay_hours,
            comment_interval_hours=comment_interval_hours,
            comment_window_hours=comment_window_hours,
            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
        )
        logger.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, ctx.message.id, channel.username)

    async with client.operation_lock:
        result = await core.ingest_channel(channel=channel, options=options, on_post_saved=_on_post_saved)
    logger.info(
        "Finished @%s processed_posts=%s stopped_reason=%s",
        channel.username,
        result.processed_posts,
        result.stopped_reason,
    )
    return result.processed_posts


async def _rebuild_event_process_graphs(*, date_from: datetime, date_to: datetime) -> None:
    async with AsyncSessionLocal() as session:
        rebuilt_events = await rebuild_events(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="telegram-pipeline",
        )
        await session.commit()
    logger.info("Rebuilt events=%s for %s..%s", rebuilt_events, date_from.isoformat(), date_to.isoformat())

    async with AsyncSessionLocal() as session:
        rebuilt_process_edges = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="telegram-pipeline",
        )
        await session.commit()
    logger.info(
        "Rebuilt process_edges=%s for %s..%s",
        rebuilt_process_edges,
        date_from.isoformat(),
        date_to.isoformat(),
    )


async def _run_link_job(*, job: Job, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        post = await session.get(Post, int(payload.get("post_id")))
        if post is None:
            await mark_job_done(session, job=db_job)
            await session.commit()
            return 0
        try:
            pipeline = NoLlmLinkingPipeline.build_default()
            result = await pipeline.run_for_post(session, post)
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info(
                "Job build_post_links post_id=%s verified=%s rejected=%s candidates=%s worker_id=%s",
                post.id,
                result.links_verified,
                result.links_rejected,
                result.candidates_checked,
                worker_id,
            )
            return 1
        except Exception as exc:
            await _persist_job_failure_after_exception(
                session,
                job_id=db_job.id,
                error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
            )
            logger.exception(
                "Job failed marker=job_unexpected op=build_post_links job_id=%s worker_id=%s err=%r",
                db_job.id,
                worker_id,
                exc,
            )
            return 0


async def _run_add_channel_job(*, job: Job, tg_client: TelegramPipelineClient, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        requested_username = str(payload.get("username") or "").strip()
        actor_user_id = payload.get("requested_by_user_id")
        try:
            async with tg_client.operation_lock:
                channel, result = await resolve_and_upsert_channel(
                    tg_client=tg_client,
                    session=session,
                    raw_username=requested_username,
                )
            await write_audit_log(
                session,
                action="channels.add.executed",
                actor_user_id=int(actor_user_id) if actor_user_id is not None else None,
                target_type="channel",
                target_id=str(channel.id),
                details={"username": channel.username, "title": channel.title, "job_id": db_job.id, "status": result["status"]},
            )
            set_job_result(db_job, result)
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info(
                "Job add_channel username=@%s status=%s channel_id=%s worker_id=%s",
                channel.username,
                result["status"],
                channel.id,
                worker_id,
            )
            return 1
        except Exception as exc:
            set_job_result(
                db_job,
                {
                    "status": "failed",
                    "job_id": db_job.id,
                    "username": requested_username,
                    "error": str(exc),
                },
            )
            try:
                await mark_job_failed(
                    session,
                    job=db_job,
                    error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
                    retry_base_seconds=120,
                    retry_max_seconds=1800,
                )
                await session.commit()
            except Exception:
                await _persist_job_failure_after_exception(
                    session,
                    job_id=db_job.id,
                    error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
                )
            logger.exception(
                "Job failed marker=job_unexpected op=add_channel job_id=%s worker_id=%s err=%r",
                db_job.id,
                worker_id,
                exc,
            )
            return 0


async def _run_maintenance_job(*, job: Job, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        try:
            if db_job.type == JobType.ARCHIVE_RETENTION:
                result = await run_archive_retention(
                    session,
                    retention_days=int(payload.get("retention_days", get_default_setting("retention", "retention_days"))),
                    batch_limit=int(payload.get("batch_limit", get_default_setting("retention", "archive_batch_size"))),
                )
            elif db_job.type == JobType.JOBS_RETENTION:
                result = await run_jobs_retention(
                    session,
                    done_retention_days=int(payload.get("done_retention_days", get_default_setting("jobs", "done_retention_days"))),
                    dead_letter_retention_days=int(
                        payload.get("dead_letter_retention_days", get_default_setting("jobs", "dead_letter_retention_days"))
                    ),
                    batch_limit=int(payload.get("batch_limit", get_default_setting("jobs", "cleanup_batch_size"))),
                )
            else:
                raise ValueError(f"Unsupported maintenance job type: {db_job.type}")
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info("Job %s status=ok details=%s worker_id=%s", db_job.type, result, worker_id)
            return 1
        except Exception as exc:
            await _persist_job_failure_after_exception(
                session,
                job_id=db_job.id,
                error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
            )
            logger.exception(
                "Job failed marker=job_unexpected op=maintenance job_id=%s worker_id=%s err=%r",
                db_job.id,
                worker_id,
                exc,
            )
            return 0


async def _run_comment_job(
    *,
    job: Job,
    tg_client: TelegramPipelineClient,
    worker_id: str,
    cc_sleep_min_ms: int,
    cc_sleep_max_ms: int,
    collect_comments_processed: int,
    collect_comments_quota_per_run: int,
    collect_comments_global_cooldown_until: datetime | None,
    collect_comments_flood_streak: int,
) -> tuple[int, int, datetime | None, int, bool]:
    executed = 0
    should_break = False
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return executed, collect_comments_processed, collect_comments_global_cooldown_until, collect_comments_flood_streak, should_break
        try:
            payload = db_job.payload_json or {}
            source = str(payload.get("source") or "scheduler")
            if collect_comments_processed >= collect_comments_quota_per_run:
                await defer_locked_job(
                    session,
                    job=db_job,
                    retry_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                    reason=f"{db_job.type}:quota_deferred",
                    preserve_attempt_budget=True,
                )
                await session.commit()
                return executed, collect_comments_processed, collect_comments_global_cooldown_until, collect_comments_flood_streak, should_break

            now = datetime.now(timezone.utc)
            if collect_comments_global_cooldown_until is not None and now < collect_comments_global_cooldown_until:
                await asyncio.sleep((collect_comments_global_cooldown_until - now).total_seconds())

            post_id = int(payload.get("post_id"))
            collect_comments_processed += 1
            async with tg_client.operation_lock:
                result = await update_post_comments(session, post_id, tg_client=tg_client)
            status = str(result.get("status") or "unknown")
            logger.info("Job %s post_id=%s status=%s worker_id=%s", db_job.type, post_id, status, worker_id)
            if status == "discussion_error" and result.get("error") == "comment_reconciliation_incomplete":
                await session.rollback()
                db_job = await session.get(Job, job.id)
                if db_job is None:
                    return executed, collect_comments_processed, collect_comments_global_cooldown_until, collect_comments_flood_streak, should_break

            if status in {"ok", "unchanged"}:
                collect_comments_flood_streak = 0
                set_job_result(db_job, result)
                await mark_job_done(session, job=db_job)
                await session.commit()
                executed += 1
            elif status == "no_discussion":
                collect_comments_flood_streak = 0
                await session.execute(
                    text(
                        "DELETE FROM jobs "
                        "WHERE type IN (:collect_type, :refresh_type) "
                        "AND status = 'pending' "
                        "AND id <> :job_id "
                        "AND payload_json->>'post_id' = :post_id"
                    ),
                    {
                        "collect_type": JobType.COLLECT_COMMENTS,
                        "refresh_type": JobType.REFRESH_COMMENTS,
                        "job_id": db_job.id,
                        "post_id": str(post_id),
                    },
                )
                set_job_result(db_job, result)
                await mark_job_done(session, job=db_job)
                await session.commit()
                executed += 1
            elif status == "flood_wait":
                wait_seconds = int(result.get("wait_seconds") or 30)
                set_job_result(db_job, result)
                now_utc = datetime.now(timezone.utc)
                retry_at = now_utc + timedelta(seconds=max(60, wait_seconds * 4))
                collect_comments_flood_streak += 1
                base_cooldown_sec = max(300, wait_seconds * 6)
                if collect_comments_flood_streak >= 2:
                    adaptive_cooldown_sec = min(1800, base_cooldown_sec * (2 ** (collect_comments_flood_streak - 1)))
                else:
                    adaptive_cooldown_sec = base_cooldown_sec
                collect_comments_global_cooldown_until = now_utc + timedelta(seconds=adaptive_cooldown_sec)
                await requeue_job(
                    session,
                    job=db_job,
                    retry_at=max(retry_at, collect_comments_global_cooldown_until),
                    error=f"{db_job.type}:flood_wait:{wait_seconds}",
                )
                await session.execute(
                    text(
                        "UPDATE jobs "
                        "SET retry_at = :retry_at "
                        "WHERE type IN (:collect_type, :refresh_type) "
                        "AND status = 'pending' "
                        "AND id <> :job_id "
                        "AND (retry_at IS NULL OR retry_at < :retry_at)"
                    ),
                    {
                        "retry_at": collect_comments_global_cooldown_until,
                        "collect_type": JobType.COLLECT_COMMENTS,
                        "refresh_type": JobType.REFRESH_COMMENTS,
                        "job_id": db_job.id,
                    },
                )
                await session.commit()
                should_break = True
            elif status in {"entity_error", "rpc_error", "discussion_error"}:
                collect_comments_flood_streak = 0
                set_job_result(db_job, result)
                await mark_job_failed(
                    session,
                    job=db_job,
                    error=f"{db_job.type}:{status}",
                    retry_base_seconds=120,
                    retry_max_seconds=7200,
                )
                await session.commit()
            elif status == "not_found":
                collect_comments_flood_streak = 0
                set_job_result(db_job, result)
                await mark_job_done(session, job=db_job)
                await session.commit()
                executed += 1
            else:
                collect_comments_flood_streak = 0
                set_job_result(db_job, result)
                await mark_job_failed(
                    session,
                    job=db_job,
                    error=f"{db_job.type}:unexpected_status:{status}",
                    retry_base_seconds=120,
                    retry_max_seconds=7200,
                )
                await session.commit()

            if cc_sleep_max_ms > 0 and not should_break:
                await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
        except Exception as exc:
            await _persist_job_failure_after_exception(
                session,
                job_id=db_job.id,
                error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
            )
            logger.exception(
                "Job failed marker=job_unexpected op=comment_job job_id=%s worker_id=%s err=%r",
                db_job.id,
                worker_id,
                exc,
            )
    return executed, collect_comments_processed, collect_comments_global_cooldown_until, collect_comments_flood_streak, should_break


async def run_telegram_link_jobs_until_idle(
    *,
    job_batch_size: int,
    worker_id: str,
    job_worker_concurrency: int,
) -> int:
    executed = 0
    parallelism = _clamp_positive_int(job_worker_concurrency, default=2, minimum=1, maximum=16)

    while True:
        async with AsyncSessionLocal() as session:
            jobs = await fetch_and_lock_jobs(
                session,
                worker_id=worker_id,
                limit=job_batch_size,
                allowed_types={JobType.BUILD_POST_LINKS},
            )
            await session.commit()

        if not jobs:
            return executed

        semaphore = asyncio.Semaphore(parallelism)

        async def _run_one(job: Job) -> int:
            async with semaphore:
                return await _run_link_job(job=job, worker_id=worker_id)

        executed += sum(await asyncio.gather(*[_run_one(job) for job in jobs]))


async def count_incomplete_link_jobs() -> int:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(func.count())
            .select_from(Job)
            .where(Job.type == JobType.BUILD_POST_LINKS)
            .where(Job.status.in_(("pending", "running")))
        )
        return int((await session.scalar(stmt)) or 0)


async def run_telegram_jobs(
    *,
    job_batch_size: int,
    worker_id: str,
    collect_comments_quota_per_run: int,
    tg_client: TelegramPipelineClient,
    job_worker_concurrency: int,
) -> int:
    executed = 0
    collect_comments_global_cooldown_until: datetime | None = None
    collect_comments_processed = 0
    collect_comments_flood_streak = 0

    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
        jobs = await fetch_and_lock_jobs(
            session,
            worker_id=worker_id,
            limit=job_batch_size,
            allowed_types=TELEGRAM_JOB_TYPES,
        )
        await session.commit()

    ingest_settings = effective_settings.get("ingest", {})
    cc_sleep_min_ms = int(ingest_settings.get("collect_comments_sleep_min_ms", get_default_setting("ingest", "collect_comments_sleep_min_ms")))
    cc_sleep_max_ms = int(ingest_settings.get("collect_comments_sleep_max_ms", get_default_setting("ingest", "collect_comments_sleep_max_ms")))
    if cc_sleep_max_ms < cc_sleep_min_ms:
        cc_sleep_max_ms = cc_sleep_min_ms

    comment_jobs, other_jobs = split_jobs_for_telegram_worker(jobs)

    if other_jobs:
        parallelism = _clamp_positive_int(job_worker_concurrency, default=2, minimum=1, maximum=16)
        semaphore = asyncio.Semaphore(parallelism)

        async def _run_other(job: Job) -> int:
            async with semaphore:
                if job.type == JobType.ADD_CHANNEL:
                    return await _run_add_channel_job(job=job, tg_client=tg_client, worker_id=worker_id)
                if job.type == JobType.BUILD_POST_LINKS:
                    return await _run_link_job(job=job, worker_id=worker_id)
                return await _run_maintenance_job(job=job, worker_id=worker_id)

        executed += sum(await asyncio.gather(*[_run_other(job) for job in other_jobs]))

    for job in comment_jobs:
        result = await _run_comment_job(
            job=job,
            tg_client=tg_client,
            worker_id=worker_id,
            cc_sleep_min_ms=cc_sleep_min_ms,
            cc_sleep_max_ms=cc_sleep_max_ms,
            collect_comments_processed=collect_comments_processed,
            collect_comments_quota_per_run=collect_comments_quota_per_run,
            collect_comments_global_cooldown_until=collect_comments_global_cooldown_until,
            collect_comments_flood_streak=collect_comments_flood_streak,
        )
        delta, collect_comments_processed, collect_comments_global_cooldown_until, collect_comments_flood_streak, should_break = result
        executed += delta
        if should_break:
            break

    return executed


async def run_ai_jobs(*, job_batch_size: int, worker_id: str, job_worker_concurrency: int) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
        jobs = await fetch_and_lock_jobs(
            session,
            worker_id=worker_id,
            limit=job_batch_size,
            allowed_types=AI_JOB_TYPES,
        )
        await session.commit()

    report_project = TgReportProject(llm_model="ollama/llama3:8b-instruct-q4_K_M")
    report_config = report_config_from_settings(effective_settings)
    parallelism = _clamp_positive_int(job_worker_concurrency, default=2, minimum=1, maximum=16)
    semaphore = asyncio.Semaphore(parallelism)

    async def _run_one(job: Job) -> int:
        async with semaphore:
            async with AsyncSessionLocal() as session:
                db_job = await session.get(Job, job.id)
                if db_job is None:
                    return 0
                payload = db_job.payload_json or {}
                try:
                    if db_job.type == JobType.BUILD_POST_REPORT:
                        result = await build_post_report(
                            session,
                            post_id=int(payload.get("post_id")),
                            report_project=report_project,
                            report_config=report_config,
                        )
                    elif db_job.type == JobType.BUILD_POST_REPORT_BATCH:
                        result = await dispatch_post_report_batch(
                            session,
                            filters=dict(payload.get("filters") or {}),
                        )
                    elif db_job.type == JobType.BUILD_EVENT_REPORT:
                        result = await build_event_report_draft(session, event_id=int(payload.get("event_id")))
                    elif db_job.type == JobType.BUILD_PROCESS_REPORT:
                        result = await build_process_report_draft(session, process_id=int(payload.get("process_id")))
                    else:
                        raise ValueError(f"Unsupported AI job type: {db_job.type}")
                    set_job_result(db_job, result)
                    await mark_job_done(session, job=db_job)
                    await session.commit()
                    logger.info("Job %s status=%s worker_id=%s", db_job.type, result.get("status"), worker_id)
                    return 1
                except Exception as exc:
                    await _persist_job_failure_after_exception(
                        session,
                        job_id=db_job.id,
                        error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
                    )
                    logger.exception(
                        "Job failed marker=job_unexpected op=ai_job job_id=%s worker_id=%s err=%r",
                        db_job.id,
                        worker_id,
                        exc,
                    )
                    return 0

    return sum(await asyncio.gather(*[_run_one(job) for job in jobs]))


async def run_telegram_cycle(
    *,
    client: TelegramPipelineClient,
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
) -> TelegramCycleMetrics:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    ingest_settings = effective_settings.get("ingest", {})
    jobs_settings = effective_settings.get("jobs", {})
    retention_settings = effective_settings.get("retention", {})
    lookback_days = int(_resolve_setting_value(
        settings_value=ingest_settings.get("lookback_days"),
        cli_value=days,
        fallback=get_default_setting("ingest", "lookback_days"),
    ))
    since_utc = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    max_posts_per_channel = int(_resolve_setting_value(
        settings_value=ingest_settings.get("max_posts_per_channel"),
        cli_value=max_posts_per_channel_arg,
        fallback=get_default_setting("ingest", "max_posts_per_channel"),
    ))
    comment_first_delay_hours = int(_resolve_setting_value(
        settings_value=ingest_settings.get("comment_first_delay_hours"),
        cli_value=comment_first_delay_hours_arg,
        fallback=get_default_setting("ingest", "comment_first_delay_hours"),
    ))
    comment_interval_hours = int(_resolve_setting_value(
        settings_value=ingest_settings.get("comment_interval_hours"),
        cli_value=comment_interval_hours_arg,
        fallback=get_default_setting("ingest", "comment_interval_hours"),
    ))
    comment_window_hours = int(_resolve_setting_value(
        settings_value=ingest_settings.get("comment_window_hours"),
        cli_value=comment_window_hours_arg,
        fallback=get_default_setting("ingest", "comment_window_hours"),
    ))
    comment_schedule_jitter_seconds = int(_resolve_setting_value(
        settings_value=ingest_settings.get("comment_schedule_jitter_seconds"),
        cli_value=None,
        fallback=get_default_setting("ingest", "comment_schedule_jitter_seconds"),
    ))
    job_batch_size = int(_resolve_setting_value(
        settings_value=jobs_settings.get("job_batch_size"),
        cli_value=job_batch_size_arg,
        fallback=get_default_setting("jobs", "job_batch_size"),
    ))
    collect_comments_quota_per_run = int(_resolve_setting_value(
        settings_value=jobs_settings.get("collect_comments_quota_per_run"),
        cli_value=None,
        fallback=get_default_setting("jobs", "collect_comments_quota_per_run"),
    ))
    done_retention_days = int(_resolve_setting_value(
        settings_value=jobs_settings.get("done_retention_days"),
        cli_value=None,
        fallback=get_default_setting("jobs", "done_retention_days"),
    ))
    dead_letter_retention_days = int(_resolve_setting_value(
        settings_value=jobs_settings.get("dead_letter_retention_days"),
        cli_value=None,
        fallback=get_default_setting("jobs", "dead_letter_retention_days"),
    ))
    cleanup_batch_size = int(_resolve_setting_value(
        settings_value=jobs_settings.get("cleanup_batch_size"),
        cli_value=None,
        fallback=get_default_setting("jobs", "cleanup_batch_size"),
    ))
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
    retention_days = int(_resolve_setting_value(
        settings_value=retention_settings.get("retention_days"),
        cli_value=retention_days_arg,
        fallback=get_default_setting("retention", "retention_days"),
    ))
    archive_batch_size = int(_resolve_setting_value(
        settings_value=retention_settings.get("archive_batch_size"),
        cli_value=archive_batch_size_arg,
        fallback=get_default_setting("retention", "archive_batch_size"),
    ))

    channels = await _get_active_channels()
    total_processed_posts = 0
    if not channels:
        logger.warning("No active channels found.")
    else:
        for channel in channels:
            try:
                total_processed_posts += await _process_channel(
                    client,
                    channel,
                    since_utc=since_utc,
                    max_posts=max_posts_per_channel,
                    comment_first_delay_hours=comment_first_delay_hours,
                    comment_interval_hours=comment_interval_hours,
                    comment_window_hours=comment_window_hours,
                    comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
                )
            except Exception as exc:
                logger.exception(
                    "Channel processing failed marker=channel_unexpected channel_id=%s channel_username=%s err=%r",
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
    return TelegramCycleMetrics(
        processed_posts=total_processed_posts,
        executed_jobs=link_jobs_executed + executed_jobs,
    )


async def run_ai_cycle(*, worker_id: str, job_batch_size_arg: int, job_worker_concurrency_arg: int, post_report_age_hours_arg: int, scheduler_limit_arg: int) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    jobs_settings = effective_settings.get("jobs", {})
    reports_settings = effective_settings.get("reports", {})
    job_batch_size = int(_resolve_setting_value(
        settings_value=jobs_settings.get("job_batch_size"),
        cli_value=job_batch_size_arg,
        fallback=get_default_setting("jobs", "job_batch_size"),
    ))
    job_worker_concurrency = _clamp_positive_int(
        _resolve_setting_value(
            settings_value=jobs_settings.get("job_worker_concurrency"),
            cli_value=job_worker_concurrency_arg,
            fallback=get_default_setting("jobs", "job_worker_concurrency"),
        ),
        default=1,
        minimum=1,
        maximum=1,
    )
    post_report_age_hours = int(_resolve_setting_value(
        settings_value=reports_settings.get("post_report_delay_hours"),
        cli_value=post_report_age_hours_arg,
        fallback=get_default_setting("reports", "post_report_delay_hours"),
    ))
    scheduler_limit = max(1, int(_resolve_setting_value(
        settings_value=jobs_settings.get("ai_scheduler_limit"),
        cli_value=scheduler_limit_arg,
        fallback=get_default_setting("jobs", "ai_scheduler_limit"),
    )))

    queued = await schedule_due_post_report_jobs(
        min_age_hours=post_report_age_hours,
        limit=scheduler_limit,
    )
    executed = await run_ai_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        job_worker_concurrency=job_worker_concurrency,
    )
    return queued, executed
