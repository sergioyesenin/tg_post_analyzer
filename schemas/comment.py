from datetime import datetime
from pydantic import BaseModel

class CommentOut(BaseModel):
    id: int
    post_id: int
    text: str
    date: datetime

    class Config:
        from_attributes = True
