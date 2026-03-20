from __future__ import annotations

import asyncio
import logging
import random
from collections import deque

from telethon.errors import FloodWaitError, RPCError
from telethon.errors.rpcerrorlist import MsgIdInvalidError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from client import client as default_client
from client.telegram import ensure_telegram_client_started, with_session_lock_retry
from config import settings
from db.models import Comment
from services.ingest import (
    set_post_comments_count,
    set_post_involvement,
    set_post_last_comments_scan_at,
    set_post_views,
    upsert_comment,
)
from services.queries import get_post_with_channel_by_post_id

COMMENTS_SLEEP_EVERY = max(1, int(getattr(settings, "COMMENTS_SLEEP_EVERY", 10)))
COMMENTS_SLEEP_BASE_SEC = max(0.0, float(getattr(settings, "COMMENTS_SLEEP_BASE_SEC", 0.6)))
COMMENTS_SLEEP_JITTER_SEC = max(0.0, float(getattr(settings, "COMMENTS_SLEEP_JITTER_SEC", 0.4)))
logger = logging.getLogger(__name__)


async def polite_sleep(base: float, jitter: float) -> None:
    await asyncio.sleep(base + random.random() * jitter)

async def _resolve_discussion_with_fallback(
    *,
    tg_client,
    entity,
    tg_message_id: int,
    original_message_date,
) -> tuple[object | None, int | None, str | None, int | None]:
    fallback_window = max(0, int(settings.DISCUSSION_FALLBACK_ID_WINDOW))
    fallback_max_seconds = max(0, int(settings.DISCUSSION_FALLBACK_MAX_SECONDS))

    candidate_msg_ids = [tg_message_id]
    for delta in range(1, fallback_window + 1):
        candidate_msg_ids.append(tg_message_id - delta)
        candidate_msg_ids.append(tg_message_id + delta)

    last_error: str | None = None
    for candidate_msg_id in candidate_msg_ids:
        if candidate_msg_id <= 0:
            continue
        try:
            candidate_msg = await tg_client.get_messages(entity, ids=candidate_msg_id)
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

            candidate_discussion = await tg_client(GetDiscussionMessageRequest(peer=entity, msg_id=candidate_msg_id))
            if candidate_discussion and candidate_discussion.chats and candidate_discussion.messages:
                return candidate_discussion, candidate_msg_id, None, None
        except MsgIdInvalidError:
            continue
        except FloodWaitError as exc:
            return None, None, "flood_wait", int(exc.seconds)
        except RPCError as exc:
            last_error = repr(exc)
            continue
        except (AttributeError, TypeError, ValueError) as exc:
            logger.warning(
                "discussion candidate skipped op=resolve_discussion candidate_msg_id=%s err=%r",
                candidate_msg_id,
                exc,
            )
            last_error = repr(exc)
            continue
        except Exception as exc:
            logger.exception(
                "unexpected discussion resolution error marker=discussion_unexpected op=resolve_discussion candidate_msg_id=%s",
                candidate_msg_id,
            )
            last_error = repr(exc)
            continue

    if last_error:
        return None, None, "rpc_error", None
    return None, None, "no_discussion", None


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
        await ensure_telegram_client_started(tg_client, op_name="tg_client.start")
        entity = await with_session_lock_retry(lambda: tg_client.get_entity(peer), op_name="tg_client.get_entity")
    except FloodWaitError as exc:
        logger.warning(
            "flood wait while resolving entity op=resolve_entity post_id=%s channel_id=%s wait_seconds=%s",
            post_id,
            channel.id,
            int(exc.seconds),
        )
        return {
            "status": "flood_wait",
            "post_id": post_id,
            "wait_seconds": int(exc.seconds),
            "flood_source": "resolve_entity",
            "comments_saved": 0,
            "commenters_count": 0,
        }
    except RPCError as exc:
        logger.warning(
            "telegram rpc entity error op=resolve_entity post_id=%s channel_id=%s err=%r",
            post_id,
            channel.id,
            exc,
        )
        return {
            "status": "entity_error",
            "post_id": post_id,
            "comments_saved": 0,
            "commenters_count": 0,
            "error": repr(exc),
        }
    except (TypeError, ValueError, AttributeError) as exc:
        logger.warning(
            "entity validation error op=resolve_entity post_id=%s channel_id=%s err=%r",
            post_id,
            channel.id,
            exc,
        )
        return {
            "status": "entity_error",
            "post_id": post_id,
            "comments_saved": 0,
            "commenters_count": 0,
            "error": repr(exc),
        }
    except Exception as exc:
        logger.exception(
            "unexpected entity resolution failure marker=entity_unexpected op=resolve_entity post_id=%s channel_id=%s",
            post_id,
            channel.id,
        )
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
    head_views = None
    head_msg = None
    try:
        head_msg = await tg_client.get_messages(entity, ids=post.tg_message_id)
        if isinstance(head_msg, list):
            head_msg = head_msg[0] if head_msg else None
        replies_obj = getattr(head_msg, "replies", None) if head_msg is not None else None
        replies_count = getattr(replies_obj, "replies", None) if replies_obj is not None else None
        if isinstance(replies_count, int) and replies_count >= 0:
            telegram_replies_count = replies_count
        current_views = getattr(head_msg, "views", None) if head_msg is not None else None
        if isinstance(current_views, int) and current_views >= 0:
            head_views = current_views
    except FloodWaitError as exc:
        logger.warning(
            "flood wait while loading head message op=load_head_message post_id=%s channel_id=%s wait_seconds=%s",
            post.id,
            channel.id,
            int(exc.seconds),
        )
        return {
            "status": "flood_wait",
            "post_id": post_id,
            "wait_seconds": int(exc.seconds),
            "flood_source": "head_message",
            "comments_saved": 0,
            "commenters_count": 0,
        }
    except (RPCError, MsgIdInvalidError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "head message probe failed op=load_head_message post_id=%s channel_id=%s err=%r",
            post.id,
            channel.id,
            exc,
        )
        telegram_replies_count = None
    except Exception:
        logger.exception(
            "unexpected head message failure marker=head_message_unexpected op=load_head_message post_id=%s channel_id=%s",
            post.id,
            channel.id,
        )
        telegram_replies_count = None

    is_album = bool(getattr(head_msg, "grouped_id", None)) if head_msg is not None else False

    if isinstance(telegram_replies_count, int):
        if telegram_replies_count != existing_comments_count and isinstance(head_views, int):
            await set_post_views(session, post_id=post.id, views=head_views)
            post.views = head_views

        if (
            not is_album
            and telegram_replies_count > 0
            and telegram_replies_count <= existing_comments_count
        ):
            await set_post_last_comments_scan_at(session, post_id=post.id)
            return {
                "status": "unchanged",
                "post_id": post.id,
                "comments_saved": existing_comments_count,
                "commenters_count": 0,
                "telegram_replies_count": telegram_replies_count,
            }

    discussion, discussion_msg_id, discussion_status, wait_seconds, discussion_source_msg_id = (
    await _resolve_discussion_for_post_or_album(
        tg_client=tg_client,
        entity=entity,
        head_msg=head_msg,
    )
)
    if discussion is None:
        if discussion_status == "flood_wait":
            return {
                "status": "flood_wait",
                "post_id": post_id,
                "wait_seconds": int(wait_seconds or 0),
                "flood_source": "resolve_discussion",
                "comments_saved": 0,
                "commenters_count": 0,
            }
        if discussion_status == "rpc_error":
            return {"status": "rpc_error", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}
        if discussion_status == "no_discussion":
            if isinstance(telegram_replies_count, int) and telegram_replies_count > 0:
                return {
                    "status": "discussion_error",
                    "post_id": post_id,
                    "comments_saved": 0,
                    "commenters_count": 0,
                    "telegram_replies_count": telegram_replies_count,
                    "error": "discussion_not_resolved_with_positive_replies",
                }
            return {"status": "no_discussion", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}
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
    sender_meta_cache: dict[int, tuple[bool, str | None]] = {}
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
                sender = getattr(c, "sender", None)
                if isinstance(from_id, PeerUser) and isinstance(author_id, int):
                    cached = sender_meta_cache.get(author_id)
                    if cached is not None:
                        is_bot, author_username = cached
                    elif isinstance(sender, User):
                        is_bot = bool(sender.bot)
                        author_username = getattr(sender, "username", None)
                        sender_meta_cache[author_id] = (is_bot, author_username)
                elif isinstance(sender, User):
                    is_bot = bool(sender.bot)
                    author_username = getattr(sender, "username", None)

                if author_username:
                    author_key_username = f"u:{author_username.lower()}"

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

                comment_replies_obj = getattr(c, "replies", None)
                nested_replies_count = getattr(comment_replies_obj, "replies", 0) if comment_replies_obj is not None else 0
                if isinstance(nested_replies_count, int) and nested_replies_count > 0:
                    queue.append((c.id, depth))

                if k >= COMMENTS_SLEEP_EVERY:
                    k = 0
                    await polite_sleep(COMMENTS_SLEEP_BASE_SEC, COMMENTS_SLEEP_JITTER_SEC)
    except FloodWaitError as e:
        return {
            "status": "flood_wait",
            "post_id": post_id,
            "wait_seconds": e.seconds,
            "flood_source": "iter_comments",
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
        }
    except MsgIdInvalidError:
        return {"status": "no_discussion", "post_id": post_id, "comments_saved": comments_saved, "commenters_count": len(commenters)}
    except RPCError as exc:
        logger.warning(
            "telegram rpc while iterating comments op=iter_comments post_id=%s channel_id=%s err=%r",
            post_id,
            channel.id,
            exc,
        )
        return {
            "status": "rpc_error",
            "post_id": post_id,
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "error": repr(exc),
        }
    except Exception:
        logger.exception(
            "unexpected comments iteration failure marker=iter_comments_unexpected op=iter_comments post_id=%s channel_id=%s",
            post_id,
            channel.id,
        )
        return {
            "status": "discussion_error",
            "post_id": post_id,
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "error": "unexpected_iter_comments_error",
        }

    await set_post_comments_count(session, post_id=post.id, comments_count=comments_saved)

    involvement = None
    if isinstance(post.views, int) and post.views > 0:
        involvement = len(commenters) / post.views
    await set_post_involvement(session, post_id=post.id, involvement=involvement)
    await set_post_last_comments_scan_at(session, post_id=post.id)

    return {
        "status": "ok",
        "post_id": post.id,
        "discussion_msg_id": discussion_msg_id,
        "comments_saved": comments_saved,
        "commenters_count": len(commenters),
        "involvement": involvement,
        "telegram_replies_count": telegram_replies_count,
    }

