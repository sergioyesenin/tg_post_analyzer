from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Role, User, UserRole
from deps import get_current_user, get_session, require_roles
from schemas.auth import LoginIn, TokenOut, UserCreateIn, UserOut, UserRolesIn
from services.auth import (
    AuthUser,
    authenticate_local_user,
    create_access_token,
    ensure_roles_exist,
    get_user_roles,
    get_user_roles_map,
    hash_password,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    write_audit_log,
)

router = APIRouter()


def _refresh_cookie_kwargs() -> dict:
    return {
        "key": settings.AUTH_REFRESH_COOKIE_NAME,
        "httponly": True,
        "secure": bool(settings.AUTH_REFRESH_COOKIE_SECURE),
        "samesite": str(settings.AUTH_REFRESH_COOKIE_SAMESITE),
        "domain": settings.AUTH_REFRESH_COOKIE_DOMAIN,
        "path": settings.AUTH_REFRESH_COOKIE_PATH,
    }


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        value=refresh_token,
        max_age=settings.AUTH_REFRESH_TTL_DAYS * 24 * 60 * 60,
        **_refresh_cookie_kwargs(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(**_refresh_cookie_kwargs())


def _read_refresh_cookie(request: Request) -> str:
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is missing")
    return refresh_token


async def _serialize_user(session: AsyncSession, user: User) -> UserOut:
    roles_map = await get_user_roles_map(session, [user.id])
    return _serialize_user_with_roles(user, roles_map)


def _serialize_user_with_roles(user: User, roles_map: dict[int, list[str]]) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_local=user.is_local,
        roles=roles_map.get(user.id, []),
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, response: Response, session: AsyncSession = Depends(get_session)):
    if settings.AUTH_PROVIDER_MODE.lower() != "local":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local login is disabled by AUTH_PROVIDER_MODE",
        )
    auth_user = await authenticate_local_user(session, username=data.username, password=data.password)
    if auth_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user_id=auth_user.id, username=auth_user.username, roles=list(auth_user.roles))
    refresh_token = await issue_refresh_token(session, user_id=auth_user.id)
    await write_audit_log(
        session,
        action="auth.login.success",
        actor_user_id=auth_user.id,
        target_type="user",
        target_id=str(auth_user.id),
    )
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenOut(
        access_token=token,
        refresh_token=None,
        expires_in_seconds=settings.AUTH_ACCESS_TTL_MINUTES * 60,
        roles=list(auth_user.roles),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    auth_user, new_refresh_token = await rotate_refresh_token(session, refresh_token=_read_refresh_cookie(request))
    token = create_access_token(user_id=auth_user.id, username=auth_user.username, roles=list(auth_user.roles))
    await write_audit_log(
        session,
        action="auth.refresh.success",
        actor_user_id=auth_user.id,
        target_type="user",
        target_id=str(auth_user.id),
    )
    await session.commit()
    _set_refresh_cookie(response, new_refresh_token)
    return TokenOut(
        access_token=token,
        refresh_token=None,
        expires_in_seconds=settings.AUTH_ACCESS_TTL_MINUTES * 60,
        roles=list(auth_user.roles),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    revoked = await revoke_refresh_token(session, refresh_token=refresh_token) if refresh_token else False
    await write_audit_log(
        session,
        action="auth.logout",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=str(current_user.id),
        details={"refresh_revoked": revoked},
    )
    await session.commit()
    _clear_refresh_cookie(response)
    return {"status": "ok", "refresh_revoked": revoked}


@router.get("/me", response_model=UserOut)
async def me(
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _serialize_user(session, user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    users = (await session.execute(select(User).order_by(User.id.asc()))).scalars().all()
    roles_map = await get_user_roles_map(session, [user.id for user in users])
    return [_serialize_user_with_roles(user, roles_map) for user in users]


@router.post("/users", response_model=UserOut)
async def create_user(
    data: UserCreateIn,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    existing = (await session.execute(select(User).where(User.username == data.username))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    roles = await ensure_roles_exist(session, data.roles or ["analyst"])
    user = User(
        username=data.username.strip(),
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        is_active=True,
        is_local=True,
    )
    session.add(user)
    await session.flush()

    for role in roles:
        session.add(UserRole(user_id=user.id, role_id=role.id))

    await write_audit_log(
        session,
        action="auth.user.create",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=str(user.id),
        details={"roles": [role.name for role in roles]},
    )
    await session.commit()
    return await _serialize_user(session, user)


@router.put("/users/{user_id}/roles", response_model=UserOut)
async def update_user_roles(
    user_id: int,
    data: UserRolesIn,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    roles = await ensure_roles_exist(session, data.roles)
    await session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
    for role in roles:
        session.add(UserRole(user_id=user_id, role_id=role.id))

    await write_audit_log(
        session,
        action="auth.user.update_roles",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=str(user.id),
        details={"roles": [role.name for role in roles]},
    )
    await session.commit()
    return await _serialize_user(session, user)


@router.put("/users/{user_id}/active", response_model=UserOut)
async def set_user_active(
    user_id: int,
    active: bool,
    current_user: AuthUser = Depends(require_roles("admin")),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = active
    await write_audit_log(
        session,
        action="auth.user.set_active",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=str(user.id),
        details={"active": active},
    )
    await session.commit()
    return await _serialize_user(session, user)
