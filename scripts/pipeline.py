from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from client.config import load_client_settings
from db.models import Channel, Post
from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.ingest import upsert_post
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes

SKIP_CHANNEL_IDS = {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse active channels for last N days and run no-LLM linking pipeline.")
    parser.add_argument("--days", type=int, default=3, help="How many days back to parse.")
    parser.add_argument("--max-posts-per-channel", type=int, default=100, help="Safety limit per channel.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--session-suffix", type=str, default="no_llm")
    parser.add_argument("--unique-session-per-run", action="store_true")
    parser.add_argument(
        "--skip-rebuild-graphs",
        action="store_true",
        help="Do not rebuild events/processes after linking run.",
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


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


async def _get_active_channels() -> list[Channel]:
    async with AsyncSessionLocal() as session:
        stmt = select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id.asc())
        return list((await session.execute(stmt)).scalars().all())


async def _get_post_by_channel_msg(*, session, channel_id: int, tg_message_id: int) -> Post | None:
    stmt = (
        select(Post)
        .where(Post.channel_id == channel_id)
        .where(Post.tg_message_id == tg_message_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _extract_parent_tg_message_id(message) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        return None
    parent_tg_message_id = getattr(reply_to, "reply_to_msg_id", None)
    if isinstance(parent_tg_message_id, int) and parent_tg_message_id > 0:
        return parent_tg_message_id
    return None


def _extract_comments_count(message) -> int:
    replies = getattr(message, "replies", None)
    count = getattr(replies, "replies", 0) if replies is not None else 0
    if isinstance(count, int) and count >= 0:
        return count
    return 0


async def _pick_album_representative_message(client: TelegramClient, entity, message):
    grouped_id = getattr(message, "grouped_id", None)
    if not isinstance(grouped_id, int):
        return message

    radius = 10
    candidate_ids = [msg_id for msg_id in range(message.id - radius, message.id + radius + 1) if msg_id > 0]
    if not candidate_ids:
        return message

    try:
        nearby = await _with_session_lock_retry(
            lambda: client.get_messages(entity, ids=candidate_ids),
            op_name="get_messages(album_nearby)",
        )
    except Exception:
        return message

    if not isinstance(nearby, list):
        nearby = [nearby] if nearby is not None else []

    grouped_messages: list = []
    for item in nearby:
        if item is None:
            continue
        if getattr(item, "grouped_id", None) != grouped_id:
            continue
        if getattr(item, "date", None) is None:
            continue
        grouped_messages.append(item)

    if not grouped_messages:
        return message

    # Prefer the message carrying discussion counters/caption, then keep deterministic tie-breakers.
    return max(
        grouped_messages,
        key=lambda m: (
            _extract_comments_count(m),
            1 if str(getattr(m, "message", "") or "").strip() else 0,
            -int(getattr(m, "id", 0) or 0),
        ),
    )


async def _ensure_parent_post(
    *,
    client: TelegramClient,
    session,
    channel: Channel,
    entity,
    parent_tg_message_id: int,
) -> Post | None:
    parent_post = await _get_post_by_channel_msg(
        session=session,
        channel_id=channel.id,
        tg_message_id=parent_tg_message_id,
    )
    if parent_post is not None:
        return parent_post

    try:
        parent_msg = await _with_session_lock_retry(
            lambda: client.get_messages(entity, ids=parent_tg_message_id),
            op_name=f"get_messages(parent:{parent_tg_message_id})",
        )
    except Exception:
        return None

    if isinstance(parent_msg, list):
        parent_msg = parent_msg[0] if parent_msg else None
    if parent_msg is None or getattr(parent_msg, "id", None) is None or getattr(parent_msg, "date", None) is None:
        return None

    parent_parent_tg_message_id = _extract_parent_tg_message_id(parent_msg)
    parent_parent_post_id: int | None = None
    if isinstance(parent_parent_tg_message_id, int):
        parent_parent_post = await _get_post_by_channel_msg(
            session=session,
            channel_id=channel.id,
            tg_message_id=parent_parent_tg_message_id,
        )
        if parent_parent_post is not None:
            parent_parent_post_id = parent_parent_post.id

    saved = await upsert_post(
        session,
        channel_id=channel.id,
        tg_message_id=parent_msg.id,
        parent_tg_message_id=parent_parent_tg_message_id,
        parent_post_id=parent_parent_post_id,
        date=parent_msg.date,
        text=parent_msg.message,
        views=getattr(parent_msg, "views", None),
        comments_count=_extract_comments_count(parent_msg),
        involvement=None,
    )
    await session.commit()
    return saved


async def _process_channel(client: TelegramClient, channel: Channel, *, since_utc: datetime, max_posts: int) -> None:
    if channel.id in SKIP_CHANNEL_IDS:
        logging.info("Skip channel id=%s (@%s): excluded by config", channel.id, channel.username)
        return

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
        logging.warning("Skip channel @%s: entity resolve failed: %r", channel.username, exc)
        return

    logging.info("Parsing channel @%s since %s", channel.username, since_utc.isoformat())
    pipeline = NoLlmLinkingPipeline.build_default()
    processed = 0
    processed_grouped_ids: set[int] = set()

    async for msg in client.iter_messages(entity):
        if processed >= max_posts:
            break
        if msg.date is None:
            continue
        if msg.date < since_utc:
            break
        grouped_id = getattr(msg, "grouped_id", None)
        if isinstance(grouped_id, int):
            if grouped_id in processed_grouped_ids:
                continue
            msg = await _pick_album_representative_message(client, entity, msg)
            processed_grouped_ids.add(grouped_id)

        parent_tg_message_id = _extract_parent_tg_message_id(msg)
        comments_count = _extract_comments_count(msg)
        async with AsyncSessionLocal() as session:
            parent_post_id: int | None = None
            if isinstance(parent_tg_message_id, int):
                parent_post = await _ensure_parent_post(
                    client=client,
                    session=session,
                    channel=channel,
                    entity=entity,
                    parent_tg_message_id=parent_tg_message_id,
                )
                if parent_post is not None:
                    parent_post_id = parent_post.id

            post = await upsert_post(
                session,
                channel_id=channel.id,
                tg_message_id=msg.id,
                parent_tg_message_id=parent_tg_message_id,
                parent_post_id=parent_post_id,
                date=msg.date,
                text=msg.message,
                views=getattr(msg, "views", None),
                comments_count=comments_count,
                involvement=None,
            )
            await session.commit()
            logging.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, msg.id, channel.username)

            db_post = await session.get(Post, post.id)
            if db_post is None:
                continue
            result = await pipeline.run_for_post(session, db_post)
            await session.commit()
            logging.info(
                "Linked post id=%s verified=%s proposed=%s review=%s rejected=%s candidates=%s",
                post.id,
                result.links_verified,
                result.links_proposed,
                result.queued_for_review,
                result.links_rejected,
                result.candidates_checked,
            )
        processed += 1

    logging.info("Finished @%s processed_posts=%s", channel.username, processed)


async def _rebuild_event_process_graphs(*, date_from: datetime, date_to: datetime) -> None:
    async with AsyncSessionLocal() as session:
        rebuilt_events = await rebuild_events(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="no-llm-pipeline",
        )
        await session.commit()
    logging.info("Rebuilt events=%s for %s..%s", rebuilt_events, date_from.isoformat(), date_to.isoformat())

    async with AsyncSessionLocal() as session:
        rebuilt_process_edges = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="no-llm-pipeline",
        )
        await session.commit()
    logging.info(
        "Rebuilt process_edges=%s for %s..%s",
        rebuilt_process_edges,
        date_from.isoformat(),
        date_to.isoformat(),
    )


async def main_async(args: argparse.Namespace) -> None:
    client = _build_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    since_utc = datetime.now(timezone.utc) - timedelta(days=args.days)
    channels = await _get_active_channels()
    if not channels:
        logging.warning("No active channels found.")
        return

    await _with_session_lock_retry(lambda: client.start(), op_name="client.start")
    try:
        for channel in channels:
            await _process_channel(client, channel, since_utc=since_utc, max_posts=args.max_posts_per_channel)
        if not args.skip_rebuild_graphs:
            await _rebuild_event_process_graphs(
                date_from=since_utc,
                date_to=datetime.now(timezone.utc),
            )
    finally:
        try:
            await _with_session_lock_retry(lambda: client.disconnect(), op_name="client.disconnect")
        except Exception as exc:
            if _is_session_locked_error(exc):
                logging.warning("Telethon session is locked during disconnect, ignored: %r", exc)
            else:
                raise


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
