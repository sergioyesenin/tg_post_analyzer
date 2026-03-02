from __future__ import annotations

import asyncio
import random
from collections import deque

from telethon.errors import FloodWaitError, RPCError
from telethon.errors.rpcerrorlist import MsgIdInvalidError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from client import client as default_client
from db.models import Comment
from services.ingest import (
    set_post_comments_count,
    set_post_involvement,
    set_post_last_comments_scan_at,
    upsert_comment,
)
from services.queries import get_post_with_channel_by_post_id

COMMENTS_SLEEP_EVERY = 50


async def polite_sleep(base: float, jitter: float) -> None:
    await asyncio.sleep(base + random.random() * jitter)


async def update_post_comments(session: AsyncSession, post_id: int, tg_client=None) -> dict:
    tg_client = tg_client or default_client
    row = await get_post_with_channel_by_post_id(session, post_id)
    if row is None:
        return {"status": "not_found", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}

    post, channel = row

    if channel.username.startswith("id_") and channel.username[3:].isdigit():
        peer = PeerChannel(int(channel.username[3:]))
    else:
        peer = f"@{channel.username}"

    try:
        if not tg_client.is_connected():
            await tg_client.start()
        entity = await tg_client.get_entity(peer)
    except Exception as exc:
        return {
            "status": "entity_error",
            "post_id": post_id,
            "comments_saved": 0,
            "commenters_count": 0,
            "error": repr(exc),
        }

    existing_comments_count = int(
        await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == post.id)
        )
        or 0
    )

    telegram_replies_count = None
    try:
        head_msg = await tg_client.get_messages(entity, ids=post.tg_message_id)
        if isinstance(head_msg, list):
            head_msg = head_msg[0] if head_msg else None
        replies_obj = getattr(head_msg, "replies", None) if head_msg is not None else None
        replies_count = getattr(replies_obj, "replies", None) if replies_obj is not None else None
        if isinstance(replies_count, int) and replies_count >= 0:
            telegram_replies_count = replies_count
    except Exception:
        telegram_replies_count = None

    if isinstance(telegram_replies_count, int):
        if telegram_replies_count == 0:
            await set_post_last_comments_scan_at(session, post_id=post.id)
            return {
                "status": "no_discussion",
                "post_id": post.id,
                "comments_saved": existing_comments_count,
                "commenters_count": 0,
                "telegram_replies_count": telegram_replies_count,
            }
        if telegram_replies_count <= existing_comments_count:
            await set_post_last_comments_scan_at(session, post_id=post.id)
            return {
                "status": "unchanged",
                "post_id": post.id,
                "comments_saved": existing_comments_count,
                "commenters_count": 0,
                "telegram_replies_count": telegram_replies_count,
            }

    try:
        discussion = await tg_client(GetDiscussionMessageRequest(peer=entity, msg_id=post.tg_message_id))
    except MsgIdInvalidError:
        return {"status": "no_discussion", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}
    except FloodWaitError as e:
        return {"status": "flood_wait", "post_id": post_id, "wait_seconds": e.seconds, "comments_saved": 0, "commenters_count": 0}
    except RPCError:
        return {"status": "rpc_error", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}
    except Exception:
        return {"status": "discussion_error", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}

    if not discussion.chats or not discussion.messages:
        return {"status": "no_discussion", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}

    discussion_chat = discussion.chats[0]
    discussion_root = discussion.messages[0]

    existing_rows = await session.execute(
        select(Comment.tg_message_id, Comment.id, Comment.depth).where(Comment.post_id == post.id)
    )
    tg_to_comment_id: dict[int, int] = {}
    tg_to_depth: dict[int, int] = {}
    for tg_message_id, comment_id, depth in existing_rows.all():
        tg_to_comment_id[tg_message_id] = comment_id
        tg_to_depth[tg_message_id] = depth

    commenters: set[str] = set()
    comments_saved = 0
    k = 0

    queue: deque[tuple[int, int]] = deque([(discussion_root.id, -1)])
    seen_comment_ids: set[int] = set()

    try:
        while queue:
            parent_tg_message_id, parent_depth = queue.popleft()

            async for c in tg_client.iter_messages(discussion_chat, reply_to=parent_tg_message_id):
                if c.id in seen_comment_ids:
                    continue
                seen_comment_ids.add(c.id)
                k += 1

                if c.date is None:
                    continue

                author_id = None
                author_key_id = None
                from_id = getattr(c, "from_id", None)
                if isinstance(from_id, PeerUser):
                    author_id = from_id.user_id
                    author_key_id = f"id:{author_id}"

                author_username = None
                author_key_username = None
                is_bot = False
                try:
                    sender = await c.get_sender()
                    if isinstance(sender, User) and bool(sender.bot):
                        is_bot = True
                    author_username = getattr(sender, "username", None)
                    if author_username:
                        author_key_username = f"u:{author_username.lower()}"
                except Exception:
                    pass

                if is_bot:
                    continue

                reply_to = getattr(c, "reply_to", None)
                reply_to_msg_id = getattr(reply_to, "reply_to_msg_id", None) if reply_to is not None else None
                effective_parent_tg = reply_to_msg_id or parent_tg_message_id

                if effective_parent_tg == discussion_root.id:
                    depth = 0
                else:
                    parent_known_depth = tg_to_depth.get(effective_parent_tg, parent_depth)
                    depth = max(0, parent_known_depth + 1)

                if author_key_id:
                    commenters.add(author_key_id)
                if author_key_username:
                    commenters.add(author_key_username)

                saved_comment = await upsert_comment(
                    session,
                    channel_id=channel.id,
                    post_id=post.id,
                    tg_message_id=c.id,
                    parent_tg_message_id=effective_parent_tg,
                    parent_comment_id=tg_to_comment_id.get(effective_parent_tg),
                    thread_root_tg_message_id=discussion_root.id,
                    depth=depth,
                    date=c.date,
                    author_id=author_id,
                    author_username=author_username,
                    text=c.message,
                )
                tg_to_comment_id[c.id] = saved_comment.id
                tg_to_depth[c.id] = depth
                comments_saved += 1

                queue.append((c.id, depth))

                if k >= COMMENTS_SLEEP_EVERY:
                    k = 0
                    await polite_sleep(0.4, 0.6)
    except FloodWaitError as e:
        return {"status": "flood_wait", "post_id": post_id, "wait_seconds": e.seconds, "comments_saved": comments_saved, "commenters_count": len(commenters)}
    except MsgIdInvalidError:
        return {"status": "no_discussion", "post_id": post_id, "comments_saved": comments_saved, "commenters_count": len(commenters)}

    await set_post_comments_count(session, post_id=post.id, comments_count=comments_saved)

    involvement = None
    if isinstance(post.views, int) and post.views > 0:
        involvement = len(commenters) / post.views
    await set_post_involvement(session, post_id=post.id, involvement=involvement)
    await set_post_last_comments_scan_at(session, post_id=post.id)

    return {
        "status": "ok",
        "post_id": post.id,
        "comments_saved": comments_saved,
        "commenters_count": len(commenters),
        "involvement": involvement,
        "telegram_replies_count": telegram_replies_count,
    }
