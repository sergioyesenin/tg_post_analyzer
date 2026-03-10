from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import TgReportProject
from deps import get_session, require_roles
from db.models import (
    Channel,
    Event,
    EventReport,
    Post,
    Process,
    ProcessReport,
    Report,
)
from schemas.report import ReportOut
from services.auth import AuthUser
from services.pipeline_runtime import (
    enqueue_event_report_job,
    enqueue_post_report_job,
    enqueue_process_report_job,
    wait_for_job_result,
)
from services.settings_store import get_all_settings, report_config_from_settings

router = APIRouter()
report_project = TgReportProject(
    llm_model="ollama/llama3:8b-instruct-q4_K_M",
)


def _parse_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    return values


def _parse_str_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token and token.strip()]


def _build_post_reports_stmt(
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


def _csv_response(*, filename: str, rows: list[dict], fieldnames: list[str]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    payload = io.BytesIO(buf.getvalue().encode("utf-8"))
    return StreamingResponse(
        payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.get("/post/{post_id}", response_model=ReportOut)
async def get_report(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Report).where(Report.post_id == post_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return report


@router.post("/post/{post_id}/update")
async def update_report(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    job = await enqueue_post_report_job(session, post_id=post_id, source="api")
    await session.commit()
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue build_post_report job")
    result = await wait_for_job_result(job_id=job.id)
    if result.get("status") == "timeout":
        raise HTTPException(status_code=504, detail="Timed out waiting for post report")
    if result.get("status") == "skipped_min_comments":
        return result
    report = (await session.execute(select(Report).where(Report.post_id == post_id))).scalar_one()
    return report


@router.get("/posts/list")
async def list_post_reports(
    channel_ids: str | None = Query(default=None, description="CSV list: 1,2,3", examples=["1,2,7"]),
    categories: str | None = Query(default=None, description="CSV list: politics,economy", examples=["regional,news"]),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    stmt = _build_post_reports_stmt(
        channel_ids=_parse_int_list(channel_ids),
        categories=_parse_str_list(categories),
        date_from=date_from,
        date_to=date_to,
    ).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "report_id": report.id,
            "post_id": post.id,
            "status": report.status,
            "created_at": report.created_at,
            "post_date": post.date,
            "channel_id": channel.id,
            "channel_username": channel.username,
            "channel_category": channel.category,
        }
        for report, post, channel in rows
    ]


@router.get("/posts/export")
async def export_post_reports(
    format: str = Query(default="json", pattern="^(json|csv)$", examples=["json", "csv"]),
    channel_ids: str | None = Query(default=None, description="CSV list: 1,2,3", examples=["4,6"]),
    categories: str | None = Query(default=None, description="CSV list: politics,economy", examples=["regional"]),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=20000),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    stmt = _build_post_reports_stmt(
        channel_ids=_parse_int_list(channel_ids),
        categories=_parse_str_list(categories),
        date_from=date_from,
        date_to=date_to,
    ).limit(limit)
    rows = (await session.execute(stmt)).all()

    items = [
        {
            "report_id": report.id,
            "post_id": post.id,
            "status": report.status,
            "content": report.content,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "post_date": post.date.isoformat() if post.date else None,
            "channel_id": channel.id,
            "channel_username": channel.username,
            "channel_category": channel.category,
        }
        for report, post, channel in rows
    ]
    if format == "json":
        return {"total": len(items), "items": items}

    return _csv_response(
        filename="post_reports.csv",
        rows=items,
        fieldnames=[
            "report_id",
            "post_id",
            "status",
            "content",
            "created_at",
            "post_date",
            "channel_id",
            "channel_username",
            "channel_category",
        ],
    )


@router.get("/events/list")
async def list_event_reports(
    event_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
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
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
    return [
        {
            "report_id": report.id,
            "event_id": event.id,
            "event_title": event.title,
            "version": report.version,
            "created_at": report.created_at,
        }
        for report, event in rows
    ]


@router.get("/events/export")
async def export_event_reports(
    format: str = Query(default="json", pattern="^(json|csv)$", examples=["json", "csv"]),
    event_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=20000),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
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
    rows = (await session.execute(stmt.limit(limit))).all()
    items = [
        {
            "report_id": report.id,
            "event_id": event.id,
            "event_title": event.title,
            "version": report.version,
            "report_text": report.report_text,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
        for report, event in rows
    ]
    if format == "json":
        return {"total": len(items), "items": items}
    return _csv_response(
        filename="event_reports.csv",
        rows=items,
        fieldnames=["report_id", "event_id", "event_title", "version", "report_text", "created_at"],
    )


@router.get("/processes/list")
async def list_process_reports(
    process_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
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
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
    return [
        {
            "report_id": report.id,
            "process_id": process.id,
            "process_title": process.title,
            "version": report.version,
            "created_at": report.created_at,
        }
        for report, process in rows
    ]


@router.get("/processes/export")
async def export_process_reports(
    format: str = Query(default="json", pattern="^(json|csv)$", examples=["json", "csv"]),
    process_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=20000),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
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
    rows = (await session.execute(stmt.limit(limit))).all()
    items = [
        {
            "report_id": report.id,
            "process_id": process.id,
            "process_title": process.title,
            "version": report.version,
            "report_text": report.report_text,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
        for report, process in rows
    ]
    if format == "json":
        return {"total": len(items), "items": items}
    return _csv_response(
        filename="process_reports.csv",
        rows=items,
        fieldnames=["report_id", "process_id", "process_title", "version", "report_text", "created_at"],
    )


@router.post("/posts/generate-by-filter")
async def generate_post_reports_by_filter(
    channel_ids: str | None = Query(default=None, description="CSV list: 1,2,3", examples=["1,3"]),
    categories: str | None = Query(default=None, description="CSV list: politics,economy", examples=["regional,incident"]),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    min_comments: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=2000),
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    parsed_channel_ids = _parse_int_list(channel_ids)
    parsed_categories = _parse_str_list(categories)
    stmt = (
        select(Post.id)
        .join(Channel, Channel.id == Post.channel_id)
        .order_by(Post.date.desc(), Post.id.desc())
    )
    conditions = []
    if parsed_channel_ids:
        conditions.append(Post.channel_id.in_(parsed_channel_ids))
    if parsed_categories:
        conditions.append(Channel.category.in_(parsed_categories))
    if date_from is not None:
        conditions.append(Post.date >= date_from)
    if date_to is not None:
        conditions.append(Post.date <= date_to)
    if min_comments is not None:
        conditions.append(Post.comments_count >= min_comments)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    post_ids = [row[0] for row in (await session.execute(stmt.limit(limit))).all()]
    if not post_ids:
        return {"status": "ok", "updated": 0, "post_ids": []}

    effective_settings = await get_all_settings(session)
    report_config = report_config_from_settings(effective_settings)
    updated = 0
    failed: list[dict] = []
    for post_id in post_ids:
        result = await build_post_report(
            session,
            post_id=post_id,
            report_project=report_project,
            report_config=report_config,
        )
        if result.get("status") in {"ready", "failed"}:
            updated += 1
        else:
            failed.append({"post_id": post_id, "status": result.get("status")})
    await session.commit()
    return {"status": "ok", "updated": updated, "failed": failed, "post_ids": post_ids}


@router.post("/events/{event_id}/update")
async def update_event_report(
    event_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    job = await enqueue_event_report_job(session, event_id=event_id, source="api")
    await session.commit()
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue build_event_report job")
    result = await wait_for_job_result(job_id=job.id)
    if result.get("status") == "timeout":
        raise HTTPException(status_code=504, detail="Timed out waiting for event report")
    return result


@router.post("/processes/{process_id}/update")
async def update_process_report(
    process_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    process = await session.get(Process, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")
    job = await enqueue_process_report_job(session, process_id=process_id, source="api")
    await session.commit()
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue build_process_report job")
    result = await wait_for_job_result(job_id=job.id)
    if result.get("status") == "timeout":
        raise HTTPException(status_code=504, detail="Timed out waiting for process report")
    return result
