from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from telethon.errors import FloodWaitError, RPCError
from telethon.errors.rpcerrorlist import MsgIdInvalidError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser, User

from client import client, ensure_telegram_client_started
from config import settings
from db.models import Channel, Post
from db.session import AsyncSessionLocal
from services.ingest import (
    set_post_comments_count,
    set_post_involvement,
    upsert_comment,
    upsert_post,
)
from services.linker import upsert_post_link

LINK_REPLY_TO = "REPLY_TO"
POSTS_SLEEP_EVERY = 50
COMMENTS_SLEEP_EVERY = 50


def yesterday_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    yesterday_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today_local = yesterday_local + timedelta(days=1)
    return yesterday_local.astimezone(timezone.utc), today_local.astimezone(timezone.utc)


async def polite_sleep(base: float, jitter: float) -> None:
    await asyncio.sleep(base + random.random() * jitter)


def extract_parent_tg_message_id(message) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        return None
    parent_tg_message_id = getattr(reply_to, "reply_to_msg_id", None)
    if isinstance(parent_tg_message_id, int) and parent_tg_message_id > 0:
        return parent_tg_message_id
    return None


async def get_post_by_channel_and_tg_message(
    *,
    session,
    channel_id: int,
    tg_message_id: int,
) -> Post | None:
    stmt = (
        select(Post)
        .where(Post.channel_id == channel_id)
        .where(Post.tg_message_id == tg_message_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_parent_post(
    *,
    session,
    channel: Channel,
    entity,
    parent_tg_message_id: int,
) -> Post | None:
    parent_post = await get_post_by_channel_and_tg_message(
        session=session,
        channel_id=channel.id,
        tg_message_id=parent_tg_message_id,
    )
    if parent_post is not None:
        return parent_post

    try:
        parent_msg = await client.get_messages(entity, ids=parent_tg_message_id)
    except Exception:
        return None

    if isinstance(parent_msg, list):
        parent_msg = parent_msg[0] if parent_msg else None
    if parent_msg is None or getattr(parent_msg, "id", None) is None or getattr(parent_msg, "date", None) is None:
        return None

    parent_replies_obj = getattr(parent_msg, "replies", None)
    parent_replies_count = getattr(parent_replies_obj, "replies", 0) if parent_replies_obj else 0
    parent_parent_tg_message_id = extract_parent_tg_message_id(parent_msg)
    parent_parent_post_id: int | None = None
    if isinstance(parent_parent_tg_message_id, int):
        parent_parent_post = await get_post_by_channel_and_tg_message(
            session=session,
            channel_id=channel.id,
            tg_message_id=parent_parent_tg_message_id,
        )
        if parent_parent_post is not None:
            parent_parent_post_id = parent_parent_post.id

    return await upsert_post(
        session,
        channel_id=channel.id,
        tg_message_id=parent_msg.id,
        parent_tg_message_id=parent_parent_tg_message_id,
        parent_post_id=parent_parent_post_id,
        date=parent_msg.date,
        text=parent_msg.message,
        views=getattr(parent_msg, "views", None),
        comments_count=int(parent_replies_count or 0),
        involvement=None,
    )


async def collect_comments_for_post(
    *,
    channel: Channel,
    session,
    entity,
    tg_message_id: int,
    post_id: int,
    original_message_date: datetime | None = None,
    fallback_window: int | None = None,
    fallback_max_seconds: int | None = None,
) -> dict:
    discussion = None
    discussion_msg_id: int | None = None
    discussion_error: str = ""

    fallback_window = fallback_window if fallback_window is not None else settings.DISCUSSION_FALLBACK_ID_WINDOW
    fallback_max_seconds = (
        fallback_max_seconds if fallback_max_seconds is not None else settings.DISCUSSION_FALLBACK_MAX_SECONDS
    )

    candidate_msg_ids = [tg_message_id]
    for delta in range(1, fallback_window + 1):
        candidate_msg_ids.append(tg_message_id - delta)
        candidate_msg_ids.append(tg_message_id + delta)

    for candidate_msg_id in candidate_msg_ids:
        if candidate_msg_id <= 0:
            continue
        try:
            candidate_msg = await client.get_messages(entity, ids=candidate_msg_id)
            if isinstance(candidate_msg, list):
                candidate_msg = candidate_msg[0] if candidate_msg else None
            if candidate_msg is None:
                continue

            candidate_date = getattr(candidate_msg, "date", None)
            if (
                original_message_date is not None
                and candidate_date is not None
                and abs((candidate_date - original_message_date).total_seconds()) > fallback_max_seconds
            ):
                continue

            candidate_discussion = await client(GetDiscussionMessageRequest(peer=entity, msg_id=candidate_msg_id))
            if candidate_discussion.chats and candidate_discussion.messages:
                discussion = candidate_discussion
                discussion_msg_id = candidate_msg_id
                break
        except MsgIdInvalidError:
            continue
        except FloodWaitError:
            return {"status": "flood_wait", "comments_saved": 0, "commenters_count": 0, "discussion_msg_id": None}
        except RPCError as exc:
            discussion_error = repr(exc)
            continue
        except Exception as exc:
            discussion_error = repr(exc)
            continue

    if discussion is None:
        return {
            "status": "no_discussion",
            "comments_saved": 0,
            "commenters_count": 0,
            "discussion_msg_id": None,
            "error": discussion_error,
        }

    discussion_chat = discussion.chats[0]
    discussion_root = discussion.messages[0]

    commenters: set[str] = set()
    comments_saved = 0
    k = 0

    try:
        async for c in client.iter_messages(discussion_chat, reply_to=discussion_root.id):
            k += 1
            if c.date is None:
                continue

            author_id = None
            from_id = getattr(c, "from_id", None)
            if isinstance(from_id, PeerUser):
                author_id = from_id.user_id
                commenters.add(f"id:{author_id}")

            author_username = None
            is_bot = False
            try:
                sender = await c.get_sender()
                if isinstance(sender, User) and bool(sender.bot):
                    is_bot = True
                author_username = getattr(sender, "username", None)
                if author_username:
                    commenters.add(f"u:{author_username.lower()}")
            except Exception:
                pass

            if is_bot:
                continue

            await upsert_comment(
                session,
                channel_id=channel.id,
                post_id=post_id,
                tg_message_id=c.id,
                parent_tg_message_id=discussion_root.id,
                parent_comment_id=None,
                thread_root_tg_message_id=discussion_root.id,
                depth=0,
                date=c.date,
                author_id=author_id,
                author_username=author_username,
                text=c.message,
            )
            comments_saved += 1

            if k >= COMMENTS_SLEEP_EVERY:
                k = 0
                await polite_sleep(0.4, 0.6)
    except FloodWaitError:
        return {
            "status": "flood_wait",
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "discussion_msg_id": discussion_msg_id,
        }
    except MsgIdInvalidError:
        return {
            "status": "no_discussion",
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "discussion_msg_id": discussion_msg_id,
        }
    except Exception as exc:
        return {
            "status": "comments_iter_error",
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "discussion_msg_id": discussion_msg_id,
            "error": repr(exc),
        }

    return {
        "status": "ok",
        "comments_saved": comments_saved,
        "commenters_count": len(commenters),
        "discussion_msg_id": discussion_msg_id,
    }
    


async def parse_channel_yesterday(channel: Channel) -> None:
    username = channel.username
    if username.startswith("id_") and username[3:].isdigit():
        peer = PeerChannel(int(username[3:]))
    else:
        peer = f"@{username}"

    try:
        entity = await client.get_entity(peer)
    except Exception:
        print(f"Cannot resolve channel entity: {channel.username}")
        return

    start_utc, end_utc = yesterday_bounds_utc(settings.tz)
    print(f"[{channel.username}] parsing window {start_utc.isoformat()}..{end_utc.isoformat()}")

    async with AsyncSessionLocal() as session:
        async with session.begin():
            i = 0
            async for msg in client.iter_messages(entity):
                i += 1
                if msg.date is None:
                    continue
                if msg.date < start_utc:
                    break
                if not (start_utc <= msg.date < end_utc):
                    continue

                replies_obj = getattr(msg, "replies", None)
                replies_count = getattr(replies_obj, "replies", 0) if replies_obj else 0
                parent_tg_message_id = extract_parent_tg_message_id(msg)
                parent_post_id: int | None = None
                if isinstance(parent_tg_message_id, int):
                    parent_post = await ensure_parent_post(
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
                    comments_count=int(replies_count or 0),
                    involvement=None,
                )

                if isinstance(parent_post_id, int):
                    await upsert_post_link(
                        session,
                        src_post_id=post.id,
                        dst_post_id=parent_post_id,
                        link_type=LINK_REPLY_TO,
                        confidence=1.0,
                        evidence={
                            "source": "telegram",
                            "kind": "native_reply",
                            "parent_tg_message_id": parent_tg_message_id,
                        },
                        model_version="telegram-native-v1",
                    )

                comments_result = await collect_comments_for_post(
                    channel=channel,
                    session=session,
                    entity=entity,
                    tg_message_id=msg.id,
                    post_id=post.id,
                    original_message_date=msg.date,
                )
                status = comments_result["status"]
                comments_saved = int(comments_result.get("comments_saved", 0))
                commenters_count = int(comments_result.get("commenters_count", 0))
                discussion_msg_id = comments_result.get("discussion_msg_id")

                final_comments_count = int(replies_count or 0)
                if status == "ok":
                    final_comments_count = comments_saved
                else:
                    print(
                        f"[{channel.username}] comments status={status} tg_msg_id={msg.id} "
                        f"discussion_msg_id={discussion_msg_id} "
                        f"keep_replies_count={final_comments_count} "
                        f"err={comments_result.get('error', '')}"
                    )

                await set_post_comments_count(session, post_id=post.id, comments_count=final_comments_count)

                views = getattr(msg, "views", None)
                involvement = None
                if isinstance(views, int) and views > 0:
                    involvement = commenters_count / views
                await set_post_involvement(session, post_id=post.id, involvement=involvement)

                print(
                    f"[{channel.username}] saved tg_msg_id={msg.id} db_post_id={post.id} "
                    f"parent={parent_tg_message_id} comments={final_comments_count} "
                    f"comments_status={status} discussion_msg_id={discussion_msg_id}"
                )

                if i >= POSTS_SLEEP_EVERY:
                    i = 0
                    await polite_sleep(0.4, 0.6)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Channel).where(Channel.is_active.is_(True)))
        channels = list(res.scalars().all())

    if not channels:
        print("No active channels in DB. Add channels first.")
        return

    await ensure_telegram_client_started(client, op_name="scripts.parse_yesterday.start")
    try:
        for channel in channels:
            await parse_channel_yesterday(channel)
    finally:
        await client.disconnect()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
