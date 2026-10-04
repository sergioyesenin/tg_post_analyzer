"""Управление stale-состоянием post-report'ов.

Определяет, когда входные данные отчёта изменились, помечает отчёт stale,
и каскадно помечает stale связанные event/process-отчёты.

Все функции работают с БД через AsyncSession.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Comment,
    EventPost,
    EventReport,
    Job,
    Post,
    ProcessEvent,
    ProcessReport,
    Report,
)
from services.jobs import JOB_STATUS_DONE, JobType
from services.reporting.constants import (
    DEFAULT_MIN_COMMENTS,
    REPORT_STATUS_READY,
    REPORT_STATUS_STALE,
)
from services.reporting.mapping import report_status_from_payload


def _signature_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _build_post_report_input_signature(
    *,
    post: Post,
    comment_rows: list[tuple],
) -> str:
    payload = {
        "post": {
            "id": int(post.id),
            "date": _signature_timestamp(post.date),
            "text": post.text or "",
            "views": int(post.views) if post.views is not None else None,
            "comments_count": int(post.comments_count or 0),
            "reactions_json": post.reactions_json if isinstance(post.reactions_json, dict) else None,
        },
        "comments": [
            {
                "tg_message_id": int(tg_message_id),
                "parent_tg_message_id": int(parent_tg_message_id) if parent_tg_message_id is not None else None,
                "thread_root_tg_message_id": int(thread_root_tg_message_id) if thread_root_tg_message_id is not None else None,
                "depth": int(depth or 0),
                "date": _signature_timestamp(date),
                "text": text or "",
                "reactions_json": reactions_json if isinstance(reactions_json, dict) else None,
            }
            for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, reactions_json in comment_rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _load_post_comment_rows_for_signature(session: AsyncSession, *, post_id: int) -> list[tuple]:
    return (
        await session.execute(
            select(
                Comment.tg_message_id,
                Comment.parent_tg_message_id,
                Comment.thread_root_tg_message_id,
                Comment.depth,
                Comment.date,
                Comment.text,
                Comment.reactions_json,
            )
            .where(Comment.post_id == post_id)
            .order_by(Comment.date.asc(), Comment.id.asc())
        )
    ).all()


async def compute_post_report_input_signature(
    session: AsyncSession,
    *,
    post_id: int,
    post: Post | None = None,
) -> str | None:
    post_row = post or await session.get(Post, post_id)
    if post_row is None:
        return None
    comment_rows = await _load_post_comment_rows_for_signature(session, post_id=post_row.id)
    return _build_post_report_input_signature(post=post_row, comment_rows=comment_rows)


async def _load_post_refresh_attempt_info(session: AsyncSession, *, post_id: int) -> dict | None:
    row = (
        await session.execute(
            select(Job.type, Job.updated_at)
            .where(Job.type.in_((JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS)))
            .where(Job.status == JOB_STATUS_DONE)
            .where(Job.payload_json["post_id"].astext == str(post_id))
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    job_type, updated_at = row
    return {
        "source": str(job_type),
        "collected_at": updated_at.isoformat() if updated_at is not None else None,
        "is_complete": False,
    }


def mark_report_payload_stale(
    payload: dict | None,
    *,
    dependency_type: str,
    dependency_id: int,
) -> dict:
    next_payload = dict(payload or {})
    previous_status = report_status_from_payload(next_payload, fallback=REPORT_STATUS_READY)
    meta = dict(next_payload.get("meta") or {})
    next_payload["status"] = REPORT_STATUS_STALE
    next_payload["meta"] = {
        **meta,
        "stale": True,
        "stale_dependency_type": dependency_type,
        "stale_dependency_id": int(dependency_id),
        "stale_marked_at": meta.get("stale_marked_at") or datetime.now(timezone.utc).isoformat(),
        "previous_status": meta.get("previous_status") or previous_status,
    }
    return next_payload


async def _mark_related_event_reports_stale_for_post(session: AsyncSession, *, post_id: int) -> tuple[int, list[int]]:
    rows = (
        await session.execute(
            select(EventReport)
            .where(
                EventReport.id.in_(
                    select(EventReport.id)
                    .join(EventPost, EventPost.event_id == EventReport.event_id)
                    .where(EventPost.post_id == post_id)
                    .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
                    .distinct(EventReport.event_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    event_ids: list[int] = []
    for report in rows:
        event_ids.append(int(report.event_id))
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="post_report",
            dependency_id=post_id,
        )
        marked += 1
    if marked:
        await session.flush()
    return marked, event_ids


async def _mark_related_process_reports_stale_for_events(session: AsyncSession, *, event_ids: list[int]) -> int:
    if not event_ids:
        return 0
    rows = (
        await session.execute(
            select(ProcessReport)
            .where(
                ProcessReport.id.in_(
                    select(ProcessReport.id)
                    .join(ProcessEvent, ProcessEvent.process_id == ProcessReport.process_id)
                    .where(ProcessEvent.event_id.in_(event_ids))
                    .order_by(ProcessReport.process_id.asc(), ProcessReport.version.desc(), ProcessReport.id.desc())
                    .distinct(ProcessReport.process_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    for report in rows:
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="event_report",
            dependency_id=int(event_ids[0]),
        )
        marked += 1
    if marked:
        await session.flush()
    return marked


async def sync_post_report_staleness(
    session: AsyncSession,
    *,
    post_id: int,
    source: str,
    dependency_type: str = "post_inputs",
    dependency_id: int | None = None,
) -> dict:
    post = await session.get(Post, post_id)
    if post is None:
        return {"status": "not_found", "post_id": post_id}

    report = (
        await session.execute(select(Report).where(Report.post_id == post_id))
    ).scalar_one_or_none()
    min_comments = DEFAULT_MIN_COMMENTS
    if report is None and int(post.comments_count or 0) < min_comments:
        return {
            "status": "ignored_below_min_comments",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    current_signature = await compute_post_report_input_signature(session, post_id=post_id, post=post)
    if current_signature is None:
        return {"status": "not_found", "post_id": post_id}

    report_payload = report.report_json if report is not None and isinstance(report.report_json, dict) else {}
    report_meta = dict(report_payload.get("meta") or {})
    stored_signature = report_meta.get("current_input_signature") or report_meta.get("input_signature")
    if stored_signature == current_signature:
        return {
            "status": "unchanged",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    stale_marked = False
    event_reports_marked = 0
    process_reports_marked = 0
    if report is not None and isinstance(report.report_json, dict):
        next_payload = mark_report_payload_stale(
            report.report_json,
            dependency_type=dependency_type,
            dependency_id=dependency_id if dependency_id is not None else post_id,
        )
        next_meta = dict(next_payload.get("meta") or {})
        next_meta["previous_input_signature"] = report_meta.get("input_signature")
        next_meta["current_input_signature"] = current_signature
        next_payload["meta"] = next_meta
        report.report_json = next_payload
        stale_marked = True
        event_reports_marked, event_ids = await _mark_related_event_reports_stale_for_post(session, post_id=post_id)
        process_reports_marked = await _mark_related_process_reports_stale_for_events(session, event_ids=event_ids)

    return {
        "status": "stale_marked" if stale_marked else "changed",
        "post_id": post_id,
        "changed": True,
        "stale_marked": stale_marked,
        "event_reports_marked_stale": event_reports_marked,
        "process_reports_marked_stale": process_reports_marked,
        "enqueued": False,
        "job_id": None,
        "input_signature": current_signature,
        "source": source,
    }