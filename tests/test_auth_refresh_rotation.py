from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from db.models import AuthRefreshToken, User
from services import auth


class _FakeResult:
    def __init__(self, token_row):
        self._token_row = token_row

    def scalar_one_or_none(self):
        return self._token_row


class _SharedTokenStore:
    def __init__(self, token_row: AuthRefreshToken):
        self.token_row = token_row
        self.created_rows: list[AuthRefreshToken] = []
        self._lock = asyncio.Lock()
        self._next_id = token_row.id + 1

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        if self._lock.locked():
            self._lock.release()

    def allocate_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value


class _FakeSession:
    def __init__(self, store: _SharedTokenStore, user: User):
        self._store = store
        self._user = user
        self._pending: list[AuthRefreshToken] = []
        self._holds_lock = False

    async def execute(self, _stmt):
        if not self._holds_lock:
            await self._store.acquire()
            self._holds_lock = True
        return _FakeResult(self._store.token_row)

    async def get(self, model, object_id: int):
        if model is User and object_id == self._user.id:
            return self._user
        return None

    def add(self, row):
        self._pending.append(row)

    async def flush(self):
        for row in self._pending:
            if row.id is None:
                row.id = self._store.allocate_id()
                self._store.created_rows.append(row)
        self._pending.clear()

    async def commit(self):
        self._store.release()
        self._holds_lock = False

    async def rollback(self):
        self._store.release()
        self._holds_lock = False


@pytest.mark.asyncio
async def test_rotate_refresh_token_allows_only_single_concurrent_use(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    token_row = AuthRefreshToken(
        id=1,
        user_id=7,
        token_hash=auth._hash_refresh_token("shared-refresh-token"),
        expires_at=now + timedelta(days=7),
        revoked_at=None,
        replaced_by_token_id=None,
    )
    user = User(
        id=7,
        username="demo",
        password_hash="hash",
        is_active=True,
        is_local=True,
    )
    store = _SharedTokenStore(token_row)

    async def _fake_roles(_session, _user_id: int):
        return ["analyst"]

    monkeypatch.setattr(auth, "get_user_roles", _fake_roles)
    monkeypatch.setattr(auth, "_utcnow", lambda: now)

    async def _use_refresh_once():
        session = _FakeSession(store, user)
        try:
            auth_user, new_token = await auth.rotate_refresh_token(session, refresh_token="shared-refresh-token")
            await session.commit()
            return {"status": "ok", "user_id": auth_user.id, "refresh_token": new_token}
        except HTTPException as exc:
            await session.rollback()
            return {"status": "error", "code": exc.status_code, "detail": exc.detail}

    first, second = await asyncio.gather(_use_refresh_once(), _use_refresh_once())

    results = [first, second]
    success = [item for item in results if item["status"] == "ok"]
    failures = [item for item in results if item["status"] == "error"]

    assert len(success) == 1
    assert len(failures) == 1
    assert failures[0] == {"status": "error", "code": 401, "detail": "Invalid refresh token"}
    assert token_row.revoked_at == now
    assert token_row.replaced_by_token_id == store.created_rows[0].id
    assert len(store.created_rows) == 1
