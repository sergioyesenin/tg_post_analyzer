import pytest

from api.routers import auth as auth_router
from db.models import Role, User, UserRole
from services.auth import hash_password


def _seed_user(session_factory, *, user_id: int, username: str, password: str, email: str, roles: list[tuple[int, str]]) -> None:
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
                is_active=True,
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
