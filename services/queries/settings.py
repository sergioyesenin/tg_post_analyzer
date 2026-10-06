from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSetting


async def list_all_settings(session: AsyncSession) -> list[AppSetting]:
    stmt = select(AppSetting).order_by(AppSetting.key.asc())
    return list((await session.execute(stmt)).scalars().all())