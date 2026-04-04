from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
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


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: int, b: int) -> None:
        pa = self.find(a)
        pb = self.find(b)
        if pa != pb:
            self.parent[pb] = pa

    def components(self) -> list[list[int]]:
        out: dict[int, list[int]] = {}
        for node in self.parent:
            root = self.find(node)
            out.setdefault(root, []).append(node)
        return list(out.values())


def _build_update_components(
    *,
    event_ids: set[int],
    post_to_event_ids: dict[int, set[int]],
    links: list[PostLink],
) -> tuple[list[list[int]], dict[int, dict]]:
    uf = _UnionFind()
    event_membership_payload: dict[int, dict] = {}

    for link in links:
        src_event_ids = post_to_event_ids.get(link.src_post_id, set())
        dst_event_ids = post_to_event_ids.get(link.dst_post_id, set())
        if not src_event_ids or not dst_event_ids:
            continue

        candidate_pairs = {
            (src_event_id, dst_event_id)
            for src_event_id in src_event_ids
            for dst_event_id in dst_event_ids
            if src_event_id in event_ids and dst_event_id in event_ids and src_event_id != dst_event_id
        }
        if not candidate_pairs:
            continue

        for src_event_id, dst_event_id in candidate_pairs:
            uf.find(src_event_id)
            uf.find(dst_event_id)
            uf.union(src_event_id, dst_event_id)

            current_score = float(link.score) if link.score is not None else 0.0
            for event_id in (src_event_id, dst_event_id):
                prev = event_membership_payload.get(event_id)
                prev_score = float(prev.get("score")) if prev and prev.get("score") is not None else -1.0
                if prev is None or current_score > prev_score:
                    event_membership_payload[event_id] = {
                        "direction": LinkDirection.NONE,
                        "evidence_json": link.evidence_json,
                        "score": link.score,
                        "model_version": link.model_version,
                        "pipeline_version": link.pipeline_version,
                    }

    components = [component for component in uf.components() if len(component) >= 2]
    return components, event_membership_payload


def _choose_process_title(events: list[Event], *, date_from: datetime, date_to: datetime) -> str:
    if not events:
        return f"Process {date_from.date().isoformat()}..{date_to.date().isoformat()}"
    first_event = sorted(events, key=lambda e: ((e.started_at or e.created_at), e.id))[0]
    first_paragraph = (first_event.title or "").split("\n", 1)[0].strip()
    return first_paragraph[:140] or f"Process {date_from.date().isoformat()}..{date_to.date().isoformat()}"


def _process_component_payload(*, component: list[int], event_by_id: dict[int, Event], date_from: datetime, date_to: datetime) -> dict | None:
    component_events = [event_by_id[event_id] for event_id in component if event_id in event_by_id]
    if len(component_events) < 2:
        return None
    started_candidates = [event.started_at for event in component_events if event.started_at is not None]
    ended_candidates = [event.ended_at for event in component_events if event.ended_at is not None]
    return {
        "event_ids": {int(event.id) for event in component_events},
        "component_events": component_events,
        "started_at": min(started_candidates) if started_candidates else None,
        "ended_at": max(ended_candidates) if ended_candidates else None,
        "title": _choose_process_title(component_events, date_from=date_from, date_to=date_to),
    }


def _match_component_to_process(
    *,
    component_event_ids: set[int],
    existing_event_ids_by_process_id: dict[int, set[int]],
    assigned_process_ids: set[int],
) -> int | None:
    best_process_id: int | None = None
    best_score: tuple[int, int] | None = None
    for process_id, existing_event_ids in existing_event_ids_by_process_id.items():
        if process_id in assigned_process_ids:
            continue
        overlap = len(component_event_ids & existing_event_ids)
        if overlap <= 0:
            continue
        score = (overlap, -process_id)
        if best_score is None or score > best_score:
            best_score = score
            best_process_id = process_id
    return best_process_id


