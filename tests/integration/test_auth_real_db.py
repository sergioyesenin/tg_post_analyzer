import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.routers import auth as auth_router
from db.models import AuthRefreshToken, Role, User, UserRole
from services.auth import hash_password
from services.auth_rate_limit import reset_auth_rate_limits


def _seed_user(
    session_factory,
    *,
    user_id: int,
    username: str,
    password: str,
    email: str,
    roles: list[tuple[int, str]],
    is_active: bool = True,
) -> None:
    with session_factory() as session:
        for role_id, role_name in roles:
            session.add(Role(id=role_id, name=role_name))
        session.add(
            User(
                id=user_id,
                username=username,
                email=email,
                full_name=username.title(),
                password_hash=hash_password(password),
                is_active=is_active,
                is_local=True,
            )
        )
        for role_id, _ in roles:
            session.add(UserRole(user_id=user_id, role_id=role_id))
        session.commit()


@pytest.mark.integration
def test_auth_login_refresh_logout_flow_against_real_db(integration_client, integration_sync_session_factory) -> None:
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="admin",
        password="AdminPass123!",
        email="admin@example.com",
        roles=[(1, "admin")],
    )

    login = integration_client.post("/api/auth/login", json={"username": "admin", "password": "AdminPass123!"})

    assert login.status_code == 200
    assert login.json()["refresh_token"] is None
    assert login.cookies.get("tgpa_refresh")

    refresh = integration_client.post("/api/auth/refresh")

    assert refresh.status_code == 200
    access_token = refresh.json()["access_token"]

    logout = integration_client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert logout.status_code == 200
    assert logout.json()["refresh_revoked"] is True


@pytest.mark.integration
def test_inactive_user_cannot_login_or_refresh_existing_session_against_real_db(
    integration_client,
    integration_sync_session_factory,
) -> None:
    # Given an existing user who first had a valid refresh session and is then deactivated in the database.
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="inactive_user",
        password="InactivePass123!",
        email="inactive@example.com",
        roles=[(1, "admin")],
        is_active=True,
    )

    initial_login = integration_client.post("/api/auth/login", json={"username": "inactive_user", "password": "InactivePass123!"})
    assert initial_login.status_code == 200
    original_refresh_cookie = initial_login.cookies.get("tgpa_refresh")
    assert original_refresh_cookie

    with integration_sync_session_factory() as session:
        user = session.get(User, 1)
        assert user is not None
        user.is_active = False
        tokens_before = session.execute(select(AuthRefreshToken).order_by(AuthRefreshToken.id.asc())).scalars().all()
        assert len(tokens_before) == 1
        original_token_row = tokens_before[0]
        original_token_id = int(original_token_row.id)
        assert original_token_row.revoked_at is None
        assert original_token_row.replaced_by_token_id is None
        session.commit()

    # When login and refresh are attempted after deactivation.
    rejected_login = integration_client.post("/api/auth/login", json={"username": "inactive_user", "password": "InactivePass123!"})
    rejected_refresh = integration_client.post("/api/auth/refresh")

    # Then both are rejected, no new credentials are issued, and the existing refresh session is not rotated.
    assert rejected_login.status_code == 401
    assert rejected_login.json() == {"detail": "Invalid credentials"}
    assert "tgpa_refresh" not in rejected_login.cookies

    assert rejected_refresh.status_code == 401
    assert rejected_refresh.json() == {"detail": "Invalid refresh token"}
    assert "tgpa_refresh" not in rejected_refresh.cookies

    with integration_sync_session_factory() as session:
        tokens_after = session.execute(select(AuthRefreshToken).order_by(AuthRefreshToken.id.asc())).scalars().all()
        assert len(tokens_after) == 1
        assert int(tokens_after[0].id) == original_token_id
        assert tokens_after[0].revoked_at is None
        assert tokens_after[0].replaced_by_token_id is None


