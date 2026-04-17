from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from datetime import datetime, timedelta, timezone

from telethon.errors import FloodWaitError, RPCError
from telethon.errors.rpcerrorlist import MsgIdInvalidError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser, User
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from client import client as default_client
from client.telegram import ensure_telegram_client_started, with_session_lock_retry
from config import settings
from db.models import Comment
from services.ingest import (
    set_post_commenters,
    set_post_comments_count,
    set_post_involvement,
    set_post_last_comments_scan_at,
    set_post_long_comments,
    set_post_reactions_json,
    set_post_views,
    upsert_comment,
)
from services.involvement import compute_involvement, count_long_comments
from services.queries import get_post_with_channel_by_post_id
from services.settings_defaults import get_default_setting
from services.settings_store import get_all_settings
from utils.serialization import to_jsonable

logger = logging.getLogger(__name__)


def _parse_iso_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_recent_reactions_payload(payload: dict | None, *, now: datetime, ttl_seconds: int) -> bool:
    if ttl_seconds <= 0 or not isinstance(payload, dict):
        return False
    collected_at = _parse_iso_datetime(payload.get("collected_at"))
    if collected_at is None:
        return False
    return (now - collected_at).total_seconds() < ttl_seconds


def _comment_reactions_resume_counts(payload: dict | None) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return 0, 0
    comment_meta = payload.get("comment_reactions")
    if not isinstance(comment_meta, dict):
        return 0, 0
    try:
        comments_scanned = max(0, int(comment_meta.get("comments_scanned") or 0))
    except (TypeError, ValueError):
        comments_scanned = 0
    try:
        visible = max(0, int(comment_meta.get("comments_with_visible_reactions") or 0))
    except (TypeError, ValueError):
        visible = 0
    return comments_scanned, visible


def _comment_reactions_status(*, is_complete: bool, comments_scanned: int, comments_with_visible_reactions: int) -> str:
    if not is_complete:
        return "partial"
    if comments_scanned <= 0 or comments_with_visible_reactions <= 0:
        return "no_reactions"
    return "complete"


async def polite_sleep(base: float, jitter: float) -> None:
    await asyncio.sleep(base + random.random() * jitter)


async def _load_comments_settings(session: AsyncSession) -> dict:
    try:
        effective_settings = await get_all_settings(session)
    except Exception:
        logger.warning("Falling back to canonical comments settings defaults.", exc_info=True)
        return {}
    return effective_settings.get("comments", {})


def _build_commenter_key(author_id: int | None, author_username: str | None) -> str | None:
    if isinstance(author_id, int):
        return f"id:{author_id}"
    if isinstance(author_username, str) and author_username:
        return f"u:{author_username.lower()}"
    return None


def _build_existing_commenter_keys(rows: list[tuple[int | None, str | None]]) -> set[str]:
    commenters: set[str] = set()
    for author_id, author_username in rows:
        commenter_key = _build_commenter_key(author_id, author_username)
        if commenter_key is not None:
            commenters.add(commenter_key)
    return commenters


def _legacy_comment_peer_id(channel_id: int) -> int:
    return int(channel_id)


def _thread_entity_debug_fields(entity: object | None) -> dict[str, object | None]:
    if entity is None:
        return {
            "entity_type": None,
            "entity_id": None,
            "entity_username": None,
            "entity_title": None,
            "entity_broadcast": None,
            "entity_megagroup": None,
            "entity_gigagroup": None,
            "entity_forum": None,
            "entity_access_hash_present": None,
        }
    access_hash = getattr(entity, "access_hash", None)
    return {
        "entity_type": type(entity).__name__,
        "entity_id": getattr(entity, "id", None),
        "entity_username": getattr(entity, "username", None),
        "entity_title": getattr(entity, "title", None),
        "entity_broadcast": getattr(entity, "broadcast", None),
        "entity_megagroup": getattr(entity, "megagroup", None),
        "entity_gigagroup": getattr(entity, "gigagroup", None),
        "entity_forum": getattr(entity, "forum", None),
        "entity_access_hash_present": bool(access_hash),
    }


def _filter_top_level_candidates(
    items: list[object],
    *,
    root_id: int,
    post_date: datetime,
) -> tuple[list[object], dict[str, int]]:
    filtered: list[object] = []
    no_date = 0
    too_old = 0
    root_echo = 0

    threshold = post_date - timedelta(days=1)
    for item in items:
        item_date = getattr(item, "date", None)
        item_id = getattr(item, "id", None)
        if item_date is None:
            no_date += 1
            continue
        if item_date < threshold:
            too_old += 1
            continue
        if item_id == root_id:
            root_echo += 1
            continue
        filtered.append(item)

    return filtered, {
        "raw": len(items),
        "kept": len(filtered),
        "dropped_no_date": no_date,
        "dropped_too_old": too_old,
        "dropped_root_echo": root_echo,
    }


async def _load_persisted_comment_snapshot_metrics(session: AsyncSession, *, post_id: int) -> tuple[int, int, int]:
    rows = (
        await session.execute(
            select(Comment.author_id, Comment.author_username, Comment.text).where(Comment.post_id == post_id)
        )
    ).all()
    commenter_keys = _build_existing_commenter_keys([(author_id, author_username) for author_id, author_username, _text in rows])
    long_comments = count_long_comments([text for _author_id, _author_username, text in rows])
    return len(rows), len(commenter_keys), long_comments


def _log_involvement_metric_anomalies(
    *,
    post_id: int,
    views: int | None,
    comments_count: int,
    commenters_count: int,
    long_comments_count: int,
) -> None:
    normalized_views = int(views or 0) if isinstance(views, int) else 0
    if normalized_views <= 0:
        logger.warning(
            "involvement_metrics_anomaly anomaly=views_non_positive post_id=%s views=%s comments_count=%s commenters=%s long_comments=%s",
            post_id,
            views,
            comments_count,
            commenters_count,
            long_comments_count,
        )
    if comments_count > 0 and commenters_count <= 0:
        logger.warning(
            "involvement_metrics_anomaly anomaly=comments_without_commenters post_id=%s views=%s comments_count=%s commenters=%s long_comments=%s",
            post_id,
            views,
            comments_count,
            commenters_count,
            long_comments_count,
        )
    if long_comments_count > comments_count:
        logger.warning(
            "involvement_metrics_anomaly anomaly=long_comments_overflow post_id=%s views=%s comments_count=%s commenters=%s long_comments=%s",
            post_id,
            views,
            comments_count,
            commenters_count,
            long_comments_count,
        )


