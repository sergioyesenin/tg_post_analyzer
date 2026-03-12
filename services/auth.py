from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import AuditLog, AuthRefreshToken, Role, User, UserRole


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    is_active: bool
    roles: tuple[str, ...]


_password_hasher = PasswordHasher()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        if isinstance(password_hash, str) and password_hash.startswith("$2"):
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        return bool(_password_hasher.verify(password_hash, password))
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(*, user_id: int, username: str, roles: list[str]) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.AUTH_ACCESS_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET, algorithm=settings.AUTH_JWT_ALG)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.AUTH_JWT_SECRET, algorithms=[settings.AUTH_JWT_ALG])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_roles(session: AsyncSession, user_id: int) -> list[str]:
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return [row[0] for row in (await session.execute(stmt)).all()]


async def get_user_roles_map(session: AsyncSession, user_ids: list[int]) -> dict[int, list[str]]:
    if not user_ids:
        return {}
    stmt = (
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(UserRole.user_id.asc(), Role.name.asc())
    )
    rows = (await session.execute(stmt)).all()
    roles_map: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
    for user_id, role_name in rows:
        roles_map.setdefault(int(user_id), []).append(str(role_name))
    return roles_map


async def authenticate_local_user(session: AsyncSession, *, username: str, password: str) -> AuthUser | None:
    user = await get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Backward-compat: transparently migrate legacy bcrypt hashes to Argon2id.
    if isinstance(user.password_hash, str) and user.password_hash.startswith("$2"):
        user.password_hash = hash_password(password)
        await session.flush()
    roles = await get_user_roles(session, user.id)
    return AuthUser(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        roles=tuple(sorted(roles)),
    )


async def ensure_roles_exist(session: AsyncSession, role_names: list[str]) -> list[Role]:
    stmt = select(Role).where(Role.name.in_(role_names))
    rows = (await session.execute(stmt)).scalars().all()
    role_by_name = {role.name: role for role in rows}
    missing = [name for name in role_names if name not in role_by_name]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown roles: {', '.join(missing)}")
    return [role_by_name[name] for name in role_names]


async def write_audit_log(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: int | None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details_json=details,
        )
    )
    await session.flush()


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user_id: int,
) -> str:
    raw_token = secrets.token_urlsafe(48)
    token_row = AuthRefreshToken(
        user_id=user_id,
        token_hash=_hash_refresh_token(raw_token),
        expires_at=_utcnow() + timedelta(days=settings.AUTH_REFRESH_TTL_DAYS),
        revoked_at=None,
        replaced_by_token_id=None,
    )
    session.add(token_row)
    await session.flush()
    return raw_token


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    refresh_token: str,
) -> tuple[AuthUser, str]:
    token_hash = _hash_refresh_token(refresh_token)
    now = _utcnow()
    token_row = (
        await session.execute(
            select(AuthRefreshToken)
            .where(AuthRefreshToken.token_hash == token_hash)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if token_row is None or token_row.revoked_at is not None or token_row.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await session.get(User, token_row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    roles = tuple(sorted(await get_user_roles(session, user.id)))
    auth_user = AuthUser(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        roles=roles,
    )

    token_row.revoked_at = now
    new_refresh_token = secrets.token_urlsafe(48)
    replacement_row = AuthRefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh_token(new_refresh_token),
        expires_at=now + timedelta(days=settings.AUTH_REFRESH_TTL_DAYS),
        revoked_at=None,
        replaced_by_token_id=None,
    )
    session.add(replacement_row)
    await session.flush()
    token_row.replaced_by_token_id = replacement_row.id
    return auth_user, new_refresh_token


async def revoke_refresh_token(
    session: AsyncSession,
    *,
    refresh_token: str,
) -> bool:
    token_hash = _hash_refresh_token(refresh_token)
    token_row = (
        await session.execute(
            select(AuthRefreshToken)
            .where(AuthRefreshToken.token_hash == token_hash)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if token_row is None:
        return False
    if token_row.revoked_at is None:
        token_row.revoked_at = _utcnow()
    await session.flush()
    return True
