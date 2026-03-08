from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.ingestion_core import IngestionCore, IngestionOptions


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None


class _FakeClient:
    def __init__(self, messages):
        self._messages = messages

    async def get_entity(self, peer):
        return SimpleNamespace(peer=peer)

    async def get_messages(self, entity, ids):
        return None

    async def iter_messages(self, entity):
        for msg in self._messages:
            yield msg


def _msg(*, msg_id: int, dt: datetime, replies: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=msg_id,
        date=dt,
        message=f"m{msg_id}",
        replies=SimpleNamespace(replies=replies),
        views=100,
        reply_to=None,
        grouped_id=None,
    )


def test_ingestion_core_applies_filters_and_runs_callback():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    messages = [
        _msg(msg_id=30, dt=now, replies=25),
        _msg(msg_id=29, dt=now - timedelta(minutes=10), replies=5),
        _msg(msg_id=10, dt=now - timedelta(days=2), replies=50),
    ]
    saved_ids: list[int] = []
    callback_ids: list[int] = []

    async def _upsert(session, **kwargs):
        saved_ids.append(int(kwargs["tg_message_id"]))
        return SimpleNamespace(id=kwargs["tg_message_id"], views=kwargs.get("views"), comments_count=kwargs.get("comments_count"))

    async def _on_saved(session, post, ctx):
        callback_ids.append(post.id)

    core = IngestionCore(
        tg_client=_FakeClient(messages),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    result = asyncio.run(
        core.ingest_channel(
            channel=SimpleNamespace(id=1, username="demo"),
            options=IngestionOptions(
                since_utc=now - timedelta(days=1),
                min_replies=20,
                resolve_album_representative=False,
                stop_on_existing_post=False,
            ),
            on_post_saved=_on_saved,
        )
    )

    assert result.processed_posts == 1
    assert result.stopped_reason == "before_since"
    assert saved_ids == [30]
    assert callback_ids == [30]


def test_ingestion_core_stops_when_existing_post_found():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    messages = [_msg(msg_id=101, dt=now, replies=30)]

    async def _upsert(session, **kwargs):
        raise AssertionError("upsert_post must not be called for already ingested posts")

    async def _existing(*, session, channel_id: int, tg_message_id: int):
        return SimpleNamespace(id=999) if tg_message_id == 101 else None

    core = IngestionCore(
        tg_client=_FakeClient(messages),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = _existing  # type: ignore[method-assign]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    result = asyncio.run(
        core.ingest_channel(
            channel=SimpleNamespace(id=7, username="demo"),
            options=IngestionOptions(
                since_utc=now - timedelta(hours=1),
                resolve_album_representative=False,
                stop_on_existing_post=True,
            ),
        )
    )

    assert result.processed_posts == 0
    assert result.stopped_reason == "already_ingested"