async def _persist_post_engagement_metrics(
    session: AsyncSession,
    *,
    post_id: int,
    views: int | None,
    reactions_payload: dict | None,
    comments_count: int,
    commenters_count: int,
    long_comments_count: int,
) -> float:
    _log_involvement_metric_anomalies(
        post_id=post_id,
        views=views,
        comments_count=comments_count,
        commenters_count=commenters_count,
        long_comments_count=long_comments_count,
    )
    try:
        involvement = compute_involvement(
            views=views,
            comments_count=comments_count,
            commenters=commenters_count,
            long_comments=long_comments_count,
            reactions_payload=reactions_payload,
        )
        await set_post_comments_count(session, post_id=post_id, comments_count=comments_count)
        await set_post_commenters(session, post_id=post_id, commenters=commenters_count)
        await set_post_long_comments(session, post_id=post_id, long_comments=long_comments_count)
        await set_post_involvement(session, post_id=post_id, involvement=involvement)
        return involvement
    except Exception:
        logger.exception(
            "involvement_recalculation_failed post_id=%s views=%s comments_count=%s commenters=%s long_comments=%s",
            post_id,
            views,
            comments_count,
            commenters_count,
            long_comments_count,
        )
        raise


def _serialize_message_reactions(message, *, top_n: int) -> dict:
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return {
            "supported": True,
            "present": False,
            "state": "no_reactions",
            "results": [],
            "results_total_count": 0,
            "results_truncated": False,
            "recent_reactions_count": 0,
            "recent_reactions": [],
            "raw_type": None,
            "can_see_list": None,
            "reactions_as_tags": None,
            "min": None,
        }

    reaction_results = []
    for item in list(getattr(reactions, "results", []) or []):
        reaction_obj = getattr(item, "reaction", None)
        reaction_results.append(
            {
                "count": getattr(item, "count", None),
                "chosen_order": getattr(item, "chosen_order", None),
                "reaction_type": None if reaction_obj is None else type(reaction_obj).__name__,
                "reaction": None if reaction_obj is None else reaction_obj.to_dict(),
            }
        )

    reaction_results = sorted(
        reaction_results,
        key=lambda item: (-int(item.get("count") or 0), str(item.get("reaction_type") or "")),
    )
    limited_results = reaction_results[:top_n]
    recent = [item.to_dict() for item in list(getattr(reactions, "recent_reactions", []) or [])]
    return {
        "supported": True,
        "present": bool(reaction_results),
        "state": "available" if reaction_results else "no_reactions",
        "raw_type": type(reactions).__name__,
        "can_see_list": getattr(reactions, "can_see_list", None),
        "reactions_as_tags": getattr(reactions, "reactions_as_tags", None),
        "min": getattr(reactions, "min", None),
        "results": limited_results,
        "results_total_count": len(reaction_results),
        "results_truncated": len(limited_results) < len(reaction_results),
        "recent_reactions_count": len(recent),
        "recent_reactions": recent,
    }


def _build_comment_reactions_payload(*, message, collected_at, top_n: int) -> dict:
    return {
        "source": "telegram_refresh",
        "collected_at": collected_at.isoformat(),
        "is_complete": True,
        **_serialize_message_reactions(message, top_n=top_n),
    }


def _build_post_reactions_payload(
    *,
    message,
    collected_at,
    top_n: int,
    is_complete: bool,
    comment_status: str,
    comments_scanned: int,
    comments_with_visible_reactions: int,
    thread_entity_type: str | None = None,
    reason: str | None = None,
) -> dict:
    return {
        "source": "telegram_refresh",
        "collected_at": collected_at.isoformat(),
        "is_complete": bool(is_complete),
        "post_reactions": _serialize_message_reactions(message, top_n=top_n),
        "comment_reactions": {
            "source": "telegram_refresh",
            "collected_at": collected_at.isoformat(),
            "is_complete": bool(is_complete),
            "status": comment_status,
            "comments_scanned": int(comments_scanned),
            "comments_with_visible_reactions": int(comments_with_visible_reactions),
            "thread_entity_type": thread_entity_type,
            "reason": reason,
        },
    }


async def _reconcile_confirmed_comment_snapshot(
    session: AsyncSession,
    *,
    post_id: int,
    tg_peer_ids: set[int],
    thread_root_tg_message_id: int,
    live_comment_keys: set[tuple[int, int]],
) -> int:
    candidate_peer_ids = sorted({int(value) for value in tg_peer_ids if isinstance(value, int) and value > 0})
    if not candidate_peer_ids or not isinstance(thread_root_tg_message_id, int) or thread_root_tg_message_id <= 0:
        return 0

    existing_rows = await session.execute(
        select(Comment.id, Comment.tg_peer_id, Comment.tg_message_id).where(
            Comment.post_id == post_id,
            Comment.tg_peer_id.in_(candidate_peer_ids),
            Comment.thread_root_tg_message_id == thread_root_tg_message_id,
        )
    )
    stale_comment_row_ids = [
        int(comment_id)
        for comment_id, tg_peer_id, tg_message_id in existing_rows.all()
        if (
            isinstance(comment_id, int)
            and (int(tg_peer_id), int(tg_message_id)) not in live_comment_keys
        )
    ]
    if not stale_comment_row_ids:
        return 0

    await session.execute(delete(Comment).where(Comment.id.in_(stale_comment_row_ids)))
    return len(stale_comment_row_ids)

