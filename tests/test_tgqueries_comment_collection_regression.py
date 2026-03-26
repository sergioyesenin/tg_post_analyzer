from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from telethon.errors import FloodWaitError

from services import TGqueries as tgqueries


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, initial_comments_count: int = 0, existing_rows=None, commenter_rows=None):
        self.initial_comments_count = initial_comments_count
        self.persisted_rows: list[dict] = []
        self._existing_rows = list(existing_rows or [])
        self._commenter_rows = list(commenter_rows or [])

    async def scalar(self, _stmt):
        if self.persisted_rows:
            return len(self.persisted_rows)
        return self.initial_comments_count

    async def execute(self, stmt):
        stmt_text = str(stmt)
        if "comments.author_id" in stmt_text and "comments.author_username" in stmt_text:
            return _RowsResult(self._commenter_rows)
        if "SELECT comments.tg_peer_id" in stmt_text and "comments.tg_message_id" not in stmt_text:
            peer_rows = [(row[0],) if isinstance(row, tuple) else (row,) for row in self._existing_rows]
            return _RowsResult(peer_rows)
        return _RowsResult(self._existing_rows)


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
        self.entity_calls: list[object] = []
        self.discussion_requests: list[int] = []

    def is_connected(self):
        return True

    async def start(self):
        return None

    async def get_entity(self, peer):
        self.entity_calls.append(peer)
        return self._entity

    async def get_messages(self, entity, ids):
        del entity
        if isinstance(ids, list):
            return [self._messages_by_id.get(item) for item in ids]
        return self._messages_by_id.get(ids)

    async def __call__(self, request):
        self.discussion_requests.append(request.msg_id)
        value = self._discussions.get(request.msg_id)
        if isinstance(value, Exception):
            raise value
        return value

    async def iter_messages(self, entity, reply_to):
        key = (getattr(entity, "id", entity), reply_to)
        value = self._iter_map.get(key, [])
        if isinstance(value, Exception):
            raise value
        for item in value:
            yield item


class _WindowedMessageClient:
    def __init__(self, message_map: dict[int, object]):
        self._message_map = dict(message_map)
        self.requests: list[list[int]] = []

    async def get_messages(self, entity, ids):
        del entity
        if not isinstance(ids, list):
            return self._message_map.get(ids)
        self.requests.append(list(ids))
        return [self._message_map.get(item) for item in ids]


def _dt(hour: int) -> datetime:
    return datetime(2026, 3, 25, hour, 0, tzinfo=timezone.utc)


def _message(
    msg_id: int,
    *,
    date: datetime,
    text: str,
    replies: int = 0,
    views: int | None = None,
    grouped_id: int | None = None,
    user_id: int = 100,
    username: str | None = "user",
    reply_to_msg_id: int | None = None,
):
    return SimpleNamespace(
        id=msg_id,
        date=date,
        message=text,
        views=views,
        grouped_id=grouped_id,
        replies=SimpleNamespace(replies=replies),
        from_id=tgqueries.PeerUser(user_id),
        sender=tgqueries.User(username=username, bot=False),
        reply_to=SimpleNamespace(reply_to_msg_id=reply_to_msg_id) if reply_to_msg_id is not None else None,
    )


def _discussion(chat_id: int, root_id: int):
    return SimpleNamespace(
        chats=[SimpleNamespace(id=chat_id)],
        messages=[SimpleNamespace(id=root_id)],
    )


@pytest.fixture(autouse=True)
def _patch_telethon_type_checks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tgqueries, "PeerUser", _FakePeerUser)
    monkeypatch.setattr(tgqueries, "User", _FakeUser)


