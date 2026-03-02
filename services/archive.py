from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ArchiveEvent,
    ArchiveEventReport,
    ArchivePostReport,
    ArchivePostText,
    ArchiveProcess,
    ArchiveProcessReport,
    Comment,
    Event,
    EventPost,
    EventReport,
    Post,
    PostFact,
    PostLink,
    Process,
    ProcessEvent,
    ProcessReport,
    Report,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _archive_posts(session: AsyncSession, *, cutoff: datetime, batch_limit: int) -> dict:
    post_rows = (
        await session.execute(
            select(Post)
            .where(Post.date < cutoff)
            .order_by(Post.date.asc(), Post.id.asc())
            .limit(batch_limit)
        )
    ).scalars().all()
    post_ids = [p.id for p in post_rows]
    if not post_ids:
        return {"archived_posts": 0, "archived_post_reports": 0, "deleted_posts": 0}

    for post in post_rows:
        await session.execute(
            insert(ArchivePostText)
            .values(
                src_post_id=post.id,
                channel_id=post.channel_id,
                tg_message_id=post.tg_message_id,
                post_date=post.date,
                text=post.text,
            )
            .on_conflict_do_nothing(index_elements=[ArchivePostText.src_post_id])
        )

    report_rows = (
        await session.execute(
            select(Report).where(Report.post_id.in_(post_ids))
        )
    ).scalars().all()
    for report in report_rows:
        await session.execute(
            insert(ArchivePostReport)
            .values(
                src_report_id=report.id,
                post_id=report.post_id,
                status=report.status,
                content=report.content,
                src_created_at=report.created_at,
            )
            .on_conflict_do_nothing(index_elements=[ArchivePostReport.src_report_id])
        )

    await session.execute(delete(Report).where(Report.post_id.in_(post_ids)))
    await session.execute(delete(PostFact).where(PostFact.post_id.in_(post_ids)))
    await session.execute(delete(EventPost).where(EventPost.post_id.in_(post_ids)))
    await session.execute(
        delete(PostLink).where(or_(PostLink.src_post_id.in_(post_ids), PostLink.dst_post_id.in_(post_ids)))
    )
    await session.execute(delete(Comment).where(Comment.post_id.in_(post_ids)))
    await session.execute(delete(Post).where(Post.id.in_(post_ids)))
    return {
        "archived_posts": len(post_rows),
        "archived_post_reports": len(report_rows),
        "deleted_posts": len(post_rows),
    }


async def _archive_processes(
    session: AsyncSession,
    *,
    cutoff: datetime,
    forced_process_ids: set[int],
    batch_limit: int,
) -> dict:
    base_process_ids = {
        row[0]
        for row in (
            await session.execute(
                select(Process.id)
                .where(func.coalesce(Process.ended_at, Process.started_at, Process.created_at) < cutoff)
                .order_by(Process.id.asc())
                .limit(batch_limit)
            )
        ).all()
    }
    process_ids = sorted(set(base_process_ids) | set(forced_process_ids))
    if not process_ids:
        return {"archived_processes": 0, "archived_process_reports": 0, "deleted_processes": 0, "process_ids": []}

    process_rows = (await session.execute(select(Process).where(Process.id.in_(process_ids)))).scalars().all()
    for process in process_rows:
        await session.execute(
            insert(ArchiveProcess)
            .values(
                src_process_id=process.id,
                title=process.title,
                started_at=process.started_at,
                ended_at=process.ended_at,
                confidence=process.confidence,
                status=process.status.value if hasattr(process.status, "value") else str(process.status),
                created_by=process.created_by,
                src_created_at=process.created_at,
                src_updated_at=process.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[ArchiveProcess.src_process_id])
        )

    process_report_rows = (
        await session.execute(select(ProcessReport).where(ProcessReport.process_id.in_(process_ids)))
    ).scalars().all()
    for report in process_report_rows:
        await session.execute(
            insert(ArchiveProcessReport)
            .values(
                src_process_report_id=report.id,
                process_id=report.process_id,
                report_text=report.report_text,
                report_json=report.report_json,
                version=report.version,
                src_created_at=report.created_at,
            )
            .on_conflict_do_nothing(index_elements=[ArchiveProcessReport.src_process_report_id])
        )

    await session.execute(delete(ProcessReport).where(ProcessReport.process_id.in_(process_ids)))
    await session.execute(delete(ProcessEvent).where(ProcessEvent.process_id.in_(process_ids)))
    await session.execute(delete(Process).where(Process.id.in_(process_ids)))
    return {
        "archived_processes": len(process_rows),
        "archived_process_reports": len(process_report_rows),
        "deleted_processes": len(process_rows),
        "process_ids": process_ids,
    }


