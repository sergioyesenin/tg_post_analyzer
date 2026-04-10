from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.models import Comment, Post
from services.ingest import set_post_reactions_json, upsert_channel, upsert_comment, upsert_post


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reactions_payloads_persist_for_post_and_comment(integration_async_session_factory):
    async with integration_async_session_factory() as session:
        channel = await upsert_channel(session, username="reactions_persist_channel", title="Reactions Persist")
        post = await upsert_post(
            session,
            channel_id=channel.id,
            tg_message_id=1001,
            date=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            text="post",
            views=10,
        )

        post_payload = {
            "source": "telegram_refresh",
            "collected_at": "2026-04-09T12:00:00+00:00",
            "is_complete": True,
            "post_reactions": {
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
            },
            "comment_reactions": {
                "source": "telegram_refresh",
                "collected_at": "2026-04-09T12:00:00+00:00",
                "is_complete": True,
                "status": "no_reactions",
                "comments_scanned": 0,
                "comments_with_visible_reactions": 0,
                "thread_entity_type": None,
                "reason": None,
            },
        }
        comment_payload = {
            "source": "telegram_refresh",
            "collected_at": "2026-04-09T12:00:00+00:00",
            "is_complete": True,
            "supported": True,
            "present": True,
            "state": "available",
            "results": [{"count": 5, "chosen_order": None, "reaction_type": "ReactionCustomEmoji", "reaction": {"emoticon": "X"}}],
            "results_total_count": 1,
            "results_truncated": False,
            "recent_reactions_count": 0,
            "recent_reactions": [],
            "raw_type": "MessageReactions",
            "can_see_list": None,
            "reactions_as_tags": None,
            "min": None,
        }

        await set_post_reactions_json(session, post_id=post.id, reactions_json=post_payload)
        await upsert_comment(
            session,
            channel_id=channel.id,
            post_id=post.id,
            tg_peer_id=channel.id,
            tg_message_id=2001,
            parent_tg_message_id=1001,
            parent_comment_id=None,
            thread_root_tg_message_id=1001,
            depth=0,
            date=datetime(2026, 4, 9, 12, 5, tzinfo=timezone.utc),
            author_id=501,
            author_username="alice",
            text="comment",
            reactions_json=comment_payload,
        )
        await session.commit()

    async with integration_async_session_factory() as session:
        stored_post = await session.scalar(select(Post).where(Post.id == post.id))
        stored_comment = await session.scalar(select(Comment).where(Comment.post_id == post.id))

        assert stored_post is not None
        assert stored_post.reactions_json == post_payload
        assert stored_comment is not None
        assert stored_comment.reactions_json == comment_payload
