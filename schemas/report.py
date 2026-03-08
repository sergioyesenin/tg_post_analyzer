from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ReportOut(BaseModel):
    id: int
    post_id: int
    status: str
    content: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
