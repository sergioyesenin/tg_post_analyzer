from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class CommentOut(BaseModel):
    id: int
    post_id: int
    tg_peer_id: int
    tg_message_id: int
    parent_tg_message_id: int | None = None
    parent_comment_id: int | None = None
    thread_root_tg_message_id: int | None = None
    depth: int
    text: str
    date: datetime
    reactions: dict | None = Field(default=None, alias="reactions_json")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
