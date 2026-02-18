from __future__ import annotations

import asyncio
import re
import sys
from typing import Optional

from telethon.tl.types import Channel as TgChannel

from db.session import get_session
from services.ingest import upsert_channel
from client import client
from db.session import AsyncSessionLocal


def normalize_channel_identifier(raw: str) -> str:
    raw = raw.strip()

    # @name
    if raw.startswith("@"):
        return raw

    # https://t.me/name or t.me/name
    m = re.search(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})", raw)
    if m:
        return "@" + m.group(1)

    # fallback: assume it's username without @
    return "@" + raw


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.add_channel @username|https://t.me/username")
        raise SystemExit(2)

    ident = normalize_channel_identifier(sys.argv[1])

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

    async with AsyncSessionLocal() as session:
        async with session.begin():
            ch = await upsert_channel(
                session,
                username=username,
                title=title,
                category=None,
                is_active=True,
            )

    print(f"OK: saved channel id={ch.id} username=@{ch.username} title={ch.title!r}")


if __name__ == "__main__":
    asyncio.run(main())
