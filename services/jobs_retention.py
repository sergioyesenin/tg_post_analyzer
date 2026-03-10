from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Job, JobDeadLetter
from services.jobs import JOB_STATUS_DONE, utcnow


async def _delete_job_batch(
    session: AsyncSession,
    *,
    done_cutoff,
    batch_limit: int,
) -> int:
    job_ids = list(
        (
            await session.execute(
                select(Job.id)
                .where(Job.status == JOB_STATUS_DONE)
                .where(Job.updated_at < done_cutoff)
                .order_by(Job.updated_at.asc(), Job.id.asc())
                .limit(batch_limit)
            )
        ).scalars()
    )
    if not job_ids:
        return 0
    result = await session.execute(delete(Job).where(Job.id.in_(job_ids)))
    return int(result.rowcount or 0)


async def _delete_dead_letter_batch(
    session: AsyncSession,
    *,
    dead_letter_cutoff,
    batch_limit: int,
) -> int:
    dead_letter_ids = list(
        (
            await session.execute(
                select(JobDeadLetter.id)
                .where(JobDeadLetter.failed_at < dead_letter_cutoff)
                .order_by(JobDeadLetter.failed_at.asc(), JobDeadLetter.id.asc())
                .limit(batch_limit)
            )
        ).scalars()
    )
    if not dead_letter_ids:
        return 0
    result = await session.execute(delete(JobDeadLetter).where(JobDeadLetter.id.in_(dead_letter_ids)))
    return int(result.rowcount or 0)


async def run_jobs_retention(
    session: AsyncSession,
    *,
    done_retention_days: int = 14,
    dead_letter_retention_days: int = 90,
    batch_limit: int = 1000,
) -> dict:
    now = utcnow()
    safe_batch_limit = max(10, int(batch_limit))
    done_cutoff = now - timedelta(days=max(1, int(done_retention_days)))
    dead_letter_cutoff = now - timedelta(days=max(1, int(dead_letter_retention_days)))

    deleted_done_jobs = await _delete_job_batch(
        session,
        done_cutoff=done_cutoff,
        batch_limit=safe_batch_limit,
    )
    deleted_dead_letters = await _delete_dead_letter_batch(
        session,
        dead_letter_cutoff=dead_letter_cutoff,
        batch_limit=safe_batch_limit,
    )

    return {
        "deleted_done_jobs": deleted_done_jobs,
        "deleted_dead_letters": deleted_dead_letters,
        "done_cutoff": done_cutoff.isoformat(),
        "dead_letter_cutoff": dead_letter_cutoff.isoformat(),
        "batch_limit": safe_batch_limit,
    }
