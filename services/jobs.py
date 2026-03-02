from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Job

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class JobType:
    COLLECT_COMMENTS: str = "collect_comments"
    BUILD_POST_REPORT: str = "build_post_report"
    BUILD_EVENT_REPORT: str = "build_event_report"
    BUILD_PROCESS_REPORT: str = "build_process_report"
    ARCHIVE_RETENTION: str = "archive_retention"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_job(
    session: AsyncSession,
    *,
    job_type: str,
    payload: dict,
    run_at: datetime | None = None,
    priority: int = 100,
    max_attempts: int = 5,
    dedupe_key: str | None = None,
) -> Job | None:
    values = {
        "type": job_type,
        "status": JOB_STATUS_PENDING,
        "priority": priority,
        "payload_json": payload,
        "run_at": run_at or utcnow(),
        "retry_at": None,
        "attempts": 0,
        "max_attempts": max_attempts,
        "dedupe_key": dedupe_key,
    }

    if dedupe_key:
        stmt = (
            insert(Job)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Job.dedupe_key])
            .returning(Job.id)
        )
        result = await session.execute(stmt)
        job_id = result.scalar_one_or_none()
        if job_id is None:
            return None
        return await session.get(Job, job_id)

    job = Job(**values)
    session.add(job)
    await session.flush()
    return job


def _job_query(now: datetime, *, limit: int, allowed_types: set[str] | None) -> Select:
    stmt = (
        select(Job)
        .where(Job.status == JOB_STATUS_PENDING)
        .where(func.coalesce(Job.retry_at, Job.run_at) <= now)
        .order_by(Job.priority.asc(), Job.run_at.asc(), Job.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    if allowed_types:
        stmt = stmt.where(Job.type.in_(allowed_types))
    return stmt


async def fetch_and_lock_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int = 20,
    allowed_types: set[str] | None = None,
) -> list[Job]:
    now = utcnow()
    jobs = (await session.execute(_job_query(now, limit=limit, allowed_types=allowed_types))).scalars().all()
    for job in jobs:
        job.status = JOB_STATUS_RUNNING
        job.locked_by = worker_id
        job.locked_at = now
        job.heartbeat_at = now
        job.attempts = int(job.attempts or 0) + 1
    await session.flush()
    return list(jobs)


async def mark_job_done(session: AsyncSession, *, job: Job) -> None:
    job.status = JOB_STATUS_DONE
    job.retry_at = None
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = None
    job.last_error = None
    await session.flush()


async def mark_job_failed(
    session: AsyncSession,
    *,
    job: Job,
    error: str,
    retry_base_seconds: int = 30,
    retry_max_seconds: int = 3600,
) -> None:
    attempts = int(job.attempts or 0)
    job.last_error = error[:4000]
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = None

    if attempts >= int(job.max_attempts or 0):
        job.status = JOB_STATUS_FAILED
        job.retry_at = None
    else:
        delay = min(retry_max_seconds, retry_base_seconds * (2 ** max(0, attempts - 1)))
        job.status = JOB_STATUS_PENDING
        job.retry_at = utcnow() + timedelta(seconds=delay)
    await session.flush()


async def requeue_job(
    session: AsyncSession,
    *,
    job: Job,
    retry_at: datetime,
    error: str | None = None,
) -> None:
    job.status = JOB_STATUS_PENDING
    job.retry_at = retry_at
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = None
    if error:
        job.last_error = error[:4000]
    await session.flush()


async def defer_locked_job(
    session: AsyncSession,
    *,
    job: Job,
    retry_at: datetime,
    reason: str | None = None,
    preserve_attempt_budget: bool = True,
) -> None:
    job.status = JOB_STATUS_PENDING
    job.retry_at = retry_at
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = None
    if preserve_attempt_budget:
        job.attempts = max(0, int(job.attempts or 0) - 1)
    if reason:
        job.last_error = reason[:4000]
    await session.flush()
