from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telethon.errors import FloodWaitError, RPCError
from telethon.errors.rpcerrorlist import MsgIdInvalidError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser, User
from sqlalchemy import select

from agent.reporter import TgReportProject
from client import client
from config import settings
from db.models import Channel, Post
from db.session import AsyncSessionLocal
from services.ingest import (
    set_post_comments_count,
    set_post_involvement,
    upsert_comment,
    upsert_post,
    upsert_report,
)
from services.linker import link_post_to_graph, upsert_post_link

report_project = TgReportProject(
    llm_model="ollama/llama3:8b-instruct-q4_K_M",
)

POSTS_SLEEP_EVERY = 50
COMMENTS_SLEEP_EVERY = 50
LINK_REPLY_TO = "REPLY_TO"


def day_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


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


async def parse_channel_today(channel: Channel) -> None:
    await client.start()
    username = channel.username
    if username.startswith("id_") and username[3:].isdigit():
        peer = PeerChannel(int(username[3:]))
    else:
        peer = f"@{username}"

    try:
        entity = await client.get_entity(peer)
    except FloodWaitError as e:
        print(f"[{channel.username}] FloodWait {e.seconds}s on get_entity, skipping channel")
        await client.disconnect()
        return
    except Exception:
        print(f"Cannot resolve channel entity: {channel.username}")
        await client.disconnect()
        return

    await get_posts(channel, entity)


async def get_posts(channel: Channel, entity) -> None:
    start_utc, end_utc = day_bounds_utc(settings.tz)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            i = 0
            try:
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
                    if replies_count < 20:
                        continue

                    try:
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

                        comments, commenters_count, comments_count = await get_comments(
                            channel=channel,
                            session=session,
                            entity=entity,
                            message_id=msg.id,
                            post_id=post.id,
                        )

                        views = getattr(msg, "views", None)
                        involvement = None
                        if isinstance(views, int) and views > 0:
                            involvement = commenters_count / views

                        await set_post_comments_count(
                            session,
                            post_id=post.id,
                            comments_count=comments_count,
                        )
                        await set_post_involvement(
                            session,
                            post_id=post.id,
                            involvement=involvement,
                        )

                        try:
                            await link_post_to_graph(session, post=post)
                        except Exception as link_err:
                            print(f"[{channel.username}] linker warning for post_id={post.id}: {link_err!r}")

                        report_text = await report_project.generate_report(
                            channel=f"@{channel.username}",
                            post_id=post.id,
                            published_at_iso=msg.date.isoformat(),
                            post_text=msg.message or "",
                            comments=comments,
                            views=views,
                        )
                        await upsert_report(
                            session,
                            post_id=post.id,
                            status="ready",
                            content=report_text,
                        )
                        print(f"Saved post: channel=@{channel.username} tg_msg_id={msg.id} db_post_id={post.id}")
                    except Exception as e:
                        print(f"[{channel.username}] error saving post tg_msg_id={msg.id}: {e!r}")
                        continue

                    if i >= POSTS_SLEEP_EVERY:
                        i = 0
                        await polite_sleep(0.4, 0.6)
            except FloodWaitError as e:
                print(f"[{channel.username}] FloodWait {e.seconds}s during iter_messages, stopping channel")
                await client.disconnect()
                return


async def get_comments(channel: Channel, session, entity, message_id: int, post_id: int) -> tuple[list[str], int, int]:
    try:
        discussion = await client(GetDiscussionMessageRequest(peer=entity, msg_id=message_id))
    except MsgIdInvalidError:
        return [], 0, 0
    except FloodWaitError as e:
        print(f"[{channel.username}] FloodWait {e.seconds}s on GetDiscussionMessage, stopping channel")
        await client.disconnect()
        return [], 0, 0
    except RPCError:
        return [], 0, 0
    except Exception:
        return [], 0, 0

    if not discussion.chats or not discussion.messages:
        return [], 0, 0

    discussion_chat = discussion.chats[0]
    discussion_root = discussion.messages[0]

    comments: list[str] = []
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

            comments.append(c.message or "")

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
    except FloodWaitError as e:
        print(f"[{channel.username}] FloodWait {e.seconds}s during comments iter, stopping channel")
        await client.disconnect()
    except MsgIdInvalidError:
        pass

    return comments, len(commenters), comments_saved


async def main() -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Channel).where(Channel.is_active.is_(True)))
        channels = list(res.scalars().all())

    if not channels:
        print("No active channels in DB. Add one via: python -m scripts.add_channel @username")
        return

    for ch in channels:
        print(f"Parsing today for @{ch.username}...")
        await parse_channel_today(ch)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
