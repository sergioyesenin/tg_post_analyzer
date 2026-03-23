from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telethon.errors import FloodWaitError
from telethon.tl.types import PeerChannel

from db.models import Channel, Post
from services.ingest import upsert_post


def day_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def extract_parent_tg_message_id(message: Any) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        return None
    parent_tg_message_id = getattr(reply_to, "reply_to_msg_id", None)
    if isinstance(parent_tg_message_id, int) and parent_tg_message_id > 0:
        return parent_tg_message_id
    return None


def extract_comments_count(message: Any) -> int:
    replies = getattr(message, "replies", None)
    count = getattr(replies, "replies", 0) if replies is not None else 0
    if isinstance(count, int) and count >= 0:
        return count
    return 0


async def polite_sleep(base: float, jitter: float) -> None:
    await asyncio.sleep(base + random.random() * jitter)


@dataclass(frozen=True)
class IngestionOptions:
    since_utc: datetime | None = None
    until_utc: datetime | None = None
    min_replies: int = 0
    max_posts: int = 100
    sleep_every: int = 50
    sleep_base_sec: float = 0.4
    sleep_jitter_sec: float = 0.6
    stop_on_existing_post: bool = True
    min_tg_message_id_exclusive: int = 0
    resolve_album_representative: bool = True


@dataclass(frozen=True)
class IngestionContext:
    channel: Channel
    entity: Any
    message: Any
    parent_tg_message_id: int | None
    comments_count: int
    parent_post_id: int | None


@dataclass(frozen=True)
class IngestionResult:
    channel_id: int
    channel_username: str
    processed_posts: int
    stopped_reason: str | None = None


OnPostSaved = Callable[[Any, Post, IngestionContext], Awaitable[None]]


class IngestionCore:
    def __init__(
        self,
        *,
        tg_client,
        session_factory,
        upsert_post_fn=upsert_post,
    ) -> None:
        self._tg_client = tg_client
        self._session_factory = session_factory
        self._upsert_post = upsert_post_fn

    @staticmethod
    def _build_peer(channel: Channel) -> Any:
        username = channel.username
        if username.startswith("id_") and username[3:].isdigit():
            return PeerChannel(int(username[3:]))
        return f"@{username}"

    async def _get_post_by_channel_msg(self, *, session, channel_id: int, tg_message_id: int) -> Post | None:
        stmt = (
            select(Post)
            .where(Post.channel_id == channel_id)
            .where(Post.tg_message_id == tg_message_id)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _ensure_parent_post(self, *, session, channel: Channel, entity, parent_tg_message_id: int) -> Post | None:
        parent_post = await self._get_post_by_channel_msg(
            session=session,
            channel_id=channel.id,
            tg_message_id=parent_tg_message_id,
        )
        if parent_post is not None:
            return parent_post

        try:
            parent_msg = await self._tg_client.get_messages(entity, ids=parent_tg_message_id)
        except Exception:
            return None

        if isinstance(parent_msg, list):
            parent_msg = parent_msg[0] if parent_msg else None
        if parent_msg is None or getattr(parent_msg, "id", None) is None or getattr(parent_msg, "date", None) is None:
            return None

        parent_parent_tg_message_id = extract_parent_tg_message_id(parent_msg)
        parent_parent_post_id: int | None = None
        if isinstance(parent_parent_tg_message_id, int):
            parent_parent_post = await self._get_post_by_channel_msg(
                session=session,
                channel_id=channel.id,
                tg_message_id=parent_parent_tg_message_id,
            )
            if parent_parent_post is not None:
                parent_parent_post_id = parent_parent_post.id

        return await self._upsert_post(
            session,
            channel_id=channel.id,
            tg_message_id=parent_msg.id,
            parent_tg_message_id=parent_parent_tg_message_id,
            parent_post_id=parent_parent_post_id,
            date=parent_msg.date,
            text=parent_msg.message,
            views=getattr(parent_msg, "views", None),
            comments_count=extract_comments_count(parent_msg),
            involvement=None,
        )

    async def _pick_album_representative_message(self, entity, message):
        grouped_id = getattr(message, "grouped_id", None)
        if not isinstance(grouped_id, int):
            return message

        radius = 10
        candidate_ids = [msg_id for msg_id in range(message.id - radius, message.id + radius + 1) if msg_id > 0]
        if not candidate_ids:
            return message

        try:
            nearby = await self._tg_client.get_messages(entity, ids=candidate_ids)
        except Exception:
            return message

        if not isinstance(nearby, list):
            nearby = [nearby] if nearby is not None else []

        grouped_messages: list[Any] = []
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

        grouped_messages.sort(key=lambda m: int(getattr(m, "id", 0) or 0))
        representative = grouped_messages[0]

        return representative

    async def ingest_channel(
        self,
        *,
        channel: Channel,
        options: IngestionOptions,
        on_post_saved: OnPostSaved | None = None,
    ) -> IngestionResult:
        peer = self._build_peer(channel)
        try:
            entity = await self._tg_client.get_entity(peer)
        except FloodWaitError:
            return IngestionResult(
                channel_id=channel.id,
                channel_username=channel.username,
                processed_posts=0,
                stopped_reason="flood_wait_on_get_entity",
            )
        except Exception:
            return IngestionResult(
                channel_id=channel.id,
                channel_username=channel.username,
                processed_posts=0,
                stopped_reason="entity_error",
            )

        processed = 0
        sleep_counter = 0
        seen_grouped_ids: set[int] = set()

        try:
            async for raw_msg in self._tg_client.iter_messages(entity):
                if processed >= options.max_posts:
                    return IngestionResult(channel.id, channel.username, processed, "max_posts_reached")
                if getattr(raw_msg, "date", None) is None:
                    continue

                msg = raw_msg
                grouped_id = getattr(msg, "grouped_id", None)
                if options.resolve_album_representative and isinstance(grouped_id, int):
                    if grouped_id in seen_grouped_ids:
                        continue
                    msg = await self._pick_album_representative_message(entity, msg)
                    seen_grouped_ids.add(grouped_id)

                if options.since_utc is not None and msg.date < options.since_utc:
                    return IngestionResult(channel.id, channel.username, processed, "before_since")
                if options.until_utc is not None and msg.date >= options.until_utc:
                    continue
                if options.min_tg_message_id_exclusive and int(msg.id or 0) <= options.min_tg_message_id_exclusive:
                    return IngestionResult(channel.id, channel.username, processed, "already_ingested")

                comments_count = extract_comments_count(msg)
                if comments_count < options.min_replies:
                    continue

                async with self._session_factory() as session:
                    parent_tg_message_id = extract_parent_tg_message_id(msg)
                    existing = await self._get_post_by_channel_msg(
                        session=session,
                        channel_id=channel.id,
                        tg_message_id=msg.id,
                    )
                    if existing is not None and options.stop_on_existing_post:
                        await session.commit()
                        return IngestionResult(channel.id, channel.username, processed, "already_ingested")

                    parent_post_id: int | None = None
                    if isinstance(parent_tg_message_id, int):
                        parent_post = await self._ensure_parent_post(
                            session=session,
                            channel=channel,
                            entity=entity,
                            parent_tg_message_id=parent_tg_message_id,
                        )
                        if parent_post is not None:
                            parent_post_id = parent_post.id

                    post = await self._upsert_post(
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

                    if on_post_saved is not None:
                        await on_post_saved(
                            session,
                            post,
                            IngestionContext(
                                channel=channel,
                                entity=entity,
                                message=msg,
                                parent_tg_message_id=parent_tg_message_id,
                                comments_count=comments_count,
                                parent_post_id=parent_post_id,
                            ),
                        )

                    await session.commit()

                processed += 1
                sleep_counter += 1
                if sleep_counter >= options.sleep_every:
                    sleep_counter = 0
                    await polite_sleep(options.sleep_base_sec, options.sleep_jitter_sec)
        except FloodWaitError:
            return IngestionResult(channel.id, channel.username, processed, "flood_wait_on_iter_messages")

        return IngestionResult(channel.id, channel.username, processed, None)
