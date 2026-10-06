from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Channel,
    Event,
    EventReport,
    Post,
    Process,
    ProcessReport,
    Report,
)


async def get_post_report_by_post_id(
    session: AsyncSession,
    *,
    post_id: int,
) -> Report | None:
    stmt = select(Report).where(Report.post_id == post_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_latest_post_report_for_trace(
    session: AsyncSession,
    *,
    post_id: int,
) -> Report | None:
    stmt = (
        select(Report)
        .where(Report.post_id == post_id)
        .order_by(Report.created_at.desc(), Report.id.desc())
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_latest_event_report_for_trace(
    session: AsyncSession,
    *,
    event_id: int,
) -> EventReport | None:
    stmt = (
        select(EventReport)
        .where(EventReport.event_id == event_id)
        .order_by(EventReport.version.desc(), EventReport.id.desc())
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def build_post_reports_stmt(
    *,
    channel_ids: list[int],
    categories: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select:
    stmt = (
        select(Report, Post, Channel)
        .join(Post, Post.id == Report.post_id)
        .join(Channel, Channel.id == Post.channel_id)
    )
    conditions = []
    if channel_ids:
        conditions.append(Post.channel_id.in_(channel_ids))
    if categories:
        conditions.append(Channel.category.in_(categories))
    if date_from is not None:
        conditions.append(Post.date >= date_from)
    if date_to is not None:
        conditions.append(Post.date <= date_to)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return stmt.order_by(Post.date.desc(), Report.id.desc())


async def list_post_reports(
    session: AsyncSession,
    *,
    channel_ids: list[int],
    categories: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> list[tuple[Report, Post, Channel]]:
    stmt = (
        build_post_reports_stmt(
            channel_ids=channel_ids,
            categories=categories,
            date_from=date_from,
            date_to=date_to,
        )
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).all())


async def export_post_reports(
    session: AsyncSession,
    *,
    channel_ids: list[int],
    categories: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> list[tuple[Report, Post, Channel]]:
    stmt = build_post_reports_stmt(
        channel_ids=channel_ids,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
    ).limit(limit)
    return list((await session.execute(stmt)).all())


async def list_event_reports(
    session: AsyncSession,
    *,
    event_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> list[tuple[EventReport, Event]]:
    stmt = (
        select(EventReport, Event)
        .join(Event, Event.id == EventReport.event_id)
        .order_by(EventReport.created_at.desc(), EventReport.id.desc())
    )
    if event_id is not None:
        stmt = stmt.where(EventReport.event_id == event_id)
    if date_from is not None:
        stmt = stmt.where(EventReport.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(EventReport.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).all())


async def export_event_reports(
    session: AsyncSession,
    *,
    event_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> list[tuple[EventReport, Event]]:
    stmt = (
        select(EventReport, Event)
        .join(Event, Event.id == EventReport.event_id)
        .order_by(EventReport.created_at.desc(), EventReport.id.desc())
    )
    if event_id is not None:
        stmt = stmt.where(EventReport.event_id == event_id)
    if date_from is not None:
        stmt = stmt.where(EventReport.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(EventReport.created_at <= date_to)
    stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).all())


async def list_process_reports(
    session: AsyncSession,
    *,
    process_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> list[tuple[ProcessReport, Process]]:
    stmt = (
        select(ProcessReport, Process)
        .join(Process, Process.id == ProcessReport.process_id)
        .order_by(ProcessReport.created_at.desc(), ProcessReport.id.desc())
    )
    if process_id is not None:
        stmt = stmt.where(ProcessReport.process_id == process_id)
    if date_from is not None:
        stmt = stmt.where(ProcessReport.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProcessReport.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).all())


async def export_process_reports(
    session: AsyncSession,
    *,
    process_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> list[tuple[ProcessReport, Process]]:
    stmt = (
        select(ProcessReport, Process)
        .join(Process, Process.id == ProcessReport.process_id)
        .order_by(ProcessReport.created_at.desc(), ProcessReport.id.desc())
    )
    if process_id is not None:
        stmt = stmt.where(ProcessReport.process_id == process_id)
    if date_from is not None:
        stmt = stmt.where(ProcessReport.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProcessReport.created_at <= date_to)
    stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).all())