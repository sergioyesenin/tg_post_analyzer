from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_session, require_roles
from schemas.linking import EventDetailOut, EventSummaryOut, LinkRunResponse, PostLinksResponse
from services.auth import AuthUser
from api.routers import linking

router = APIRouter()


def _mark_deprecated(response: Response, successor: str) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'


@router.post("/posts/{post_id}/run", response_model=LinkRunResponse, deprecated=True)
async def run_linker_legacy(
    post_id: int,
    response: Response,
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    _mark_deprecated(response, f"/api/linking/run?post_id={post_id}")
    return await linking.run_linking(post_id=post_id, current_user=_, session=session)


@router.get("/posts/{post_id}", response_model=PostLinksResponse, deprecated=True)
async def get_post_links_legacy(
    post_id: int,
    response: Response,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    _mark_deprecated(response, f"/api/posts/{post_id}/links")
    return await linking.get_post_links(post_id=post_id, _=_, session=session)


@router.get("/events", response_model=list[EventSummaryOut], deprecated=True)
async def list_events_legacy(
    response: Response,
    limit: int = 50,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    _mark_deprecated(response, "/api/events")
    return await linking.list_events(limit=limit, _=_, session=session)


@router.get("/events/{event_id}", response_model=EventDetailOut, deprecated=True)
async def get_event_legacy(
    event_id: int,
    response: Response,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    _mark_deprecated(response, f"/api/events/{event_id}")
    return await linking.get_event(event_id=event_id, _=_, session=session)
