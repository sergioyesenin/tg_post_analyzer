from collections.abc import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.session import AsyncSessionLocal
from services.auth import AuthUser, decode_access_token, get_user_roles

bearer_scheme = HTTPBearer(auto_error=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(credentials.credentials)
    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    roles = tuple(sorted(await get_user_roles(session, user.id)))
    return AuthUser(id=user.id, username=user.username, is_active=user.is_active, roles=roles)


def require_roles(*role_names: str):
    role_set = set(role_names)

    async def dependency(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if role_set and not role_set.intersection(set(current_user.roles)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency
