from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from client.config import load_client_settings
from db.models import Channel
from db.session import AsyncSessionLocal
from services.ingest import upsert_post

SKIP_CHANNEL_IDS = {2}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch and save last post for each active channel from DB.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--include-inactive", action="store_true", help="Also include inactive channels.")
    parser.add_argument("--session-suffix", type=str, default="last_post_probe")
    parser.add_argument("--unique-session-per-run", action="store_true")
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


def _extract_comments_count(message) -> int:
    replies = getattr(message, "replies", None)
    count = getattr(replies, "replies", 0) if replies is not None else 0
    if isinstance(count, int) and count >= 0:
        return count
    return 0


def _is_session_locked_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


def _build_client(*, session_suffix: str, unique_session_per_run: bool) -> TelegramClient:
    client_settings = load_client_settings()
    suffix = session_suffix
    if unique_session_per_run:
        suffix = f"{suffix}_{os.getpid()}"
    return TelegramClient(
        session=client_settings.session,
        api_id=client_settings.api_id,
        api_hash=client_settings.api_hash,
        flood_sleep_threshold=client_settings.flood_sleep_threshold,
    )


async def _with_session_lock_retry(coro_factory, *, op_name: str, retries: int = 3, delay_sec: float = 1.5):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not _is_session_locked_error(exc) or attempt >= retries:
                raise
            logging.warning(
                "Telethon session locked during %s. Retry %s/%s after %.1fs",
                op_name,
                attempt,
                retries,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{op_name} failed unexpectedly")


async def _get_channels(include_inactive: bool) -> list[Channel]:
    async with AsyncSessionLocal() as session:
        stmt = select(Channel).order_by(Channel.id.asc())
        if not include_inactive:
            stmt = stmt.where(Channel.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())


async def _process_channel(client: TelegramClient, channel: Channel) -> bool:
    if channel.id in SKIP_CHANNEL_IDS:
        logging.info("Skip channel id=%s (@%s): excluded by config", channel.id, channel.username)
        return True

    if channel.username.startswith("id_") and channel.username[3:].isdigit():
        peer = PeerChannel(int(channel.username[3:]))
    else:
        peer = f"@{channel.username}"

    try:
        entity = await _with_session_lock_retry(
            lambda: client.get_entity(peer),
            op_name=f"get_entity(@{channel.username})",
        )
    except Exception as exc:
        logging.warning("Skip @%s: cannot resolve entity: %r", channel.username, exc)
        return False

    msgs = await _with_session_lock_retry(
        lambda: client.get_messages(entity, limit=1),
        op_name=f"get_messages(@{channel.username})",
    )
    if isinstance(msgs, list):
        last_msg = msgs[0] if msgs else None
    else:
        last_msg = msgs

    if last_msg is None or getattr(last_msg, "id", None) is None or getattr(last_msg, "date", None) is None:
        logging.warning("Skip @%s: no messages found", channel.username)
        return False

    comments_count = _extract_comments_count(last_msg)
    async with AsyncSessionLocal() as session:
        post = await upsert_post(
            session,
            channel_id=channel.id,
            tg_message_id=last_msg.id,
            parent_tg_message_id=None,
            parent_post_id=None,
            date=last_msg.date,
            text=getattr(last_msg, "message", None),
            views=getattr(last_msg, "views", None),
            comments_count=comments_count,
            involvement=None,
        )
        await session.commit()

    logging.info(
        "Saved last post: channel=@%s post_id=%s tg_message_id=%s date=%s comments=%s",
        channel.username,
        post.id,
        last_msg.id,
        last_msg.date.astimezone(timezone.utc).isoformat(),
        comments_count,
    )
    return True


async def main_async(args: argparse.Namespace) -> None:
    client = _build_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    channels = await _get_channels(args.include_inactive)
    if not channels:
        logging.warning("No channels found.")
        return

    logging.info("Channels to process: %s", len(channels))

    await _with_session_lock_retry(lambda: client.start(), op_name="client.start")
    ok = 0
    failed = 0
    try:
        for channel in channels:
            try:
                if await _process_channel(client, channel):
                    ok += 1
                else:
                    failed += 1
            except Exception as exc:
                if _is_session_locked_error(exc):
                    logging.warning("Session DB locked while processing @%s: %r", channel.username, exc)
                else:
                    logging.exception("Unexpected error for @%s", channel.username)
                failed += 1
    finally:
        try:
            await _with_session_lock_retry(lambda: client.disconnect(), op_name="client.disconnect")
        except Exception as exc:
            if _is_session_locked_error(exc):
                logging.warning("Telethon session is locked during disconnect, ignored: %r", exc)
            else:
                raise

    logging.info("Done. success=%s failed=%s", ok, failed)


def main() -> None:
    args = _build_parser().parse_args()
    _configure_logging(args.log_level)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
