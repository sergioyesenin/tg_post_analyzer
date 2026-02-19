from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from telethon.tl.types import Channel as TgChannel

from deps import get_session
from db.models import Channel
from schemas.channel import ChannelOut, ChannelIn
from scripts.add_channel import normalize_channel_identifier
from client import client
from services.ingest import upsert_channel

router = APIRouter()

@router.get("/", response_model=list[ChannelOut])
async def list_channels(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Channel))
    return result.scalars().all()

@router.post("/add")
async def add_channel(user: ChannelIn, session: AsyncSession = Depends(get_session) ):
    ident = normalize_channel_identifier(user.username)
    if not client:
        await client.start()

    entity = await client.get_entity(ident)
    if not isinstance(entity, TgChannel):
        print(f"ERROR: {ident} is not a channel (got {type(entity)})")
        raise SystemExit(1)

    username: Optional[str] = entity.username
    title: Optional[str] = getattr(entity, "title", None)

    # username обязательный в БД
    if not username:
        username = f"id_{entity.id}"

    async with session.begin(): 
        ch = await upsert_channel(
            session,
            username=username,
            title=title,
            category=None,
            is_active=True,
        )
    return (f"OK: saved channel id={ch.id} username=@{ch.username} title={ch.title!r}")
