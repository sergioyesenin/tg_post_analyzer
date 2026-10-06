from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


async def list_all_users(session: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.id.asc())
    return list((await session.execute(stmt)).scalars().all())


async def find_user_by_username(
    session: AsyncSession,
    *,
    username: str,
) -> User | None:
    stmt = select(User).where(User.username == username)
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_user_by_email(
    session: AsyncSession,
    *,
    email: str,
) -> User | None:
    stmt = select(User).where(User.email == email)
    return (await session.execute(stmt)).scalar_one_or_none()