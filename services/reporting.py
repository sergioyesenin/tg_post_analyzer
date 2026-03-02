from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import ReportConfig, TgReportProject
from db.models import Channel, Comment, Event, EventPost, EventReport, Post, Process, ProcessEvent, ProcessReport
from services.ingest import upsert_report


async def build_post_report(
    session: AsyncSession,
    *,
    post_id: int,
    report_project: TgReportProject,
    report_config: ReportConfig | None = None,
) -> dict:
    post_result = await session.execute(
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = post_result.first()
    if row is None:
        return {"status": "not_found", "post_id": post_id}

    post, channel = row
    comments_result = await session.execute(
        select(
            Comment.tg_message_id,
            Comment.parent_tg_message_id,
            Comment.thread_root_tg_message_id,
            Comment.depth,
            Comment.date,
            Comment.text,
        )
        .where(Comment.post_id == post.id)
        .order_by(Comment.date.asc(), Comment.id.asc())
    )

    comments: list[str] = []
    thread_comments: list[dict] = []
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text in comments_result.all():
        if not text or not text.strip():
            continue
        comments.append(text)
        normalized_parent_id = parent_tg_message_id
        if thread_root_tg_message_id is not None and parent_tg_message_id == thread_root_tg_message_id:
            normalized_parent_id = None
        thread_comments.append(
            {
                "id": tg_message_id,
                "parent_id": normalized_parent_id,
                "depth": depth,
                "date": date.isoformat() if date is not None else None,
                "text": text,
            }
        )

    channel_label = f"@{channel.username}" if channel.username else f"channel:{channel.id}"
    status = "ready"
    try:
        content = await report_project.generate_report(
            channel=channel_label,
            post_id=post.id,
            published_at_iso=post.date.isoformat(),
            post_text=post.text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=post.views,
            config=report_config,
        )
    except Exception as exc:
        status = "failed"
        content = f"STATUS: FAILED\nREASON: {exc!r}"

    report = await upsert_report(
        session,
        post_id=post.id,
        status=status,
        content=content,
    )
    return {"status": status, "post_id": post.id, "report_id": report.id}


async def build_event_report_draft(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict:
    event = await session.get(Event, event_id)
    if event is None:
        return {"status": "not_found", "event_id": event_id}

    rows = (
        await session.execute(
            select(Post)
            .join(EventPost, EventPost.post_id == Post.id)
            .where(EventPost.event_id == event_id)
            .order_by(Post.date.asc(), Post.id.asc())
        )
    ).scalars().all()
    payload = {
        "type": "event_report_draft_v1",
        "event_id": event_id,
        "event_title": event.title,
        "posts_count": len(rows),
        "post_ids": [p.id for p in rows],
    }
    last_version = (
        await session.execute(
            select(EventReport.version)
            .where(EventReport.event_id == event_id)
            .order_by(EventReport.version.desc(), EventReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = EventReport(event_id=event_id, report_text=str(payload), report_json=payload, version=next_version)
    session.add(report)
    await session.flush()
    return {"status": "ready", "event_id": event_id, "report_id": report.id}


async def build_process_report_draft(
    session: AsyncSession,
    *,
    process_id: int,
) -> dict:
    process = await session.get(Process, process_id)
    if process is None:
        return {"status": "not_found", "process_id": process_id}

    rows = (
        await session.execute(
            select(ProcessEvent.event_id, ProcessEvent.relation_type, ProcessEvent.score)
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc())
        )
    ).all()
    payload = {
        "type": "process_report_draft_v1",
        "process_id": process_id,
        "process_title": process.title,
        "events_count": len(rows),
        "events": [
            {
                "event_id": event_id,
                "relation_type": relation_type.value if hasattr(relation_type, "value") else str(relation_type),
                "score": score,
            }
            for event_id, relation_type, score in rows
        ],
    }
    last_version = (
        await session.execute(
            select(ProcessReport.version)
            .where(ProcessReport.process_id == process_id)
            .order_by(ProcessReport.version.desc(), ProcessReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = ProcessReport(
        process_id=process_id,
        report_text=str(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": "ready", "process_id": process_id, "report_id": report.id}
