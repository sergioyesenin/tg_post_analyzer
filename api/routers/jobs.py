from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Job, JobDeadLetter
from deps import get_session, require_roles
from services.auth import AuthUser, write_audit_log
from services.jobs import JobType, enqueue_job, get_job_result

router = APIRouter()


def _serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "priority": job.priority,
        "run_at": job.run_at,
        "retry_at": job.retry_at,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "locked_by": job.locked_by,
        "locked_at": job.locked_at,
        "heartbeat_at": job.heartbeat_at,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "result_url": f"/api/jobs/{job.id}/result",
    }


@router.get("/summary")
async def jobs_summary(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Job.status, func.count(Job.id))
            .group_by(Job.status)
            .order_by(Job.status.asc())
        )
    ).all()
    return {
        "total": int(sum(count for _, count in rows)),
        "by_status": {status: int(count) for status, count in rows},
    }


@router.get("/pending")
async def jobs_pending(
    limit: int = 100,
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Job)
        .where(Job.status.in_(("pending", "running", "failed")))
        .order_by(Job.priority.asc(), Job.run_at.asc(), Job.id.asc())
        .limit(limit)
    )
    jobs = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "priority": job.priority,
            "run_at": job.run_at,
            "retry_at": job.retry_at,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "locked_by": job.locked_by,
            "last_error": job.last_error,
        }
        for job in jobs
    ]


@router.get("/dead-letter")
async def jobs_dead_letter(
    limit: int = 100,
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(JobDeadLetter)
        .order_by(JobDeadLetter.failed_at.desc(), JobDeadLetter.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": row.id,
            "source_job_id": row.source_job_id,
            "type": row.type,
            "priority": row.priority,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "last_error": row.last_error,
            "failed_at": row.failed_at,
        }
        for row in rows
    ]


@router.post("/dead-letter/{dead_letter_id}/retry")
async def retry_dead_letter_job(
    dead_letter_id: int,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    dead_row = await session.get(JobDeadLetter, dead_letter_id)
    if dead_row is None:
        return {"status": "not_found", "dead_letter_id": dead_letter_id}

    requeued = await enqueue_job(
        session,
        job_type=dead_row.type,
        payload=dead_row.payload_json or {},
        priority=int(dead_row.priority or 100),
        max_attempts=int(dead_row.max_attempts or 5),
        dedupe_key=None,
    )
    await session.execute(delete(JobDeadLetter).where(JobDeadLetter.id == dead_letter_id))
    await write_audit_log(
        session,
        action="jobs.dead_letter.retry",
        actor_user_id=current_user.id,
        target_type="job_dead_letter",
        target_id=str(dead_letter_id),
        details={
            "source_job_id": dead_row.source_job_id,
            "new_job_id": requeued.id if requeued else None,
            "type": dead_row.type,
        },
    )
    await session.commit()
    return {
        "status": "queued",
        "dead_letter_id": dead_letter_id,
        "source_job_id": dead_row.source_job_id,
        "new_job_id": requeued.id if requeued else None,
        "type": dead_row.type,
    }


@router.post("/failed/{job_id}/retry")
async def retry_failed_job(
    job_id: int,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(Job, job_id)
    if job is None:
        return {"status": "not_found", "job_id": job_id}
    if job.status != "failed":
        return {"status": "ignored", "job_id": job_id, "reason": f"job status is {job.status}, expected failed"}

    job.status = "pending"
    job.retry_at = None
    job.locked_by = None
    job.locked_at = None
    job.heartbeat_at = None
    job.last_error = None
    job.attempts = 0

    await write_audit_log(
        session,
        action="jobs.failed.retry",
        actor_user_id=current_user.id,
        target_type="job",
        target_id=str(job_id),
        details={"type": job.type},
    )
    await session.commit()
    return {"status": "queued", "job_id": job_id, "type": job.type}


@router.post("/archive/run")
async def run_archive_job(
    retention_days: int = 30,
    batch_limit: int = 1000,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    job = await enqueue_job(
        session,
        job_type=JobType.ARCHIVE_RETENTION,
        payload={"retention_days": retention_days, "batch_limit": batch_limit},
        priority=90,
        dedupe_key=None,
    )
    await write_audit_log(
        session,
        action="archive.run",
        actor_user_id=current_user.id,
        target_type="archive",
        details={"retention_days": retention_days, "batch_limit": batch_limit, "job_id": job.id if job else None},
    )
    await session.commit()
    return {
        "status": "queued",
        "job_id": job.id if job else None,
        "job_type": JobType.ARCHIVE_RETENTION,
        "retention_days": retention_days,
        "batch_limit": batch_limit,
    }


@router.post("/retention/run")
async def run_jobs_retention_job(
    done_retention_days: int = 14,
    dead_letter_retention_days: int = 90,
    batch_limit: int = 1000,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    job = await enqueue_job(
        session,
        job_type=JobType.JOBS_RETENTION,
        payload={
            "done_retention_days": done_retention_days,
            "dead_letter_retention_days": dead_letter_retention_days,
            "batch_limit": batch_limit,
        },
        priority=96,
        dedupe_key=None,
    )
    await write_audit_log(
        session,
        action="jobs.retention.run",
        actor_user_id=current_user.id,
        target_type="jobs_retention",
        details={
            "done_retention_days": done_retention_days,
            "dead_letter_retention_days": dead_letter_retention_days,
            "batch_limit": batch_limit,
            "job_id": job.id if job else None,
        },
    )
    await session.commit()
    return {
        "status": "queued",
        "job_id": job.id if job else None,
        "job_type": JobType.JOBS_RETENTION,
        "done_retention_days": done_retention_days,
        "dead_letter_retention_days": dead_letter_retention_days,
        "batch_limit": batch_limit,
    }


@router.get("/{job_id}")
async def job_status(
    job_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return jsonable_encoder(_serialize_job(job))


@router.get("/{job_id}/result")
async def job_result(
    job_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = get_job_result(job)
    if job.status == "done":
        return jsonable_encoder(result or {"status": "done", "job_id": job.id})
    if job.status == "failed":
        payload = dict(result or {})
        payload.setdefault("status", "failed")
        payload.setdefault("job_id", job.id)
        if job.last_error:
            payload.setdefault("error", job.last_error)
        return jsonable_encoder(payload)
    return {
        "status": job.status,
        "job_id": job.id,
        "ready": False,
        "result": None,
    }
