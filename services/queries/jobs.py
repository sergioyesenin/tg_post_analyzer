from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Job, JobDeadLetter


async def get_job_by_id(session: AsyncSession, *, job_id: int) -> Job | None:
    return await session.get(Job, job_id)


async def summarize_jobs_by_status(
    session: AsyncSession,
) -> list[tuple[str, int]]:
    stmt = (
        select(Job.status, func.count(Job.id))
        .group_by(Job.status)
        .order_by(Job.status.asc())
    )
    return list((await session.execute(stmt)).all())


async def list_pending_jobs(
    session: AsyncSession,
    *,
    limit: int,
) -> list[Job]:
    stmt = (
        select(Job)
        .where(Job.status.in_(("pending", "running", "failed")))
        .order_by(Job.priority.asc(), Job.run_at.asc(), Job.id.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_dead_letters(
    session: AsyncSession,
    *,
    limit: int,
) -> list[JobDeadLetter]:
    stmt = (
        select(JobDeadLetter)
        .order_by(JobDeadLetter.failed_at.desc(), JobDeadLetter.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def delete_dead_letter(
    session: AsyncSession,
    *,
    dead_letter_id: int,
) -> None:
    await session.execute(delete(JobDeadLetter).where(JobDeadLetter.id == dead_letter_id))