from datetime import datetime
from pydantic import BaseModel, ConfigDict

class PostCardOut(BaseModel):
    id: int
    channel_id: int
    channel_username: str
    date: datetime
    text_preview: str | None
    comments_count: int
    views: int | None = None
    involvement: float | None

class PostDetailOut(BaseModel):
    id: int
    channel_id: int
    text: str | None
    date: datetime
    comments_count: int
    views: int | None = None
    involvement: float | None = None

    model_config = ConfigDict(from_attributes=True)
