from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import auth as auth_router
from db.models import AuthRefreshToken, Role, User, UserRole
from deps import get_current_user
from services import auth as auth_service
from services.auth import AuthUser


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return type('_Scalars', (), {'all': lambda self_: list(self._rows)})()


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _AuthStore:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.now = now
        self.users = {
            1: User(
                id=1,
                username='admin',
                email='admin@example.com',
                full_name='Admin',
                password_hash=auth_router.hash_password('AdminPass123!'),
                is_active=True,
                is_local=True,
                created_at=now,
            ),
            2: User(
                id=2,
                username='viewer',
                email='viewer@example.com',
                full_name='Viewer',
                password_hash=auth_router.hash_password('ViewerPass123!'),
                is_active=True,
                is_local=True,
                created_at=now,
            ),
        }
        self.roles = {
            1: Role(id=1, name='admin', created_at=now),
            2: Role(id=2, name='viewer', created_at=now),
        }
        self.user_roles = [
            UserRole(user_id=1, role_id=1, created_at=now),
            UserRole(user_id=2, role_id=2, created_at=now),
        ]
        self.refresh_tokens: dict[int, AuthRefreshToken] = {}
        self.audit_logs: list[object] = []
        self.next_refresh_id = 1

    def add_refresh_token(self, *, user_id: int, raw_token: str, expires_at: datetime, revoked_at=None) -> AuthRefreshToken:
        row = AuthRefreshToken(
            id=self.next_refresh_id,
            user_id=user_id,
            token_hash=auth_service._hash_refresh_token(raw_token),
            expires_at=expires_at,
            revoked_at=revoked_at,
            replaced_by_token_id=None,
            created_at=self.now,
        )
        self.refresh_tokens[row.id] = row
        self.next_refresh_id += 1
        return row


class _FakeSession:
    def __init__(self, store: _AuthStore) -> None:
        self.store = store
        self.commit_calls = 0
        self.rollback_calls = 0
        self.execute_calls = 0
        self._pending: list[object] = []

    async def execute(self, stmt):
        self.execute_calls += 1
        sql = str(stmt)
        params = stmt.compile().params
        if 'FROM users' in sql and 'WHERE users.username' in sql:
            username = next(iter(params.values()))
            user = next((item for item in self.store.users.values() if item.username == username), None)
            return _ScalarOneOrNoneResult(user)
        if 'FROM auth_refresh_tokens' in sql:
            token_hash = next(iter(params.values()))
            row = next((item for item in self.store.refresh_tokens.values() if item.token_hash == token_hash), None)
            return _ScalarOneOrNoneResult(row)
        if 'SELECT users.id, users.username' in sql and 'FROM users' in sql:
            users = [self.store.users[user_id] for user_id in sorted(self.store.users)]
            return _ScalarsResult(users)
        if 'SELECT roles.name' in sql and 'WHERE user_roles.user_id =' in sql:
            user_id = int(next(iter(params.values())))
            role_names = []
            for link in self.store.user_roles:
                if link.user_id == user_id:
                    role_names.append((self.store.roles[link.role_id].name,))
            return _RowsResult(role_names)
        if 'SELECT user_roles.user_id, roles.name' in sql:
            rows = []
            for link in sorted(self.store.user_roles, key=lambda item: (item.user_id, self.store.roles[item.role_id].name)):
                rows.append((link.user_id, self.store.roles[link.role_id].name))
            return _RowsResult(rows)
        raise AssertionError(f'Unexpected SQL: {sql}')

    async def get(self, model, object_id: int):
        if model is User:
            return self.store.users.get(object_id)
        return None

    def add(self, row):
        self._pending.append(row)

    async def flush(self):
        for row in self._pending:
            if isinstance(row, AuthRefreshToken):
                if row.id is None:
                    row.id = self.store.next_refresh_id
                    self.store.next_refresh_id += 1
                self.store.refresh_tokens[row.id] = row
            else:
                self.store.audit_logs.append(row)
        self._pending.clear()

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


def _build_client(session: _FakeSession) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router.router, prefix='/api/auth')

    async def _fake_get_session():
        yield session

    app.dependency_overrides[auth_router.get_session] = _fake_get_session
    return TestClient(app)


def _auth_header(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _apply_cookie_settings(monkeypatch):
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_NAME', 'tgpa_refresh')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_PATH', '/api/auth')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_DOMAIN', None)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SAMESITE', 'lax')
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_COOKIE_SECURE', False)


