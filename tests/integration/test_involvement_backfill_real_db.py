from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.models import Post
from scripts.backfill_involvement_metrics import backfill_involvement_metrics
from services.ingest import set_post_reactions_json, upsert_channel, upsert_comment, upsert_post
from services.involvement import compute_involvement


@pytest.mark.integration
@pytest.mark.asyncio
async def test_involvement_backfill_recomputes_persisted_metrics_idempotently(integration_async_session_factory):
    payload = {
        "source": "telegram_refresh",
        "collected_at": "2026-04-09T12:00:00+00:00",
        "is_complete": True,
        "post_reactions": {
            "supported": True,
            "present": True,
            "state": "available",
            "results": [{"count": 10}, {"count": 5}, {"count": -4}, None],
            "results_total_count": 2,
            "results_truncated": False,
            "recent_reactions_count": 0,
            "recent_reactions": [],
            "raw_type": "MessageReactions",
            "can_see_list": None,
            "reactions_as_tags": None,
            "min": None,
        },
        "comment_reactions": {
            "source": "telegram_refresh",
            "collected_at": "2026-04-09T12:00:00+00:00",
            "is_complete": True,
            "status": "available",
            "comments_scanned": 2,
            "comments_with_visible_reactions": 0,
            "thread_entity_type": "Channel",
            "reason": None,
        },
    }

    async with integration_async_session_factory() as session:
        channel = await upsert_channel(session, username="backfill_metrics_channel", title="Backfill Metrics")
        post = await upsert_post(
            session,
            channel_id=channel.id,
            tg_message_id=4001,
            date=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
            text="post",
            views=200,
            comments_count=3,
        )
        await set_post_reactions_json(session, post_id=post.id, reactions_json=payload)
        await upsert_comment(
            session,
            channel_id=channel.id,
            post_id=post.id,
            tg_peer_id=channel.id,
            tg_message_id=5001,
            parent_tg_message_id=post.tg_message_id,
            parent_comment_id=None,
            thread_root_tg_message_id=post.tg_message_id,
            depth=0,
            date=datetime(2026, 4, 9, 12, 5, tzinfo=timezone.utc),
            author_id=101,
            author_username="alice",
            text="A" * 100,
            reactions_json=None,
        )
        await upsert_comment(
            session,
            channel_id=channel.id,
            post_id=post.id,
            tg_peer_id=channel.id,
            tg_message_id=5002,
            parent_tg_message_id=post.tg_message_id,
            parent_comment_id=None,
            thread_root_tg_message_id=post.tg_message_id,
            depth=0,
            date=datetime(2026, 4, 9, 12, 6, tzinfo=timezone.utc),
            author_id=102,
            author_username="bob",
            text="   ",
            reactions_json=None,
        )
        post.commenters = 99
        post.long_comments = 99
        post.involvement = 99.0
        await session.commit()
        post_id = int(post.id)

    first_run = await backfill_involvement_metrics(
        session_factory=integration_async_session_factory,
        batch_size=1,
        limit=10,
    )

    expected_involvement = compute_involvement(
        views=200,
        comments_count=3,
        commenters=2,
        long_comments=1,
        reactions_payload=payload,
    )

    async with integration_async_session_factory() as session:
        stored_post = await session.scalar(select(Post).where(Post.id == post_id))
        assert stored_post is not None
        assert stored_post.comments_count == 3
        assert stored_post.commenters == 2
        assert stored_post.long_comments == 1
        assert stored_post.involvement == pytest.approx(expected_involvement)

    second_run = await backfill_involvement_metrics(
        session_factory=integration_async_session_factory,
        batch_size=1,
        limit=10,
    )

    async with integration_async_session_factory() as session:
        stored_post = await session.scalar(select(Post).where(Post.id == post_id))
        assert stored_post is not None
        assert stored_post.commenters == 2
        assert stored_post.long_comments == 1
        assert stored_post.involvement == pytest.approx(expected_involvement)

    assert first_run["processed"] >= 1
    assert first_run["updated"] >= 1
    assert second_run["processed"] >= 1
    assert second_run["updated"] >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_involvement_backfill_dry_run_does_not_persist_changes(integration_async_session_factory):
    async with integration_async_session_factory() as session:
        channel = await upsert_channel(session, username="backfill_metrics_dry_run_channel", title="Backfill Metrics Dry Run")
        post = await upsert_post(
            session,
            channel_id=channel.id,
            tg_message_id=4101,
            date=datetime(2026, 4, 9, 13, 0, tzinfo=timezone.utc),
            text="post",
            views=120,
            comments_count=1,
        )
        await upsert_comment(
            session,
            channel_id=channel.id,
            post_id=post.id,
            tg_peer_id=channel.id,
            tg_message_id=5101,
            parent_tg_message_id=post.tg_message_id,
            parent_comment_id=None,
            thread_root_tg_message_id=post.tg_message_id,
            depth=0,
            date=datetime(2026, 4, 9, 13, 5, tzinfo=timezone.utc),
            author_id=201,
            author_username="carol",
            text="B" * 120,
            reactions_json=None,
        )
        post.commenters = 0
        post.long_comments = 0
        post.involvement = 0.0
        await session.commit()
        post_id = int(post.id)

    dry_run = await backfill_involvement_metrics(
        session_factory=integration_async_session_factory,
        batch_size=10,
        dry_run=True,
        min_post_id=post_id,
        max_post_id=post_id,
    )

    async with integration_async_session_factory() as session:
        stored_post = await session.scalar(select(Post).where(Post.id == post_id))
        assert stored_post is not None
        assert stored_post.commenters == 0
        assert stored_post.long_comments == 0
        assert stored_post.involvement == 0.0

    assert dry_run["processed"] == 1
    assert dry_run["updated"] == 0
    assert dry_run["dry_run"] is True
