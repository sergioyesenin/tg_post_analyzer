from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from telethon.errors import RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel as TgChannel

from client import client
from db.models import Channel
from deps import get_session, require_roles
from schemas.channel import ChannelIn, ChannelOut
from scripts.add_channel import normalize_channel_identifier
from services.auth import AuthUser, write_audit_log
from services.ingest import upsert_channel

router = APIRouter()


@router.get("/", response_model=list[ChannelOut])
async def list_channels(
    _: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Channel))
    return result.scalars().all()


@router.post("/add")
async def add_channel(
    user: ChannelIn,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    ident = normalize_channel_identifier(user.username)
    normalized_username = ident.lstrip("@").strip()
    if not client.is_connected():
        await client.start()

    try:
        entity = await client.get_entity(ident)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot resolve channel: {ident}") from exc

    if not isinstance(entity, TgChannel):
        raise HTTPException(status_code=400, detail=f"{ident} is not a Telegram channel")

    try:
        await client(JoinChannelRequest(entity))
    except RPCError:
        # Already joined or join is not required for public reads.
        pass

    username: Optional[str] = entity.username
    title: Optional[str] = getattr(entity, "title", None)
    if not username and normalized_username:
        # Telethon may return a minimal entity without username populated.
        username = normalized_username
    if not username:
        raise HTTPException(
            status_code=400,
            detail=(
                "Channel has no public username. "
                "Only channels with username are supported by this endpoint."
            ),
        )

    async with session.begin():
        ch = await upsert_channel(
            session,
            username=username,
            title=title,
            category=None,
            is_active=True,
        )
        await write_audit_log(
            session,
            action="channels.add",
            actor_user_id=current_user.id,
            target_type="channel",
            target_id=str(ch.id),
            details={"username": ch.username, "title": ch.title},
        )
    return f"OK: saved channel id={ch.id} username=@{ch.username} title={ch.title!r}"


@router.put("/{channel_id}/active", response_model=ChannelOut)
async def set_channel_active(
    channel_id: int,
    is_active: bool,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.is_active = is_active
    await write_audit_log(
        session,
        action="channels.set_active",
        actor_user_id=current_user.id,
        target_type="channel",
        target_id=str(channel.id),
        details={"username": channel.username, "is_active": is_active},
    )
    await session.commit()
    await session.refresh(channel)
    return channel


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: int,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    username = channel.username
    await session.delete(channel)
    await write_audit_log(
        session,
        action="channels.delete",
        actor_user_id=current_user.id,
        target_type="channel",
        target_id=str(channel_id),
        details={"username": username},
    )
    await session.commit()
    return {"status": "deleted", "channel_id": channel_id, "username": username}