async def _resolve_discussion_for_post_or_album(
    tg_client,
    entity,
    head_msg,
):
    if head_msg is None:
        return None, None, "no_discussion", None, None
    candidate_ids = [head_msg.id]

    if getattr(head_msg, "grouped_id", None):
        candidate_ids = await _collect_album_message_ids(
            tg_client=tg_client,
            entity=entity,
            head_msg=head_msg,
        )

    last_status = "no_discussion"
    last_wait_seconds = 0

    for candidate_msg_id in candidate_ids:
        discussion, discussion_msg_id, status, wait_seconds = await _resolve_discussion_with_fallback(
            tg_client=tg_client,
            entity=entity,
            tg_message_id=candidate_msg_id,
            original_message_date=getattr(head_msg, "date", None),
        )

        if discussion is not None:
            return discussion, discussion_msg_id, status, wait_seconds, candidate_msg_id

        if status == "flood_wait":
            return None, None, status, wait_seconds, candidate_msg_id

        last_status = status
        last_wait_seconds = wait_seconds or 0

    return None, None, last_status, last_wait_seconds, None

async def _collect_album_message_ids(
    tg_client,
    entity,
    head_msg,
    window_before: int = 10,
    window_after: int = 10,
) -> list[int]:
    grouped_id = getattr(head_msg, "grouped_id", None)
    if not grouped_id:
        return [head_msg.id]

    ids: list[int] = []
    seen: set[int] = set()

    # Берём небольшой диапазон вокруг head_msg.id.
    # У альбома сообщения обычно идут подряд.
    min_id = max(0, head_msg.id - window_before - 1)
    max_id = head_msg.id + window_after + 1

    msgs = await tg_client.get_messages(
        entity,
        min_id=min_id,
        max_id=max_id,
        limit=window_before + window_after + 5,
    )

    for m in msgs:
        if not m:
            continue
        if getattr(m, "grouped_id", None) == grouped_id:
            if m.id not in seen:
                seen.add(m.id)
                ids.append(m.id)

    # На всякий случай гарантируем наличие исходного сообщения
    if head_msg.id not in seen:
        ids.append(head_msg.id)

    ids.sort()
    return ids