from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.ingestion_core import IngestionCore, IngestionOptions


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, key):
        del model, key
        return None

    async def commit(self) -> None:
        return None


class _FakeClient:
    def __init__(self, messages, messages_by_id=None):
        self._messages = messages
        self._messages_by_id = messages_by_id or {}

    async def get_entity(self, peer):
        return SimpleNamespace(peer=peer)

    async def get_messages(self, entity, ids):
        return self._messages_by_id.get(ids)

    async def iter_messages(self, entity):
        for msg in self._messages:
            yield msg


class _WindowedClient:
    def __init__(self, responses_by_window, messages=None):
        self._responses_by_window = dict(responses_by_window)
        self._messages = list(messages or [])
        self.requests: list[tuple[int, ...]] = []

    async def get_entity(self, peer):
        return SimpleNamespace(peer=peer)

    async def get_messages(self, entity, ids):
        del entity
        if isinstance(ids, list):
            key = tuple(ids)
            self.requests.append(key)
            return self._responses_by_window.get(key, [])
        return self._responses_by_window.get(ids)

    async def iter_messages(self, entity):
        for msg in self._messages:
            yield msg


def _msg(*, msg_id: int, dt: datetime, replies: int, reply_to_msg_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=msg_id,
        date=dt,
        message=f"m{msg_id}",
        replies=SimpleNamespace(replies=replies),
        views=100,
        reply_to=SimpleNamespace(reply_to_msg_id=reply_to_msg_id) if reply_to_msg_id is not None else None,
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


def test_ingestion_core_does_not_stop_on_parent_post_hydrated_in_same_run():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    parent_msg = _msg(msg_id=101, dt=now - timedelta(minutes=1), replies=12)
    child_msg = _msg(msg_id=105, dt=now, replies=30, reply_to_msg_id=101)
    messages = [child_msg, parent_msg]
    stored_posts: dict[int, SimpleNamespace] = {}
    saved_ids: list[int] = []

    async def _upsert(session, **kwargs):
        tg_message_id = int(kwargs["tg_message_id"])
        saved_ids.append(tg_message_id)
        post = SimpleNamespace(id=tg_message_id, tg_message_id=tg_message_id)
        stored_posts[tg_message_id] = post
        return post

    async def _existing(*, session, channel_id: int, tg_message_id: int):
        return stored_posts.get(tg_message_id)

    core = IngestionCore(
        tg_client=_FakeClient(messages, messages_by_id={101: parent_msg}),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = _existing  # type: ignore[method-assign]

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

    assert result.processed_posts == 2
    assert result.stopped_reason is None
    assert saved_ids == [101, 105, 101]


def test_pick_album_representative_message_keeps_current_working_album_case():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    head_msg = SimpleNamespace(id=103, date=now, message="m103", grouped_id=555)
    album_101 = SimpleNamespace(id=101, date=now, message="m101", grouped_id=555)
    album_102 = SimpleNamespace(id=102, date=now, message="m102", grouped_id=555)
    album_103 = head_msg
    responses = {
        tuple(range(93, 114)): [album_101, album_102, album_103],
        tuple(range(91, 101)): [],
        tuple(range(104, 114)): [],
    }
    core = IngestionCore(
        tg_client=_WindowedClient(responses),
        session_factory=_FakeSession,
    )

    representative = asyncio.run(core._pick_album_representative_message(SimpleNamespace(id=1), head_msg))

    assert representative.id == 101


def test_pick_album_representative_message_recovers_from_partial_nearby_fetch():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    head_msg = SimpleNamespace(id=103, date=now, message="m103", grouped_id=555)
    album_101 = SimpleNamespace(id=101, date=now, message="m101", grouped_id=555)
    album_103 = head_msg
    responses = {
        tuple(range(93, 114)): [album_103],
        tuple(range(93, 103)): [album_101],
        tuple(range(104, 114)): [],
        tuple(range(91, 101)): [],
    }
    client = _WindowedClient(responses)
    core = IngestionCore(
        tg_client=client,
        session_factory=_FakeSession,
    )

    representative = asyncio.run(core._pick_album_representative_message(SimpleNamespace(id=1), head_msg))

    assert representative.id == 101
    assert len(client.requests) >= 2


def test_ingestion_core_skips_album_without_text_and_logs_validation_failure(caplog):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    messages = [
        SimpleNamespace(
            id=103,
            date=now,
            message=None,
            replies=SimpleNamespace(replies=8),
            views=100,
            reply_to=None,
            grouped_id=555,
        )
    ]
    album_101 = SimpleNamespace(id=101, date=now, message=None, grouped_id=555)
    album_102 = SimpleNamespace(id=102, date=now, message=None, grouped_id=555)
    album_103 = messages[0]
    responses = {
        tuple(range(93, 114)): [album_101, album_102, album_103],
        tuple(range(91, 101)): [],
        tuple(range(104, 114)): [],
    }
    saved_ids: list[int] = []

    async def _upsert(session, **kwargs):
        saved_ids.append(int(kwargs["tg_message_id"]))
        return SimpleNamespace(id=kwargs["tg_message_id"])

    core = IngestionCore(
        tg_client=_WindowedClient(responses_by_window=responses, messages=messages),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO, logger="services.ingestion_core"):
        result = asyncio.run(
            core.ingest_channel(
                channel=SimpleNamespace(id=1, username="demo"),
                options=IngestionOptions(
                    since_utc=now - timedelta(hours=1),
                    stop_on_existing_post=False,
                ),
            )
        )

    assert result.processed_posts == 0
    assert saved_ids == []
    validation_record = next(record for record in caplog.records if record.msg == "post_text_validation_failed")
    assert validation_record.reason == "text_none"
    assert validation_record.is_album is True
    assert validation_record.grouped_id == 555


def test_ingestion_core_skips_whitespace_only_text(caplog):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    messages = [
        SimpleNamespace(
            id=301,
            date=now,
            message="   ",
            replies=SimpleNamespace(replies=4),
            views=100,
            reply_to=None,
            grouped_id=None,
        )
    ]
    saved_ids: list[int] = []

    async def _upsert(session, **kwargs):
        saved_ids.append(int(kwargs["tg_message_id"]))
        return SimpleNamespace(id=kwargs["tg_message_id"])

    core = IngestionCore(
        tg_client=_FakeClient(messages),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO, logger="services.ingestion_core"):
        result = asyncio.run(
            core.ingest_channel(
                channel=SimpleNamespace(id=1, username="demo"),
                options=IngestionOptions(
                    since_utc=now - timedelta(hours=1),
                    stop_on_existing_post=False,
                ),
            )
        )

    assert result.processed_posts == 0
    assert saved_ids == []
    validation_record = next(record for record in caplog.records if record.msg == "post_text_validation_failed")
    assert validation_record.reason == "text_whitespace_only"
    assert validation_record.raw_text_len == 3


def test_ingestion_core_keeps_normal_text_flow():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    messages = [_msg(msg_id=401, dt=now, replies=7)]
    saved_ids: list[int] = []
    callback_ids: list[int] = []

    async def _upsert(session, **kwargs):
        saved_ids.append(int(kwargs["tg_message_id"]))
        return SimpleNamespace(id=kwargs["tg_message_id"])

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
                since_utc=now - timedelta(hours=1),
                stop_on_existing_post=False,
            ),
            on_post_saved=_on_saved,
        )
    )

    assert result.processed_posts == 1
    assert saved_ids == [401]
    assert callback_ids == [401]


