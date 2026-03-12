from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EventPost, Post, ProcessEvent


async def load_event_metrics(session: AsyncSession, event_ids: list[int]) -> dict[int, dict[str, float | int | None]]:
    if not event_ids:
        return {}

    stmt = (
        select(
            EventPost.event_id.label("entity_id"),
            func.coalesce(func.sum(Post.comments_count), 0).label("comments_count"),
            func.avg(Post.involvement).label("involvement"),
        )
        .join(Post, Post.id == EventPost.post_id)
        .where(EventPost.event_id.in_(event_ids))
        .group_by(EventPost.event_id)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return {
        int(row["entity_id"]): {
            "comments_count": int(row["comments_count"] or 0),
            "involvement": float(row["involvement"]) if row["involvement"] is not None else None,
        }
        for row in rows
    }


async def load_process_metrics(session: AsyncSession, process_ids: list[int]) -> dict[int, dict[str, float | int | None]]:
    if not process_ids:
        return {}

    process_posts = (
        select(
            ProcessEvent.process_id.label("process_id"),
            EventPost.post_id.label("post_id"),
        )
        .join(EventPost, EventPost.event_id == ProcessEvent.event_id)
        .where(ProcessEvent.process_id.in_(process_ids))
        .distinct()
        .subquery()
    )
    stmt = (
        select(
            process_posts.c.process_id.label("entity_id"),
            func.coalesce(func.sum(Post.comments_count), 0).label("comments_count"),
            func.avg(Post.involvement).label("involvement"),
        )
        .join(Post, Post.id == process_posts.c.post_id)
        .group_by(process_posts.c.process_id)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return {
        int(row["entity_id"]): {
            "comments_count": int(row["comments_count"] or 0),
            "involvement": float(row["involvement"]) if row["involvement"] is not None else None,
        }
        for row in rows
    }
