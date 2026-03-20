from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from telethon.errors import RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import Channel as TgChannel

from client.telegram import TelegramClientHandle, ensure_telegram_client_started
from db.models import Channel
from services.ingest import upsert_channel


def normalize_channel_identifier(raw: str) -> str:
    raw = raw.strip()

    if raw.startswith("@"):
        return raw

    match = re.search(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})", raw)
    if match:
        return "@" + match.group(1)

    return "@" + raw


async def resolve_and_upsert_channel(
    *,
    tg_client: TelegramClientHandle,
    session,
    raw_username: str,
) -> tuple[Channel, dict]:
    ident = normalize_channel_identifier(raw_username)
    normalized_username = ident.lstrip("@").strip()

    await ensure_telegram_client_started(tg_client, op_name="channels.add.resolve")

    try:
        entity = await tg_client.get_entity(ident)
    except Exception as exc:
        raise ValueError(f"Cannot resolve channel: {ident}") from exc

    if not isinstance(entity, TgChannel):
        raise ValueError(f"{ident} is not a Telegram channel")

    # try:
        # await tg_client(JoinChannelRequest(entity))
    # except RPCError:
        # Already joined or join is not required for public reads.
    #    pass

    username: Optional[str] = entity.username
    title: Optional[str] = getattr(entity, "title", None)
    if not username and normalized_username:
        username = normalized_username
    if not username:
        raise ValueError(
            "Channel has no public username. Only channels with username are supported by this endpoint."
        )

    existing_channel = await session.scalar(select(Channel.id).where(Channel.username == username).limit(1))
    channel = await upsert_channel(
        session,
        username=username,
        title=title,
        category=None,
        is_active=True,
    )
    return channel, {
        "status": "updated" if existing_channel is not None else "created",
        "channel_id": channel.id,
        "username": channel.username,
        "title": channel.title,
    }
