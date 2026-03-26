from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services import TGqueries as tgqueries


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ReconSession:
    def __init__(self, *, comment_rows: list[dict]):
        self.comment_rows = [dict(row) for row in comment_rows]
        self.persisted_rows: list[dict] = []

    async def scalar(self, stmt):
        params = stmt.compile().params
        post_id = int(next(iter(params.values())))
        return sum(1 for row in self.comment_rows if int(row["post_id"]) == post_id)

    async def execute(self, stmt):
        stmt_text = str(stmt)
        params = stmt.compile().params

        if "comments.author_id" in stmt_text and "comments.author_username" in stmt_text:
            post_id = int(next(iter(params.values())))
            rows = [
                (row.get("author_id"), row.get("author_username"))
                for row in self.comment_rows
                if int(row["post_id"]) == post_id
            ]
            return _RowsResult(rows)

        if "SELECT comments.tg_peer_id " in stmt_text and "comments.tg_message_id" not in stmt_text:
            post_id = int(next(iter(params.values())))
            rows = [
                (int(row["tg_peer_id"]),)
                for row in self.comment_rows
                if int(row["post_id"]) == post_id
            ]
            return _RowsResult(rows)

        if "comments.tg_peer_id, comments.tg_message_id, comments.id, comments.depth" in stmt_text:
            post_id = int(next(iter(params.values())))
            rows = [
                (int(row["tg_peer_id"]), int(row["tg_message_id"]), int(row["id"]), int(row.get("depth", 0)))
                for row in self.comment_rows
                if int(row["post_id"]) == post_id
            ]
            return _RowsResult(rows)

        if "comments.id, comments.tg_peer_id, comments.tg_message_id" in stmt_text:
            post_id = int(params["post_id_1"])
            thread_root = int(params["thread_root_tg_message_id_1"])
            peer_values = params["tg_peer_id_1"]
            rows = [
                (int(row["id"]), int(row["tg_peer_id"]), int(row["tg_message_id"]))
                for row in self.comment_rows
                if int(row["post_id"]) == post_id
                and int(row["thread_root_tg_message_id"]) == thread_root
                and int(row["tg_peer_id"]) in set(int(value) for value in peer_values)
            ]
            return _RowsResult(rows)

        if stmt_text.startswith("DELETE FROM comments"):
            stale_ids = {int(value) for value in params["id_1"]}
            self.comment_rows = [row for row in self.comment_rows if int(row["id"]) not in stale_ids]
            return _RowsResult([])

        raise AssertionError(f"Unexpected statement: {stmt_text}")


class _FakePeerUser:
    def __init__(self, user_id: int):
        self.user_id = user_id


class _FakeUser:
    def __init__(self, *, username: str | None, bot: bool = False):
        self.username = username
        self.bot = bot


class _FakeTelegramClient:
    def __init__(self, *, entity, messages_by_id=None, iter_map=None, discussions=None):
        self._entity = entity
        self._messages_by_id = dict(messages_by_id or {})
        self._iter_map = dict(iter_map or {})
        self._discussions = dict(discussions or {})

    def is_connected(self):
        return True

    async def start(self):
        return None

    async def get_entity(self, peer):
        del peer
        return self._entity

    async def get_messages(self, entity, ids):
        del entity
        if isinstance(ids, list):
            return [self._messages_by_id.get(item) for item in ids]
        return self._messages_by_id.get(ids)

    async def __call__(self, request):
        return self._discussions.get(request.msg_id)

    async def iter_messages(self, entity, reply_to):
        key = (getattr(entity, "id", entity), reply_to)
        for item in self._iter_map.get(key, []):
            yield item


def _dt(hour: int) -> datetime:
    return datetime(2026, 3, 25, hour, 0, tzinfo=timezone.utc)


def _message(
    msg_id: int,
    *,
    date: datetime,
    text: str,
    replies: int = 0,
    views: int | None = None,
    user_id: int = 100,
    username: str | None = "user",
    reply_to_msg_id: int | None = None,
):
    return SimpleNamespace(
        id=msg_id,
        date=date,
        message=text,
        views=views,
        replies=SimpleNamespace(replies=replies),
        from_id=tgqueries.PeerUser(user_id),
        sender=tgqueries.User(username=username, bot=False),
        reply_to=SimpleNamespace(reply_to_msg_id=reply_to_msg_id) if reply_to_msg_id is not None else None,
        grouped_id=None,
    )


