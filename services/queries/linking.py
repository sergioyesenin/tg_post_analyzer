from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Channel,
    Event,
    EventPost,
    EventReport,
    Job,
    Post,
    PostLink,
    ProcessEvent,
    ProcessReport,
)
from services.jobs import JOB_STATUS_PENDING, JOB_STATUS_RUNNING, JobType


async def find_active_job_by_dedupe_key(
    session: AsyncSession,
    *,
    job_type: str,
    dedupe_key: str,
) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.type == job_type)
        .where(Job.dedupe_key == dedupe_key)
        .where(Job.status.in_((JOB_STATUS_PENDING, JOB_STATUS_RUNNING)))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_events_summary(
    session: AsyncSession,
    *,
    limit: int,
) -> list[Event]:
    stmt = (
        select(Event)
        .order_by(Event.started_at.desc().nullslast(), Event.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_post_or_none(
    session: AsyncSession,
    *,
    post_id: int,
) -> Post | None:
    stmt = select(Post).where(Post.id == post_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_links_for_post(
    session: AsyncSession,
    *,
    post_id: int,
) -> list[PostLink]:
    stmt = (
        select(PostLink)
        .where(or_(PostLink.src_post_id == post_id, PostLink.dst_post_id == post_id))
        .order_by(PostLink.updated_at.desc(), PostLink.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_event_post_ids(
    session: AsyncSession,
    *,
    event_id: int,
) -> list[int]:
    stmt = select(EventPost.post_id).where(EventPost.event_id == event_id)
    return [int(row[0]) for row in (await session.execute(stmt)).all()]


async def get_event_root_post_id(
    session: AsyncSession,
    *,
    event_id: int,
) -> int | None:
    stmt = (
        select(EventPost.post_id)
        .where(EventPost.event_id == event_id)
        .where(EventPost.role == "root")
        .limit(1)
    )
    value = await session.scalar(stmt)
    return int(value) if value is not None else None


async def list_event_channel_usernames(
    session: AsyncSession,
    *,
    event_id: int,
) -> list[str]:
    stmt = (
        select(Channel.username)
        .select_from(EventPost)
        .join(Post, Post.id == EventPost.post_id)
        .join(Channel, Channel.id == Post.channel_id)
        .where(EventPost.event_id == event_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return [str(username) for (username,) in rows if username]


async def get_latest_event_report(
    session: AsyncSession,
    *,
    event_id: int,
) -> EventReport | None:
    stmt = (
        select(EventReport)
        .where(EventReport.event_id == event_id)
        .order_by(EventReport.version.desc(), EventReport.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_process_events_with_event_meta(
    session: AsyncSession,
    *,
    process_id: int,
) -> list[tuple[ProcessEvent, str | None, object, object, float | None]]:
    stmt = (
        select(
            ProcessEvent,
            Event.title,
            Event.started_at,
            Event.ended_at,
            Event.confidence,
        )
        .join(Event, Event.id == ProcessEvent.event_id)
        .where(ProcessEvent.process_id == process_id)
        .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
    )
    return list((await session.execute(stmt)).all())


async def list_post_ids_for_events(
    session: AsyncSession,
    *,
    event_ids: list[int],
) -> list[tuple[int, int]]:
    stmt = (
        select(EventPost.event_id, EventPost.post_id)
        .where(EventPost.event_id.in_(event_ids))
        .order_by(EventPost.event_id.asc(), EventPost.created_at.asc(), EventPost.post_id.asc())
    )
    return list((await session.execute(stmt)).all())


async def get_latest_process_report(
    session: AsyncSession,
    *,
    process_id: int,
) -> ProcessReport | None:
    stmt = (
        select(ProcessReport)
        .where(ProcessReport.process_id == process_id)
        .order_by(ProcessReport.version.desc(), ProcessReport.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()