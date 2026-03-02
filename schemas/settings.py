from datetime import datetime

from pydantic import BaseModel


class AppSettingOut(BaseModel):
    key: str
    value_json: dict
    description: str | None = None
    updated_by_user_id: int | None = None
    updated_at: datetime


class AppSettingUpdateIn(BaseModel):
    value_json: dict
    description: str | None = None
