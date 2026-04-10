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
            "recent_reactions_count": 0,
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

    recent = []
    for item in list(getattr(reactions, "recent_reactions", []) or []):
        recent.append(item.to_dict())

    return {
        "supported": True,
        "present": True,
        "raw_type": type(reactions).__name__,
        "can_see_list": getattr(reactions, "can_see_list", None),
        "reactions_as_tags": getattr(reactions, "reactions_as_tags", None),
        "min": getattr(reactions, "min", None),
        "results": reaction_results,
        "recent_reactions_count": len(recent),
        "recent_reactions": recent,
    }


async def run_spike(post_id: int, *, session_suffix: str = "", unique_session_per_run: bool = False) -> dict:
    target = await _load_target_by_post_id(post_id)
    handle = build_telegram_client(session_suffix=session_suffix, unique_session_per_run=unique_session_per_run)
    try:
        await ensure_telegram_client_started(handle, op_name="spike_post_reactions.start")
        entity_ref = target.channel_username or target.channel_id
        entity = await handle.get_entity(entity_ref)
        message = await handle.get_messages(entity, ids=target.tg_message_id)
        if message is None:
            raise RuntimeError(
                f"Telegram returned no message for channel={entity_ref!r} tg_message_id={target.tg_message_id}"
            )
        return {
            "status": "ok",
            "target": asdict(target),
            "entity_ref": entity_ref,
            "message_id": getattr(message, "id", None),
            "message_date": None if getattr(message, "date", None) is None else message.date.isoformat(),
            "views": getattr(message, "views", None),
            "forwards": getattr(message, "forwards", None),
            "replies": None if getattr(message, "replies", None) is None else message.replies.to_dict(),
            "reactions": _serialize_reactions(message),
        }
    finally:
        await handle.disconnect()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exploratory spike for Telegram post reactions retrieval.")
    parser.add_argument("--post-id", type=int, required=True, help="Local Post.id to inspect via Telegram")
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
            session_suffix=args.session_suffix,
            unique_session_per_run=args.unique_session_per_run,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
