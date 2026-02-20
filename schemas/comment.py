from datetime import datetime
from pydantic import BaseModel

class CommentOut(BaseModel):
    id: int
    post_id: int
    tg_message_id: int
    parent_tg_message_id: int | None = None
    parent_comment_id: int | None = None
    thread_root_tg_message_id: int | None = None
    depth: int
    text: str
    date: datetime

    class Config:
        from_attributes = True