def test_ingestion_core_filters_album_when_representative_has_no_text(caplog):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    head_msg = SimpleNamespace(
        id=103,
        date=now,
        message="caption on later message",
        replies=SimpleNamespace(replies=6),
        views=100,
        reply_to=None,
        grouped_id=555,
    )
    album_101 = SimpleNamespace(id=101, date=now, message=None, grouped_id=555)
    album_102 = SimpleNamespace(id=102, date=now, message="caption on later message", grouped_id=555)
    album_103 = head_msg
    responses = {
        tuple(range(93, 114)): [album_101, album_102, album_103],
        tuple(range(91, 101)): [],
        tuple(range(104, 114)): [],
    }
    saved_ids: list[int] = []

    async def _upsert(session, **kwargs):
        saved_ids.append(int(kwargs["tg_message_id"]))
        return SimpleNamespace(id=kwargs["tg_message_id"])

    core = IngestionCore(
        tg_client=_WindowedClient(responses, messages=[head_msg]),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = AsyncMock(return_value=None)  # type: ignore[attr-defined]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    with caplog.at_level(logging.INFO, logger="services.ingestion_core"):
        result = asyncio.run(
            core.ingest_channel(
                channel=SimpleNamespace(id=1, username="demo"),
                options=IngestionOptions(
                    since_utc=now - timedelta(hours=1),
                    stop_on_existing_post=False,
                ),
            )
        )

    assert result.processed_posts == 0
    assert saved_ids == []
    selected_record = next(record for record in caplog.records if record.msg == "album_representative_selected")
    assert selected_record.selected_id == 101
    assert selected_record.has_text is False
    validation_record = next(record for record in caplog.records if record.msg == "post_text_validation_failed")
    assert validation_record.representative_id == 101
    assert validation_record.reason == "text_none"


def test_pick_album_representative_logs_fallback_on_fetch_failure(caplog):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    head_msg = SimpleNamespace(id=103, date=now, message="m103", grouped_id=555)

    class _FailingClient:
        async def get_entity(self, peer):
            return SimpleNamespace(peer=peer)

        async def get_messages(self, entity, ids):
            raise RuntimeError("boom")

        async def iter_messages(self, entity):
            if False:
                yield entity

    core = IngestionCore(
        tg_client=_FailingClient(),
        session_factory=_FakeSession,
    )

    with caplog.at_level(logging.INFO, logger="services.ingestion_core"):
        representative = asyncio.run(core._pick_album_representative_message(SimpleNamespace(id=1), head_msg))

    assert representative is head_msg
    fallback_record = next(record for record in caplog.records if record.msg == "album_representative_fallback")
    assert fallback_record.reason == "fetch_failed_or_empty"
    assert fallback_record.fallback_message_id == 103


def test_ingestion_core_marks_post_report_stale_when_existing_post_inputs_change(monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    message = _msg(msg_id=201, dt=now, replies=12)
    sync_calls: list[dict] = []

    async def _upsert(session, **kwargs):
        return SimpleNamespace(id=501, tg_message_id=kwargs["tg_message_id"])

    async def _existing(*, session, channel_id: int, tg_message_id: int):
        return SimpleNamespace(
            id=501,
            tg_message_id=tg_message_id,
            date=now - timedelta(minutes=5),
            text="old text",
            views=10,
            comments_count=1,
        )

    async def _fake_sync_post_report_staleness(_session, *, post_id, source, dependency_type, dependency_id):
        sync_calls.append(
            {
                "post_id": post_id,
                "source": source,
                "dependency_type": dependency_type,
                "dependency_id": dependency_id,
            }
        )
        return {"status": "queued"}

    monkeypatch.setattr("services.reporting.sync_post_report_staleness", _fake_sync_post_report_staleness)

    core = IngestionCore(
        tg_client=_FakeClient([message]),
        session_factory=_FakeSession,
        upsert_post_fn=_upsert,
    )
    core._get_post_by_channel_msg = _existing  # type: ignore[method-assign]
    core._ensure_parent_post = AsyncMock(return_value=None)  # type: ignore[attr-defined]

    result = asyncio.run(
        core.ingest_channel(
            channel=SimpleNamespace(id=1, username="demo"),
            options=IngestionOptions(
                since_utc=now - timedelta(hours=1),
                resolve_album_representative=False,
                stop_on_existing_post=False,
            ),
        )
    )

    assert result.processed_posts == 1
    assert sync_calls == [
        {
            "post_id": 501,
            "source": "ingestion.post_update",
            "dependency_type": "post_ingestion",
            "dependency_id": 501,
        }
    ]
