from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import AuditLog, Role, User, UserRole


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    is_active: bool
    roles: tuple[str, ...]


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(*, user_id: int, username: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
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


async def authenticate_local_user(session: AsyncSession, *, username: str, password: str) -> AuthUser | None:
    user = await get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
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
