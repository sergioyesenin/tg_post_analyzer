from __future__ import annotations

import asyncio
from collections import deque
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError

from api.routers import auth as auth_router
from deps import get_current_user
from services.auth import AuthUser
from services import auth_rate_limit as auth_rate_limit_service
from services.auth_rate_limit import reset_auth_rate_limits


class _FakeSharedRateLimiterBackend:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], deque] = {}
        self._lock = asyncio.Lock()

    async def check(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None:
        now = auth_rate_limit_service._utcnow()
        window_start = now - timedelta(seconds=window_seconds)
        bucket_key = (scope, key)
        async with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int((bucket[0] + timedelta(seconds=window_seconds) - now).total_seconds()))
                raise auth_rate_limit_service._rate_limit_exception(retry_after=retry_after)
            bucket.append(now)

    async def clear(self) -> None:
        async with self._lock:
            self._buckets.clear()


class _FakeSession:
    def __init__(self, *, users_by_username=None, users_by_email=None, flush_error: Exception | None = None):
        self.commit_calls = 0
        self.rollback_calls = 0
        self.flush_error = flush_error
        self.users_by_username = users_by_username or {}
        self.users_by_email = users_by_email or {}
        self.added: list[object] = []
        self.next_user_id = 100

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1

    async def execute(self, stmt):
        sql = str(stmt)
        params = stmt.compile().params
        if 'FROM users' in sql and 'WHERE users.username' in sql:
            username = next(iter(params.values()))
            value = self.users_by_username.get(username)
            return type('_ScalarOneOrNone', (), {'scalar_one_or_none': lambda self_: value})()
        if 'FROM users' in sql and 'WHERE users.email' in sql:
            email = next(iter(params.values()))
            value = self.users_by_email.get(email)
            return type('_ScalarOneOrNone', (), {'scalar_one_or_none': lambda self_: value})()
        raise AssertionError(f'Unexpected SQL: {sql}')

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        if self.flush_error is not None:
            raise self.flush_error
        for row in self.added:
            if getattr(row, 'id', None) is None:
                row.id = self.next_user_id
                self.next_user_id += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router.router, prefix='/api/auth')

    async def _fake_get_session():
        yield session

    app.dependency_overrides[auth_router.get_session] = _fake_get_session
    return TestClient(app)


def _reset_rate_limits() -> None:
    import asyncio

    asyncio.run(reset_auth_rate_limits())


def _override_admin(client: TestClient) -> None:
    async def _fake_current_user():
        return AuthUser(id=1, username='admin', is_active=True, roles=('admin',))

    client.app.dependency_overrides[get_current_user] = _fake_current_user


@pytest.fixture(autouse=True)
def _stub_shared_rate_limiter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_router.auth_rate_limiter, '_shared_backend', _FakeSharedRateLimiterBackend())


def test_auth_login_smoke(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)

    monkeypatch.setattr(auth_router.settings, 'AUTH_PROVIDER_MODE', 'local')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/auth')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_DOMAIN', None)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SAMESITE', 'lax')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SECURE', False)

    async def _fake_authenticate(_session, *, username: str, password: str):
        assert username == 'demo'
        assert password == 'password'
        return AuthUser(id=10, username='demo', is_active=True, roles=('admin',))

    async def _fake_issue_refresh_token(_session, *, user_id: int):
        assert user_id == 10
        return 'refresh-demo'

    async def _fake_write_audit_log(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_router, 'authenticate_local_user', _fake_authenticate)
    monkeypatch.setattr(auth_router, 'create_access_token', lambda **_kwargs: 'access-demo')
    monkeypatch.setattr(auth_router, 'issue_refresh_token', _fake_issue_refresh_token)
    monkeypatch.setattr(auth_router, 'write_audit_log', _fake_write_audit_log)

    response = client.post('/api/auth/login', json={'username': 'demo', 'password': 'password'})

    assert response.status_code == 200
    assert response.json()['access_token'] == 'access-demo'
    assert response.json()['refresh_token'] is None
    assert response.json()['token_type'] == 'bearer'
    assert response.json()['roles'] == ['admin']
    assert response.cookies.get('tgpa_refresh') == 'refresh-demo'
    assert session.commit_calls == 1


