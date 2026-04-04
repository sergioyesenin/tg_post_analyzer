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
        self._hydrated_parent_tg_message_ids: set[int] = set()

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

        previous_parent_state = {
            "date": getattr(parent_post, "date", None) if parent_post is not None else None,
            "text": getattr(parent_post, "text", None) if parent_post is not None else None,
            "views": getattr(parent_post, "views", None) if parent_post is not None else None,
            "comments_count": getattr(parent_post, "comments_count", None) if parent_post is not None else None,
        } if parent_post is not None else None

        parent_post = await self._upsert_post(
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
        if previous_parent_state is not None and (
            previous_parent_state["date"] != parent_msg.date
            or previous_parent_state["text"] != parent_msg.message
            or previous_parent_state["views"] != getattr(parent_msg, "views", None)
            or previous_parent_state["comments_count"] != extract_comments_count(parent_msg)
        ):
            from services.reporting import sync_post_report_staleness

            await sync_post_report_staleness(
                session,
                post_id=parent_post.id,
                source="ingestion.parent_post_update",
                dependency_type="post_ingestion",
                dependency_id=parent_post.id,
            )
        self._hydrated_parent_tg_message_ids.add(int(parent_msg.id))
        return parent_post

    async def _pick_album_representative_message(self, entity, message):
        grouped_id = getattr(message, "grouped_id", None)
        if not isinstance(grouped_id, int):
            return message

        grouped_messages: list[Any] = []
        seen_ids: set[int] = set()
        radius = 10
        expansion_steps = 6
        head_id = int(message.id)

        async def _fetch_into(candidate_ids: list[int]) -> bool:
            new_candidate_ids = [msg_id for msg_id in candidate_ids if msg_id > 0]
            if not new_candidate_ids:
                return False

            try:
                nearby = await self._tg_client.get_messages(entity, ids=new_candidate_ids)
            except Exception:
                return False

            if not isinstance(nearby, list):
                nearby = [nearby] if nearby is not None else []

            found_new = False
            for item in nearby:
                if item is None:
                    continue
                if getattr(item, "grouped_id", None) != grouped_id:
                    continue
                if getattr(item, "date", None) is None:
                    continue
                item_id = getattr(item, "id", None)
                if not isinstance(item_id, int) or item_id <= 0 or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                grouped_messages.append(item)
                found_new = True
            return found_new

        found_new = await _fetch_into([msg_id for msg_id in range(head_id - radius, head_id + radius + 1) if msg_id > 0])

        for step in range(1, expansion_steps + 1):
            left_end = head_id - radius * (step - 1)
            left_start = max(1, head_id - radius * step)
            right_start = head_id + radius * (step - 1) + 1
            right_end = head_id + radius * step
            found_left = await _fetch_into([msg_id for msg_id in range(left_start, left_end)])
            found_right = await _fetch_into([msg_id for msg_id in range(right_start, right_end + 1)])
            if not found_new and not found_left and not found_right:
                break
            found_new = found_left or found_right

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
        self._hydrated_parent_tg_message_ids = set()
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
                    previous_post_state = {
                        "date": getattr(existing, "date", None) if existing is not None else None,
                        "text": getattr(existing, "text", None) if existing is not None else None,
                        "views": getattr(existing, "views", None) if existing is not None else None,
                        "comments_count": getattr(existing, "comments_count", None) if existing is not None else None,
                    } if existing is not None else None
                    if (
                        existing is not None
                        and options.stop_on_existing_post
                        and int(msg.id) not in self._hydrated_parent_tg_message_ids
                    ):
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
                    if previous_post_state is not None and (
                        previous_post_state["date"] != msg.date
                        or previous_post_state["text"] != msg.message
                        or previous_post_state["views"] != getattr(msg, "views", None)
                        or previous_post_state["comments_count"] != comments_count
                    ):
                        from services.reporting import sync_post_report_staleness

                        await sync_post_report_staleness(
                            session,
                            post_id=post.id,
                            source="ingestion.post_update",
                            dependency_type="post_ingestion",
                            dependency_id=post.id,
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