def _discussion(chat_id: int, root_id: int):
    return SimpleNamespace(
        chats=[SimpleNamespace(id=chat_id)],
        messages=[SimpleNamespace(id=root_id)],
    )


@pytest.fixture(autouse=True)
def _patch_types(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tgqueries, "PeerUser", _FakePeerUser)
    monkeypatch.setattr(tgqueries, "User", _FakeUser)


@pytest.fixture
def _common_patches(monkeypatch: pytest.MonkeyPatch):
    updates = {"comments_count": [], "involvement": [], "views": [], "scan_at": []}

    async def _fake_ensure_started(_client, *, op_name: str = "tg_client.start"):
        del _client, op_name
        return None

    async def _fake_upsert_comment(session, **kwargs):
        for row in session.comment_rows:
            if (
                int(row["post_id"]) == int(kwargs["post_id"])
                and int(row["tg_peer_id"]) == int(kwargs["tg_peer_id"])
                and int(row["tg_message_id"]) == int(kwargs["tg_message_id"])
            ):
                row.update(kwargs)
                saved = SimpleNamespace(id=row["id"], **kwargs)
                session.persisted_rows.append(kwargs)
                return saved
        new_id = max((int(row["id"]) for row in session.comment_rows), default=0) + 1
        row = {"id": new_id, **kwargs}
        session.comment_rows.append(row)
        session.persisted_rows.append(kwargs)
        return SimpleNamespace(id=new_id, **kwargs)

    async def _fake_set_post_views(_session, *, post_id: int, views: int | None):
        updates["views"].append({"post_id": post_id, "views": views})

    async def _fake_set_post_comments_count(_session, *, post_id: int, comments_count: int):
        updates["comments_count"].append({"post_id": post_id, "comments_count": comments_count})

    async def _fake_set_post_involvement(_session, *, post_id: int, involvement: float | None):
        updates["involvement"].append({"post_id": post_id, "involvement": involvement})

    async def _fake_set_post_last_comments_scan_at(_session, *, post_id: int, scanned_at=None):
        updates["scan_at"].append({"post_id": post_id, "scanned_at": scanned_at})

    async def _fake_polite_sleep(_base: float, _jitter: float):
        return None

    monkeypatch.setattr(tgqueries, "ensure_telegram_client_started", _fake_ensure_started)
    monkeypatch.setattr(tgqueries, "upsert_comment", _fake_upsert_comment)
    monkeypatch.setattr(tgqueries, "set_post_views", _fake_set_post_views)
    monkeypatch.setattr(tgqueries, "set_post_comments_count", _fake_set_post_comments_count)
    monkeypatch.setattr(tgqueries, "set_post_involvement", _fake_set_post_involvement)
    monkeypatch.setattr(tgqueries, "set_post_last_comments_scan_at", _fake_set_post_last_comments_scan_at)
    monkeypatch.setattr(tgqueries, "polite_sleep", _fake_polite_sleep)
    return updates


def _patch_post_lookup(monkeypatch: pytest.MonkeyPatch, *, post, channel):
    async def _fake_get_post_with_channel_by_post_id(_session, post_id: int):
        assert post_id == post.id
        return post, channel

    monkeypatch.setattr(tgqueries, "get_post_with_channel_by_post_id", _fake_get_post_with_channel_by_post_id)


