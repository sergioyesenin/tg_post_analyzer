from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Job
from deps import get_session, require_roles
from schemas.channel import ChannelIn, ChannelOut, ChannelUpdate
from services.auth import AuthUser, write_audit_log
from services.channel_management import normalize_channel_identifier
from services.jobs import JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JobType, enqueue_job

router = APIRouter()


def _serialize_accepted_job(job: Job) -> dict:
    return {
        "status": "queued",
        "job_id": job.id,
        "job_type": job.type,
        "status_url": f"/api/jobs/{job.id}",
        "result_url": f"/api/jobs/{job.id}/result",
    }


async def _find_inflight_add_channel_job(session: AsyncSession, *, normalized_username: str) -> Job | None:
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


@router.get("/", response_model=list[ChannelOut])
async def list_channels(
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Channel))
    return result.scalars().all()


@router.post("/add", status_code=status.HTTP_202_ACCEPTED)
async def add_channel(
    user: ChannelIn,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    ident = normalize_channel_identifier(user.username)
    normalized_username = ident.lstrip("@").strip()
    if not normalized_username:
        raise HTTPException(status_code=400, detail="Channel username is required")

    inflight_job = await _find_inflight_add_channel_job(session, normalized_username=normalized_username)
    if inflight_job is not None:
        return _serialize_accepted_job(inflight_job)

    job = await enqueue_job(
        session,
        job_type=JobType.ADD_CHANNEL,
        payload={
            "username": normalized_username,
            "requested_by_user_id": current_user.id,
            "source": "api.channels.add",
        },
        priority=5,
        max_attempts=3,
    )
    assert job is not None
    await write_audit_log(
        session,
        action="channels.add.queued",
        actor_user_id=current_user.id,
        target_type="job",
        target_id=str(job.id),
        details={"username": normalized_username, "job_type": job.type},
    )
    await session.commit()
    return _serialize_accepted_job(job)


@router.put("/{channel_id}/active", response_model=ChannelOut)
async def set_channel_active(
    channel_id: int,
    is_active: bool,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.is_active = is_active
    await write_audit_log(
        session,
        action="channels.set_active",
        actor_user_id=current_user.id,
        target_type="channel",
        target_id=str(channel.id),
        details={"username": channel.username, "is_active": is_active},
    )
    await session.commit()
    await session.refresh(channel)
    return channel


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: int,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    username = channel.username
    await session.delete(channel)
    await write_audit_log(
        session,
        action="channels.delete",
        actor_user_id=current_user.id,
        target_type="channel",
        target_id=str(channel_id),
        details={"username": username},
    )
    await session.commit()
    return {"status": "deleted", "channel_id": channel_id, "username": username}


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int,
    payload: ChannelUpdate,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    if payload.title is not None:
        channel.title = payload.title
    if payload.category is not None:
        channel.category = payload.category
    if payload.is_active is not None:
        channel.is_active = payload.is_active

    await write_audit_log(
        session,
        action="channels.update",
        actor_user_id=current_user.id,
        target_type="channel",
        target_id=str(channel.id),
        details={
            "username": channel.username,
            "title": channel.title,
            "category": channel.category,
            "is_active": channel.is_active,
        },
    )
    await session.commit()
    await session.refresh(channel)
    return channel
