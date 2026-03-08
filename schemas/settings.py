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
        description="Partial or full settings object for the given key.",
        examples=[
            {"poll_seconds": 120, "max_posts_per_channel": 150},
            {"post_report_delay_hours": 6, "min_comments": 20, "report_word_target": 350},
            {"retention_days": 30, "archive_batch_size": 1000},
            {
                "disk_used_percent_warn": 80,
                "disk_used_percent_crit": 90,
                "pending_jobs_warn": 500,
                "pending_jobs_crit": 2000,
                "database_latency_ms_warn": 200,
                "database_latency_ms_crit": 1000,
                "telegram_disconnected_is_warn": True,
            },
        ],
    )
    description: str | None = None
