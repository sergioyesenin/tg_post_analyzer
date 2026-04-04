from __future__ import annotations

from collections import Counter
from datetime import datetime
from unicodedata import normalize

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Event, EventPost, Post, PostFact, PostLink, PostLinkType, VerificationStatus


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

    def components(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for node in self.parent:
            root = self.find(node)
            out.setdefault(root, []).append(node)
        return out


def _canonical_title(posts: list[Post], facts_map: dict[int, PostFact]) -> str:
    entities: Counter[str] = Counter()
    for post in posts:
        facts = facts_map.get(post.id)
        if not facts:
            continue
        values = facts.entities_json.get("entities", []) if isinstance(facts.entities_json, dict) else []
        entities.update(v for v in values if isinstance(v, str))
    common = [name for name, _ in entities.most_common(3)]
    if common:
        return f"Event: {' | '.join(common)}"
    return f"Event cluster ({len(posts)} posts)"


def _first_post_title(posts: list[Post], facts_map: dict[int, PostFact]) -> str:
    if not posts:
        return "Event cluster (0 posts)"
    # Deterministic "first in cluster": earliest post by date, then id.
    first = sorted(posts, key=lambda p: (p.date, p.id))[0]
    first_paragraph = ""
    if first.text:
        first_paragraph = first.text.split("\n", 1)[0].strip()
    if first_paragraph:
        return first_paragraph[:140]
    return _canonical_title(posts, facts_map)


def _normalized_event_title(title: str | None) -> str | None:
    if not title:
        return None
    normalized = normalize("NFKC", title).strip().casefold()
    return normalized or None


def _merge_components_by_title(
    components: list[list[int]],
    *,
    post_by_id: dict[int, Post],
    facts_map: dict[int, PostFact],
) -> list[list[int]]:
    merged_components: list[list[int]] = []
    component_indexes_by_title: dict[str, int] = {}
    fallback_components: list[list[int]] = []

    for component in components:
        component_posts = [post_by_id[pid] for pid in component if pid in post_by_id]
        if not component_posts:
            continue
        title_key = _normalized_event_title(_first_post_title(component_posts, facts_map))
        if title_key is None:
            fallback_components.append(component)
            continue
        existing_index = component_indexes_by_title.get(title_key)
        if existing_index is None:
            component_indexes_by_title[title_key] = len(merged_components)
            merged_components.append(list(component))
            continue
        merged_components[existing_index].extend(component)

    merged_components.extend(fallback_components)
    return [sorted(set(component)) for component in merged_components]


def _component_payload(*, component: list[int], post_by_id: dict[int, Post], facts_map: dict[int, PostFact]) -> dict | None:
    component_posts = [post_by_id[pid] for pid in component if pid in post_by_id]
    if not component_posts:
        return None
    root_post = sorted(component_posts, key=lambda post: (post.date, post.id))[0]
    return {
        "post_ids": {int(post.id) for post in component_posts},
        "component_posts": component_posts,
        "root_post_id": int(root_post.id),
        "started_at": min(post.date for post in component_posts),
        "ended_at": max(post.date for post in component_posts),
        "title": _first_post_title(component_posts, facts_map),
    }


def _membership_payload(*, post_id: int, root_post_id: int, facts_map: dict[int, PostFact]) -> dict:
    facts = facts_map.get(post_id)
    return {
        "role": "root" if post_id == root_post_id else "context",
        "evidence_json": {
            "anchors": facts.entities_json if facts else {},
            "spans": [],
            "rationale": "Clustered from verified post links.",
            "counterarguments": [],
        },
        "score": 0.8,
        "status": VerificationStatus.VERIFIED,
        "model_version": "graph-cluster-v1",
        "pipeline_version": "events-rebuild-v1",
    }


def _match_component_to_event(
    *,
    component_post_ids: set[int],
    root_post_id: int,
    existing_post_ids_by_event_id: dict[int, set[int]],
    assigned_event_ids: set[int],
) -> int | None:
    best_event_id: int | None = None
    best_score: tuple[int, int, int] | None = None
    for event_id, existing_post_ids in existing_post_ids_by_event_id.items():
        if event_id in assigned_event_ids:
            continue
        overlap = len(component_post_ids & existing_post_ids)
        root_match = 1 if root_post_id in existing_post_ids else 0
        if overlap <= 0 and root_match <= 0:
            continue
        score = (root_match, overlap, -event_id)
        if best_score is None or score > best_score:
            best_score = score
            best_event_id = event_id
    return best_event_id


async def rebuild_events(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    created_by: str = "pipeline",
) -> int:
    seed_posts_stmt = select(Post).where(and_(Post.date >= date_from, Post.date <= date_to))
    seed_posts = (await session.execute(seed_posts_stmt)).scalars().all()
    if not seed_posts:
        return 0

    post_ids = {post.id for post in seed_posts}
    event_ids: set[int] = set()
    changed = True
    while changed:
        changed = False

        links_stmt = (
            select(PostLink)
            .where(
                and_(
                    PostLink.status == VerificationStatus.VERIFIED,
                    PostLink.link_type.in_([PostLinkType.SAME_EVENT, PostLinkType.RELATED]),
                    or_(PostLink.src_post_id.in_(post_ids), PostLink.dst_post_id.in_(post_ids)),
                )
            )
        )
        links = (await session.execute(links_stmt)).scalars().all()
        linked_post_ids = {
            linked_post_id
            for link in links
            for linked_post_id in (link.src_post_id, link.dst_post_id)
        }
        if not linked_post_ids.issubset(post_ids):
            post_ids.update(linked_post_ids)
            changed = True

        event_ids_stmt = (
            select(EventPost.event_id)
            .distinct()
            .where(EventPost.post_id.in_(post_ids))
        )
        discovered_event_ids = {row[0] for row in (await session.execute(event_ids_stmt)).all()}
        if not discovered_event_ids.issubset(event_ids):
            event_ids.update(discovered_event_ids)
            changed = True

        if event_ids:
            event_post_ids_stmt = select(EventPost.post_id).where(EventPost.event_id.in_(event_ids))
            existing_event_post_ids = {row[0] for row in (await session.execute(event_post_ids_stmt)).all()}
            if not existing_event_post_ids.issubset(post_ids):
                post_ids.update(existing_event_post_ids)
                changed = True

    posts_stmt = select(Post).where(Post.id.in_(post_ids))
    posts = (await session.execute(posts_stmt)).scalars().all()
    post_by_id = {post.id: post for post in posts}

    links_stmt = (
        select(PostLink)
        .where(
            and_(
                PostLink.src_post_id.in_(post_ids),
                PostLink.dst_post_id.in_(post_ids),
                PostLink.status == VerificationStatus.VERIFIED,
                PostLink.link_type.in_([PostLinkType.SAME_EVENT, PostLinkType.RELATED]),
            )
        )
    )
    links = (await session.execute(links_stmt)).scalars().all()

    uf = _UnionFind()
    for post_id in post_ids:
        uf.find(post_id)
    for link in links:
        uf.union(link.src_post_id, link.dst_post_id)
    components = list(uf.components().values())

    facts_stmt = select(PostFact).where(PostFact.post_id.in_(post_ids))
    facts_map = {f.post_id: f for f in (await session.execute(facts_stmt)).scalars().all()}
    components = _merge_components_by_title(components, post_by_id=post_by_id, facts_map=facts_map)
    component_payloads = [
        payload
        for payload in (
            _component_payload(component=component, post_by_id=post_by_id, facts_map=facts_map)
            for component in components
        )
        if payload is not None
    ]

    existing_events = []
    existing_memberships = []
    if event_ids:
        existing_events = (await session.execute(select(Event).where(Event.id.in_(event_ids)))).scalars().all()
        existing_memberships = (
            await session.execute(select(EventPost).where(EventPost.event_id.in_(event_ids)))
        ).scalars().all()

    existing_event_by_id = {int(event.id): event for event in existing_events}
    existing_memberships_by_event_id: dict[int, dict[int, EventPost]] = {}
    existing_post_ids_by_event_id: dict[int, set[int]] = {}
    for membership in existing_memberships:
        event_id = int(membership.event_id)
        post_id = int(membership.post_id)
        existing_memberships_by_event_id.setdefault(event_id, {})[post_id] = membership
        existing_post_ids_by_event_id.setdefault(event_id, set()).add(post_id)

    assigned_event_ids: set[int] = set()
    active_event_ids: set[int] = set()
    rebuilt = 0

    for payload in sorted(component_payloads, key=lambda item: (item["started_at"], item["root_post_id"])):
        matched_event_id = _match_component_to_event(
            component_post_ids=payload["post_ids"],
            root_post_id=payload["root_post_id"],
            existing_post_ids_by_event_id=existing_post_ids_by_event_id,
            assigned_event_ids=assigned_event_ids,
        )
        if matched_event_id is not None:
            event = existing_event_by_id[matched_event_id]
            assigned_event_ids.add(matched_event_id)
        else:
            event = Event(
                title=payload["title"],
                started_at=payload["started_at"],
                ended_at=payload["ended_at"],
                confidence=0.8,
                status=VerificationStatus.VERIFIED,
                created_by=created_by,
            )
            session.add(event)
            await session.flush()
            matched_event_id = int(event.id)
            existing_event_by_id[matched_event_id] = event
            existing_memberships_by_event_id[matched_event_id] = {}
            existing_post_ids_by_event_id[matched_event_id] = set()
            assigned_event_ids.add(matched_event_id)

        event.title = payload["title"]
        event.started_at = payload["started_at"]
        event.ended_at = payload["ended_at"]
        event.confidence = 0.8
        event.status = VerificationStatus.VERIFIED
        active_event_ids.add(matched_event_id)

        existing_memberships_for_event = existing_memberships_by_event_id.get(matched_event_id, {})
        stale_post_ids = set(existing_memberships_for_event) - payload["post_ids"]
        if stale_post_ids:
            await session.execute(
                delete(EventPost)
                .where(EventPost.event_id == matched_event_id)
                .where(EventPost.post_id.in_(stale_post_ids))
            )
            for stale_post_id in stale_post_ids:
                existing_memberships_for_event.pop(stale_post_id, None)
            existing_post_ids_by_event_id[matched_event_id] = set(existing_memberships_for_event)

        for post_obj in sorted(payload["component_posts"], key=lambda post: (post.date, post.id)):
            membership_values = _membership_payload(
                post_id=int(post_obj.id),
                root_post_id=payload["root_post_id"],
                facts_map=facts_map,
            )
            existing_membership = existing_memberships_for_event.get(int(post_obj.id))
            if existing_membership is not None:
                existing_membership.role = membership_values["role"]
                existing_membership.evidence_json = membership_values["evidence_json"]
                existing_membership.score = membership_values["score"]
                existing_membership.status = membership_values["status"]
                existing_membership.model_version = membership_values["model_version"]
                existing_membership.pipeline_version = membership_values["pipeline_version"]
                continue

            membership_stmt = (
                insert(EventPost)
                .values(
                    event_id=matched_event_id,
                    post_id=post_obj.id,
                    role=membership_values["role"],
                    evidence_json=membership_values["evidence_json"],
                    score=membership_values["score"],
                    status=membership_values["status"],
                    model_version=membership_values["model_version"],
                    pipeline_version=membership_values["pipeline_version"],
                )
                .on_conflict_do_nothing()
            )
            await session.execute(membership_stmt)
        rebuilt += 1

    stale_event_ids = set(existing_event_by_id) - active_event_ids
    for stale_event_id in stale_event_ids:
        if existing_post_ids_by_event_id.get(stale_event_id):
            await session.execute(delete(EventPost).where(EventPost.event_id == stale_event_id))
        stale_event = existing_event_by_id[stale_event_id]
        stale_event.status = VerificationStatus.REJECTED
        stale_event.confidence = 0.0

    return rebuilt