@pytest.mark.asyncio
async def test_reconcile_confirmed_comment_snapshot_cleans_stale_rows():
    session = _ReconSession(
        comment_rows=[
            {"id": 1, "post_id": 42, "tg_peer_id": 3001, "tg_message_id": 701, "thread_root_tg_message_id": 8001},
            {"id": 2, "post_id": 42, "tg_peer_id": 3001, "tg_message_id": 799, "thread_root_tg_message_id": 8001},
            {"id": 3, "post_id": 42, "tg_peer_id": 7, "tg_message_id": 888, "thread_root_tg_message_id": 8001},
        ]
    )

    deleted = await tgqueries._reconcile_confirmed_comment_snapshot(
        session,
        post_id=42,
        tg_peer_ids={3001, 7},
        thread_root_tg_message_id=8001,
        live_comment_keys={(3001, 701)},
    )

    assert deleted == 2
    assert {(row["tg_peer_id"], row["tg_message_id"]) for row in session.comment_rows} == {(3001, 701)}


@pytest.mark.asyncio
async def test_reconcile_confirmed_comment_snapshot_does_not_delete_valid_rows():
    session = _ReconSession(
        comment_rows=[
            {"id": 1, "post_id": 42, "tg_peer_id": 3001, "tg_message_id": 701, "thread_root_tg_message_id": 8001},
        ]
    )

    deleted = await tgqueries._reconcile_confirmed_comment_snapshot(
        session,
        post_id=42,
        tg_peer_ids={3001},
        thread_root_tg_message_id=8001,
        live_comment_keys={(3001, 701)},
    )

    assert deleted == 0
    assert len(session.comment_rows) == 1


@pytest.mark.asyncio
async def test_update_post_comments_reconciliation_realigns_comments_count(monkeypatch: pytest.MonkeyPatch, _common_patches):
    monkeypatch.setattr(tgqueries.settings, "COMMENTS_RECONCILIATION_ENABLED", True)
    session = _ReconSession(
        comment_rows=[
            {
                "id": 1,
                "post_id": 52,
                "tg_peer_id": 3001,
                "tg_message_id": 799,
                "thread_root_tg_message_id": 8001,
                "depth": 0,
                "author_id": 111,
                "author_username": "stale",
            },
            {
                "id": 2,
                "post_id": 52,
                "tg_peer_id": 3001,
                "tg_message_id": 798,
                "thread_root_tg_message_id": 8001,
                "depth": 0,
                "author_id": 112,
                "author_username": "stale2",
            },
        ]
    )
    post = SimpleNamespace(id=52, tg_message_id=500, date=_dt(10), views=50)
    channel = SimpleNamespace(id=7, username="demo_channel")
    head_msg = _message(500, date=_dt(10), text="post", replies=1, views=77)
    top_comment = _message(701, date=_dt(11), text="first comment", user_id=101, username="alice")
    tg_client = _FakeTelegramClient(
        entity=SimpleNamespace(id=9001),
        messages_by_id={500: head_msg},
        discussions={500: _discussion(chat_id=3001, root_id=8001)},
        iter_map={(3001, 8001): [top_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "ok"
    assert result["comments_count"] == 1
    assert {(row["tg_peer_id"], row["tg_message_id"]) for row in session.comment_rows} == {(7, 701)}
    assert _common_patches["comments_count"] == [{"post_id": 52, "comments_count": 1}]


@pytest.mark.asyncio
async def test_update_post_comments_reconciliation_incomplete_returns_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    monkeypatch.setattr(tgqueries.settings, "COMMENTS_RECONCILIATION_ENABLED", True)
    session = _ReconSession(comment_rows=[])
    post = SimpleNamespace(id=53, tg_message_id=500, date=_dt(10), views=50)
    channel = SimpleNamespace(id=7, username="demo_channel")
    head_msg = _message(500, date=_dt(10), text="post", replies=1, views=77)
    top_comment = _message(701, date=_dt(11), text="first comment", user_id=101, username="alice")
    tg_client = _FakeTelegramClient(
        entity=SimpleNamespace(id=9001),
        messages_by_id={500: head_msg},
        discussions={500: _discussion(chat_id=3001, root_id=8001)},
        iter_map={(3001, 8001): [top_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    async def _fake_reconcile(**_kwargs):
        raise RuntimeError("reconcile failed")

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    monkeypatch.setattr(tgqueries, "_reconcile_confirmed_comment_snapshot", _fake_reconcile)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "discussion_error"
    assert result["error"] == "comment_reconciliation_incomplete"
    assert _common_patches["comments_count"] == []
