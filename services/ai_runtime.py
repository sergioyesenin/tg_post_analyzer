from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import get_report_project
from db.models import Job
from db.session import AsyncSessionLocal
from services.jobs import (
    JOB_STATUS_FAILED,
    JobType,
    defer_locked_job,
    fetch_and_lock_jobs,
    mark_job_done,
    mark_job_failed,
    requeue_job,
    set_job_result,
)
from services.pipeline_runtime_common import (
    clamp_positive_int,
    get_default_setting,
    resolve_setting_value,
)
from services.pipeline_runtime_support import (
    enqueue_comment_refresh_job,
    enqueue_event_report_job,
    enqueue_post_report_job,
    enqueue_process_report_job,
)
from services.reporting import (
    REPORT_STATUS_DEFERRED,
    REPORT_STATUS_READY,
    REPORT_STATUS_DRAFT,
    build_event_report_draft,
    build_post_report,
    build_process_report_draft,
    _mark_related_event_reports_stale,
    _mark_related_process_reports_stale,
)
from services.settings_store import get_all_settings, report_config_from_settings

logger = logging.getLogger(__name__)

AI_JOB_TYPES = {
    JobType.BUILD_POST_REPORT,
    JobType.BUILD_POST_REPORT_BATCH,
    JobType.BUILD_EVENT_REPORT,
    JobType.BUILD_PROCESS_REPORT,
}


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


async def run_ai_jobs(*, job_batch_size: int, worker_id: str, job_worker_concurrency: int) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    report_project = get_report_project()
    report_config = report_config_from_settings(effective_settings)
    jobs_settings = effective_settings.get("jobs", {})
    ai_job_timeout_seconds = max(
        5,
        int(
            resolve_setting_value(
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
                        report_project=report_project,
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

                if db_job.type == JobType.BUILD_POST_REPORT and result_status == REPORT_STATUS_READY:
                    if result_status == REPORT_STATUS_READY:
                        await _mark_related_event_reports_stale(
                            session,
                            post_id=int(payload.get("post_id")),
                        )
                elif db_job.type == JobType.BUILD_EVENT_REPORT and result_status in {REPORT_STATUS_READY, REPORT_STATUS_DRAFT}:
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


async def run_ai_cycle(*, worker_id: str, job_batch_size_arg: int, job_worker_concurrency_arg: int, post_report_age_hours_arg: int, scheduler_limit_arg: int) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)

    jobs_settings = effective_settings.get("jobs", {})
    job_batch_size = int(_resolve_setting_value(
        settings_value=jobs_settings.get("job_batch_size"),
        cli_value=job_batch_size_arg,
        fallback=get_default_setting("jobs", "job_batch_size"),
    ))
    job_worker_concurrency = clamp_positive_int(
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
