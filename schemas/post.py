from datetime import datetime
from pydantic import BaseModel

class PostCardOut(BaseModel):
    id: int
    channel_id: int
    channel_username: str
    date: datetime
    text_preview: str | None
    comments_count: int

class PostDetailOut(BaseModel):
    id: int
    channel_id: int
    text: str | None
    date: datetime
    comments_count: int
    views: int | None = None

    class Config:
        from_attributes = True
