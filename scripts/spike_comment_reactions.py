from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel

from client.telegram import build_telegram_client, ensure_telegram_client_started
from db.models import Channel, Post
from db.session import AsyncSessionLocal


@dataclass
class SpikeTarget:
    post_id: int
    channel_id: int
    channel_username: str | None
    channel_title: str | None
    tg_message_id: int
    comments_count: int | None


async def _load_target_by_post_id(post_id: int) -> SpikeTarget:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(
                    Post.id,
                    Post.channel_id,
                    Channel.username,
                    Channel.title,
                    Post.tg_message_id,
                    Post.comments_count,
                )
                .join(Channel, Channel.id == Post.channel_id)
                .where(Post.id == post_id)
            )
        ).first()
    if row is None:
        raise RuntimeError(f"Post id={post_id} was not found")
    return SpikeTarget(
        post_id=int(row[0]),
        channel_id=int(row[1]),
        channel_username=row[2],
        channel_title=row[3],
        tg_message_id=int(row[4]),
        comments_count=None if row[5] is None else int(row[5]),
    )


def _serialize_reactions(message) -> dict:
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return {
            "supported": True,
            "present": False,
            "results": [],
            "raw_type": None,
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

    return {
        "supported": True,
        "present": True,
        "raw_type": type(reactions).__name__,
        "can_see_list": getattr(reactions, "can_see_list", None),
        "reactions_as_tags": getattr(reactions, "reactions_as_tags", None),
        "min": getattr(reactions, "min", None),
        "results": reaction_results,
    }


def _comment_preview(message) -> dict:
    text = getattr(message, "message", None)
    return {
        "id": getattr(message, "id", None),
        "date": None if getattr(message, "date", None) is None else message.date.isoformat(),
        "reply_to_msg_id": None
        if getattr(message, "reply_to", None) is None
        else getattr(message.reply_to, "reply_to_msg_id", None),
        "text_preview": None if text is None else text[:120],
        "reactions": _serialize_reactions(message),
    }


async def _collect_top_level_comments(entity, *, root_id: int, client, limit: int) -> list[object]:
    items: list[object] = []
    async for message in client.iter_messages(entity, reply_to=root_id):
        items.append(message)
        if len(items) >= limit:
            break
    return items


async def run_spike(post_id: int, *, limit: int, session_suffix: str = "", unique_session_per_run: bool = False) -> dict:
    target = await _load_target_by_post_id(post_id)
    handle = build_telegram_client(session_suffix=session_suffix, unique_session_per_run=unique_session_per_run)
    try:
        await ensure_telegram_client_started(handle, op_name="spike_comment_reactions.start")
        entity_ref = target.channel_username or target.channel_id
        source_entity = await handle.get_entity(entity_ref)
        head_msg = await handle.get_messages(source_entity, ids=target.tg_message_id)
        if head_msg is None:
            raise RuntimeError(
                f"Telegram returned no source message for channel={entity_ref!r} tg_message_id={target.tg_message_id}"
            )

        discussion = await handle(GetDiscussionMessageRequest(peer=source_entity, msg_id=target.tg_message_id))
        discussion_messages = list(getattr(discussion, "messages", []) or [])
        discussion_chats = list(getattr(discussion, "chats", []) or [])
        if not discussion_messages or not discussion_chats:
            return {
                "status": "unsupported_or_no_discussion",
                "target": asdict(target),
                "entity_ref": entity_ref,
                "reason": "GetDiscussionMessageRequest returned no discussion messages/chats",
            }

        discussion_root = discussion_messages[0]
        discussion_chat = discussion_chats[0]
        discussion_root_id = getattr(discussion_root, "id", None)
        if not isinstance(discussion_root_id, int) or discussion_root_id <= 0:
            return {
                "status": "unsupported_or_no_discussion",
                "target": asdict(target),
                "entity_ref": entity_ref,
                "reason": "Discussion root id is missing or invalid",
            }

        discussion_top_level = await _collect_top_level_comments(
            discussion_chat,
            root_id=discussion_root_id,
            client=handle,
            limit=limit,
        )
        source_top_level = await _collect_top_level_comments(
            source_entity,
            root_id=target.tg_message_id,
            client=handle,
            limit=limit,
        )

        discussion_with_reactions = [item for item in discussion_top_level if getattr(item, "reactions", None) is not None]
        source_with_reactions = [item for item in source_top_level if getattr(item, "reactions", None) is not None]

        return {
            "status": "ok",
            "target": asdict(target),
            "entity_ref": entity_ref,
            "source_head_message_id": getattr(head_msg, "id", None),
            "discussion_chat_id": getattr(discussion_chat, "id", None),
            "discussion_root_id": discussion_root_id,
            "discussion_scan": {
                "entity_type": type(discussion_chat).__name__,
                "top_level_comments_scanned": len(discussion_top_level),
                "comments_with_reactions": len(discussion_with_reactions),
                "samples": [_comment_preview(message) for message in discussion_top_level[: min(5, len(discussion_top_level))]],
            },
            "source_scan": {
                "entity_type": type(source_entity).__name__,
                "top_level_comments_scanned": len(source_top_level),
                "comments_with_reactions": len(source_with_reactions),
                "samples": [_comment_preview(message) for message in source_top_level[: min(5, len(source_top_level))]],
            },
        }
    finally:
        await handle.disconnect()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exploratory spike for Telegram comment reactions retrieval.")
    parser.add_argument("--post-id", type=int, required=True, help="Local Post.id to inspect via Telegram discussion thread")
    parser.add_argument("--limit", type=int, default=20, help="Top-level comments to scan per entity")
    parser.add_argument("--session-suffix", type=str, default="", help="Optional existing Telethon session suffix")
    parser.add_argument("--unique-session-per-run", action="store_true", help="Use a unique session file for the run")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    result = asyncio.run(
        run_spike(
            args.post_id,
            limit=args.limit,
            session_suffix=args.session_suffix,
            unique_session_per_run=args.unique_session_per_run,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
