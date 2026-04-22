from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from api.public_report_boundary import to_public_report_out
from schemas.query_params import CsvIntList, CsvStrList
from schemas.report import ReportOut, ReportTraceOut
from services.auth import AuthUser
from services.jobs import build_report_request_dedupe_key, find_blocking_report_duplicate
from services.orchestration import (
    enqueue_event_report_job,
    enqueue_post_report_job,
    enqueue_post_report_batch_job,
    enqueue_process_report_job,
)
from services.reporting import canonicalize_multi_agent_trace, report_status_from_payload

router = APIRouter()


def _event_process_report_status(report) -> str:
    return report_status_from_payload(getattr(report, "report_json", None))


def _job_accepted_response(*, job_id: int, job_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=jsonable_encoder(
            {
                "status": "queued",
                "job_id": job_id,
                "job_type": job_type,
                "status_url": f"/api/jobs/{job_id}",
                "result_url": f"/api/jobs/{job_id}/result",
            }
        ),
    )


def _extract_multi_agent_trace(report_json: dict | None) -> dict | None:
    if not isinstance(report_json, dict):
        return None
    canonical = canonicalize_multi_agent_trace(report_json)
    if canonical:
        return canonical
    meta = report_json.get("meta")
    if not isinstance(meta, dict):
        return None
    trace = meta.get("multi_agent")
    if not isinstance(trace, dict):
        return None
    return trace


def _duplicate_blocked_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            {
                "status": "blocked",
                "reason": "duplicate_request",
                "message": "Отчет уже формируется или был недавно построен",
            }
        ),
    )


def _batch_job_accepted_response(*, job_id: int, job_type: str, filters: dict) -> JSONResponse:
    payload = {
        "status": "queued",
        "job_id": job_id,
        "job_type": job_type,
        "status_url": f"/api/jobs/{job_id}",
        "result_url": f"/api/jobs/{job_id}/result",
        "batch": {
            "limit": filters.get("limit"),
            "channel_ids": filters.get("channel_ids", []),
            "categories": filters.get("categories", []),
            "date_from": filters.get("date_from"),
            "date_to": filters.get("date_to"),
            "min_comments": filters.get("min_comments"),
        },
    }
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=jsonable_encoder(payload))

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

    return to_public_report_out(report)


@router.get("/post/{post_id}/trace", response_model=ReportTraceOut)
async def get_post_report_trace(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Report).where(Report.post_id == post_id).order_by(Report.created_at.desc(), Report.id.desc())
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    trace = _extract_multi_agent_trace(report.report_json)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return ReportTraceOut(
        entity_type="post",
        entity_id=post_id,
        report_id=report.id,
        version=None,
        status=report.status,
        trace=trace,
        created_at=report.created_at,
    )


@router.get("/events/{event_id}/trace", response_model=ReportTraceOut)
async def get_event_report_trace(
    event_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(EventReport)
        .where(EventReport.event_id == event_id)
        .order_by(EventReport.version.desc(), EventReport.id.desc())
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Event report not found")

    trace = _extract_multi_agent_trace(report.report_json)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return ReportTraceOut(
        entity_type="event",
        entity_id=event_id,
        report_id=report.id,
        version=report.version,
        status=_event_process_report_status(report),
        trace=trace,
        created_at=report.created_at,
    )


@router.post("/post/{post_id}/update")
async def update_report(
    post_id: int,
    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    duplicate = await find_blocking_report_duplicate(session, entity_type="post", entity_id=post_id)
    if duplicate is not None:
        return _duplicate_blocked_response()

    job = await enqueue_post_report_job(
        session,
        post_id=post_id,
        source="api",
        requested_by_user_id=current_user.id,
        dedupe_key=build_report_request_dedupe_key(entity_type="post", entity_id=post_id),
    )
    await session.commit()
    if job is None:
        return _duplicate_blocked_response()
    return _job_accepted_response(job_id=job.id, job_type=job.type)


@router.get("/posts/list")
async def list_post_reports(
    channel_ids: Annotated[CsvIntList, Query(description="CSV list: 1,2,3", examples=["1,2,7"])] = [],
    categories: Annotated[CsvStrList, Query(description="CSV list: politics,economy", examples=["regional,news"])] = [],
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    stmt = _build_post_reports_stmt(
        channel_ids=channel_ids,
        categories=categories,
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
    channel_ids: Annotated[CsvIntList, Query(description="CSV list: 1,2,3", examples=["4,6"])] = [],
    categories: Annotated[CsvStrList, Query(description="CSV list: politics,economy", examples=["regional"])] = [],
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=20000),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    stmt = _build_post_reports_stmt(
        channel_ids=channel_ids,
        categories=categories,
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
            "status": _event_process_report_status(report),
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
            "status": _event_process_report_status(report),
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
        fieldnames=["report_id", "event_id", "event_title", "status", "version", "report_text", "created_at"],
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
            "status": _event_process_report_status(report),
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
            "status": _event_process_report_status(report),
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
        fieldnames=["report_id", "process_id", "process_title", "status", "version", "report_text", "created_at"],
    )


@router.post("/posts/generate-by-filter")
async def generate_post_reports_by_filter(
    channel_ids: Annotated[CsvIntList, Query(description="CSV list: 1,2,3", examples=["1,3"])] = [],
    categories: Annotated[CsvStrList, Query(description="CSV list: politics,economy", examples=["regional,incident"])] = [],
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    min_comments: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    filters = {
        "channel_ids": channel_ids,
        "categories": categories,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "min_comments": min_comments,
        "limit": limit,
    }
    job = await enqueue_post_report_batch_job(
        session,
        filters=filters,
        source="api",
    )
    await session.commit()
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue build_post_report_batch job")
    return _batch_job_accepted_response(job_id=job.id, job_type=job.type, filters=filters)


@router.post("/events/{event_id}/update")
async def update_event_report(
    event_id: int,
    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    duplicate = await find_blocking_report_duplicate(session, entity_type="event", entity_id=event_id)
    if duplicate is not None:
        return _duplicate_blocked_response()

    job = await enqueue_event_report_job(
        session,
        event_id=event_id,
        source="api",
        requested_by_user_id=current_user.id,
        dedupe_key=build_report_request_dedupe_key(entity_type="event", entity_id=event_id),
    )
    await session.commit()
    if job is None:
        return _duplicate_blocked_response()
    return _job_accepted_response(job_id=job.id, job_type=job.type)


@router.post("/processes/{process_id}/update")
async def update_process_report(
    process_id: int,
    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    process = await session.get(Process, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")

    duplicate = await find_blocking_report_duplicate(session, entity_type="process", entity_id=process_id)
    if duplicate is not None:
        return _duplicate_blocked_response()

    job = await enqueue_process_report_job(
        session,
        process_id=process_id,
        source="api",
        requested_by_user_id=current_user.id,
        dedupe_key=build_report_request_dedupe_key(entity_type="process", entity_id=process_id),
    )
    await session.commit()
    if job is None:
        return _duplicate_blocked_response()
    return _job_accepted_response(job_id=job.id, job_type=job.type)
