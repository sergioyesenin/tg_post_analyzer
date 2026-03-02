from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestSettings(_StrictConfigModel):
    poll_seconds: int = Field(default=90, ge=5, le=3600)
    max_posts_per_channel: int = Field(default=100, ge=1, le=2000)
    comment_first_delay_hours: int = Field(default=2, ge=1, le=24)
    comment_interval_hours: int = Field(default=2, ge=1, le=24)
    comment_window_hours: int = Field(default=24, ge=1, le=168)


class ReportsSettings(_StrictConfigModel):
    post_report_delay_hours: int = Field(default=6, ge=1, le=72)
    min_comments: int = Field(default=20, ge=0, le=100000)
    report_word_target: int = Field(default=350, ge=50, le=3000)
    report_word_min: int = Field(default=200, ge=50, le=3000)
    report_word_max: int = Field(default=500, ge=50, le=5000)


class RetentionSettings(_StrictConfigModel):
    retention_days: int = Field(default=30, ge=1, le=3650)
    archive_batch_size: int = Field(default=1000, ge=10, le=50000)


class JobsSettings(_StrictConfigModel):
    job_batch_size: int = Field(default=50, ge=1, le=5000)


class ApiSettings(_StrictConfigModel):
    top_posts_default_limit: int = Field(default=20, ge=1, le=500)


SCHEMA_BY_KEY = {
    "ingest": IngestSettings,
    "reports": ReportsSettings,
    "retention": RetentionSettings,
    "jobs": JobsSettings,
    "api": ApiSettings,
}


def validate_setting_payload(key: str, payload: dict) -> dict:
    schema = SCHEMA_BY_KEY.get(key)
    if schema is None:
        raise ValueError(f"Unknown settings key: {key}")
    try:
        model = schema.model_validate(payload or {})
    except ValidationError:
        raise
    return model.model_dump()
