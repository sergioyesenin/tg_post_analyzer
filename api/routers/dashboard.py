from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_session, require_roles
from schemas.query_params import CsvIntList, CsvStrList
from schemas.dashboard import (
    EventGraphResponse,
    EventsDashboardResponse,
    PostsDashboardResponse,
    ProcessGraphResponse,
    ProcessesDashboardResponse,
)
from services.auth import AuthUser
from services.dashboard import (
    build_event_graph,
    build_events_dashboard,
    build_posts_dashboard,
    build_process_graph,
    build_processes_dashboard,
)
from services.settings_store import get_setting

router = APIRouter()

POST_SORTS = ("comments_count", "date", "views", "involvement")
EVENT_SORTS = ("started_at", "comments_count", "involvement", "posts_count")
PROCESS_SORTS = ("started_at", "comments_count", "involvement", "events_count")
SORT_ORDERS = ("asc", "desc")


async def _resolve_limit(session: AsyncSession, limit: int | None) -> int:
    if limit is not None:
        return limit
    api_settings = await get_setting(session, "api")
    return int(api_settings.get("top_posts_default_limit", 20))


@router.get("/posts", response_model=PostsDashboardResponse)
async def get_posts_dashboard(
    date_from: datetime,
    date_to: datetime,
    limit: int | None = Query(default=None, ge=1, le=500),
    channel_ids: Annotated[CsvIntList, Query()] = [],
    categories: Annotated[CsvStrList, Query()] = [],
    min_comments: int | None = Query(default=None, ge=0),
    report_status: Annotated[CsvStrList, Query()] = [],
    sort_by: str = Query(default="comments_count", pattern="^(comments_count|date|views|involvement)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    return await build_posts_dashboard(
        session,
        date_from=date_from,
        date_to=date_to,
        limit=await _resolve_limit(session, limit),
        channel_ids=channel_ids,
        categories=categories,
        min_comments=min_comments,
        report_status=report_status,
        sort_by=sort_by,
        sort_order=sort_order,
        comments_refresh_available=bool({"admin", "analyst"}.intersection(set(current_user.roles))),
    )


@router.get("/events", response_model=EventsDashboardResponse)
async def get_events_dashboard(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    status: Annotated[CsvStrList, Query()] = [],
    channel_ids: Annotated[CsvIntList, Query()] = [],
    categories: Annotated[CsvStrList, Query()] = [],
    min_comments: int | None = Query(default=None, ge=0),
    sort_by: str = Query(default="started_at", pattern="^(started_at|comments_count|involvement|posts_count)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    return await build_events_dashboard(
        session,
        date_from=date_from,
        date_to=date_to,
        limit=await _resolve_limit(session, limit),
        status=status,
        channel_ids=channel_ids,
        categories=categories,
        min_comments=min_comments,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/events/{event_id}/graph", response_model=EventGraphResponse)
async def get_event_graph(
    event_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    payload = await build_event_graph(session, event_id=event_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return payload


@router.get("/processes", response_model=ProcessesDashboardResponse)
async def get_processes_dashboard(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    status: Annotated[CsvStrList, Query()] = [],
    min_comments: int | None = Query(default=None, ge=0),
    sort_by: str = Query(default="started_at", pattern="^(started_at|comments_count|involvement|events_count)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    return await build_processes_dashboard(
        session,
        date_from=date_from,
        date_to=date_to,
        limit=await _resolve_limit(session, limit),
        status=status,
        min_comments=min_comments,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/processes/{process_id}/graph", response_model=ProcessGraphResponse)
async def get_process_graph(
    process_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    payload = await build_process_graph(session, process_id=process_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Process not found")
    return payload
