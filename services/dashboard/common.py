from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EventPost, EventReport, Job, Post, PostLink, ProcessEvent, ProcessReport, Report
from services.reporting import (
    REPORT_STATUS_DRAFT,
    REPORT_STATUS_FAILED,
    REPORT_STATUS_INSUFFICIENT_DATA,
    REPORT_STATUS_LIMITED,
    REPORT_STATUS_READY,
    report_status_from_payload,
)


POST_PENDING_JOB_STATUSES = ("pending", "running")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def text_preview(value: str | None) -> str | None:
    if not value:
        return None
    line = value.splitlines()[0].strip()
    return line or None


def average_or_none(values: list[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


async def load_post_report_statuses(session: AsyncSession, post_ids: list[int]) -> dict[int, str]:
    if not post_ids:
        return {}

    statuses: dict[int, str] = {post_id: "missing" for post_id in post_ids}
    report_rows = (
        await session.execute(select(Report.post_id, Report.status).where(Report.post_id.in_(post_ids)))
    ).all()
    for post_id, status in report_rows:
        statuses[int(post_id)] = str(status or "ready")

    job_post_id = cast(Job.payload_json["post_id"].astext, Integer)
    job_rows = (
        await session.execute(
            select(job_post_id.label("post_id"))
            .where(Job.type == "build_post_report")
            .where(Job.status.in_(POST_PENDING_JOB_STATUSES))
            .where(job_post_id.in_(post_ids))
            .group_by(job_post_id)
        )
    ).all()
    for row in job_rows:
        post_id = int(row[0])
        if statuses.get(post_id) == "missing":
            statuses[post_id] = "pending"

    return statuses


async def load_post_link_counts(session: AsyncSession, post_ids: list[int]) -> dict[int, int]:
    if not post_ids:
        return {}

    rows = (
        await session.execute(
            select(PostLink.src_post_id.label("post_id"), func.count(PostLink.id).label("links_count"))
            .where(PostLink.src_post_id.in_(post_ids))
            .group_by(PostLink.src_post_id)
        )
    ).all()
    counts: defaultdict[int, int] = defaultdict(int)
    for post_id, links_count in rows:
        counts[int(post_id)] += int(links_count or 0)

    rows = (
        await session.execute(
            select(PostLink.dst_post_id.label("post_id"), func.count(PostLink.id).label("links_count"))
            .where(PostLink.dst_post_id.in_(post_ids))
            .group_by(PostLink.dst_post_id)
        )
    ).all()
    for post_id, links_count in rows:
        counts[int(post_id)] += int(links_count or 0)
    return dict(counts)


async def load_latest_event_report_statuses(session: AsyncSession, event_ids: list[int]) -> dict[int, str]:
    if not event_ids:
        return {}

    rows = (
        await session.execute(
            select(EventReport.event_id, EventReport.report_json)
            .where(EventReport.event_id.in_(event_ids))
            .order_by(EventReport.event_id.asc(), EventReport.created_at.desc(), EventReport.id.desc())
        )
    ).all()
    statuses: dict[int, str] = {}
    for event_id, payload in rows:
        key = int(event_id)
        if key in statuses:
            continue
        statuses[key] = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    return statuses


async def load_latest_process_report_statuses(session: AsyncSession, process_ids: list[int]) -> dict[int, str]:
    if not process_ids:
        return {}

    rows = (
        await session.execute(
            select(ProcessReport.process_id, ProcessReport.report_json)
            .where(ProcessReport.process_id.in_(process_ids))
            .order_by(ProcessReport.process_id.asc(), ProcessReport.created_at.desc(), ProcessReport.id.desc())
        )
    ).all()
    statuses: dict[int, str] = {}
    for process_id, payload in rows:
        key = int(process_id)
        if key in statuses:
            continue
        statuses[key] = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    return statuses


async def load_event_post_rows(session: AsyncSession, event_ids: list[int]) -> list[tuple]:
    if not event_ids:
        return []
    return (
        await session.execute(
            select(
                EventPost.event_id,
                EventPost.post_id,
                EventPost.role,
                EventPost.score,
                Post.channel_id,
                Post.date,
                Post.comments_count,
                Post.involvement,
            )
            .join(Post, Post.id == EventPost.post_id)
            .where(EventPost.event_id.in_(event_ids))
            .order_by(EventPost.event_id.asc(), EventPost.created_at.asc(), Post.date.asc(), Post.id.asc())
        )
    ).all()


async def load_process_event_rows(session: AsyncSession, process_ids: list[int]) -> list[tuple]:
    if not process_ids:
        return []
    return (
        await session.execute(
            select(
                ProcessEvent.process_id,
                ProcessEvent.event_id,
                ProcessEvent.relation_type,
                ProcessEvent.direction,
                ProcessEvent.score,
            )
            .where(ProcessEvent.process_id.in_(process_ids))
            .order_by(ProcessEvent.process_id.asc(), ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()


def summarize_report_statuses(statuses: list[str]) -> dict[str, int]:
    counts = {
        REPORT_STATUS_DRAFT: 0,
        REPORT_STATUS_READY: 0,
        REPORT_STATUS_LIMITED: 0,
        REPORT_STATUS_INSUFFICIENT_DATA: 0,
        REPORT_STATUS_FAILED: 0,
        "missing": 0,
        "pending": 0,
    }
    for status in statuses:
        counts[str(status)] = counts.get(str(status), 0) + 1
    return counts
