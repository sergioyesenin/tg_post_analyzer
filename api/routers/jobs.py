from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Job
from deps import get_session, require_roles
from services.auth import AuthUser

router = APIRouter()


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