def test_auth_refresh_smoke(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'old-refresh')

    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/auth')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_DOMAIN', None)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SAMESITE', 'lax')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SECURE', False)

    async def _fake_rotate(_session, *, refresh_token: str):
        assert refresh_token == 'old-refresh'
        return AuthUser(id=11, username='user11', is_active=True, roles=('analyst',)), 'new-refresh'

    async def _fake_write_audit_log(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_router, 'rotate_refresh_token', _fake_rotate)
    monkeypatch.setattr(auth_router, 'create_access_token', lambda **_kwargs: 'access-11')
    monkeypatch.setattr(auth_router, 'write_audit_log', _fake_write_audit_log)

    response = client.post('/api/auth/refresh')

    assert response.status_code == 200
    assert response.json()['access_token'] == 'access-11'
    assert response.json()['refresh_token'] is None
    assert response.json()['roles'] == ['analyst']
    assert response.cookies.get('tgpa_refresh') == 'new-refresh'
    assert session.commit_calls == 1


def test_auth_logout_smoke(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'refresh-to-revoke')

    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/auth')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_DOMAIN', None)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SAMESITE', 'lax')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SECURE', False)

    async def _fake_current_user():
        return AuthUser(id=12, username='user12', is_active=True, roles=('admin',))

    async def _fake_revoke(_session, *, refresh_token: str):
        assert refresh_token == 'refresh-to-revoke'
        return True

    async def _fake_write_audit_log(*_args, **_kwargs):
        return None

    app = client.app
    app.dependency_overrides[get_current_user] = _fake_current_user

    monkeypatch.setattr(auth_router, 'revoke_refresh_token', _fake_revoke)
    monkeypatch.setattr(auth_router, 'write_audit_log', _fake_write_audit_log)

    response = client.post('/api/auth/logout')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'refresh_revoked': True}
    assert session.commit_calls == 1


def test_create_user_rejects_duplicate_username(monkeypatch):
    _reset_rate_limits()
    existing_user = type('ExistingUser', (), {'id': 2})()
    session = _FakeSession(users_by_username={'taken': existing_user})
    client = _build_client(session)
    _override_admin(client)

    response = client.post(
        '/api/auth/users',
        json={
            'username': 'taken',
            'password': 'Password123!',
            'email': 'new@example.com',
            'roles': ['analyst'],
        },
    )

    assert response.status_code == 409
    assert response.json() == {'detail': 'Username already exists'}


def test_create_user_rejects_duplicate_email(monkeypatch):
    _reset_rate_limits()
    existing_user = type('ExistingUser', (), {'id': 3})()
    session = _FakeSession(users_by_email={'taken@example.com': existing_user})
    client = _build_client(session)
    _override_admin(client)

    response = client.post(
        '/api/auth/users',
        json={
            'username': 'new-user',
            'password': 'Password123!',
            'email': 'taken@example.com',
            'roles': ['analyst'],
        },
    )

    assert response.status_code == 409
    assert response.json() == {'detail': 'Email already exists'}


