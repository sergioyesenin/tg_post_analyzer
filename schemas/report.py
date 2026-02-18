from datetime import datetime
from pydantic import BaseModel

class ReportOut(BaseModel):
    id: int
    post_id: int
    status: str
    content: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
