from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Event,
    EventPost,
    LinkDirection,
    PostLink,
    PostLinkType,
    Process,
    ProcessEvent,
    ProcessRelationType,
    VerificationStatus,
)

POST_LINK_TO_PROCESS_RELATION = {
    PostLinkType.CAUSE: ProcessRelationType.CAUSE,
    PostLinkType.CONSEQUENCE: ProcessRelationType.EFFECT,
    PostLinkType.UPDATE: ProcessRelationType.UPDATE,
    PostLinkType.CONTRADICTION: ProcessRelationType.CONTRADICTION,
    PostLinkType.RELATED: ProcessRelationType.RELATED,
}


async def rebuild_processes(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    created_by: str = "pipeline",
) -> int:
    events_stmt = select(Event).where(and_(Event.started_at >= date_from, Event.started_at <= date_to))
    events = (await session.execute(events_stmt)).scalars().all()
    if not events:
        return 0

    event_ids = {event.id for event in events}
    post_to_event_stmt = select(EventPost.post_id, EventPost.event_id).where(EventPost.event_id.in_(event_ids))
    post_to_event = {post_id: event_id for post_id, event_id in (await session.execute(post_to_event_stmt)).all()}

    process_ids_stmt = select(Process.id).where(and_(Process.started_at >= date_from, Process.started_at <= date_to))
    process_ids = [row[0] for row in (await session.execute(process_ids_stmt)).all()]
    if process_ids:
        await session.execute(delete(ProcessEvent).where(ProcessEvent.process_id.in_(process_ids)))
        await session.execute(delete(Process).where(Process.id.in_(process_ids)))

    links_stmt = (
        select(PostLink)
        .where(
            and_(
                PostLink.status == VerificationStatus.VERIFIED,
                PostLink.link_type.in_(list(POST_LINK_TO_PROCESS_RELATION.keys())),
            )
        )
        .order_by(PostLink.id.asc())
    )
    links = (await session.execute(links_stmt)).scalars().all()

    # Keep only best edge candidate per destination event for this process.
    event_edge_payload: dict[int, dict] = {}
    for link in links:
        src_event_id = post_to_event.get(link.src_post_id)
        dst_event_id = post_to_event.get(link.dst_post_id)
        if not src_event_id or not dst_event_id or src_event_id == dst_event_id:
            continue
        relation = POST_LINK_TO_PROCESS_RELATION.get(link.link_type)
        if relation is None:
            continue

        direction = link.direction if isinstance(link.direction, LinkDirection) else LinkDirection.NONE
        prev = event_edge_payload.get(dst_event_id)
        prev_score = float(prev.get("score")) if prev and prev.get("score") is not None else -1.0
        current_score = float(link.score) if link.score is not None else 0.0
        if prev is None or current_score > prev_score:
            event_edge_payload[dst_event_id] = {
                "relation_type": relation,
                "direction": direction,
                "evidence_json": link.evidence_json,
                "score": link.score,
                "model_version": link.model_version,
                "pipeline_version": link.pipeline_version,
            }

    if not event_edge_payload:
        # No validated cross-event relations => no process should be created.
        return 0

    started_candidates = [event.started_at for event in events if event.started_at is not None]
    ended_candidates = [event.ended_at for event in events if event.ended_at is not None]
    process_events_scope = [event for event in events if event.id in event_edge_payload]
    if process_events_scope:
        first_event = sorted(
            process_events_scope,
            key=lambda e: ((e.started_at or e.created_at), e.id),
        )[0]
        first_paragraph = (first_event.title or "").split("\n", 1)[0].strip()
        title = first_paragraph[:140] or f"Процесс {date_from.date().isoformat()}..{date_to.date().isoformat()}"
    else:
        title = f"Процесс {date_from.date().isoformat()}..{date_to.date().isoformat()}"

    process = Process(
        title=title,
        started_at=min(started_candidates) if started_candidates else None,
        ended_at=max(ended_candidates) if ended_candidates else None,
        confidence=0.75,
        status=VerificationStatus.VERIFIED,
        created_by=created_by,
    )
    session.add(process)
    await session.flush()

    created_edges = 0
    for event_id, payload in event_edge_payload.items():
        stmt = (
            insert(ProcessEvent)
            .values(
                process_id=process.id,
                event_id=event_id,
                relation_type=payload["relation_type"],
                direction=payload["direction"],
                evidence_json=payload["evidence_json"],
                score=payload["score"],
                status=VerificationStatus.VERIFIED,
                model_version=payload["model_version"],
                pipeline_version=payload["pipeline_version"],
            )
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)
        created_edges += 1

    return created_edges
