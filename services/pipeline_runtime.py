from __future__ import annotations

import asyncio
import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from client.telegram import (
    TelegramClientHandle,
    is_session_locked_error,
    with_session_lock_retry,
)
from db.models import Channel, EventPost, EventReport, Job, JobDeadLetter, Post, ProcessEvent, ProcessReport, Report
from db.session import AsyncSessionLocal
from services.archive import run_archive_retention
from services.auth import write_audit_log
from services.channel_management import resolve_and_upsert_channel
from services.events.build_events import rebuild_events
from services.ingestion_core import IngestionCore, IngestionContext, IngestionOptions
from services.jobs import (
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
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
from services.pipeline_runtime_common import (
    TelegramCycleMetrics,
    build_tg_client,
    build_worker_id,
    clamp_positive_int,
    collect_backlog_snapshot,
    configure_logging,
    get_ai_poll_seconds,
    get_telegram_poll_seconds,
    has_due_priority_job,
    resolve_setting_value,
    sleep_until_next_telegram_cycle,
)
from services.pipeline_runtime_support import (
    collect_comments_job_priority,
    dispatch_post_report_batch as dispatch_post_report_batch_impl,
    enqueue_comment_refresh_job as enqueue_comment_refresh_job_impl,
    enqueue_event_report_job as enqueue_event_report_job_impl,
    enqueue_post_link_job as enqueue_post_link_job_impl,
    enqueue_post_report_batch_job as enqueue_post_report_batch_job_impl,
    enqueue_post_report_job as enqueue_post_report_job_impl,
    enqueue_process_report_job as enqueue_process_report_job_impl,
    enqueue_rebuild_events_job as enqueue_rebuild_events_job_impl,
    enqueue_rebuild_processes_job as enqueue_rebuild_processes_job_impl,
    enqueue_related_event_report_jobs as enqueue_related_event_report_jobs_impl,
    enqueue_related_process_report_jobs as enqueue_related_process_report_jobs_impl,
    get_active_channels,
    mark_related_event_reports_stale as mark_related_event_reports_stale_impl,
    mark_related_process_reports_stale as mark_related_process_reports_stale_impl,
    process_channel as process_channel_impl,
    rebuild_event_process_graphs as rebuild_event_process_graphs_impl,
    schedule_due_post_report_jobs as schedule_due_post_report_jobs_impl,
    split_jobs_for_telegram_worker,
)
from services import reporting as reporting_module
from services.reporting import (
    REPORT_STATUS_DEFERRED,
    build_event_report_draft,
    build_post_report,
    build_process_report_draft,
)
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
PRIORITY_REBUILD_EVENTS = 6
PRIORITY_REBUILD_PROCESSES = 7
PRIORITY_BUILD_POST_REPORT = 40
PRIORITY_BUILD_EVENT_REPORT = 45
PRIORITY_BUILD_PROCESS_REPORT = 50
PRIORITY_ARCHIVE_RETENTION = 95
PRIORITY_JOBS_RETENTION = 96
TELEGRAM_JOB_TYPES = {
    JobType.ADD_CHANNEL,
    JobType.COLLECT_COMMENTS,
    JobType.REFRESH_COMMENTS,
    JobType.BUILD_POST_LINKS,
    JobType.REBUILD_EVENTS,
    JobType.REBUILD_PROCESSES,
    JobType.ARCHIVE_RETENTION,
    JobType.JOBS_RETENTION,
}

AI_JOB_TYPES = {
    JobType.BUILD_POST_REPORT,
    JobType.BUILD_POST_REPORT_BATCH,
    JobType.BUILD_EVENT_REPORT,
    JobType.BUILD_PROCESS_REPORT,
}
TELEGRAM_PREEMPTION_MAX_PRIORITY = PRIORITY_REBUILD_PROCESSES
LINK_PREEMPTION_MAX_PRIORITY = PRIORITY_BUILD_POST_LINKS - 1

SKIP_CHANNEL_IDS: dict[int, str] = {}


TelegramPipelineClient = TelegramClientHandle
_clamp_positive_int = clamp_positive_int
_resolve_setting_value = resolve_setting_value


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 2)