def test_login_refresh_logout_and_revoked_refresh_flow(monkeypatch):
    store = _AuthStore()
    session = _FakeSession(store)
    client = _build_client(session)

    monkeypatch.setattr(auth_router.settings, 'AUTH_PROVIDER_MODE', 'local')
    monkeypatch.setattr(auth_router.settings, 'AUTH_ACCESS_TTL_MINUTES', 60)
    monkeypatch.setattr(auth_router.settings, 'AUTH_REFRESH_TTL_DAYS', 30)
    monkeypatch.setattr(auth_service, '_utcnow', lambda: store.now)
    monkeypatch.setattr(auth_router, 'write_audit_log', auth_router.write_audit_log)
    _apply_cookie_settings(monkeypatch)

    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'AdminPass123!'})
    assert login.status_code == 200
    login_payload = login.json()
    assert login_payload['roles'] == ['admin']
    assert login_payload['refresh_token'] is None
    first_cookie = login.cookies.get('tgpa_refresh')
    assert first_cookie

    refresh = client.post('/api/auth/refresh')
    assert refresh.status_code == 200
    refresh_payload = refresh.json()
    assert refresh_payload['refresh_token'] is None
    second_cookie = refresh.cookies.get('tgpa_refresh')
    assert second_cookie and second_cookie != first_cookie
    assert len(store.refresh_tokens) == 2

    logout = client.post(
        '/api/auth/logout',
        headers=_auth_header(refresh_payload['access_token']),
    )
    assert logout.status_code == 200
    assert logout.json() == {'status': 'ok', 'refresh_revoked': True}

    revoked_refresh = client.post('/api/auth/refresh')
    assert revoked_refresh.status_code == 401
    assert revoked_refresh.json()['detail'] == 'Refresh session is missing'


def test_refresh_rejects_expired_token(monkeypatch):
    store = _AuthStore()
    expired = store.add_refresh_token(
        user_id=1,
        raw_token='expired-token',
        expires_at=store.now - timedelta(seconds=1),
    )
    session = _FakeSession(store)
    client = _build_client(session)
    client.cookies.set('tgpa_refresh', 'expired-token')

    monkeypatch.setattr(auth_service, '_utcnow', lambda: store.now)
    monkeypatch.setattr(auth_router, 'write_audit_log', auth_router.write_audit_log)
    _apply_cookie_settings(monkeypatch)

    response = client.post('/api/auth/refresh')

    assert expired.expires_at < store.now
    assert response.status_code == 401
    assert response.json()['detail'] == 'Invalid refresh token'


def test_rbac_blocks_viewer_and_allows_admin_for_user_listing():
    store = _AuthStore()
    session = _FakeSession(store)
    client = _build_client(session)

    viewer_token = auth_router.create_access_token(user_id=2, username='viewer', roles=['viewer'])
    forbidden = client.get('/api/auth/users', headers=_auth_header(viewer_token))
    assert forbidden.status_code == 403
    assert forbidden.json()['detail'] == 'Insufficient permissions'

    admin_token = auth_router.create_access_token(user_id=1, username='admin', roles=['admin'])
    allowed = client.get('/api/auth/users', headers=_auth_header(admin_token))
    assert allowed.status_code == 200
    assert [item['username'] for item in allowed.json()] == ['admin', 'viewer']


def test_list_users_uses_bulk_role_loading_without_n_plus_one(monkeypatch):
    store = _AuthStore()
    session = _FakeSession(store)
    client = _build_client(session)

    async def _fake_current_user():
        return AuthUser(id=1, username='admin', is_active=True, roles=('admin',))

    app = client.app
    app.dependency_overrides[get_current_user] = _fake_current_user

    response = client.get('/api/auth/users')

    assert response.status_code == 200
    assert session.execute_calls == 2
    assert response.json() == [
        {
            'id': 1,
            'username': 'admin',
            'email': 'admin@example.com',
            'full_name': 'Admin',
            'is_active': True,
            'is_local': True,
            'roles': ['admin'],
            'created_at': store.now.isoformat().replace('+00:00', 'Z'),
        },
        {
            'id': 2,
            'username': 'viewer',
            'email': 'viewer@example.com',
            'full_name': 'Viewer',
            'is_active': True,
            'is_local': True,
            'roles': ['viewer'],
            'created_at': store.now.isoformat().replace('+00:00', 'Z'),
        },
    ]
