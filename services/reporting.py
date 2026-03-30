from __future__ import annotations

import json
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import ReportConfig, TgReportProject
from db.models import Channel, Comment, Event, EventPost, EventReport, Post, Process, ProcessEvent, ProcessReport, Report
from services.ingest import upsert_report
from services.report_aggregation import build_event_report_payload, build_process_report_payload


SKIPPED_MIN_COMMENTS_PREFIX = "STATUS: SKIPPED_MIN_COMMENTS"
REPORT_GENERATION_FAILED_CONTENT = "STATUS: FAILED\nREASON: report_generation_failed"
REPORT_STATUS_DRAFT = "draft"
REPORT_STATUS_READY = "ready"
REPORT_STATUS_FAILED = "failed"
REPORT_STATUS_DEFERRED = "deferred_waiting_dependencies"


def _serialize_report_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_post_report_text(payload: dict) -> str:
    lines = [
        f"Заголовок: {payload.get('title') or 'Отчет по посту'}",
        "",
        f"Краткое резюме: {payload.get('summary') or 'Нет данных.'}",
    ]
    sentiment = payload.get("sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    lines.extend(
        [
            "",
            "Тональность:",
            f"- Доминирующая: {sentiment.get('dominant') or 'neutral'}",
            (
                f"- Распределение: позитив {distribution.get('positive', 0)} / "
                f"негатив {distribution.get('negative', 0)} / "
                f"нейтрально {distribution.get('neutral', 0)}"
            ),
        ]
    )
    topics = [item.get("name") for item in payload.get("topics") or [] if isinstance(item, dict) and item.get("name")]
    if topics:
        lines.extend(["", "Темы:", *[f"- {topic}" for topic in topics[:5]]])
    risks = [item for item in payload.get("risks") or [] if isinstance(item, str) and item.strip()]
    if risks:
        lines.extend(["", "Риски:", *[f"- {item}" for item in risks[:5]]])
    return "\n".join(lines).strip()


def _render_event_or_process_text(payload: dict) -> str:
    title = payload.get("event_title") or payload.get("process_title") or payload.get("title") or "Отчет"
    lines = [
        f"Заголовок: {title}",
        "",
        f"Краткое резюме: {payload.get('summary') or 'Нет данных.'}",
    ]
    sentiment = payload.get("sentiment") or payload.get("overall_sentiment") or {}
    if isinstance(sentiment, dict):
        lines.extend(
            [
                "",
                "Тональность:",
                f"- Доминирующая: {sentiment.get('dominant') or 'neutral'}",
            ]
        )
    risks = [item for item in payload.get("risks") or [] if isinstance(item, str) and item.strip()]
    if risks:
        lines.extend(["", "Риски:", *[f"- {item}" for item in risks[:5]]])
    return "\n".join(lines).strip()


def report_status_from_payload(payload: dict | None, *, fallback: str = REPORT_STATUS_READY) -> str:
    if not isinstance(payload, dict):
        return fallback
    status = payload.get("status")
    if isinstance(status, str) and status:
        return status
    payload_type = payload.get("type")
    if payload_type in {"event_report_draft_v1", "process_report_draft_v1"}:
        return REPORT_STATUS_DRAFT
    return fallback


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
    status = REPORT_STATUS_READY
    report_json: dict | None = None
    try:
        report_json = await report_project.generate_post_report_payload(
            channel=channel_label,
            post_id=post.id,
            published_at_iso=post.date.isoformat(),
            post_text=post.text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=post.views,
            config=report_config,
        )
        report_json.setdefault("post_id", post.id)
        report_json.setdefault("published_at", post.date.isoformat())
        content = _render_post_report_text(report_json)
    except Exception as exc:
        status = REPORT_STATUS_FAILED
        content = REPORT_GENERATION_FAILED_CONTENT
        technical_error = f"{type(exc).__name__}: {exc}"
    else:
        technical_error = None

    if isinstance(report_json, dict) and report_json.get("status") == "skipped_min_comments":
        return {
            "status": "skipped_min_comments",
            "post_id": post.id,
            "report_id": None,
        }

    report = await upsert_report(
        session,
        post_id=post.id,
        status=status,
        content=content,
        report_json=report_json,
    )
    result = {"status": status, "post_id": post.id, "report_id": report.id}
    if technical_error is not None:
        result["technical_error"] = technical_error
    return result


async def _load_post_report_payloads_for_event(session: AsyncSession, *, event_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(Report.report_json, Report.post_id, EventPost.role, Post.date)
            .join(EventPost, EventPost.post_id == Report.post_id)
            .join(Post, Post.id == Report.post_id)
            .where(EventPost.event_id == event_id)
            .where(Report.report_json.is_not(None))
            .order_by(Post.date.asc(), Report.id.asc())
        )
    ).all()
    payloads: list[dict] = []
    for report_json, post_id, role, post_date in rows:
        if not isinstance(report_json, dict):
            continue
        payload = dict(report_json)
        payload.setdefault("post_id", int(post_id))
        payload["event_role"] = role
        payload.setdefault("published_at", post_date.isoformat() if post_date is not None else None)
        payloads.append(payload)
    return payloads


