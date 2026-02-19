from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

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