async def rebuild_processes(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    created_by: str = "pipeline",
) -> int:
    seed_events_stmt = select(Event).where(and_(Event.started_at >= date_from, Event.started_at <= date_to))
    seed_events = (await session.execute(seed_events_stmt)).scalars().all()
    if not seed_events:
        return 0

    event_ids = {event.id for event in seed_events}
    process_ids: set[int] = set()
    changed = True
    while changed:
        changed = False

        linked_process_ids_stmt = (
            select(ProcessEvent.process_id)
            .distinct()
            .where(ProcessEvent.event_id.in_(event_ids))
        )
        discovered_process_ids = {row[0] for row in (await session.execute(linked_process_ids_stmt)).all()}
        if not discovered_process_ids.issubset(process_ids):
            process_ids.update(discovered_process_ids)
            changed = True

        if process_ids:
            linked_event_ids_stmt = select(ProcessEvent.event_id).where(ProcessEvent.process_id.in_(process_ids))
            discovered_event_ids = {row[0] for row in (await session.execute(linked_event_ids_stmt)).all()}
            if not discovered_event_ids.issubset(event_ids):
                event_ids.update(discovered_event_ids)
                changed = True

        event_post_rows = (
            await session.execute(
                select(EventPost.post_id, EventPost.event_id).where(EventPost.event_id.in_(event_ids))
            )
        ).all()
        post_ids = {row[0] for row in event_post_rows}
        post_to_event_ids: dict[int, set[int]] = defaultdict(set)
        for post_id, event_id in event_post_rows:
            post_to_event_ids[post_id].add(event_id)

        if post_ids:
            links_stmt = (
                select(PostLink)
                .where(
                    and_(
                        PostLink.status == VerificationStatus.VERIFIED,
                        PostLink.link_type == PostLinkType.UPDATE,
                        or_(PostLink.src_post_id.in_(post_ids), PostLink.dst_post_id.in_(post_ids)),
                    )
                )
                .order_by(PostLink.id.asc())
            )
            links = (await session.execute(links_stmt)).scalars().all()
            linked_post_ids = {
                linked_post_id
                for link in links
                for linked_post_id in (link.src_post_id, link.dst_post_id)
            }
            if linked_post_ids:
                linked_event_rows = (
                    await session.execute(
                        select(EventPost.post_id, EventPost.event_id).where(EventPost.post_id.in_(linked_post_ids))
                    )
                ).all()
                linked_event_ids = {row[1] for row in linked_event_rows}
                if not linked_event_ids.issubset(event_ids):
                    event_ids.update(linked_event_ids)
                    changed = True

    process_ids_stmt = (
        select(Process.id)
        .where(and_(Process.started_at >= date_from, Process.started_at <= date_to))
    )
    process_ids.update(row[0] for row in (await session.execute(process_ids_stmt)).all())

    events_stmt = select(Event).where(Event.id.in_(event_ids))
    events = (await session.execute(events_stmt)).scalars().all()
    event_by_id = {event.id: event for event in events}

    post_to_event_rows = (
        await session.execute(
            select(EventPost.post_id, EventPost.event_id).where(EventPost.event_id.in_(event_ids))
        )
    ).all()
    post_to_event_ids: dict[int, set[int]] = defaultdict(set)
    for post_id, event_id in post_to_event_rows:
        post_to_event_ids[post_id].add(event_id)

    links_stmt = (
        select(PostLink)
        .where(
            and_(
                PostLink.status == VerificationStatus.VERIFIED,
                PostLink.link_type == PostLinkType.UPDATE,
            )
        )
        .order_by(PostLink.id.asc())
    )
    links = (await session.execute(links_stmt)).scalars().all()

    components, event_membership_payload = _build_update_components(
        event_ids=event_ids,
        post_to_event_ids=dict(post_to_event_ids),
        links=links,
    )
    if not components:
        return 0

    component_payloads = [
        payload
        for payload in (
            _process_component_payload(component=component, event_by_id=event_by_id, date_from=date_from, date_to=date_to)
            for component in components
        )
        if payload is not None
    ]
    if not component_payloads:
        return 0

    existing_processes = []
    existing_memberships = []
    if process_ids:
        existing_processes = (await session.execute(select(Process).where(Process.id.in_(process_ids)))).scalars().all()
        existing_memberships = (
            await session.execute(select(ProcessEvent).where(ProcessEvent.process_id.in_(process_ids)))
        ).scalars().all()

    existing_process_by_id = {int(process.id): process for process in existing_processes}
    existing_memberships_by_process_id: dict[int, dict[int, ProcessEvent]] = {}
    existing_event_ids_by_process_id: dict[int, set[int]] = {}
    for membership in existing_memberships:
        process_id = int(membership.process_id)
        event_id = int(membership.event_id)
        existing_memberships_by_process_id.setdefault(process_id, {})[event_id] = membership
        existing_event_ids_by_process_id.setdefault(process_id, set()).add(event_id)

    assigned_process_ids: set[int] = set()
    active_process_ids: set[int] = set()
    created_memberships = 0

    for payload in sorted(component_payloads, key=lambda item: ((item["started_at"] or datetime.min), min(item["event_ids"]))):
        matched_process_id = _match_component_to_process(
            component_event_ids=payload["event_ids"],
            existing_event_ids_by_process_id=existing_event_ids_by_process_id,
            assigned_process_ids=assigned_process_ids,
        )
        if matched_process_id is not None:
            process = existing_process_by_id[matched_process_id]
            assigned_process_ids.add(matched_process_id)
        else:
            process = Process(
                title=payload["title"],
                started_at=payload["started_at"],
                ended_at=payload["ended_at"],
                confidence=0.75,
                status=VerificationStatus.VERIFIED,
                created_by=created_by,
            )
            session.add(process)
            await session.flush()
            matched_process_id = int(process.id)
            existing_process_by_id[matched_process_id] = process
            existing_memberships_by_process_id[matched_process_id] = {}
            existing_event_ids_by_process_id[matched_process_id] = set()
            assigned_process_ids.add(matched_process_id)

        process.title = payload["title"]
        process.started_at = payload["started_at"]
        process.ended_at = payload["ended_at"]
        process.confidence = 0.75
        process.status = VerificationStatus.VERIFIED
        active_process_ids.add(matched_process_id)

        existing_memberships_for_process = existing_memberships_by_process_id.get(matched_process_id, {})
        stale_event_ids = set(existing_memberships_for_process) - payload["event_ids"]
        if stale_event_ids:
            await session.execute(
                delete(ProcessEvent)
                .where(ProcessEvent.process_id == matched_process_id)
                .where(ProcessEvent.event_id.in_(stale_event_ids))
            )
            for stale_event_id in stale_event_ids:
                existing_memberships_for_process.pop(stale_event_id, None)
            existing_event_ids_by_process_id[matched_process_id] = set(existing_memberships_for_process)

        for event in sorted(payload["component_events"], key=lambda item: ((item.started_at or item.created_at), item.id)):
            membership_values = {
                "relation_type": ProcessRelationType.UPDATE,
                "direction": event_membership_payload.get(event.id, {}).get("direction", LinkDirection.NONE),
                "evidence_json": event_membership_payload.get(event.id, {}).get("evidence_json"),
                "score": event_membership_payload.get(event.id, {}).get("score"),
                "status": VerificationStatus.VERIFIED,
                "model_version": event_membership_payload.get(event.id, {}).get("model_version"),
                "pipeline_version": event_membership_payload.get(event.id, {}).get("pipeline_version"),
            }
            existing_membership = existing_memberships_for_process.get(int(event.id))
            if existing_membership is not None:
                existing_membership.relation_type = membership_values["relation_type"]
                existing_membership.direction = membership_values["direction"]
                existing_membership.evidence_json = membership_values["evidence_json"]
                existing_membership.score = membership_values["score"]
                existing_membership.status = membership_values["status"]
                existing_membership.model_version = membership_values["model_version"]
                existing_membership.pipeline_version = membership_values["pipeline_version"]
                continue

            stmt = (
                insert(ProcessEvent)
                .values(
                    process_id=matched_process_id,
                    event_id=event.id,
                    relation_type=membership_values["relation_type"],
                    direction=membership_values["direction"],
                    evidence_json=membership_values["evidence_json"],
                    score=membership_values["score"],
                    status=membership_values["status"],
                    model_version=membership_values["model_version"],
                    pipeline_version=membership_values["pipeline_version"],
                )
                .on_conflict_do_nothing()
            )
            await session.execute(stmt)
            created_memberships += 1

    stale_process_ids = set(existing_process_by_id) - active_process_ids
    for stale_process_id in stale_process_ids:
        if existing_event_ids_by_process_id.get(stale_process_id):
            await session.execute(delete(ProcessEvent).where(ProcessEvent.process_id == stale_process_id))
        stale_process = existing_process_by_id[stale_process_id]
        stale_process.status = VerificationStatus.REJECTED
        stale_process.confidence = 0.0

    return created_memberships
