from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class PostCardOut(BaseModel):
    id: int
    channel_id: int
    channel_username: str
    date: datetime
    text_preview: str | None
    comments_count: int
    views: int | None = None
    involvement: float | None
    reactions: dict | None = Field(default=None, alias="reactions_json")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class PostDetailOut(BaseModel):
    id: int
    channel_id: int
    text: str | None
    date: datetime
    comments_count: int
    views: int | None = None
    involvement: float | None = None
    reactions: dict | None = Field(default=None, alias="reactions_json")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
