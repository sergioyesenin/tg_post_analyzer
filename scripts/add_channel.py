from __future__ import annotations

import asyncio
import sys

from client import client, ensure_telegram_client_started
from db.session import AsyncSessionLocal
from services.channel_management import normalize_channel_identifier, resolve_and_upsert_channel


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.add_channel @username|https://t.me/username")
        raise SystemExit(2)

    ident = normalize_channel_identifier(sys.argv[1])

    await ensure_telegram_client_started(client, op_name="scripts.add_channel.start")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            ch, result = await resolve_and_upsert_channel(
                tg_client=client,
                session=session,
                raw_username=ident,
            )

    print(
        f"OK: {result['status']} channel id={ch.id} "
        f"username=@{ch.username} title={ch.title!r}"
    )


if __name__ == "__main__":
    asyncio.run(main())
