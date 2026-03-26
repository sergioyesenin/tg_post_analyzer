from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from schemas.comment import CommentOut
from services.ingest import upsert_comment


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeUpsertSession:
    def __init__(self):
        self._rows_by_key: dict[tuple[int, int, int], SimpleNamespace] = {}
        self._rows_by_id: dict[int, SimpleNamespace] = {}
        self._next_id = 1
        self.seen_constraint_names: list[str] = []

    async def execute(self, stmt):
        compiled = stmt.compile(dialect=postgresql.dialect())
        params = compiled.params
        sql_text = str(compiled)
        if "uq_comments_channel_peer_msg" in sql_text:
            self.seen_constraint_names.append("uq_comments_channel_peer_msg")

        key = (
            int(params["channel_id"]),
            int(params["tg_peer_id"]),
            int(params["tg_message_id"]),
        )
        existing = self._rows_by_key.get(key)
        if existing is None:
            row_id = self._next_id
            self._next_id += 1
            existing = SimpleNamespace(id=row_id)
            self._rows_by_key[key] = existing
            self._rows_by_id[row_id] = existing
        for name, value in params.items():
            if name == "created_at":
                continue
            setattr(existing, name, value)
        return _ScalarOneResult(existing.id)

    async def get(self, model, row_id: int):
        del model
        return self._rows_by_id.get(row_id)


def test_upsert_comment_keeps_old_callers_compatible_by_defaulting_tg_peer_id_to_channel_id():
    session = _FakeUpsertSession()

    comment = asyncio.run(
        upsert_comment(
            session,
            channel_id=7,
            post_id=42,
            tg_message_id=701,
            parent_tg_message_id=None,
            parent_comment_id=None,
            thread_root_tg_message_id=None,
            depth=0,
            date=datetime(2026, 3, 25, tzinfo=timezone.utc),
            author_id=1001,
            author_username="alice",
            text="hello",
        )
    )

    assert comment.tg_peer_id == 7
    assert session.seen_constraint_names == ["uq_comments_channel_peer_msg"]


def test_upsert_comment_does_not_overwrite_same_tg_message_id_from_different_peers():
    session = _FakeUpsertSession()

    first = asyncio.run(
        upsert_comment(
            session,
            channel_id=7,
            post_id=42,
            tg_peer_id=3001,
            tg_message_id=701,
            parent_tg_message_id=None,
            parent_comment_id=None,
            thread_root_tg_message_id=8001,
            depth=0,
            date=datetime(2026, 3, 25, tzinfo=timezone.utc),
            author_id=1001,
            author_username="alice",
            text="from peer A",
        )
    )
    second = asyncio.run(
        upsert_comment(
            session,
            channel_id=7,
            post_id=42,
            tg_peer_id=3002,
            tg_message_id=701,
            parent_tg_message_id=None,
            parent_comment_id=None,
            thread_root_tg_message_id=8002,
            depth=0,
            date=datetime(2026, 3, 25, tzinfo=timezone.utc),
            author_id=1002,
            author_username="bob",
            text="from peer B",
        )
    )

    assert first.id != second.id
    assert first.text == "from peer A"
    assert second.text == "from peer B"


def test_comment_read_shape_supports_tg_peer_id_after_migration():
    payload = CommentOut.model_validate(
        SimpleNamespace(
            id=1,
            post_id=42,
            tg_peer_id=3001,
            tg_message_id=701,
            parent_tg_message_id=None,
            parent_comment_id=None,
            thread_root_tg_message_id=8001,
            depth=0,
            text="hello",
            date=datetime(2026, 3, 25, tzinfo=timezone.utc),
        )
    )

    assert payload.model_dump()["tg_peer_id"] == 3001
