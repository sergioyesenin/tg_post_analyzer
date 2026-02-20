from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from db.models import Channel, Post, Comment, Report  

async def get_post_with_channel_by_post_id(session: AsyncSession, post_id: int) -> tuple[Post, Channel] | None:
    stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]

async def get_channel_by_post_id(session: AsyncSession, post_id: int) -> Channel | None:
    stmt = (
        select(Channel)
        .join(Post, Post.channel_id == Channel.id)
        .where(Post.id == post_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_tg_message_id(session: AsyncSession, post_id: int) -> int | None:
    stmt = (
        select(Post.tg_message_id).where(Post.id == post_id)
        )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def cleanup_empty_album_like_posts(
    session: AsyncSession,
    *,
    window_seconds: int = 5,
    id_gap: int = 1,
    limit: int = 500,
    dry_run: bool = True,
) -> dict:
    """
    Delete empty-text posts that look like media-group duplicates.

    A post is considered removable when:
    - its text is empty/whitespace;
    - there is a non-empty post in the same channel within `window_seconds`;
    - tg_message_id differs by at most `id_gap`.

    This function does not commit. Caller decides transaction boundaries.
    """
    sibling = aliased(Post)

    current_is_empty = func.length(func.trim(func.coalesce(Post.text, ""))) == 0
    sibling_is_non_empty = func.length(func.trim(func.coalesce(sibling.text, ""))) > 0

    sibling_exists = (
        select(1)
        .select_from(sibling)
        .where(
            and_(
                sibling.channel_id == Post.channel_id,
                sibling.id != Post.id,
                sibling_is_non_empty,
                func.abs(func.extract("epoch", sibling.date - Post.date)) <= window_seconds,
                func.abs(sibling.tg_message_id - Post.tg_message_id) <= id_gap,
            )
        )
        .exists()
    )

    candidates_stmt = (
        select(Post.id)
        .where(and_(current_is_empty, sibling_exists))
        .order_by(Post.id.asc())
        .limit(limit)
    )
    candidate_ids = [row[0] for row in (await session.execute(candidates_stmt)).all()]

    if dry_run or not candidate_ids:
        return {
            "dry_run": dry_run,
            "deleted_count": 0,
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids,
        }

    delete_stmt = delete(Post).where(Post.id.in_(candidate_ids))
    await session.execute(delete_stmt)
    return {
        "dry_run": dry_run,
        "deleted_count": len(candidate_ids),
        "candidate_count": len(candidate_ids),
        "candidate_ids": candidate_ids,
    }
