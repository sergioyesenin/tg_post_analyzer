from __future__ import annotations

import asyncio
import re
import sys
from typing import Optional

from telethon.tl.types import Channel as TgChannel

from client import client, ensure_telegram_client_started
from db.session import AsyncSessionLocal
from services.ingest import upsert_channel


def normalize_channel_identifier(raw: str) -> str:
    raw = raw.strip()

    if raw.startswith("@"):
        return raw

    m = re.search(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})", raw)
    if m:
        return "@" + m.group(1)

    return "@" + raw


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.add_channel @username|https://t.me/username")
        raise SystemExit(2)

    ident = normalize_channel_identifier(sys.argv[1])
    normalized_username = ident.lstrip("@").strip()

    await ensure_telegram_client_started(client, op_name="scripts.add_channel.start")

    entity = await client.get_entity(ident)
    if not isinstance(entity, TgChannel):
        print(f"ERROR: {ident} is not a channel (got {type(entity)})")
        raise SystemExit(1)

    username: Optional[str] = entity.username
    title: Optional[str] = getattr(entity, "title", None)
    if not username and normalized_username:
        username = normalized_username
    if not username:
        print("ERROR: channel has no public username. Only channels with username are supported.")
        raise SystemExit(1)

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