async def _event_report_readiness(session: AsyncSession, *, event_id: int) -> dict:
    min_comments = ReportConfig().min_comments
    rows = (
        await session.execute(
            select(EventPost.post_id, EventPost.role, Post.comments_count, Report.report_json)
            .join(Post, Post.id == EventPost.post_id)
            .outerjoin(Report, Report.post_id == EventPost.post_id)
            .where(EventPost.event_id == event_id)
            .order_by(EventPost.created_at.asc(), EventPost.post_id.asc())
        )
    ).all()
    total_posts = len(rows)
    if total_posts == 0:
        return {
            "ready": True,
            "reason": "no_posts",
            "total_posts": 0,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "root_ready": True,
        }

    eligible_posts = 0
    ready_post_reports = 0
    root_ready = False
    for _post_id, role, comments_count, report_json in rows:
        eligible = int(comments_count or 0) >= min_comments
        has_report = isinstance(report_json, dict)
        if eligible:
            eligible_posts += 1
            if has_report:
                ready_post_reports += 1
        if role == "root":
            root_ready = has_report or not eligible

    if eligible_posts == 0:
        return {
            "ready": True,
            "reason": "no_eligible_posts",
            "total_posts": total_posts,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "required_ready_post_reports": 0,
            "root_ready": True,
        }

    required_ready = max(1, math.ceil(eligible_posts * 0.7))
    ready = root_ready and ready_post_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else "waiting_post_reports",
        "total_posts": total_posts,
        "eligible_posts": eligible_posts,
        "ready_post_reports": ready_post_reports,
        "required_ready_post_reports": required_ready,
        "root_ready": root_ready,
    }


async def build_event_report_draft(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict:
    event = await session.get(Event, event_id)
    if event is None:
        return {"status": "not_found", "event_id": event_id}

    readiness = await _event_report_readiness(session, event_id=event_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "event_id": event_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
        }

    post_payloads = await _load_post_report_payloads_for_event(session, event_id=event_id)
    if not post_payloads:
        payload = {
            "type": "event_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "event_id": event_id,
            "event_title": event.title,
            "posts_count": int(readiness.get("total_posts") or 0),
            "source_post_reports": [],
            "summary": "Для события пока нет готовых отчетов по постам.",
            "meta": {"prompt_version": "event_report_v2", "source_type": "post_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_event_report_payload(
            event_id=event_id,
            event_title=event.title,
            post_reports=post_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)

    last_version = (
        await session.execute(
            select(EventReport.version)
            .where(EventReport.event_id == event_id)
            .order_by(EventReport.version.desc(), EventReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = EventReport(
        event_id=event_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "event_id": event_id, "report_id": report.id}


async def _load_latest_event_report_payloads_for_process(session: AsyncSession, *, process_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(
                ProcessEvent.event_id,
                Event.title,
                EventReport.report_json,
                EventReport.id,
            )
            .join(Event, Event.id == ProcessEvent.event_id)
            .outerjoin(
                EventReport,
                EventReport.id
                == (
                    select(EventReport.id)
                    .where(EventReport.event_id == ProcessEvent.event_id)
                    .order_by(EventReport.version.desc(), EventReport.id.desc())
                    .limit(1)
                    .scalar_subquery()
                ),
            )
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()
    payloads: list[dict] = []
    fallback_event_ids: list[int] = []
    for event_id, event_title, report_json, _report_id in rows:
        if isinstance(report_json, dict):
            payload = dict(report_json)
            payload.setdefault("event_id", int(event_id))
            payload.setdefault("event_title", event_title)
            payloads.append(payload)
        else:
            fallback_event_ids.append(int(event_id))
    for event_id in fallback_event_ids:
        post_payloads = await _load_post_report_payloads_for_event(session, event_id=event_id)
        if not post_payloads:
            continue
        event = await session.get(Event, event_id)
        payloads.append(
            build_event_report_payload(
                event_id=event_id,
                event_title=event.title if event is not None else None,
                post_reports=post_payloads,
            )
        )
    return payloads


async def _process_report_readiness(session: AsyncSession, *, process_id: int) -> dict:
    event_ids = [
        int(row[0])
        for row in (
            await session.execute(
                select(ProcessEvent.event_id)
                .where(ProcessEvent.process_id == process_id)
                .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
            )
        ).all()
    ]
    total_events = len(event_ids)
    if total_events == 0:
        return {
            "ready": True,
            "reason": "no_events",
            "total_events": 0,
            "ready_event_reports": 0,
            "required_ready_event_reports": 0,
        }

    ready_event_reports = len(
        {
            int(row[0])
            for row in (
                await session.execute(
                    select(EventReport.event_id)
                    .where(EventReport.event_id.in_(event_ids))
                    .distinct()
                )
            ).all()
        }
    )
    required_ready = max(1, math.ceil(total_events * 0.7))
    ready = ready_event_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else "waiting_event_reports",
        "total_events": total_events,
        "ready_event_reports": ready_event_reports,
        "required_ready_event_reports": required_ready,
    }


async def build_process_report_draft(
    session: AsyncSession,
    *,
    process_id: int,
) -> dict:
    process = await session.get(Process, process_id)
    if process is None:
        return {"status": "not_found", "process_id": process_id}

    readiness = await _process_report_readiness(session, process_id=process_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "process_id": process_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
        }

    event_payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    if not event_payloads:
        payload = {
            "type": "process_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "process_id": process_id,
            "process_title": process.title,
            "events_count": int(readiness.get("total_events") or 0),
            "source_event_reports": [],
            "summary": "Для процесса пока нет готовых отчетов по событиям или постам.",
            "meta": {"prompt_version": "process_report_v2", "source_type": "event_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_process_report_payload(
            process_id=process_id,
            process_title=process.title,
            event_reports=event_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)

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
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "process_id": process_id, "report_id": report.id}
