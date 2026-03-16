from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from api.routers import auth as auth_router
from deps import get_current_user
from services.auth import AuthUser


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


def _override_admin(client: TestClient) -> None:
    async def _fake_current_user():
        return AuthUser(id=1, username='admin', is_active=True, roles=('admin',))

    client.app.dependency_overrides[get_current_user] = _fake_current_user


def test_auth_login_smoke(monkeypatch):
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