async def _archive_events(session: AsyncSession, *, cutoff: datetime, batch_limit: int) -> dict:
    event_rows = (
        await session.execute(
            select(Event)
            .where(func.coalesce(Event.ended_at, Event.started_at, Event.created_at) < cutoff)
            .order_by(Event.id.asc())
            .limit(batch_limit)
        )
    ).scalars().all()
    event_ids = [event.id for event in event_rows]
    if not event_ids:
        return {"archived_events": 0, "archived_event_reports": 0, "deleted_events": 0, "forced_process_ids": []}

    for event in event_rows:
        await session.execute(
            insert(ArchiveEvent)
            .values(
                src_event_id=event.id,
                title=event.title,
                started_at=event.started_at,
                ended_at=event.ended_at,
                confidence=event.confidence,
                status=event.status.value if hasattr(event.status, "value") else str(event.status),
                created_by=event.created_by,
                src_created_at=event.created_at,
                src_updated_at=event.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[ArchiveEvent.src_event_id])
        )

    event_report_rows = (
        await session.execute(select(EventReport).where(EventReport.event_id.in_(event_ids)))
    ).scalars().all()
    for report in event_report_rows:
        await session.execute(
            insert(ArchiveEventReport)
            .values(
                src_event_report_id=report.id,
                event_id=report.event_id,
                report_text=report.report_text,
                report_json=report.report_json,
                version=report.version,
                src_created_at=report.created_at,
            )
            .on_conflict_do_nothing(index_elements=[ArchiveEventReport.src_event_report_id])
        )

    forced_process_ids = {
        row[0]
        for row in (
            await session.execute(select(ProcessEvent.process_id).where(ProcessEvent.event_id.in_(event_ids)))
        ).all()
    }

    await session.execute(delete(EventReport).where(EventReport.event_id.in_(event_ids)))
    await session.execute(delete(EventPost).where(EventPost.event_id.in_(event_ids)))
    await session.execute(delete(ProcessEvent).where(ProcessEvent.event_id.in_(event_ids)))
    await session.execute(delete(Event).where(Event.id.in_(event_ids)))
    return {
        "archived_events": len(event_rows),
        "archived_event_reports": len(event_report_rows),
        "deleted_events": len(event_rows),
        "forced_process_ids": sorted(forced_process_ids),
    }


async def run_archive_retention(
    session: AsyncSession,
    *,
    retention_days: int = 30,
    batch_limit: int = 1000,
) -> dict:
    cutoff = utcnow() - timedelta(days=retention_days)

    deleted_comments = await session.execute(delete(Comment).where(Comment.date < cutoff))
    deleted_comments_count = int(deleted_comments.rowcount or 0)

    post_stats = await _archive_posts(session, cutoff=cutoff, batch_limit=batch_limit)
    event_stats = await _archive_events(session, cutoff=cutoff, batch_limit=batch_limit)
    process_stats = await _archive_processes(
        session,
        cutoff=cutoff,
        forced_process_ids=set(event_stats.get("forced_process_ids", [])),
        batch_limit=batch_limit,
    )

    return {
        "cutoff": cutoff.isoformat(),
        "deleted_comments": deleted_comments_count,
        **post_stats,
        **{k: v for k, v in event_stats.items() if k != "forced_process_ids"},
        **{k: v for k, v in process_stats.items() if k != "process_ids"},
    }
