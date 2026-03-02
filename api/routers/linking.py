from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Event, EventPost, Post, PostLink, Process, ProcessEvent
from deps import get_session
from schemas.linking import (
    EventDetailOut,
    EventSummaryOut,
    LinkRunResponse,
    PostLinksResponse,
    ProcessDetailOut,
    ProcessEventOut,
    ProcessSummaryOut,
)
from services.events.build_events import rebuild_events
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes

router = APIRouter()


@router.post("/linking/run", response_model=LinkRunResponse)
async def run_linking(
    post_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    pipeline = NoLlmLinkingPipeline.build_default()
    result = await pipeline.run_for_post(session, post)
    await session.commit()
    return result


@router.post("/events/rebuild")
async def rebuild_events_api(
    date_from: datetime,
    date_to: datetime,
    session: AsyncSession = Depends(get_session),
):
    rebuilt = await rebuild_events(session, date_from=date_from, date_to=date_to)
    await session.commit()
    return {"rebuilt_events": rebuilt, "date_from": date_from, "date_to": date_to}


@router.post("/processes/rebuild")
async def rebuild_processes_api(
    date_from: datetime,
    date_to: datetime,
    session: AsyncSession = Depends(get_session),
):
    rebuilt_edges = await rebuild_processes(session, date_from=date_from, date_to=date_to)
    await session.commit()
    return {"rebuilt_process_edges": rebuilt_edges, "date_from": date_from, "date_to": date_to}


@router.get("/posts/{post_id}/links", response_model=PostLinksResponse)
async def get_post_links(post_id: int, session: AsyncSession = Depends(get_session)):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    stmt = (
        select(PostLink)
        .where(or_(PostLink.src_post_id == post_id, PostLink.dst_post_id == post_id))
        .order_by(PostLink.updated_at.desc(), PostLink.id.desc())
    )
    links = (await session.execute(stmt)).scalars().all()
    return PostLinksResponse(post_id=post_id, links=links)


@router.get("/events/{event_id}", response_model=EventDetailOut)
async def get_event(event_id: int, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    post_ids_stmt = select(EventPost.post_id).where(EventPost.event_id == event_id)
    post_ids = [row[0] for row in (await session.execute(post_ids_stmt)).all()]
    return EventDetailOut(event=EventSummaryOut.model_validate(event), post_ids=post_ids)


@router.get("/processes/{process_id}", response_model=ProcessDetailOut)
async def get_process(process_id: int, session: AsyncSession = Depends(get_session)):
    process = await session.get(Process, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")
    events_stmt = (
        select(ProcessEvent)
        .where(ProcessEvent.process_id == process_id)
        .order_by(ProcessEvent.created_at.desc())
    )
    events = (await session.execute(events_stmt)).scalars().all()
    return ProcessDetailOut(
        process=ProcessSummaryOut.model_validate(process),
        events=[
            ProcessEventOut(
                event_id=item.event_id,
                relation_type=item.relation_type.value if hasattr(item.relation_type, "value") else str(item.relation_type),
                direction=item.direction.value if hasattr(item.direction, "value") else str(item.direction),
                score=item.score,
                status=item.status.value if hasattr(item.status, "value") else str(item.status),
            )
            for item in events
        ],
    )
