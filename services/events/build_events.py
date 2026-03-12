from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy import and_, delete, select
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


async def rebuild_events(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    created_by: str = "pipeline",
) -> int:
    posts_stmt = select(Post).where(and_(Post.date >= date_from, Post.date <= date_to))
    posts = (await session.execute(posts_stmt)).scalars().all()
    if not posts:
        return 0
    post_by_id = {p.id: p for p in posts}
    post_ids = set(post_by_id.keys())

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

    event_ids_stmt = (
        select(EventPost.event_id)
        .distinct()
        .where(EventPost.post_id.in_(post_ids))
    )
    event_ids = [row[0] for row in (await session.execute(event_ids_stmt)).all()]
    if event_ids:
        await session.execute(delete(EventPost).where(EventPost.event_id.in_(event_ids)))
        await session.execute(delete(Event).where(Event.id.in_(event_ids)))

    facts_stmt = select(PostFact).where(PostFact.post_id.in_(post_ids))
    facts_map = {f.post_id: f for f in (await session.execute(facts_stmt)).scalars().all()}

    rebuilt = 0
    for component in components:
        component_posts = [post_by_id[pid] for pid in component if pid in post_by_id]
        if not component_posts:
            continue
        started_at = min(p.date for p in component_posts)
        ended_at = max(p.date for p in component_posts)
        title = _first_post_title(component_posts, facts_map)
        event = Event(
            title=title,
            started_at=started_at,
            ended_at=ended_at,
            confidence=0.8,
            status=VerificationStatus.VERIFIED,
            created_by=created_by,
        )
        session.add(event)
        await session.flush()

        for post_obj in component_posts:
            membership_stmt = (
                insert(EventPost)
                .values(
                    event_id=event.id,
                    post_id=post_obj.id,
                    role="context",
                    evidence_json={
                        "anchors": facts_map.get(post_obj.id).entities_json if facts_map.get(post_obj.id) else {},
                        "spans": [],
                        "rationale": "Clustered from verified post links.",
                        "counterarguments": [],
                    },
                    score=0.8,
                    status=VerificationStatus.VERIFIED,
                    model_version="graph-cluster-v1",
                    pipeline_version="events-rebuild-v1",
                )
                .on_conflict_do_nothing()
            )
            await session.execute(membership_stmt)
        rebuilt += 1
    return rebuilt