def test_create_user_maps_integrity_error_to_conflict(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession(
        flush_error=IntegrityError(
            statement='insert into users ...',
            params={},
            orig=Exception('duplicate key value violates unique constraint "uq_users_email"'),
        )
    )
    client = _build_client(session)
    _override_admin(client)

    async def _fake_ensure_roles_exist(_session, roles):
        return [type('RoleRow', (), {'id': 7, 'name': role})() for role in roles]

    async def _fake_write_audit_log(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_router, 'ensure_roles_exist', _fake_ensure_roles_exist)
    monkeypatch.setattr(auth_router, 'write_audit_log', _fake_write_audit_log)

    response = client.post(
        '/api/auth/users',
        json={
            'username': 'new-user',
            'password': 'Password123!',
            'email': 'taken@example.com',
            'roles': ['analyst'],
        },
    )

    assert response.status_code == 409
    assert response.json() == {'detail': 'Email already exists'}
    assert session.rollback_calls == 1


def test_auth_login_rate_limit_returns_429(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)

    monkeypatch.setattr(auth_router.settings, 'AUTH_PROVIDER_MODE', 'local')
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_LOGIN_MAX_ATTEMPTS', 1)

    async def _fake_authenticate(_session, *, username: str, password: str):
        return None

    monkeypatch.setattr(auth_router, 'authenticate_local_user', _fake_authenticate)

    first = client.post('/api/auth/login', json={'username': 'demo', 'password': 'bad'})
    second = client.post('/api/auth/login', json={'username': 'demo', 'password': 'bad'})

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json() == {'detail': 'Too many authentication attempts'}


def test_auth_login_rate_limit_applies_per_username_across_client_ips(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)

    monkeypatch.setattr(auth_router.settings, 'AUTH_PROVIDER_MODE', 'local')
    monkeypatch.setattr(auth_router.settings, 'AUTH_TRUST_PROXY_HEADERS', True)
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_LOGIN_MAX_ATTEMPTS', 1)

    async def _fake_authenticate(_session, *, username: str, password: str):
        return None

    monkeypatch.setattr(auth_router, 'authenticate_local_user', _fake_authenticate)

    first = client.post(
        '/api/auth/login',
        headers={'x-forwarded-for': '198.51.100.10'},
        json={'username': 'demo', 'password': 'bad'},
    )
    second = client.post(
        '/api/auth/login',
        headers={'x-forwarded-for': '203.0.113.77'},
        json={'username': 'demo', 'password': 'bad'},
    )

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json() == {'detail': 'Too many authentication attempts'}


def test_auth_refresh_rate_limit_returns_429(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'old-refresh')

    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_MAX_ATTEMPTS', 1)

    calls = {'count': 0}

    async def _fake_rotate(_session, *, refresh_token: str):
        calls['count'] += 1
        raise auth_router.HTTPException(status_code=401, detail='Invalid refresh token')

    monkeypatch.setattr(auth_router, 'rotate_refresh_token', _fake_rotate)

    first = client.post('/api/auth/refresh')
    second = client.post('/api/auth/refresh')

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json() == {'detail': 'Too many authentication attempts'}
    assert calls['count'] == 1


def test_auth_refresh_rate_limit_applies_per_token_across_client_ips(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'old-refresh')

    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_TRUST_PROXY_HEADERS', True)
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_MAX_ATTEMPTS', 1)

    calls = {'count': 0}

    async def _fake_rotate(_session, *, refresh_token: str):
        calls['count'] += 1
        raise auth_router.HTTPException(status_code=401, detail='Invalid refresh token')

    monkeypatch.setattr(auth_router, 'rotate_refresh_token', _fake_rotate)

    first = client.post('/api/auth/refresh', headers={'x-forwarded-for': '198.51.100.10'})
    second = client.post('/api/auth/refresh', headers={'x-forwarded-for': '203.0.113.77'})

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json() == {'detail': 'Too many authentication attempts'}
    assert calls['count'] == 1


def test_auth_login_returns_503_when_shared_rate_limiter_backend_fails(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)

    monkeypatch.setattr(auth_router.settings, 'AUTH_PROVIDER_MODE', 'local')
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_LOGIN_MAX_ATTEMPTS', 1)

    async def _failing_shared_backend(**_kwargs):
        raise SQLAlchemyError('shared backend unavailable')

    async def _fake_authenticate(_session, *, username: str, password: str):
        return None

    monkeypatch.setattr(auth_router.auth_rate_limiter._shared_backend, 'check', _failing_shared_backend)
    monkeypatch.setattr(auth_router, 'authenticate_local_user', _fake_authenticate)

    response = client.post('/api/auth/login', json={'username': 'demo', 'password': 'bad'})

    assert response.status_code == 503
    assert response.json() == {'detail': 'Authentication rate limiting is temporarily unavailable'}


def test_auth_refresh_returns_503_when_shared_rate_limiter_backend_fails(monkeypatch):
    _reset_rate_limits()
    session = _FakeSession()
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'old-refresh')

    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_MAX_ATTEMPTS', 1)

    async def _failing_shared_backend(**_kwargs):
        raise SQLAlchemyError('shared backend unavailable')

    monkeypatch.setattr(auth_router.auth_rate_limiter._shared_backend, 'check', _failing_shared_backend)

    response = client.post('/api/auth/refresh')

    assert response.status_code == 503
    assert response.json() == {'detail': 'Authentication rate limiting is temporarily unavailable'}


def test_auth_refresh_cookie_forces_secure_outside_dev(monkeypatch):
    monkeypatch.setattr(auth_router.settings, 'IS_NON_PROD', False)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/auth')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_DOMAIN', None)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SAMESITE', 'lax')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SECURE', False)

    cookie_kwargs = auth_router._refresh_cookie_kwargs()

    assert cookie_kwargs['secure'] is True


def test_request_identity_ignores_forwarded_for_without_explicit_trust(monkeypatch):
    monkeypatch.setattr(auth_router.settings, 'AUTH_TRUST_PROXY_HEADERS', False)

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/api/auth/login',
        'headers': [(b'x-forwarded-for', b'203.0.113.50')],
        'client': ('127.0.0.1', 12345),
    }
    request = auth_router.Request(scope)

    assert auth_router._request_client_identity(request) == '127.0.0.1'


def test_request_identity_uses_forwarded_for_when_proxy_headers_are_trusted(monkeypatch):
    monkeypatch.setattr(auth_router.settings, 'AUTH_TRUST_PROXY_HEADERS', True)

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/api/auth/login',
        'headers': [(b'x-forwarded-for', b'203.0.113.50, 10.0.0.1')],
        'client': ('127.0.0.1', 12345),
    }
    request = auth_router.Request(scope)

    assert auth_router._request_client_identity(request) == '203.0.113.50'