async def _resolve_discussion_with_fallback(
    *,
    tg_client,
    entity,
    tg_message_id: int,
    original_message_id: int,
    original_message_date,
    original_message_text,
    original_grouped_id,
    fallback_window: int,
    fallback_max_seconds: int,
) -> tuple[object | None, int | None, str | None, int | None, int | None]:
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

            candidate_real_id = getattr(candidate_msg, "id", None)
            if not isinstance(candidate_real_id, int) or candidate_real_id <= 0:
                continue

            candidate_grouped_id = getattr(candidate_msg, "grouped_id", None)
            if candidate_msg_id != original_message_id:
                if original_grouped_id:
                    if candidate_grouped_id != original_grouped_id:
                        logger.debug(
                            "discussion fallback candidate rejected by album identity requested_msg_id=%s candidate_msg_id=%s original_grouped_id=%s candidate_grouped_id=%s",
                            original_message_id,
                            candidate_msg_id,
                            original_grouped_id,
                            candidate_grouped_id,
                        )
                        continue
                else:
                    if (
                        getattr(candidate_msg, "date", None) != original_message_date
                        or getattr(candidate_msg, "message", None) != original_message_text
                    ):
                        logger.debug(
                            "discussion fallback candidate rejected by non_album identity requested_msg_id=%s candidate_msg_id=%s",
                            original_message_id,
                            candidate_msg_id,
                        )
                        continue

            candidate_date = getattr(candidate_msg, "date", None)
            if (
                original_message_date is not None
                and candidate_date is not None
                and abs((candidate_date - original_message_date).total_seconds()) > fallback_max_seconds
            ):
                continue

            candidate_discussion = await tg_client(GetDiscussionMessageRequest(peer=entity, msg_id=candidate_msg_id))
            discussion_messages = getattr(candidate_discussion, "messages", None) if candidate_discussion is not None else None
            discussion_chats = getattr(candidate_discussion, "chats", None) if candidate_discussion is not None else None
            discussion_root = discussion_messages[0] if discussion_messages else None
            discussion_root_id = getattr(discussion_root, "id", None)

            if (
                candidate_discussion
                and discussion_chats
                and discussion_messages
                and isinstance(discussion_root_id, int)
                and discussion_root_id > 0
            ):
                return candidate_discussion, candidate_msg_id, None, None, candidate_real_id
        except MsgIdInvalidError:
            continue
        except FloodWaitError as exc:
            return None, None, "flood_wait", int(exc.seconds), None
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
        return None, None, "rpc_error", None, None
    return None, None, "no_discussion", None, None

async def _load_top_level_thread_comments(
    tg_client,
    *,
    entity,
    discussion_chat,
    discussion_root,
    discussion_msg_id,
    discussion_source_msg_id,
    head_msg,
    post_date,
):
    discussion_chat_roots: list[int] = []
    source_entity_roots: list[int] = []
    successful_discussion_scans = 0
    successful_source_scans = 0
    scan_errors = 0
    discussion_chat_invalid_root = False

    seen_discussion: set[int] = set()
    seen_source: set[int] = set()

    discussion_root_id = getattr(discussion_root, "id", None)
    if isinstance(discussion_root_id, int) and discussion_root_id > 0:
        discussion_chat_roots.append(discussion_root_id)
        seen_discussion.add(discussion_root_id)

    for value in [
        discussion_source_msg_id,
        discussion_msg_id,
    ]:
        if isinstance(value, int) and value > 0 and value not in seen_source:
            seen_source.add(value)
            source_entity_roots.append(value)

    logger.debug(
        "thread root candidates discussion_chat_roots=%s source_entity_roots=%s",
        discussion_chat_roots,
        source_entity_roots,
    )
    discussion_debug = _thread_entity_debug_fields(discussion_chat)
    source_debug = _thread_entity_debug_fields(entity)

    # 1) linked discussion chat: only discussion_root.id
    for root_id in discussion_chat_roots:
        items = []
        try:
            async for c in tg_client.iter_messages(discussion_chat, reply_to=root_id):
                items.append(c)
            successful_discussion_scans += 1
        except FloodWaitError:
            raise
        except MsgIdInvalidError:
            discussion_chat_invalid_root = True
            scan_errors += 1
            logger.warning(
                "top-level scan invalid discussion root_id=%s chat_id=%s discussion_msg_id=%s discussion_source_msg_id=%s",
                root_id,
                getattr(discussion_chat, "id", None),
                discussion_msg_id,
                discussion_source_msg_id,
            )
            items = []
        except RPCError as exc:
            scan_errors += 1
            logger.warning(
                "top-level scan rpc_error in discussion chat root_id=%s chat_id=%s discussion_msg_id=%s discussion_source_msg_id=%s err_type=%s err=%r",
                root_id,
                getattr(discussion_chat, "id", None),
                discussion_msg_id,
                discussion_source_msg_id,
                type(exc).__name__,
                exc,
            )
            items = []
        except Exception:
            scan_errors += 1
            logger.exception(
                "top-level scan failed in discussion chat root_id=%s chat_id=%s",
                root_id,
                getattr(discussion_chat, "id", None),
            )
            items = []

        logger.debug(
            "top-level scan discussion_chat root_id=%s found=%s",
            root_id,
            len(items),
        )

        # sanity filter: comments must not be older than the post itself
        filtered, filter_stats = _filter_top_level_candidates(items, root_id=root_id, post_date=post_date)

        logger.debug(
            "top-level scan discussion_chat root_id=%s filtered=%s dropped_no_date=%s dropped_too_old=%s dropped_root_echo=%s",
            root_id,
            filter_stats["kept"],
            filter_stats["dropped_no_date"],
            filter_stats["dropped_too_old"],
            filter_stats["dropped_root_echo"],
        )

        if items and not filtered:
            logger.warning(
                "top-level scan returned only non-persistable items in discussion chat "
                "root_id=%s raw=%s dropped_no_date=%s dropped_too_old=%s dropped_root_echo=%s "
                "discussion_msg_id=%s discussion_source_msg_id=%s post_date=%s discussion_chat=%s",
                root_id,
                filter_stats["raw"],
                filter_stats["dropped_no_date"],
                filter_stats["dropped_too_old"],
                filter_stats["dropped_root_echo"],
                discussion_msg_id,
                discussion_source_msg_id,
                post_date.isoformat() if isinstance(post_date, datetime) else post_date,
                discussion_debug,
            )

        if filtered:
            return discussion_chat, root_id, filtered

    source_fallback_confirmed = discussion_chat_invalid_root and bool(source_entity_roots)
    if source_fallback_confirmed:
        for root_id in source_entity_roots:
            items = []
            try:
                async for c in tg_client.iter_messages(entity, reply_to=root_id):
                    items.append(c)
                successful_source_scans += 1
            except FloodWaitError:
                raise
            except RPCError as exc:
                scan_errors += 1
                logger.warning(
                    "top-level scan rpc_error in source entity root_id=%s discussion_msg_id=%s discussion_source_msg_id=%s err_type=%s err=%r",
                    root_id,
                    discussion_msg_id,
                    discussion_source_msg_id,
                    type(exc).__name__,
                    exc,
                )
                items = []
            except Exception:
                scan_errors += 1
                logger.exception(
                    "top-level scan failed in source entity root_id=%s",
                    root_id,
                )
                items = []

            logger.debug(
                "top-level scan source entity root_id=%s found=%s",
                root_id,
                len(items),
            )

            filtered, filter_stats = _filter_top_level_candidates(items, root_id=root_id, post_date=post_date)

            logger.debug(
                "top-level scan source entity root_id=%s filtered=%s dropped_no_date=%s dropped_too_old=%s dropped_root_echo=%s",
                root_id,
                filter_stats["kept"],
                filter_stats["dropped_no_date"],
                filter_stats["dropped_too_old"],
                filter_stats["dropped_root_echo"],
            )

            if items and not filtered:
                logger.warning(
                    "source fallback scan returned only non-persistable items "
                    "root_id=%s raw=%s dropped_no_date=%s dropped_too_old=%s dropped_root_echo=%s "
                    "discussion_msg_id=%s discussion_source_msg_id=%s source_entity=%s",
                    root_id,
                    filter_stats["raw"],
                    filter_stats["dropped_no_date"],
                    filter_stats["dropped_too_old"],
                    filter_stats["dropped_root_echo"],
                    discussion_msg_id,
                    discussion_source_msg_id,
                    source_debug,
                )

            if filtered:
                return entity, root_id, filtered

    if successful_discussion_scans > 0 and discussion_chat_roots:
        return discussion_chat, discussion_chat_roots[0], []

    if source_fallback_confirmed and not discussion_chat_roots and successful_source_scans > 0 and source_entity_roots:
        return entity, source_entity_roots[0], []

    logger.warning(
        "top-level thread comments could not be confirmed discussion_msg_id=%s discussion_source_msg_id=%s discussion_root_id=%s "
        "scan_errors=%s successful_discussion_scans=%s successful_source_scans=%s discussion_chat_invalid_root=%s "
        "discussion_chat=%s source_entity=%s telegram_head_msg_id=%s",
        discussion_msg_id,
        discussion_source_msg_id,
        discussion_root_id,
        scan_errors,
        successful_discussion_scans,
        successful_source_scans,
        discussion_chat_invalid_root,
        discussion_debug,
        source_debug,
        getattr(head_msg, "id", None) if head_msg is not None else None,
    )
    return None, None, []


