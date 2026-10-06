from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Job
from services.jobs import JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JobType


async def list_all_channels(session: AsyncSession) -> list[Channel]:
    stmt = select(Channel)
    return list((await session.execute(stmt)).scalars().all())


async def find_inflight_add_channel_job(
    session: AsyncSession,
    *,
    normalized_username: str,
) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.type == JobType.ADD_CHANNEL)
        .where(Job.status.in_((JOB_STATUS_PENDING, JOB_STATUS_RUNNING)))
        .order_by(Job.created_at.desc(), Job.id.desc())
    )
    jobs = (await session.execute(stmt)).scalars().all()
    for job in jobs:
        payload = job.payload_json or {}
        if str(payload.get("username") or "").strip().lower() == normalized_username.lower():
            return job
    return None