@pytest.mark.integration
def test_inactive_user_existing_access_token_is_rejected_on_protected_route_against_real_db(
    integration_client,
    integration_sync_session_factory,
) -> None:
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="inactive_access_user",
        password="InactiveAccess123!",
        email="inactive-access@example.com",
        roles=[(1, "admin")],
        is_active=True,
    )

    login = integration_client.post("/api/auth/login", json={"username": "inactive_access_user", "password": "InactiveAccess123!"})
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    with integration_sync_session_factory() as session:
        user = session.get(User, 1)
        assert user is not None
        user.is_active = False
        session.commit()

    protected = integration_client.get(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert protected.status_code == 401
    assert protected.json() == {"detail": "User not found or inactive"}


@pytest.mark.integration
def test_login_rate_limit_blocks_repeated_failed_attempts_against_real_db(
    integration_client,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real local user whose login path can be failed repeatedly.
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="rate_limited_login_user",
        password="CorrectPass123!",
        email="rate-limited-login@example.com",
        roles=[(1, "admin")],
    )
    integration_client.cookies.clear()

    import asyncio

    asyncio.run(reset_auth_rate_limits())

    monkeypatch.setattr(auth_router.settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_router.settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)

    # When failed login attempts reach and exceed the configured limit.
    first = integration_client.post("/api/auth/login", json={"username": "rate_limited_login_user", "password": "wrong-pass"})
    second = integration_client.post("/api/auth/login", json={"username": "rate_limited_login_user", "password": "wrong-pass"})
    limited = integration_client.post("/api/auth/login", json={"username": "rate_limited_login_user", "password": "wrong-pass"})

    # Then the auth path becomes visibly rate-limited instead of continuing normal credential checks.
    assert first.status_code == 401
    assert first.json() == {"detail": "Invalid credentials"}
    assert second.status_code == 401
    assert second.json() == {"detail": "Invalid credentials"}

    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many authentication attempts"}
    assert limited.headers["Retry-After"]
    assert "tgpa_refresh" not in limited.cookies


@pytest.mark.integration
def test_login_rate_limit_expires_and_allows_normal_auth_flow_against_real_db(
    integration_client,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real local user and a login path whose rate-limit budget is exhausted.
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="rate_limit_user",
        password="RightPass123!",
        email="rate-limit@example.com",
        roles=[(1, "admin")],
    )
    integration_client.cookies.clear()

    import asyncio

    asyncio.run(reset_auth_rate_limits())

    frozen_now = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_router.settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_router.settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr("services.auth_rate_limit._utcnow", lambda: frozen_now)

    first = integration_client.post("/api/auth/login", json={"username": "rate_limit_user", "password": "wrong-pass"})
    second = integration_client.post("/api/auth/login", json={"username": "rate_limit_user", "password": "wrong-pass"})
    limited = integration_client.post("/api/auth/login", json={"username": "rate_limit_user", "password": "wrong-pass"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many authentication attempts"}

    # When time moves beyond the configured rate-limit window and a new login is attempted.
    monkeypatch.setattr("services.auth_rate_limit._utcnow", lambda: frozen_now + timedelta(seconds=61))
    after_window = integration_client.post("/api/auth/login", json={"username": "rate_limit_user", "password": "RightPass123!"})

    # Then the old window no longer keeps the user blocked: the request goes through the normal auth flow.
    assert after_window.status_code == 200
    assert after_window.json()["refresh_token"] is None
    assert after_window.json()["roles"] == ["admin"]
    assert after_window.cookies.get("tgpa_refresh")


@pytest.mark.integration
def test_refresh_rate_limit_blocks_repeated_failed_attempts_against_real_db(
    integration_client,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="refresh_rate_limited_user",
        password="RefreshPass123!",
        email="refresh-rate-limit@example.com",
        roles=[(1, "admin")],
    )
    integration_client.cookies.clear()

    import asyncio

    asyncio.run(reset_auth_rate_limits())

    monkeypatch.setattr(auth_router.settings, "AUTH_REFRESH_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_router.settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)

    integration_client.cookies.set("tgpa_refresh", "invalid-refresh-token")

    first = integration_client.post("/api/auth/refresh")
    second = integration_client.post("/api/auth/refresh")
    limited = integration_client.post("/api/auth/refresh")

    assert first.status_code == 401
    assert first.json() == {"detail": "Invalid refresh token"}
    assert second.status_code == 401
    assert second.json() == {"detail": "Invalid refresh token"}

    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many authentication attempts"}
    assert limited.headers["Retry-After"]
    assert "tgpa_refresh" not in limited.cookies


@pytest.mark.integration
def test_refresh_rate_limit_expires_and_allows_normal_refresh_flow_against_real_db(
    integration_client,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="refresh_window_user",
        password="RefreshWindow123!",
        email="refresh-window@example.com",
        roles=[(1, "admin")],
    )
    integration_client.cookies.clear()

    login = integration_client.post("/api/auth/login", json={"username": "refresh_window_user", "password": "RefreshWindow123!"})
    assert login.status_code == 200
    valid_refresh_cookie = login.cookies.get("tgpa_refresh")
    assert valid_refresh_cookie

    import asyncio

    asyncio.run(reset_auth_rate_limits())

    frozen_now = datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_router.settings, "AUTH_REFRESH_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_router.settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr("services.auth_rate_limit._utcnow", lambda: frozen_now)

    integration_client.cookies.set("tgpa_refresh", "invalid-refresh-token")

    first = integration_client.post("/api/auth/refresh")
    second = integration_client.post("/api/auth/refresh")
    limited = integration_client.post("/api/auth/refresh")

    assert first.status_code == 401
    assert second.status_code == 401
    assert limited.status_code == 429
    assert limited.json() == {"detail": "Too many authentication attempts"}

    monkeypatch.setattr("services.auth_rate_limit._utcnow", lambda: frozen_now + timedelta(seconds=61))
    integration_client.cookies.set("tgpa_refresh", valid_refresh_cookie)

    after_window = integration_client.post("/api/auth/refresh")

    assert after_window.status_code == 200
    assert after_window.json()["refresh_token"] is None
    assert after_window.json()["roles"] == ["admin"]
    assert after_window.cookies.get("tgpa_refresh")


@pytest.mark.integration
def test_create_user_reports_duplicate_username_and_email_against_real_db(integration_client, integration_sync_session_factory) -> None:
    _seed_user(
        integration_sync_session_factory,
        user_id=1,
        username="admin",
        password="AdminPass123!",
        email="admin@example.com",
        roles=[(1, "admin")],
    )
    _seed_user(
        integration_sync_session_factory,
        user_id=2,
        username="existing",
        password="ExistingPass123!",
        email="existing@example.com",
        roles=[(2, "analyst")],
    )
    admin_token = auth_router.create_access_token(user_id=1, username="admin", roles=["admin"])

    duplicate_username = integration_client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "existing",
            "password": "Password123!",
            "email": "new@example.com",
            "roles": ["analyst"],
        },
    )
    duplicate_email = integration_client.post(
        "/api/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "new-user",
            "password": "Password123!",
            "email": "existing@example.com",
            "roles": ["analyst"],
        },
    )

    assert duplicate_username.status_code == 409
    assert duplicate_username.json() == {"detail": "Username already exists"}
    assert duplicate_email.status_code == 409
    assert duplicate_email.json() == {"detail": "Email already exists"}
