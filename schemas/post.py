from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, computed_field
from services.dashboard.common import text_preview

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
    @computed_field
    @property
    def preview(self) -> str | None:
        """Вычисляет превью текста аналогично text_preview"""
        return text_preview(self.text)