@pytest.fixture
def _common_patches(monkeypatch: pytest.MonkeyPatch):
    updates: dict[str, list[dict]] = {
        "views": [],
        "comments_count": [],
        "involvement": [],
        "scan_at": [],
    }

    async def _fake_ensure_started(_client, *, op_name: str = "tg_client.start"):
        del op_name
        return None

    async def _fake_upsert_comment(session, **kwargs):
        saved = SimpleNamespace(id=len(session.persisted_rows) + 1, **kwargs)
        session.persisted_rows.append(kwargs)
        return saved

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
async def test_update_post_comments_baseline_non_album_post(monkeypatch: pytest.MonkeyPatch, _common_patches):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=42, tg_message_id=500, date=_dt(10), views=50)
    channel = SimpleNamespace(id=7, username="demo_channel")
    head_msg = _message(500, date=_dt(10), text="post", replies=1, views=77)
    top_comment = _message(701, date=_dt(11), text="first comment", user_id=101, username="alice")
    entity = SimpleNamespace(id=9001)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={500: head_msg},
        discussions={500: _discussion(chat_id=3001, root_id=8001)},
        iter_map={(3001, 8001): [top_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "ok",
        "post_id": 42,
        "discussion_msg_id": 500,
        "discussion_source_msg_id": 500,
        "album_grouped_id": None,
        "comments_saved": 1,
        "comments_count": 1,
        "commenters_count": 1,
        "involvement": 1 / 77,
        "telegram_replies_count": 1,
    }
    assert session.persisted_rows == [
        {
            "channel_id": 7,
            "post_id": 42,
            "tg_peer_id": 7,
            "tg_message_id": 701,
            "parent_tg_message_id": 8001,
            "parent_comment_id": None,
            "thread_root_tg_message_id": 8001,
            "depth": 0,
            "date": _dt(11),
            "author_id": 101,
            "author_username": "alice",
            "text": "first comment",
        }
    ]
    assert _common_patches["views"] == [{"post_id": 42, "views": 77}]
    assert _common_patches["comments_count"] == [{"post_id": 42, "comments_count": 1}]
    assert _common_patches["scan_at"] == [{"post_id": 42, "scanned_at": None}]


@pytest.mark.asyncio
async def test_update_post_comments_baseline_album_case_resolves_other_album_member(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=1)
    post = SimpleNamespace(id=43, tg_message_id=103, date=_dt(10), views=10)
    channel = SimpleNamespace(id=8, username="album_channel")
    head_msg = _message(103, date=_dt(10), text="album head", replies=1, views=10, grouped_id=555)
    album_msg_101 = _message(101, date=_dt(10), text="album first", grouped_id=555)
    album_msg_102 = _message(102, date=_dt(10), text="album second", grouped_id=555)
    entity = SimpleNamespace(id=9002)
    album_comment = _message(901, date=_dt(11), text="album comment", user_id=201, username="bob")
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={
            103: head_msg,
            101: album_msg_101,
            102: album_msg_102,
        },
        discussions={
            101: _discussion(chat_id=3002, root_id=8101),
        },
        iter_map={(3002, 8101): [album_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "ok"
    assert result["discussion_msg_id"] == 101
    assert result["discussion_source_msg_id"] == 101
    assert result["album_grouped_id"] == 555
    assert result["comments_saved"] == 1
    assert tg_client.discussion_requests == [101]


@pytest.mark.asyncio
async def test_collect_album_message_ids_expands_for_sparse_gapped_album_ids():
    head_msg = _message(103, date=_dt(10), text="album head", grouped_id=555)
    message_map = {
        83: _message(83, date=_dt(10), text="album early", grouped_id=555),
        103: head_msg,
        123: _message(123, date=_dt(10), text="album late", grouped_id=555),
        130: _message(130, date=_dt(10), text="other album", grouped_id=777),
    }
    client = _WindowedMessageClient(message_map)

    result = await tgqueries._collect_album_message_ids(
        tg_client=client,
        entity=SimpleNamespace(id=1),
        head_msg=head_msg,
    )

    assert result == [83, 103, 123]
    assert len(client.requests) >= 2


@pytest.mark.asyncio
async def test_update_post_comments_rejects_false_positive_neighbor_discussion_match(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=431, tg_message_id=500, date=_dt(10), views=10)
    channel = SimpleNamespace(id=19, username="neighbor_channel")
    head_msg = _message(500, date=_dt(10), text="post", replies=1, views=10)
    neighbor_msg = _message(499, date=_dt(10), text="neighbor post", replies=1, views=10)
    entity = SimpleNamespace(id=9031)
    neighbor_comment = _message(799, date=_dt(11), text="wrong thread comment", user_id=211, username="mallory")
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={500: head_msg, 499: neighbor_msg},
        discussions={499: _discussion(chat_id=3031, root_id=8131)},
        iter_map={(3031, 8131): [neighbor_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "discussion_error",
        "post_id": 431,
        "comments_saved": 0,
        "commenters_count": 0,
        "telegram_replies_count": 1,
        "album_grouped_id": None,
        "discussion_source_msg_id": None,
        "error": "discussion_not_resolved_with_positive_replies",
    }
    assert tg_client.discussion_requests == [500]
    assert session.persisted_rows == []
    assert _common_patches["comments_count"] == []
    assert _common_patches["scan_at"] == []


@pytest.mark.asyncio
async def test_update_post_comments_recovers_non_album_discussion_via_adjacent_id_with_strong_identity_checks(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    monkeypatch.setattr(tgqueries.settings, "DISCUSSION_FALLBACK_ID_WINDOW", 1)
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=432, tg_message_id=500, date=_dt(10), views=10)
    channel = SimpleNamespace(id=20, username="adjacent_channel")
    head_msg = _message(500, date=_dt(10), text="post", replies=1, views=10)
    adjacent_msg = _message(501, date=_dt(10), text="post", replies=1, views=10)
    adjacent_comment = _message(880, date=_dt(11), text="real thread comment", user_id=222, username="eve")
    tg_client = _FakeTelegramClient(
        entity=SimpleNamespace(id=9032),
        messages_by_id={500: head_msg, 501: adjacent_msg},
        discussions={501: _discussion(chat_id=3032, root_id=8132)},
        iter_map={(3032, 8132): [adjacent_comment]},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "ok"
    assert result["discussion_msg_id"] == 501
    assert result["discussion_source_msg_id"] == 501
    assert [row["tg_message_id"] for row in session.persisted_rows] == [880]
    assert [row["tg_peer_id"] for row in session.persisted_rows] == [20]


@pytest.mark.asyncio
async def test_update_post_comments_falls_back_to_confirmed_source_root_after_invalid_discussion_root(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=433, tg_message_id=14711, date=_dt(10), views=10)
    channel = SimpleNamespace(id=21, username="album_source_fallback")
    head_msg = _message(14711, date=_dt(10), text="album post", replies=1, views=10, grouped_id=555)
    top_comment = _message(881, date=_dt(11), text="source root comment", user_id=223, username="zoe")
    entity = SimpleNamespace(id=9033)
    discussion_chat = 3033
    discussion_root = 8133
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={14711: head_msg},
        discussions={14711: _discussion(chat_id=discussion_chat, root_id=discussion_root)},
        iter_map={
            (discussion_chat, discussion_root): tgqueries.MsgIdInvalidError(None),
            (entity.id, 14711): [top_comment],
        },
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "ok"
    assert result["discussion_msg_id"] == 14711
    assert result["discussion_source_msg_id"] == 14711
    assert [row["tg_message_id"] for row in session.persisted_rows] == [881]
    assert [row["parent_tg_message_id"] for row in session.persisted_rows] == [14711]


@pytest.mark.asyncio
async def test_update_post_comments_returns_error_when_discussion_resolves_but_top_level_thread_is_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=1)
    post = SimpleNamespace(id=430, tg_message_id=530, date=_dt(10), views=10)
    channel = SimpleNamespace(id=18, username="broken_thread_channel")
    head_msg = _message(530, date=_dt(10), text="post", replies=2, views=10)
    entity = SimpleNamespace(id=9030)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={530: head_msg},
        discussions={530: _discussion(chat_id=3030, root_id=8130)},
        iter_map={(3030, 8130): RuntimeError("thread scan failed")},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "discussion_error",
        "post_id": 430,
        "discussion_msg_id": 530,
        "discussion_source_msg_id": 530,
        "album_grouped_id": None,
        "comments_saved": 0,
        "comments_count": 1,
        "commenters_count": 0,
        "telegram_replies_count": 2,
        "error": "discussion_resolved_but_top_level_thread_unconfirmed",
    }
    assert session.persisted_rows == []
    assert _common_patches["comments_count"] == []
    assert _common_patches["scan_at"] == []


@pytest.mark.asyncio
async def test_update_post_comments_baseline_nested_replies_traversal(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=44, tg_message_id=600, date=_dt(10), views=100)
    channel = SimpleNamespace(id=9, username="threaded_channel")
    head_msg = _message(600, date=_dt(10), text="post", replies=3, views=100)
    top_comment = _message(710, date=_dt(11), text="top", replies=1, user_id=301, username="carol")
    child_comment = _message(711, date=_dt(11) + timedelta(minutes=1), text="child", replies=1, user_id=302, username="dave", reply_to_msg_id=710)
    grandchild_comment = _message(712, date=_dt(11) + timedelta(minutes=2), text="grandchild", user_id=303, username="erin", reply_to_msg_id=711)
    entity = SimpleNamespace(id=9003)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={600: head_msg},
        discussions={600: _discussion(chat_id=3003, root_id=8200)},
        iter_map={
            (3003, 8200): [top_comment],
            (3003, 710): [child_comment],
            (3003, 711): [grandchild_comment],
        },
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "ok"
    assert result["comments_saved"] == 3
    assert [row["tg_message_id"] for row in session.persisted_rows] == [710, 711, 712]
    assert [row["tg_peer_id"] for row in session.persisted_rows] == [9, 9, 9]
    assert [row["depth"] for row in session.persisted_rows] == [0, 1, 2]
    assert [row["parent_tg_message_id"] for row in session.persisted_rows] == [8200, 710, 711]
    assert [row["parent_comment_id"] for row in session.persisted_rows] == [None, 1, 2]
    assert all(row["thread_root_tg_message_id"] == 8200 for row in session.persisted_rows)


@pytest.mark.asyncio
async def test_update_post_comments_baseline_resolve_entity_flood_wait_uses_retry_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=45, tg_message_id=700, date=_dt(10), views=5)
    channel = SimpleNamespace(id=10, username="retry_channel")
    entity = SimpleNamespace(id=9004)
    tg_client = _FakeTelegramClient(entity=entity)
    calls: list[str] = []

    async def _fake_with_session_lock_retry(coro_factory, *, op_name: str, **_kwargs):
        calls.append(op_name)
        raise FloodWaitError(None, 12)

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert calls == ["tg_client.get_entity"]
    assert result == {
        "status": "flood_wait",
        "post_id": 45,
        "wait_seconds": 12,
        "flood_source": "resolve_entity",
        "comments_saved": 0,
        "commenters_count": 0,
    }
    assert _common_patches["scan_at"] == []


@pytest.mark.asyncio
async def test_update_post_comments_baseline_iter_comments_flood_wait_preserves_partial_progress(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(initial_comments_count=0)
    post = SimpleNamespace(id=46, tg_message_id=800, date=_dt(10), views=10)
    channel = SimpleNamespace(id=11, username="flood_channel")
    head_msg = _message(800, date=_dt(10), text="post", replies=2, views=10)
    top_comment = _message(720, date=_dt(11), text="top", replies=1, user_id=401, username="frank")
    entity = SimpleNamespace(id=9005)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={800: head_msg},
        discussions={800: _discussion(chat_id=3004, root_id=8300)},
        iter_map={
            (3004, 8300): [top_comment],
            (3004, 720): FloodWaitError(None, 9),
        },
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "flood_wait",
        "post_id": 46,
        "wait_seconds": 9,
        "flood_source": "iter_comments",
        "comments_saved": 1,
        "commenters_count": 1,
    }
    assert [row["tg_message_id"] for row in session.persisted_rows] == [720]
    assert _common_patches["comments_count"] == []
    assert _common_patches["scan_at"] == []


@pytest.mark.asyncio
async def test_update_post_comments_baseline_fast_path_unchanged_for_non_album(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(
        initial_comments_count=2,
        commenter_rows=[(101, "alice"), (None, "alice"), (202, "bob")],
    )
    post = SimpleNamespace(id=47, tg_message_id=900, date=_dt(10), views=15)
    channel = SimpleNamespace(id=12, username="fast_path_channel")
    head_msg = _message(900, date=_dt(10), text="post", replies=2, views=15)
    entity = SimpleNamespace(id=9006)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={900: head_msg},
    )
    discussion_attempted = {"called": False}

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    async def _fake_resolve_discussion_for_post_or_album(**_kwargs):
        discussion_attempted["called"] = True
        return None, None, "no_discussion", None, None

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    monkeypatch.setattr(tgqueries, "_resolve_discussion_for_post_or_album", _fake_resolve_discussion_for_post_or_album)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "unchanged",
        "post_id": 47,
        "comments_saved": 2,
        "comments_count": 2,
        "commenters_count": 3,
        "involvement": 3 / 15,
        "views": 15,
        "telegram_replies_count": 2,
    }
    assert discussion_attempted["called"] is False
    assert session.persisted_rows == []
    assert _common_patches["views"] == []
    assert _common_patches["comments_count"] == [{"post_id": 47, "comments_count": 2}]
    assert _common_patches["involvement"] == [{"post_id": 47, "involvement": 3 / 15}]
    assert _common_patches["scan_at"] == [{"post_id": 47, "scanned_at": None}]


@pytest.mark.asyncio
async def test_update_post_comments_unchanged_refreshes_views_when_replies_count_matches(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(
        initial_comments_count=2,
        commenter_rows=[(101, "alice"), (202, "bob")],
    )
    post = SimpleNamespace(id=48, tg_message_id=901, date=_dt(10), views=15)
    channel = SimpleNamespace(id=13, username="fresh_views_channel")
    head_msg = _message(901, date=_dt(10), text="post", replies=2, views=99)
    entity = SimpleNamespace(id=9007)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={901: head_msg},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    async def _fake_resolve_discussion_for_post_or_album(**_kwargs):
        raise AssertionError("unchanged fast-path must not resolve discussion")

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    monkeypatch.setattr(tgqueries, "_resolve_discussion_for_post_or_album", _fake_resolve_discussion_for_post_or_album)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result["status"] == "unchanged"
    assert result["views"] == 99
    assert result["involvement"] == 2 / 99
    assert _common_patches["views"] == [{"post_id": 48, "views": 99}]
    assert _common_patches["involvement"] == [{"post_id": 48, "involvement": 2 / 99}]


@pytest.mark.asyncio
async def test_update_post_comments_unchanged_keeps_comments_count_and_involvement_consistent(
    monkeypatch: pytest.MonkeyPatch,
    _common_patches,
):
    session = _FakeSession(
        initial_comments_count=3,
        commenter_rows=[(101, "alice"), (101, "alice"), (None, "guest"), (None, "guest2")],
    )
    post = SimpleNamespace(id=49, tg_message_id=902, date=_dt(10), views=20)
    channel = SimpleNamespace(id=14, username="consistent_metrics_channel")
    head_msg = _message(902, date=_dt(10), text="post", replies=2, views=20)
    entity = SimpleNamespace(id=9008)
    tg_client = _FakeTelegramClient(
        entity=entity,
        messages_by_id={902: head_msg},
    )

    async def _fake_with_session_lock_retry(coro_factory, **_kwargs):
        return await coro_factory()

    async def _fake_resolve_discussion_for_post_or_album(**_kwargs):
        raise AssertionError("unchanged fast-path must not resolve discussion")

    monkeypatch.setattr(tgqueries, "with_session_lock_retry", _fake_with_session_lock_retry)
    monkeypatch.setattr(tgqueries, "_resolve_discussion_for_post_or_album", _fake_resolve_discussion_for_post_or_album)
    _patch_post_lookup(monkeypatch, post=post, channel=channel)

    result = await tgqueries.update_post_comments(session, post.id, tg_client=tg_client)

    assert result == {
        "status": "unchanged",
        "post_id": 49,
        "comments_saved": 3,
        "comments_count": 3,
        "commenters_count": 3,
        "involvement": 3 / 20,
        "views": 20,
        "telegram_replies_count": 2,
    }
    assert _common_patches["comments_count"] == [{"post_id": 49, "comments_count": 3}]
    assert _common_patches["involvement"] == [{"post_id": 49, "involvement": 3 / 20}]
