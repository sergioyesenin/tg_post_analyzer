from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Event, EventPost, Post, PostLink
from deps import get_session, require_roles
from schemas.linking import EventDetailOut, EventSummaryOut, LinkRunResponse, PostLinksResponse
from services.auth import AuthUser
from services.linking_metrics import load_event_metrics
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline

router = APIRouter()


@router.post("/posts/{post_id}/run", response_model=LinkRunResponse)
async def run_linker(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    result = await NoLlmLinkingPipeline.build_default().run_for_post(session, post)
    await session.commit()
    return result


@router.get("/posts/{post_id}", response_model=PostLinksResponse)
async def get_post_links(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    links_stmt = (
        select(PostLink)
        .where(or_(PostLink.src_post_id == post_id, PostLink.dst_post_id == post_id))
        .order_by(PostLink.updated_at.desc(), PostLink.id.desc())
    )
    links = (await session.execute(links_stmt)).scalars().all()
    return PostLinksResponse(post_id=post_id, links=links)


@router.get("/events", response_model=list[EventSummaryOut])
async def list_events(
    limit: int = 50,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Event)
        .order_by(Event.started_at.desc().nullslast(), Event.id.desc())
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()
    metrics_by_event_id = await load_event_metrics(session, [event.id for event in events])
    return [
        EventSummaryOut.model_validate(event).model_copy(
            update=metrics_by_event_id.get(event.id, {"comments_count": 0, "involvement": None})
        )
        for event in events
    ]


@router.get("/events/{event_id}", response_model=EventDetailOut)
async def get_event(
    event_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    post_ids_stmt = select(EventPost.post_id).where(EventPost.event_id == event_id)
    post_ids = [row[0] for row in (await session.execute(post_ids_stmt)).all()]
    metrics_by_event_id = await load_event_metrics(session, [event_id])
    return EventDetailOut(
        event=EventSummaryOut.model_validate(event).model_copy(
            update=metrics_by_event_id.get(event_id, {"comments_count": 0, "involvement": None})
        ),
        post_ids=post_ids,
    )
