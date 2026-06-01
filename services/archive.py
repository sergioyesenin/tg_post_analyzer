from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    ArchiveEvent,
    ArchiveEventReport,
    ArchiveWatermark,
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

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _checksum(*parts) -> str:
    normalized = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
                checksum=_checksum("post_text", post.id, post.channel_id, post.tg_message_id, post.date, post.text),
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
                report_json=report.report_json,
                src_created_at=report.created_at,
                checksum=_checksum(
                    "post_report",
                    report.id,
                    report.post_id,
                    report.status,
                    report.created_at,
                    report.content,
                    report.report_json,
                ),
            )
            .on_conflict_do_nothing(index_elements=[ArchivePostReport.src_report_id])
        )

    # Удаление исходных записей (только после успешной вставки)
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
                checksum=_checksum(
                    "process",
                    process.id,
                    process.title,
                    process.started_at,
                    process.ended_at,
                    process.status.value if hasattr(process.status, "value") else str(process.status),
                    process.updated_at,
                ),
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
                checksum=_checksum("process_report", report.id, report.process_id, report.version, report.created_at, report.report_text),
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
                checksum=_checksum(
                    "event",
                    event.id,
                    event.title,
                    event.started_at,
                    event.ended_at,
                    event.status.value if hasattr(event.status, "value") else str(event.status),
                    event.updated_at,
                ),
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
                checksum=_checksum("event_report", report.id, report.event_id, report.version, report.created_at, report.report_text),
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
    """
    Атомарная архивация старых данных:
    - сначала вставка в архивные таблицы,
    - затем удаление исходных записей,
    - обновление archive_watermarks.
    При любой ошибке транзакция откатывается.
    """
    cutoff = utcnow() - timedelta(days=retention_days)

    # 1. Архивация постов (включая связанные комментарии, факты, отчёты, ссылки)
    post_stats = await _archive_posts(session, cutoff=cutoff, batch_limit=batch_limit)

    # 2. Архивация событий (и связанных отчётов)
    event_stats = await _archive_events(session, cutoff=cutoff, batch_limit=batch_limit)

    # 3. Архивация процессов (включая принудительные ID от событий)
    process_stats = await _archive_processes(
        session,
        cutoff=cutoff,
        forced_process_ids=set(event_stats.get("forced_process_ids", [])),
        batch_limit=batch_limit,
    )

    # 4. Подсчёт общего количества заархивированных строк
    total_rows_archived = int(
        post_stats.get("archived_posts", 0)
        + post_stats.get("archived_post_reports", 0)
        + event_stats.get("archived_events", 0)
        + event_stats.get("archived_event_reports", 0)
        + process_stats.get("archived_processes", 0)
        + process_stats.get("archived_process_reports", 0)
    )

    # 5. Обновление водяного знака (archive_watermarks)
    #    Используем ON CONFLICT, так как таблица уже существует и имеет уникальное ограничение на job_name
    await session.execute(
        insert(ArchiveWatermark)
        .values(
            job_name="archive_retention",
            archived_before=cutoff,
            last_run_at=utcnow(),
            last_success_at=utcnow(),
            rows_archived_last_run=total_rows_archived,
            last_error=None,
        )
        .on_conflict_do_update(
            index_elements=[ArchiveWatermark.job_name],
            set_={
                "archived_before": cutoff,
                "last_run_at": utcnow(),
                "last_success_at": utcnow(),
                "rows_archived_last_run": total_rows_archived,
                "last_error": None,
            },
        )
    )

    # 6. Фиксация транзакции (произойдёт автоматически при выходе из session, если нет ошибок)
    #    session.commit() вызывается в вызывающем коде (например, run_retention.py через async with)

    return {
        "cutoff": cutoff.isoformat(),
        "deleted_comments": post_stats.get("deleted_posts", 0),  # комментарии удалены вместе с постами
        "rows_archived_last_run": total_rows_archived,
        **post_stats,
        **{k: v for k, v in event_stats.items() if k != "forced_process_ids"},
        **{k: v for k, v in process_stats.items() if k != "process_ids"},
    }