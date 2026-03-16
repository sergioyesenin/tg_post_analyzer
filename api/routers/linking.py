from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Event, EventPost, Post, PostLink, Process, ProcessEvent
from deps import get_session, require_roles
from schemas.linking import (
    EventDetailOut,
    EventSummaryOut,
    LinkRunResponse,
    PostLinksResponse,
    ProcessDetailOut,
    ProcessEventOut,
    ProcessSummaryOut,
)
from services.auth import AuthUser, write_audit_log
from services.events.build_events import rebuild_events
from services.linking_metrics import load_event_metrics, load_process_metrics
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes

router = APIRouter()


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


@router.post("/linking/run", response_model=LinkRunResponse)
async def run_linking(
    post_id: int = Query(...),
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    pipeline = NoLlmLinkingPipeline.build_default()
    result = await pipeline.run_for_post(session, post)
    await write_audit_log(
        session,
        action="linking.run",
        actor_user_id=current_user.id,
        target_type="post",
        target_id=str(post.id),
    )
    await session.commit()
    return result


@router.post("/events/rebuild")
async def rebuild_events_api(
    date_from: datetime,
    date_to: datetime,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    rebuilt = await rebuild_events(session, date_from=date_from, date_to=date_to)
    await write_audit_log(
        session,
        action="events.rebuild",
        actor_user_id=current_user.id,
        target_type="events",
        details={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "rebuilt": rebuilt},
    )
    await session.commit()
    return {"rebuilt_events": rebuilt, "date_from": date_from, "date_to": date_to}


@router.post("/processes/rebuild")
async def rebuild_processes_api(
    date_from: datetime,
    date_to: datetime,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    rebuilt_edges = await rebuild_processes(session, date_from=date_from, date_to=date_to)
    await write_audit_log(
        session,
        action="processes.rebuild",
        actor_user_id=current_user.id,
        target_type="processes",
        details={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "rebuilt_edges": rebuilt_edges},
    )
    await session.commit()
    return {"rebuilt_process_edges": rebuilt_edges, "date_from": date_from, "date_to": date_to}


@router.get("/posts/{post_id}/links", response_model=PostLinksResponse)
async def get_post_links(
    post_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
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
async def get_event(
    event_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    post_ids_stmt = select(EventPost.post_id).where(EventPost.event_id == event_id)
    post_ids = [int(row[0]) for row in (await session.execute(post_ids_stmt)).all()]
    root_post_id = (
        await session.scalar(
            select(EventPost.post_id)
            .where(EventPost.event_id == event_id)
            .where(EventPost.role == "root")
            .limit(1)
        )
    )
    metrics_by_event_id = await load_event_metrics(session, [event_id])
    channel_rows = (
        await session.execute(
            select(Channel.username)
            .select_from(EventPost)
            .join(Post, Post.id == EventPost.post_id)
            .join(Channel, Channel.id == Post.channel_id)
            .where(EventPost.event_id == event_id)
            .distinct()
        )
    ).all()
    return EventDetailOut(
        event=EventSummaryOut.model_validate(event).model_copy(
            update=metrics_by_event_id.get(event_id, {"comments_count": 0, "involvement": None})
        ),
        post_ids=post_ids,
        root_post_id=int(root_post_id) if root_post_id is not None else (int(post_ids[0]) if post_ids else None),
        channels=[str(username) for username, in channel_rows if username],
    )


@router.get("/processes/{process_id}", response_model=ProcessDetailOut)
async def get_process(
    process_id: int,
    _: AuthUser = Depends(require_roles("admin", "analyst", "viewer")),
    session: AsyncSession = Depends(get_session),
):
    process = await session.get(Process, process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")
    events_stmt = (
        select(
            ProcessEvent,
            Event.title,
            Event.started_at,
            Event.ended_at,
            Event.confidence,
        )
        .join(Event, Event.id == ProcessEvent.event_id)
        .where(ProcessEvent.process_id == process_id)
        .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
    )
    event_rows = (await session.execute(events_stmt)).all()
    event_ids = [int(item[0].event_id) for item in event_rows]
    post_rows = []
    if event_ids:
        post_rows = (
            await session.execute(
                select(EventPost.event_id, EventPost.post_id)
                .where(EventPost.event_id.in_(event_ids))
                .order_by(EventPost.event_id.asc(), EventPost.created_at.asc(), EventPost.post_id.asc())
            )
        ).all()
    post_ids_by_event_id: dict[int, list[int]] = defaultdict(list)
    for event_id, post_id in post_rows:
        bucket = post_ids_by_event_id[int(event_id)]
        parsed_post_id = int(post_id)
        if parsed_post_id not in bucket:
            bucket.append(parsed_post_id)
    metrics_by_process_id = await load_process_metrics(session, [process_id])
    return ProcessDetailOut(
        process=ProcessSummaryOut.model_validate(process).model_copy(
            update=metrics_by_process_id.get(process_id, {"comments_count": 0, "involvement": None})
        ),
        events=[
            ProcessEventOut(
                event_id=item.event_id,
                title=title,
                started_at=started_at,
                ended_at=ended_at,
                confidence=float(confidence) if confidence is not None else None,
                relation_type=item.relation_type.value if hasattr(item.relation_type, "value") else str(item.relation_type),
                direction=item.direction.value if hasattr(item.direction, "value") else str(item.direction),
                score=item.score,
                status=item.status.value if hasattr(item.status, "value") else str(item.status),
                post_ids=post_ids_by_event_id.get(int(item.event_id), []),
            )
            for item, title, started_at, ended_at, confidence in event_rows
        ],
    )
