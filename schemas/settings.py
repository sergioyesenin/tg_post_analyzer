from datetime import datetime

from pydantic import BaseModel, Field


class AppSettingOut(BaseModel):
    key: str
    value_json: dict
    description: str | None = None
    updated_by_user_id: int | None = None
    updated_at: datetime


class AppSettingUpdateIn(BaseModel):
    value_json: dict = Field(
        ...,
        description="Частичный или полный объект настроек для указанного key.",
        examples=[
            {"poll_seconds": 120, "max_posts_per_channel": 150},
            {"post_report_delay_hours": 6, "min_comments": 20, "report_word_target": 350},
            {"retention_days": 30, "archive_batch_size": 1000},
        ],
    )
    description: str | None = None