async def update_post_comments(session: AsyncSession, post_id: int, tg_client=None) -> dict:
    tg_client = tg_client or default_client
    comments_settings = await _load_comments_settings(session)
    comments_sleep_every = max(
        1,
        int(
            comments_settings.get(
                "sleep_every",
                getattr(settings, "COMMENTS_SLEEP_EVERY", get_default_setting("comments", "sleep_every")),
            )
        ),
    )
    comments_sleep_base_sec = max(
        0.0,
        float(
            comments_settings.get(
                "sleep_base_sec",
                getattr(settings, "COMMENTS_SLEEP_BASE_SEC", get_default_setting("comments", "sleep_base_sec")),
            )
        ),
    )
    comments_sleep_jitter_sec = max(
        0.0,
        float(
            comments_settings.get(
                "sleep_jitter_sec",
                getattr(settings, "COMMENTS_SLEEP_JITTER_SEC", get_default_setting("comments", "sleep_jitter_sec")),
            )
        ),
    )
    discussion_fallback_id_window = max(
        0,
        int(
            comments_settings.get(
                "discussion_fallback_id_window",
                getattr(
                    settings,
                    "DISCUSSION_FALLBACK_ID_WINDOW",
                    get_default_setting("comments", "discussion_fallback_id_window"),
                ),
            )
        ),
    )
    discussion_fallback_max_seconds = max(
        0,
        int(
            comments_settings.get(
                "discussion_fallback_max_seconds",
                getattr(
                    settings,
                    "DISCUSSION_FALLBACK_MAX_SECONDS",
                    get_default_setting("comments", "discussion_fallback_max_seconds"),
                ),
            )
        ),
    )
    reconciliation_enabled = bool(
        comments_settings.get(
            "reconciliation_enabled",
            getattr(settings, "COMMENTS_RECONCILIATION_ENABLED", get_default_setting("comments", "reconciliation_enabled")),
        )
    )
    album_discussion_expansion_steps = max(
        2,
        int(
            comments_settings.get(
                "album_discussion_expansion_steps",
                getattr(
                    settings,
                    "ALBUM_DISCUSSION_EXPANSION_STEPS",
                    get_default_setting("comments", "album_discussion_expansion_steps"),
                ),
            )
        ),
    )
    reactions_refresh_ttl_seconds = max(
        0,
        int(
            comments_settings.get(
                "reactions_refresh_ttl_seconds",
                getattr(
                    settings,
                    "COMMENTS_REACTIONS_REFRESH_TTL_SECONDS",
                    get_default_setting("comments", "reactions_refresh_ttl_seconds"),
                ),
            )
        ),
    )
    reactions_top_n = max(
        1,
        int(
            comments_settings.get(
                "reactions_top_n",
                getattr(settings, "COMMENTS_REACTIONS_TOP_N", get_default_setting("comments", "reactions_top_n")),
            )
        ),
    )

    row = await get_post_with_channel_by_post_id(session, post_id)
    if row is None:
        return {"status": "not_found", "post_id": post_id, "comments_saved": 0, "commenters_count": 0}

    post, channel = row
    reactions_collected_at = datetime.now(timezone.utc)

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
    legacy_peer_id = _legacy_comment_peer_id(channel.id)
    existing_peer_rows = await session.execute(
        select(Comment.tg_peer_id).where(Comment.post_id == post.id)
    )
    existing_peer_ids = {
        int(tg_peer_id)
        for (tg_peer_id,) in existing_peer_rows.all()
        if isinstance(tg_peer_id, int)
    }
    has_non_legacy_comment_peers = any(tg_peer_id != legacy_peer_id for tg_peer_id in existing_peer_ids)

    telegram_replies_count = None
    head_views = None
    head_msg = None

    async def persist_post_reactions(
        *,
        is_complete: bool,
        comment_status: str,
        comments_scanned: int = 0,
        comments_with_visible_reactions: int = 0,
        thread_entity_type: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        if head_msg is None:
            return None
        payload = _build_post_reactions_payload(
            message=head_msg,
            collected_at=reactions_collected_at,
            top_n=reactions_top_n,
            is_complete=is_complete,
            comment_status=comment_status,
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason=reason,
        )
        await set_post_reactions_json(session, post_id=post.id, reactions_json=payload)
        post.reactions_json = payload
        return payload

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
        if isinstance(head_views, int) and head_views != getattr(post, "views", None):
            await set_post_views(session, post_id=post.id, views=head_views)
            post.views = head_views

        # Для альбомов не выходим раньше времени, even if counts look unchanged.
        existing_reactions_payload = post.reactions_json if isinstance(getattr(post, "reactions_json", None), dict) else None
        recent_reactions_payload = _is_recent_reactions_payload(
            existing_reactions_payload,
            now=reactions_collected_at,
            ttl_seconds=reactions_refresh_ttl_seconds,
        )

        if (
            not is_album
            and telegram_replies_count >= 0
            and telegram_replies_count <= existing_comments_count
            and not has_non_legacy_comment_peers
            and recent_reactions_payload
            and (not reconciliation_enabled or telegram_replies_count == existing_comments_count)
        ):
            snapshot_comments_count, snapshot_commenters_count, snapshot_long_comments_count = (
                await _load_persisted_comment_snapshot_metrics(session, post_id=post.id)
            )
            involvement = await _persist_post_engagement_metrics(
                session,
                post_id=post.id,
                views=post.views,
                reactions_payload=existing_reactions_payload,
                comments_count=snapshot_comments_count,
                commenters_count=snapshot_commenters_count,
                long_comments_count=snapshot_long_comments_count,
            )
            await set_post_last_comments_scan_at(session, post_id=post.id)
            return {
                "status": "unchanged",
                "post_id": post.id,
                "comments_saved": snapshot_comments_count,
                "comments_count": snapshot_comments_count,
                "commenters_count": snapshot_commenters_count,
                "involvement": involvement,
                "views": post.views,
                "telegram_replies_count": telegram_replies_count,
            }

    discussion, discussion_msg_id, discussion_status, wait_seconds, discussion_source_msg_id = (
        await _resolve_discussion_for_post_or_album(
            tg_client=tg_client,
            entity=entity,
            head_msg=head_msg,
            fallback_window=discussion_fallback_id_window,
            fallback_max_seconds=discussion_fallback_max_seconds,
            album_discussion_expansion_steps=album_discussion_expansion_steps,
        )
    )

    if discussion is None:
        if discussion_status == "flood_wait":
            await persist_post_reactions(
                is_complete=False,
                comment_status="partial",
                reason="discussion_resolve_flood_wait",
            )
            return {
                "status": "flood_wait",
                "post_id": post_id,
                "wait_seconds": int(wait_seconds or 0),
                "flood_source": "resolve_discussion",
                "comments_saved": 0,
                "commenters_count": 0,
                "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                "discussion_source_msg_id": discussion_source_msg_id,
            }
        if discussion_status == "rpc_error":
            post_reactions_payload = await persist_post_reactions(
                is_complete=False,
                comment_status="unavailable",
                reason="discussion_resolve_rpc_error",
            )
            return {
                "status": "rpc_error",
                "post_id": post_id,
                "comments_saved": 0,
                "commenters_count": 0,
                "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                "discussion_source_msg_id": discussion_source_msg_id,
                "reactions": post_reactions_payload,
            }
        if discussion_status == "no_discussion":
            if isinstance(telegram_replies_count, int) and telegram_replies_count > 0:
                post_reactions_payload = await persist_post_reactions(
                    is_complete=False,
                    comment_status="unavailable",
                    reason="discussion_not_resolved_with_positive_replies",
                )
                logger.warning(
                    "discussion not resolved despite positive replies post_id=%s tg_message_id=%s telegram_replies_count=%s "
                    "entity=%s grouped_id=%s fallback_window=%s fallback_max_seconds=%s",
                    post.id,
                    post.tg_message_id,
                    telegram_replies_count,
                    _thread_entity_debug_fields(entity),
                    getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                    discussion_fallback_id_window,
                    discussion_fallback_max_seconds,
                )
                return {
                    "status": "discussion_error",
                    "post_id": post_id,
                    "comments_saved": 0,
                    "commenters_count": 0,
                    "telegram_replies_count": telegram_replies_count,
                    "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                    "discussion_source_msg_id": discussion_source_msg_id,
                    "error": "discussion_not_resolved_with_positive_replies",
                    "reactions": post_reactions_payload,
                }
            post_reactions_payload = await persist_post_reactions(
                is_complete=True,
                comment_status="no_reactions",
                reason="no_discussion",
            )
            snapshot_comments_count, snapshot_commenters_count, snapshot_long_comments_count = (
                await _load_persisted_comment_snapshot_metrics(session, post_id=post.id)
            )
            involvement = await _persist_post_engagement_metrics(
                session,
                post_id=post.id,
                views=post.views,
                reactions_payload=post_reactions_payload,
                comments_count=snapshot_comments_count,
                commenters_count=snapshot_commenters_count,
                long_comments_count=snapshot_long_comments_count,
            )
            await set_post_last_comments_scan_at(session, post_id=post.id)
            return {
                "status": "no_discussion",
                "post_id": post_id,
                "comments_saved": snapshot_comments_count,
                "commenters_count": snapshot_commenters_count,
                "comments_count": snapshot_comments_count,
                "involvement": involvement,
                "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                "discussion_source_msg_id": discussion_source_msg_id,
                "reactions": post_reactions_payload,
            }
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="unavailable",
            reason="discussion_resolution_failed",
        )
        return {
            "status": "discussion_error",
            "post_id": post_id,
            "comments_saved": 0,
            "commenters_count": 0,
            "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
            "discussion_source_msg_id": discussion_source_msg_id,
            "reactions": post_reactions_payload,
        }

    if not discussion.chats or not discussion.messages:
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="unavailable",
            reason="discussion_payload_empty",
        )
        return {
            "status": "no_discussion",
            "post_id": post_id,
            "comments_saved": 0,
            "commenters_count": 0,
            "reactions": post_reactions_payload,
        }

    discussion_chat = discussion.chats[0]
    discussion_root = discussion.messages[0]

    logger.debug(
        "discussion root resolved post_id=%s discussion_msg_id=%s discussion_root_id=%s discussion_chat_id=%s grouped_id=%s",
        post.id,
        discussion_msg_id,
        getattr(discussion_root, "id", None),
        getattr(discussion_chat, "id", None),
        getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
    )

    existing_rows = await session.execute(
        select(Comment.tg_peer_id, Comment.tg_message_id, Comment.id, Comment.depth).where(Comment.post_id == post.id)
    )
    tg_to_comment_id: dict[tuple[int, int], int] = {}
    tg_to_depth: dict[tuple[int, int], int] = {}
    for tg_peer_id, tg_message_id, comment_id, depth in existing_rows.all():
        if not isinstance(tg_peer_id, int):
            continue
        comment_key = (int(tg_peer_id), int(tg_message_id))
        tg_to_comment_id[comment_key] = comment_id
        tg_to_depth[comment_key] = depth

    commenters: set[str] = set()
    sender_meta_cache: dict[int, tuple[bool, str | None]] = {}
    comments_saved = 0
    comments_scanned, comments_with_visible_reactions = _comment_reactions_resume_counts(
        post.reactions_json if isinstance(getattr(post, "reactions_json", None), dict) else None
    )
    k = 0
    seen_comment_ids: set[tuple[int, int]] = set()
    persisted_comment_keys: set[tuple[int, int]] = set()
    top_level_seen = 0
    top_level_skipped_duplicate = 0
    top_level_skipped_no_date = 0
    top_level_skipped_bot = 0
    top_level_existing_rows_reused = 0
    nested_seen = 0
    nested_skipped_duplicate = 0
    nested_skipped_no_date = 0
    nested_skipped_bot = 0
    nested_existing_rows_reused = 0

    thread_entity, top_level_root_id, top_level_comments = await _load_top_level_thread_comments(
    tg_client=tg_client,
    entity=entity,
    discussion_chat=discussion_chat,
    discussion_root=discussion_root,
    discussion_msg_id=discussion_msg_id,
    discussion_source_msg_id=discussion_source_msg_id,
    head_msg=head_msg,
    post_date=post.date,
)

    if thread_entity is None:
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            reason="discussion_resolved_but_top_level_thread_unconfirmed",
        )
        logger.warning(
            "no top-level thread comments resolved post_id=%s discussion_msg_id=%s discussion_root_id=%s "
            "telegram_replies_count=%s discussion_chat=%s source_entity=%s",
            post.id,
            discussion_msg_id,
            getattr(discussion_root, "id", None),
            telegram_replies_count,
            _thread_entity_debug_fields(discussion_chat),
            _thread_entity_debug_fields(entity),
        )
        return {
            "status": "discussion_error",
            "post_id": post.id,
            "discussion_msg_id": discussion_msg_id,
            "discussion_source_msg_id": discussion_source_msg_id,
            "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
            "comments_saved": comments_saved,
            "comments_count": existing_comments_count,
            "commenters_count": len(commenters),
            "telegram_replies_count": telegram_replies_count,
            "error": "discussion_resolved_but_top_level_thread_unconfirmed",
            "reactions": post_reactions_payload,
        }

    queue: deque[tuple[int, int]] = deque()
    active_comment_peer_id = legacy_peer_id
    thread_entity_type = type(thread_entity).__name__

    try:
        # Сначала сохраняем top-level comments
        for c in top_level_comments:
            top_level_seen += 1
            comment_key = (active_comment_peer_id, int(c.id))
            if comment_key in seen_comment_ids:
                top_level_skipped_duplicate += 1
                continue
            seen_comment_ids.add(comment_key)
            k += 1

            if c.date is None:
                top_level_skipped_no_date += 1
                continue

            author_id = None
            from_id = getattr(c, "from_id", None)
            if isinstance(from_id, PeerUser):
                author_id = from_id.user_id

            author_username = None
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

            if is_bot:
                top_level_skipped_bot += 1
                continue

            commenter_key = _build_commenter_key(author_id, author_username)
            if commenter_key is not None:
                commenters.add(commenter_key)

            if comment_key not in tg_to_comment_id:
                comment_reactions_payload = _build_comment_reactions_payload(
                    message=c,
                    collected_at=reactions_collected_at,
                    top_n=reactions_top_n,
                )
                comments_scanned += 1
                if bool(comment_reactions_payload.get("present")):
                    comments_with_visible_reactions += 1

                safe_reactions_json = to_jsonable(comment_reactions_payload)
                saved_comment = await upsert_comment(
                    session,
                    channel_id=channel.id,
                    post_id=post.id,
                    tg_peer_id=active_comment_peer_id,
                    tg_message_id=c.id,
                    parent_tg_message_id=top_level_root_id,
                    parent_comment_id=None,
                    thread_root_tg_message_id=top_level_root_id,
                    depth=0,
                    date=c.date,
                    author_id=author_id,
                    author_username=author_username,
                    text=c.message,
                    reactions_json=safe_reactions_json,
                )
                tg_to_comment_id[comment_key] = saved_comment.id
                tg_to_depth[comment_key] = 0
                comments_saved += 1
            else:
                top_level_existing_rows_reused += 1
            persisted_comment_keys.add(comment_key)

            comment_replies_obj = getattr(c, "replies", None)
            nested_replies_count = getattr(comment_replies_obj, "replies", 0) if comment_replies_obj is not None else 0
            if isinstance(nested_replies_count, int) and nested_replies_count > 0:
                queue.append((c.id, 0))

            if k >= comments_sleep_every:
                k = 0
                await polite_sleep(comments_sleep_base_sec, comments_sleep_jitter_sec)

        # Потом обходим вложенные ответы
        while queue:
            parent_tg_message_id, parent_depth = queue.popleft()

            async for c in tg_client.iter_messages(thread_entity, reply_to=parent_tg_message_id):
                nested_seen += 1
                comment_key = (active_comment_peer_id, int(c.id))
                if comment_key in seen_comment_ids:
                    nested_skipped_duplicate += 1
                    continue
                seen_comment_ids.add(comment_key)
                k += 1

                if c.date is None:
                    nested_skipped_no_date += 1
                    continue

                author_id = None
                from_id = getattr(c, "from_id", None)
                if isinstance(from_id, PeerUser):
                    author_id = from_id.user_id

                author_username = None
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

                if is_bot:
                    nested_skipped_bot += 1
                    continue

                reply_to = getattr(c, "reply_to", None)
                reply_to_msg_id = getattr(reply_to, "reply_to_msg_id", None) if reply_to is not None else None
                effective_parent_tg = reply_to_msg_id or parent_tg_message_id

                parent_comment_key = (active_comment_peer_id, int(effective_parent_tg))
                parent_known_depth = tg_to_depth.get(parent_comment_key, parent_depth)
                depth = max(1, parent_known_depth + 1)

                commenter_key = _build_commenter_key(author_id, author_username)
                if commenter_key is not None:
                    commenters.add(commenter_key)

                if comment_key not in tg_to_comment_id:
                    comment_reactions_payload = _build_comment_reactions_payload(
                        message=c,
                        collected_at=reactions_collected_at,
                        top_n=reactions_top_n,
                    )
                    comments_scanned += 1
                    if bool(comment_reactions_payload.get("present")):
                        comments_with_visible_reactions += 1

                    saved_comment = await upsert_comment(
                        session,
                        channel_id=channel.id,
                        post_id=post.id,
                        tg_peer_id=active_comment_peer_id,
                        tg_message_id=c.id,
                        parent_tg_message_id=effective_parent_tg,
                        parent_comment_id=tg_to_comment_id.get(parent_comment_key),
                        thread_root_tg_message_id=top_level_root_id or getattr(discussion_root, "id", None),
                        depth=depth,
                        date=c.date,
                        author_id=author_id,
                        author_username=author_username,
                        text=c.message,
                        reactions_json=comment_reactions_payload,
                    )
                    tg_to_comment_id[comment_key] = saved_comment.id
                    tg_to_depth[comment_key] = depth
                    comments_saved += 1
                else:
                    nested_existing_rows_reused += 1
                persisted_comment_keys.add(comment_key)

                comment_replies_obj = getattr(c, "replies", None)
                nested_replies_count = getattr(comment_replies_obj, "replies", 0) if comment_replies_obj is not None else 0
                if isinstance(nested_replies_count, int) and nested_replies_count > 0:
                    queue.append((c.id, depth))

                if k >= comments_sleep_every:
                    k = 0
                    await polite_sleep(comments_sleep_base_sec, comments_sleep_jitter_sec)

    except FloodWaitError as e:
        await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason="iter_comments_flood_wait",
        )
        return {
            "status": "flood_wait",
            "post_id": post_id,
            "wait_seconds": e.seconds,
            "flood_source": "iter_comments",
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
        }
    except MsgIdInvalidError:
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason="iter_comments_msg_id_invalid",
        )
        return {
            "status": "no_discussion",
            "post_id": post_id,
            "comments_saved": comments_saved,
            "commenters_count": len(commenters),
            "reactions": post_reactions_payload,
        }
    except RPCError as exc:
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason="iter_comments_rpc_error",
        )
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
            "reactions": post_reactions_payload,
        }
    except Exception:
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason="unexpected_iter_comments_error",
        )
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
            "reactions": post_reactions_payload,
        }

    if reconciliation_enabled or has_non_legacy_comment_peers:
        scope_thread_root_id = top_level_root_id or getattr(discussion_root, "id", None)
        reconciliation_peer_ids = set(existing_peer_ids) | {active_comment_peer_id}
        try:
            await _reconcile_confirmed_comment_snapshot(
                session,
                post_id=post.id,
                tg_peer_ids=reconciliation_peer_ids,
                thread_root_tg_message_id=scope_thread_root_id,
                live_comment_keys=persisted_comment_keys,
            )
        except FloodWaitError:
            raise
        except Exception:
            post_reactions_payload = await persist_post_reactions(
                is_complete=False,
                comment_status="partial",
                comments_scanned=comments_scanned,
                comments_with_visible_reactions=comments_with_visible_reactions,
                thread_entity_type=thread_entity_type,
                reason="comment_reconciliation_incomplete",
            )
            logger.exception(
                "comment reconciliation failed marker=comments_reconciliation op=reconcile_comments post_id=%s thread_root_tg_message_id=%s",
                post.id,
                scope_thread_root_id,
            )
            return {
                "status": "discussion_error",
                "post_id": post.id,
                "discussion_msg_id": discussion_msg_id,
                "discussion_source_msg_id": discussion_source_msg_id,
                "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
                "comments_saved": comments_saved,
                "commenters_count": len(commenters),
                "telegram_replies_count": telegram_replies_count,
                "error": "comment_reconciliation_incomplete",
                "reactions": post_reactions_payload,
            }

    actual_comments_count = int(
        await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == post.id)
        )
        or 0
    )

    if (
        isinstance(telegram_replies_count, int)
        and telegram_replies_count > 0
        and actual_comments_count == 0
    ):
        post_reactions_payload = await persist_post_reactions(
            is_complete=False,
            comment_status="partial",
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
            thread_entity_type=thread_entity_type,
            reason="discussion_resolved_but_no_comments_persisted",
        )
        logger.warning(
            "comments scan produced zero persisted rows despite positive telegram replies "
            "post_id=%s discussion_msg_id=%s discussion_source_msg_id=%s telegram_replies_count=%s grouped_id=%s "
            "thread_entity_type=%s thread_entity_id=%s top_level_comments=%s top_level_seen=%s "
            "top_level_skipped_duplicate=%s top_level_skipped_no_date=%s top_level_skipped_bot=%s "
            "top_level_existing_rows_reused=%s nested_seen=%s nested_skipped_duplicate=%s nested_skipped_no_date=%s "
            "nested_skipped_bot=%s nested_existing_rows_reused=%s comments_scanned=%s comments_with_visible_reactions=%s",
            post.id,
            discussion_msg_id,
            discussion_source_msg_id,
            telegram_replies_count,
            getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
            thread_entity_type,
            getattr(thread_entity, "id", None),
            len(top_level_comments),
            top_level_seen,
            top_level_skipped_duplicate,
            top_level_skipped_no_date,
            top_level_skipped_bot,
            top_level_existing_rows_reused,
            nested_seen,
            nested_skipped_duplicate,
            nested_skipped_no_date,
            nested_skipped_bot,
            nested_existing_rows_reused,
            comments_scanned,
            comments_with_visible_reactions,
        )
        return {
            "status": "discussion_error",
            "post_id": post.id,
            "discussion_msg_id": discussion_msg_id,
            "discussion_source_msg_id": discussion_source_msg_id,
            "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
            "comments_saved": comments_saved,
            "comments_count": actual_comments_count,
            "commenters_count": len(commenters),
            "telegram_replies_count": telegram_replies_count,
            "error": "discussion_resolved_but_no_comments_persisted",
            "reactions": post_reactions_payload,
        }

    post_reactions_payload = await persist_post_reactions(
        is_complete=True,
        comment_status=_comment_reactions_status(
            is_complete=True,
            comments_scanned=comments_scanned,
            comments_with_visible_reactions=comments_with_visible_reactions,
        ),
        comments_scanned=comments_scanned,
        comments_with_visible_reactions=comments_with_visible_reactions,
        thread_entity_type=thread_entity_type,
    )
    snapshot_comments_count, snapshot_commenters_count, snapshot_long_comments_count = (
        await _load_persisted_comment_snapshot_metrics(session, post_id=post.id)
    )
    involvement = await _persist_post_engagement_metrics(
        session,
        post_id=post.id,
        views=post.views,
        reactions_payload=post_reactions_payload,
        comments_count=snapshot_comments_count,
        commenters_count=snapshot_commenters_count,
        long_comments_count=snapshot_long_comments_count,
    )
    await set_post_last_comments_scan_at(session, post_id=post.id)

    return {
        "status": "ok",
        "post_id": post.id,
        "discussion_msg_id": discussion_msg_id,
        "discussion_source_msg_id": discussion_source_msg_id,
        "album_grouped_id": getattr(head_msg, "grouped_id", None) if head_msg is not None else None,
        "comments_saved": comments_saved,
        "comments_count": snapshot_comments_count,
        "commenters_count": snapshot_commenters_count,
        "involvement": involvement,
        "telegram_replies_count": telegram_replies_count,
        "reactions": post_reactions_payload,
    }

