from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Post, Comment, Report  


async def upsert_channel(
    session: AsyncSession,
    *,
    username: str,
    title: Optional[str],
    category: Optional[str] = None,
    is_active: bool = True,
) -> Channel:
    stmt = (
        insert(Channel)
        .values(
            username=username,
            title=title,
            category=category,
            is_active=is_active,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            index_elements=[Channel.username],
            set_={
                "title": title,
                "category": category,
                "is_active": is_active,
            },
        )
        .returning(Channel.id)
    )
    res = await session.execute(stmt)
    channel_id = res.scalar_one()

    ch = await session.get(Channel, channel_id)
    assert ch is not None
    return ch


async def upsert_post(
    session: AsyncSession,
    *,
    channel_id: int,
    tg_message_id: int,
    date: datetime,
    text: Optional[str],
    views: Optional[int],
    comments_count: int = 0,
) -> Post:
    stmt = (
        insert(Post)
        .values(
            channel_id=channel_id,
            tg_message_id=tg_message_id,
            date=date,
            text=text,
            views=views,
            comments_count=comments_count,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_posts_channel_msg",
            set_={
                # date/text обычно неизменны, но пусть обновляются — это безопасно
                "date": date,
                "text": text,
                "views": views,
                # comments_count будем обновлять позже отдельным апдейтом, но и тут можно
                "comments_count": comments_count,
            },
        )
        .returning(Post.id)
    )
    res = await session.execute(stmt)
    post_id = res.scalar_one()

    post = await session.get(Post, post_id)
    assert post is not None
    return post


async def upsert_comment(
    session: AsyncSession,
    *,
    channel_id: int,
    post_id: int,
    tg_message_id: int,
    date: datetime,
    author_id: Optional[int],
    author_username: Optional[str],
    text: Optional[str],
) -> Comment:
    stmt = (
        insert(Comment)
        .values(
            channel_id=channel_id,
            post_id=post_id,
            tg_message_id=tg_message_id,
            date=date,
            author_id=author_id,
            author_username=author_username,
            text=text,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_comments_channel_msg",
            set_={
                "post_id": post_id,
                "date": date,
                "author_id": author_id,
                "author_username": author_username,
                "text": text,
            },
        )
        .returning(Comment.id)
    )
    res = await session.execute(stmt)
    comment_id = res.scalar_one()

    c = await session.get(Comment, comment_id)
    assert c is not None
    return c


async def set_post_comments_count(session: AsyncSession, *, post_id: int, comments_count: int) -> None:
    # лёгкий апдейт без SELECT
    await session.execute(
        Post.__table__.update()
        .where(Post.id == post_id)
        .values(comments_count=comments_count)
    )

async def upsert_report(
    session: AsyncSession,
    *,
    post_id: int,
    content: str,
    status: str = "ready",
) -> Report:
    """
    Upsert отчета по post_id.

    - Если отчет для post_id уже есть: обновляет status/content.
    - Если нет: создает новый Report.

    ВАЖНО: функция не делает session.commit() — вы вызываете ее внутри transaction/session.begin().
    """
    # Ищем существующий отчет по уникальному post_id
    res = await session.execute(select(Report).where(Report.post_id == post_id))
    report: Optional[Report] = res.scalar_one_or_none()

    if report is None:
        report = Report(
            post_id=post_id,
            status=status,
            content=content,
            # created_at задан default-ом на модели, но можно проставить явно:
            created_at=datetime.now(timezone.utc),
        )
        session.add(report)
        # flush, чтобы получить report.id в рамках текущей транзакции
        await session.flush()
        return report

    # Update существующего
    report.status = status
    report.content = content
    # created_at не трогаем: это "время создания"
    await session.flush()
    return report