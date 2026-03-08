from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in_seconds: int
    roles: list[str]


class UserCreateIn(BaseModel):
    username: str
    password: str = Field(min_length=8)
    email: str | None = None
    full_name: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["analyst"])


class UserRolesIn(BaseModel):
    roles: list[str]


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    is_active: bool
    is_local: bool
    roles: list[str]
    created_at: datetime