async def _resolve_discussion_for_post_or_album(
    tg_client,
    entity,
    head_msg,
    fallback_window: int,
    fallback_max_seconds: int,
    album_discussion_expansion_steps: int,
):
    if head_msg is None:
        return None, None, "no_discussion", None, None

    head_msg_id = int(head_msg.id)
    grouped_id = getattr(head_msg, "grouped_id", None)

    candidate_ids: list[int] = [head_msg_id]

    if grouped_id:
        album_ids = await _collect_album_message_ids(
            tg_client=tg_client,
            entity=entity,
            head_msg=head_msg,
            expansion_steps=album_discussion_expansion_steps,
        )

        ordered: list[int] = []
        seen: set[int] = set()

        preferred_ids = []
        if album_ids:
            preferred_ids.append(min(album_ids))
        preferred_ids.append(head_msg_id)
        preferred_ids.extend(album_ids)

        for cid in preferred_ids:
            cid = int(cid)
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)

        candidate_ids = ordered

    logger.debug(
        "album discussion candidates head_msg_id=%s grouped_id=%s candidate_ids=%s",
        head_msg_id,
        grouped_id,
        candidate_ids,
    )

    last_status = "no_discussion"
    last_wait_seconds = 0

    for candidate_msg_id in candidate_ids:
        discussion, discussion_msg_id, status, wait_seconds, resolved_source_msg_id = await _resolve_discussion_with_fallback(
            tg_client=tg_client,
            entity=entity,
            tg_message_id=candidate_msg_id,
            original_message_id=head_msg_id,
            original_message_date=getattr(head_msg, "date", None),
            original_message_text=getattr(head_msg, "message", None),
            original_grouped_id=grouped_id,
            fallback_window=fallback_window,
            fallback_max_seconds=fallback_max_seconds,
        )

        if discussion is not None:
            logger.debug(
                "album discussion resolved source_msg_id=%s discussion_msg_id=%s grouped_id=%s",
                resolved_source_msg_id,
                discussion_msg_id,
                grouped_id,
            )
            return discussion, discussion_msg_id, status, wait_seconds, resolved_source_msg_id

        if status == "flood_wait":
            logger.warning(
                "album discussion flood_wait source_msg_id=%s grouped_id=%s wait_seconds=%s",
                candidate_msg_id,
                grouped_id,
                int(wait_seconds or 0),
            )
            return None, None, status, wait_seconds, resolved_source_msg_id

        logger.debug(
            "album discussion miss source_msg_id=%s grouped_id=%s status=%s",
            candidate_msg_id,
            grouped_id,
            status,
        )

        last_status = status
        last_wait_seconds = wait_seconds or 0

    return None, None, last_status, last_wait_seconds, None

async def _collect_album_message_ids(
    tg_client,
    entity,
    head_msg,
    window_before: int = 10,
    window_after: int = 10,
    expansion_steps: int = 6,
) -> list[int]:
    grouped_id = getattr(head_msg, "grouped_id", None)
    if not grouped_id:
        return [int(head_msg.id)]

    head_id = int(head_msg.id)
    result: list[int] = []
    seen: set[int] = set()
    async def _fetch_into(candidate_ids: list[int]) -> bool:
        if not candidate_ids:
            return False

        new_candidate_ids = [msg_id for msg_id in candidate_ids if msg_id > 0]
        if not new_candidate_ids:
            return False

        try:
            msgs = await tg_client.get_messages(entity, ids=new_candidate_ids)
        except FloodWaitError:
            raise
        except Exception:
            logger.exception(
                "album candidate fetch failed op=collect_album_message_ids head_msg_id=%s grouped_id=%s candidate_span=%s..%s",
                getattr(head_msg, "id", None),
                grouped_id,
                min(new_candidate_ids),
                max(new_candidate_ids),
            )
            return False

        if not isinstance(msgs, list):
            msgs = [msgs] if msgs is not None else []

        found_new = False
        for m in msgs:
            if not m:
                continue
            if getattr(m, "grouped_id", None) != grouped_id:
                continue
            mid = int(m.id)
            if mid not in seen:
                seen.add(mid)
                result.append(mid)
                found_new = True
        return found_new

    initial_ids = list(range(max(1, head_id - int(window_before)), head_id + int(window_after) + 1))
    found_new = await _fetch_into(initial_ids)

    for step in range(1, expansion_steps + 1):
        left_end = head_id - int(window_before) * (step - 1)
        left_start = max(1, head_id - int(window_before) * step)
        right_start = head_id + int(window_after) * (step - 1) + 1
        right_end = head_id + int(window_after) * step
        found_left = await _fetch_into(list(range(left_start, left_end)))
        found_right = await _fetch_into(list(range(right_start, right_end + 1)))
        if not found_new and not found_left and not found_right:
            break
        found_new = found_left or found_right
    if head_id not in seen:
        result.append(head_id)

    result.sort()
    return result