def _extract_post_report_rerun_stage(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    direct_value = payload.get("stage_rerun_from")
    if isinstance(direct_value, str) and direct_value.strip():
        return direct_value.strip()
    nested = payload.get("multi_agent")
    if isinstance(nested, dict):
        nested_value = nested.get("rerun_stage")
        if isinstance(nested_value, str) and nested_value.strip():
            return nested_value.strip()
    return None


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


async def enqueue_comment_refresh_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int = PRIORITY_API_COMMENT_REFRESH,
    source: str = "api",
) -> Job | None:
    return await enqueue_comment_refresh_job_impl(session, post_id=post_id, priority=priority, source=source)


async def enqueue_event_report_job(
    session: AsyncSession,
    *,
    event_id: int,
    priority: int = PRIORITY_API_REPORT,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_event_report_job_impl(
        session,
        event_id=event_id,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_process_report_job(
    session: AsyncSession,
    *,
    process_id: int,
    priority: int = PRIORITY_API_REPORT,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_process_report_job_impl(
        session,
        process_id=process_id,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_post_report_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int = PRIORITY_API_POST_REPORT,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_post_report_job_impl(
        session,
        post_id=post_id,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_post_report_batch_job(
    session: AsyncSession,
    *,
    filters: dict,
    priority: int = PRIORITY_API_POST_REPORT_BATCH,
    source: str = "api",
) -> Job | None:
    return await enqueue_post_report_batch_job_impl(session, filters=filters, priority=priority, source=source)


async def enqueue_post_link_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int = PRIORITY_BUILD_POST_LINKS,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_post_link_job_impl(
        session,
        post_id=post_id,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_rebuild_events_job(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    priority: int = PRIORITY_REBUILD_EVENTS,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_rebuild_events_job_impl(
        session,
        date_from=date_from,
        date_to=date_to,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def enqueue_rebuild_processes_job(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    priority: int = PRIORITY_REBUILD_PROCESSES,
    source: str = "api",
    requested_by_user_id: int | None = None,
    dedupe_key: str | None = None,
) -> Job | None:
    return await enqueue_rebuild_processes_job_impl(
        session,
        date_from=date_from,
        date_to=date_to,
        priority=priority,
        source=source,
        requested_by_user_id=requested_by_user_id,
        dedupe_key=dedupe_key,
    )


async def schedule_due_post_report_jobs(*, min_age_hours: int, limit: int) -> int:
    return await schedule_due_post_report_jobs_impl(
        min_age_hours=min_age_hours,
        limit=limit,
        priority_build_post_report=PRIORITY_BUILD_POST_REPORT,
    )


async def dispatch_post_report_batch(
    session: AsyncSession,
    *,
    filters: dict,
) -> dict:
    return await dispatch_post_report_batch_impl(
        session,
        filters=filters,
        priority_build_post_report=PRIORITY_BUILD_POST_REPORT,
        enqueue_post_report_job_fn=enqueue_post_report_job,
    )


async def _enqueue_related_event_report_jobs(
    session: AsyncSession,
    *,
    post_id: int,
    source: str,
) -> int:
    return await enqueue_related_event_report_jobs_impl(
        session,
        post_id=post_id,
        source=source,
        priority_build_event_report=PRIORITY_BUILD_EVENT_REPORT,
        enqueue_event_report_job_fn=enqueue_event_report_job,
    )


async def _mark_related_event_reports_stale(
    session: AsyncSession,
    *,
    post_id: int,
) -> int:
    return await mark_related_event_reports_stale_impl(session, post_id=post_id)


async def _enqueue_related_process_report_jobs(
    session: AsyncSession,
    *,
    event_id: int,
    source: str,
) -> int:
    return await enqueue_related_process_report_jobs_impl(
        session,
        event_id=event_id,
        source=source,
        priority_build_process_report=PRIORITY_BUILD_PROCESS_REPORT,
        enqueue_process_report_job_fn=enqueue_process_report_job,
    )


async def _mark_related_process_reports_stale(
    session: AsyncSession,
    *,
    event_id: int,
) -> int:
    return await mark_related_process_reports_stale_impl(session, event_id=event_id)


async def _has_active_dependency_job(
    session: AsyncSession,
    *,
    job_type: str,
    payload_key: str,
    entity_id: int,
) -> bool:
    job_id = await session.scalar(
        text(
            "SELECT id FROM jobs "
            "WHERE type = :job_type "
            "AND status IN ('pending', 'running') "
            "AND payload_json->>:payload_key = :entity_id "
            "LIMIT 1"
        ),
        {
            "job_type": job_type,
            "payload_key": payload_key,
            "entity_id": str(entity_id),
        },
    )
    return job_id is not None


async def _enqueue_ai_job_dependencies(
    session: AsyncSession,
    *,
    parent_job: Job,
    dependencies: list[dict],
) -> dict:
    enqueued = 0
    active = 0
    seen: set[tuple[str, int]] = set()
    source = f"{parent_job.type}:dependency"

    for dependency in dependencies:
        job_type = str(dependency.get("job_type") or "")
        entity_id = dependency.get("post_id")
        payload_key = "post_id"
        enqueue_coro = None
        kwargs: dict = {"source": source}

        if job_type == JobType.REFRESH_COMMENTS:
            entity_id = dependency.get("post_id")
            payload_key = "post_id"
            enqueue_coro = enqueue_comment_refresh_job
            kwargs["post_id"] = int(entity_id)
        elif job_type == JobType.BUILD_POST_REPORT:
            entity_id = dependency.get("post_id")
            payload_key = "post_id"
            enqueue_coro = enqueue_post_report_job
            kwargs["post_id"] = int(entity_id)
            kwargs["dedupe_key"] = f"{job_type}:{int(entity_id)}"
        elif job_type == JobType.BUILD_EVENT_REPORT:
            entity_id = dependency.get("event_id")
            payload_key = "event_id"
            enqueue_coro = enqueue_event_report_job
            kwargs["event_id"] = int(entity_id)
            kwargs["dedupe_key"] = f"{job_type}:{int(entity_id)}"
        elif job_type == JobType.BUILD_PROCESS_REPORT:
            entity_id = dependency.get("process_id")
            payload_key = "process_id"
            enqueue_coro = enqueue_process_report_job
            kwargs["process_id"] = int(entity_id)
            kwargs["dedupe_key"] = f"{job_type}:{int(entity_id)}"
        else:
            continue

        key = (job_type, int(entity_id))
        if key in seen:
            continue
        seen.add(key)

        if await _has_active_dependency_job(
            session,
            job_type=job_type,
            payload_key=payload_key,
            entity_id=int(entity_id),
        ):
            active += 1
            continue

        job = await enqueue_coro(session, **kwargs)
        if job is None:
            active += 1
        else:
            enqueued += 1

    if seen:
        logger.debug(
            "AI dependency enqueue summary parent_job_type=%s parent_job_id=%s requested=%s enqueued=%s already_active=%s",
            parent_job.type,
            parent_job.id,
            len(seen),
            enqueued,
            active,
        )

    return {
        "requested": len(seen),
        "enqueued": enqueued,
        "already_active": active,
    }


async def _get_active_channels() -> list[Channel]:
    return await get_active_channels()


def _collect_comments_job_priority(*, post: Post, scan_index: int) -> int:
    return collect_comments_job_priority(post=post, scan_index=scan_index)


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
    return await process_channel_impl(
        client,
        channel,
        since_utc=since_utc,
        max_posts=max_posts,
        comment_first_delay_hours=comment_first_delay_hours,
        comment_interval_hours=comment_interval_hours,
        comment_window_hours=comment_window_hours,
        comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
        skip_channel_ids=SKIP_CHANNEL_IDS,
        priority_build_post_links=PRIORITY_BUILD_POST_LINKS,
        collect_comments_job_priority_fn=_collect_comments_job_priority,
    )


async def _rebuild_event_process_graphs(*, date_from: datetime, date_to: datetime) -> None:
    await rebuild_event_process_graphs_impl(
        date_from=date_from,
        date_to=date_to,
        created_by="telegram-pipeline",
    )


async def _run_link_job(*, job: Job, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        started_at = time.perf_counter()
        post = await session.get(Post, int(payload.get("post_id")))
        if post is None:
            await mark_job_done(session, job=db_job)
            await session.commit()
            return 0
        try:
            pipeline = NoLlmLinkingPipeline.build_default()
            result = await pipeline.run_for_post(session, post)
            set_job_result(db_job, result.model_dump())
            actor_user_id = payload.get("requested_by_user_id")
            if actor_user_id is not None:
                await write_audit_log(
                    session,
                    action="linking.run.executed",
                    actor_user_id=int(actor_user_id),
                    target_type="post",
                    target_id=str(post.id),
                    details={
                        "job_id": db_job.id,
                        "job_type": db_job.type,
                        "source": payload.get("source"),
                        "links_verified": result.links_verified,
                        "links_rejected": result.links_rejected,
                        "candidates_checked": result.candidates_checked,
                    },
                )
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info(
                "Job build_post_links post_id=%s verified=%s rejected=%s candidates=%s latency_ms=%s worker_id=%s",
                post.id,
                result.links_verified,
                result.links_rejected,
                result.candidates_checked,
                _elapsed_ms(started_at),
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


async def _run_rebuild_events_job(*, job: Job, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        started_at = time.perf_counter()
        try:
            date_from = datetime.fromisoformat(str(payload.get("date_from")))
            date_to = datetime.fromisoformat(str(payload.get("date_to")))
            rebuilt = await rebuild_events(
                session,
                date_from=date_from,
                date_to=date_to,
                created_by="job-pipeline",
            )
            result = {
                "status": "done",
                "rebuilt_events": rebuilt,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            }
            set_job_result(db_job, result)
            actor_user_id = payload.get("requested_by_user_id")
            if actor_user_id is not None:
                await write_audit_log(
                    session,
                    action="events.rebuild.executed",
                    actor_user_id=int(actor_user_id),
                    target_type="events",
                    target_id=None,
                    details={
                        "job_id": db_job.id,
                        "job_type": db_job.type,
                        "source": payload.get("source"),
                        "date_from": result["date_from"],
                        "date_to": result["date_to"],
                        "rebuilt_events": rebuilt,
                    },
                )
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info(
                "Job rebuild_events rebuilt=%s date_from=%s date_to=%s latency_ms=%s worker_id=%s",
                rebuilt,
                result["date_from"],
                result["date_to"],
                _elapsed_ms(started_at),
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
                "Job failed marker=job_unexpected op=rebuild_events job_id=%s worker_id=%s err=%r",
                db_job.id,
                worker_id,
                exc,
            )
            return 0


async def _run_rebuild_processes_job(*, job: Job, worker_id: str) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job.id)
        if db_job is None:
            return 0
        payload = db_job.payload_json or {}
        started_at = time.perf_counter()
        try:
            date_from = datetime.fromisoformat(str(payload.get("date_from")))
            date_to = datetime.fromisoformat(str(payload.get("date_to")))
            rebuilt = await rebuild_processes(
                session,
                date_from=date_from,
                date_to=date_to,
                created_by="job-pipeline",
            )
            result = {
                "status": "done",
                "rebuilt_process_edges": rebuilt,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            }
            set_job_result(db_job, result)
            actor_user_id = payload.get("requested_by_user_id")
            if actor_user_id is not None:
                await write_audit_log(
                    session,
                    action="processes.rebuild.executed",
                    actor_user_id=int(actor_user_id),
                    target_type="processes",
                    target_id=None,
                    details={
                        "job_id": db_job.id,
                        "job_type": db_job.type,
                        "source": payload.get("source"),
                        "date_from": result["date_from"],
                        "date_to": result["date_to"],
                        "rebuilt_process_edges": rebuilt,
                    },
                )
            await mark_job_done(session, job=db_job)
            await session.commit()
            logger.info(
                "Job rebuild_processes rebuilt_edges=%s date_from=%s date_to=%s latency_ms=%s worker_id=%s",
                rebuilt,
                result["date_from"],
                result["date_to"],
                _elapsed_ms(started_at),
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
                "Job failed marker=job_unexpected op=rebuild_processes job_id=%s worker_id=%s err=%r",
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
        started_at = time.perf_counter()
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
                "Job add_channel username=@%s status=%s channel_id=%s latency_ms=%s worker_id=%s",
                channel.username,
                result["status"],
                channel.id,
                _elapsed_ms(started_at),
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
        started_at = time.perf_counter()
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
            logger.debug("Job %s status=ok details=%s latency_ms=%s worker_id=%s", db_job.type, result, _elapsed_ms(started_at), worker_id)
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


async def _has_due_telegram_preemption_job(*, max_priority: int) -> bool:
    if max_priority < 0:
        return False
    return await has_due_priority_job(
        allowed_types=TELEGRAM_JOB_TYPES,
        max_priority=max_priority,
    )


async def _run_telegram_preemption_burst(
    *,
    job_batch_size: int,
    worker_id: str,
    collect_comments_quota_per_run: int,
    tg_client: TelegramPipelineClient,
    job_worker_concurrency: int,
    max_priority: int = TELEGRAM_PREEMPTION_MAX_PRIORITY,
) -> int:
    if not await _has_due_telegram_preemption_job(max_priority=max_priority):
        return 0
    return await run_telegram_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        collect_comments_quota_per_run=collect_comments_quota_per_run,
        tg_client=tg_client,
        job_worker_concurrency=job_worker_concurrency,
        allowed_types=TELEGRAM_JOB_TYPES,
        max_priority=max_priority,
    )


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
            started_at = time.perf_counter()
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
            refresh_latency_ms = _elapsed_ms(started_at)
            logger.debug(
                "Job %s post_id=%s status=%s comments_saved=%s latency_ms=%s worker_id=%s",
                db_job.type,
                post_id,
                status,
                result.get("comments_saved"),
                refresh_latency_ms,
                worker_id,
            )
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
    del job_batch_size, job_worker_concurrency

    while True:
        if await _has_due_telegram_preemption_job(max_priority=LINK_PREEMPTION_MAX_PRIORITY):
            return executed

        async with AsyncSessionLocal() as session:
            jobs = await fetch_and_lock_jobs(
                session,
                worker_id=worker_id,
                limit=1,
                allowed_types={JobType.BUILD_POST_LINKS},
            )
            await session.commit()

        if not jobs:
            return executed

        executed += await _run_link_job(job=jobs[0], worker_id=worker_id)


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
    allowed_types: set[str] | None = None,
    max_priority: int | None = None,
) -> int:
    executed = 0
    processed_units = 0
    collect_comments_global_cooldown_until: datetime | None = None
    collect_comments_processed = 0
    collect_comments_flood_streak = 0

    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    ingest_settings = effective_settings.get("ingest", {})
    cc_sleep_min_ms = int(ingest_settings.get("collect_comments_sleep_min_ms", get_default_setting("ingest", "collect_comments_sleep_min_ms")))
    cc_sleep_max_ms = int(ingest_settings.get("collect_comments_sleep_max_ms", get_default_setting("ingest", "collect_comments_sleep_max_ms")))
    if cc_sleep_max_ms < cc_sleep_min_ms:
        cc_sleep_max_ms = cc_sleep_min_ms

    del job_worker_concurrency
    effective_allowed_types = TELEGRAM_JOB_TYPES if allowed_types is None else set(allowed_types)

    while processed_units < max(0, int(job_batch_size)):
        async with AsyncSessionLocal() as session:
            jobs = await fetch_and_lock_jobs(
                session,
                worker_id=worker_id,
                limit=1,
                allowed_types=effective_allowed_types,
                max_priority=max_priority,
            )
            await session.commit()

        if not jobs:
            break

        job = jobs[0]
        processed_units += 1

        if job.type in {JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS}:
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
            continue

        if job.type == JobType.ADD_CHANNEL:
            executed += await _run_add_channel_job(job=job, tg_client=tg_client, worker_id=worker_id)
        elif job.type == JobType.BUILD_POST_LINKS:
            executed += await _run_link_job(job=job, worker_id=worker_id)
        elif job.type == JobType.REBUILD_EVENTS:
            executed += await _run_rebuild_events_job(job=job, worker_id=worker_id)
        elif job.type == JobType.REBUILD_PROCESSES:
            executed += await _run_rebuild_processes_job(job=job, worker_id=worker_id)
        else:
            executed += await _run_maintenance_job(job=job, worker_id=worker_id)

    return executed


async def run_ai_jobs(*, job_batch_size: int, worker_id: str, job_worker_concurrency: int) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    report_config = report_config_from_settings(effective_settings)
    jobs_settings = effective_settings.get("jobs", {})
    ai_job_timeout_seconds = max(
        5,
        int(
            _resolve_setting_value(
                settings_value=jobs_settings.get("ai_job_timeout_seconds"),
                cli_value=None,
                fallback=get_default_setting("jobs", "ai_job_timeout_seconds"),
            )
        ),
    )
    del job_worker_concurrency
    executed = 0
    processed_units = 0

    while processed_units < max(0, int(job_batch_size)):
        async with AsyncSessionLocal() as session:
            jobs = await fetch_and_lock_jobs(
                session,
                worker_id=worker_id,
                limit=1,
                allowed_types=AI_JOB_TYPES,
            )
            await session.commit()

        if not jobs:
            break

        processed_units += 1
        job = jobs[0]

        async with AsyncSessionLocal() as session:
            db_job = await session.get(Job, job.id)
            if db_job is None:
                continue
            job_type = str(db_job.type)
            job_id = int(db_job.id)
            payload = db_job.payload_json or {}
            try:
                logger.debug("AI job start type=%s job_id=%s worker_id=%s", job_type, job_id, worker_id)
                started_at = time.perf_counter()
                if db_job.type == JobType.BUILD_POST_REPORT:
                    job_coro = build_post_report(
                        session,
                        post_id=int(payload.get("post_id")),
                        report_project=None,
                        report_config=report_config,
                        job_timeout_seconds=ai_job_timeout_seconds,
                        rerun_stage=_extract_post_report_rerun_stage(payload),
                    )
                elif db_job.type == JobType.BUILD_POST_REPORT_BATCH:
                    result = {
                        "status": "failed",
                        "reason": "passive_ai_worker_no_batch_dispatch",
                        "message": "AI worker passive mode does not expand batch report jobs into build_post_report jobs.",
                        "filters": dict(payload.get("filters") or {}),
                    }
                    set_job_result(db_job, result)
                    db_job.status = JOB_STATUS_FAILED
                    db_job.retry_at = None
                    db_job.locked_by = None
                    db_job.locked_at = None
                    db_job.heartbeat_at = None
                    db_job.last_error = f"{db_job.type}:passive_mode_batch_dispatch_disabled"
                    await session.commit()
                    logger.warning(
                        "AI job type=%s job_id=%s worker_id=%s skipped reason=%s",
                        job_type,
                        job_id,
                        worker_id,
                        result["reason"],
                    )
                    continue
                elif db_job.type == JobType.BUILD_EVENT_REPORT:
                    job_coro = build_event_report_draft(session, event_id=int(payload.get("event_id")))
                elif db_job.type == JobType.BUILD_PROCESS_REPORT:
                    job_coro = build_process_report_draft(session, process_id=int(payload.get("process_id")))
                else:
                    raise ValueError(f"Unsupported AI job type: {db_job.type}")

                result = await asyncio.wait_for(job_coro, timeout=ai_job_timeout_seconds)

                result_status = str(result.get("status") or "")
                if result_status == REPORT_STATUS_DEFERRED:
                    dependency_result = await _enqueue_ai_job_dependencies(
                        session,
                        parent_job=db_job,
                        dependencies=list(result.get("dependencies") or []),
                    )
                    set_job_result(
                        db_job,
                        {
                            **result,
                            "dependency_enqueue": dependency_result,
                        },
                    )
                    if int(db_job.attempts or 0) >= int(db_job.max_attempts or 0):
                        await mark_job_failed(
                            session,
                            job=db_job,
                            error=f"{db_job.type}:waiting_dependencies:{result.get('reason')}",
                        )
                        await session.commit()
                        logger.warning(
                            "Job %s exhausted dependency wait budget reason=%s worker_id=%s",
                            db_job.type,
                            result.get("reason"),
                            worker_id,
                        )
                    else:
                        await requeue_job(
                            session,
                            job=db_job,
                            retry_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                            error=f"{db_job.type}:waiting_dependencies",
                        )
                        await session.commit()
                        logger.debug(
                            "Job %s deferred reason=%s enqueued=%s active=%s worker_id=%s",
                            db_job.type,
                            result.get("reason"),
                            dependency_result.get("enqueued"),
                            dependency_result.get("already_active"),
                            worker_id,
                        )
                    continue

                if db_job.type == JobType.BUILD_POST_REPORT and result_status == reporting_module.REPORT_STATUS_READY:
                    if result_status == reporting_module.REPORT_STATUS_READY:
                        await _mark_related_event_reports_stale(
                            session,
                            post_id=int(payload.get("post_id")),
                        )
                elif db_job.type == JobType.BUILD_EVENT_REPORT and result_status in {
                    reporting_module.REPORT_STATUS_READY,
                    reporting_module.REPORT_STATUS_LIMITED,
                    reporting_module.REPORT_STATUS_INSUFFICIENT_DATA,
                    reporting_module.REPORT_STATUS_DRAFT,
                }:
                    await _mark_related_process_reports_stale(
                        session,
                        event_id=int(payload.get("event_id")),
                    )

                set_job_result(db_job, result)
                await mark_job_done(session, job=db_job)
                await session.commit()
                logger.info(
                    "Job %s status=%s latency_ms=%s worker_id=%s",
                    job_type,
                    result.get("status"),
                    _elapsed_ms(started_at),
                    worker_id,
                )
                executed += 1
            except asyncio.TimeoutError:
                await session.rollback()
                await session.execute(
                    update(Job)
                        .where(Job.id == job_id)
                        .values(
                        last_error=f"job_timeout:{job_type}:{ai_job_timeout_seconds}s",
                        status=JOB_STATUS_PENDING,
                        retry_at=datetime.now(timezone.utc) + timedelta(seconds=30),
                        locked_by=None,
                        locked_at=None,
                        heartbeat_at=None,
                    )
                )
                await session.commit()
                logger.error(
                    "Job failed marker=job_timeout op=ai_job job_id=%s worker_id=%s timeout=%ss",
                    job_id,
                    worker_id,
                    ai_job_timeout_seconds,
                )
            except Exception as exc:
                await session.rollback()
                await _persist_job_failure_after_exception(
                    session,
                    job_id=job_id,
                    error=f"job_unexpected:{job_type}:{type(exc).__name__}:{exc}",
                )
                logger.exception(
                    "Job failed marker=job_unexpected op=ai_job job_id=%s worker_id=%s err=%r",
                    job_id,
                    worker_id,
                    exc,
                )

    return executed


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
    telegram_jobs_executed = 0
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
            telegram_jobs_executed += await _run_telegram_preemption_burst(
                job_batch_size=job_batch_size,
                worker_id=worker_id,
                collect_comments_quota_per_run=collect_comments_quota_per_run,
                tg_client=client,
                job_worker_concurrency=job_worker_concurrency,
            )

    link_jobs_executed = 0
    while True:
        link_jobs_executed += await run_telegram_link_jobs_until_idle(
            job_batch_size=job_batch_size,
            worker_id=worker_id,
            job_worker_concurrency=job_worker_concurrency,
        )
        preempted = await _run_telegram_preemption_burst(
            job_batch_size=job_batch_size,
            worker_id=worker_id,
            collect_comments_quota_per_run=collect_comments_quota_per_run,
            tg_client=client,
            job_worker_concurrency=job_worker_concurrency,
            max_priority=LINK_PREEMPTION_MAX_PRIORITY,
        )
        telegram_jobs_executed += preempted
        if preempted <= 0:
            break

    incomplete_link_jobs = await count_incomplete_link_jobs()

    if not skip_rebuild_graphs and incomplete_link_jobs <= 0:
        telegram_jobs_executed += await _run_telegram_preemption_burst(
            job_batch_size=job_batch_size,
            worker_id=worker_id,
            collect_comments_quota_per_run=collect_comments_quota_per_run,
            tg_client=client,
            job_worker_concurrency=job_worker_concurrency,
        )
        incomplete_link_jobs = await count_incomplete_link_jobs()

    if not skip_rebuild_graphs and incomplete_link_jobs > 0:
        logger.debug(
            "Skip rebuild: build_post_links queue is not drained yet incomplete_link_jobs=%s",
            incomplete_link_jobs,
        )
    elif not skip_rebuild_graphs and (total_processed_posts > 0 or link_jobs_executed > 0):
        await _rebuild_event_process_graphs(date_from=since_utc, date_to=datetime.now(timezone.utc))
    elif not skip_rebuild_graphs:
        logger.debug("Skip rebuild: no new posts or completed link jobs in this cycle.")

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
        executed_jobs=link_jobs_executed + telegram_jobs_executed + executed_jobs,
    )


async def run_ai_cycle(*, worker_id: str, job_batch_size_arg: int, job_worker_concurrency_arg: int, post_report_age_hours_arg: int, scheduler_limit_arg: int) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    jobs_settings = effective_settings.get("jobs", {})
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
    del post_report_age_hours_arg, scheduler_limit_arg

    queued = 0
    executed = await run_ai_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        job_worker_concurrency=job_worker_concurrency,
    )
    return queued, executed
