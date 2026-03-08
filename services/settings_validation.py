from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestSettings(_StrictConfigModel):
    poll_seconds: int = Field(default=240, ge=5, le=3600)
    max_posts_per_channel: int = Field(default=30, ge=1, le=2000)
    comment_first_delay_hours: int = Field(default=2, ge=1, le=24)
    comment_interval_hours: int = Field(default=2, ge=1, le=24)
    comment_window_hours: int = Field(default=24, ge=1, le=168)
    collect_comments_sleep_min_ms: int = Field(default=2000, ge=0, le=10000)
    collect_comments_sleep_max_ms: int = Field(default=4000, ge=0, le=15000)
    comment_schedule_jitter_seconds: int = Field(default=7200, ge=0, le=21600)


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
    job_batch_size: int = Field(default=20, ge=1, le=5000)
    collect_comments_quota_per_run: int = Field(default=5, ge=1, le=5000)


class ApiSettings(_StrictConfigModel):
    top_posts_default_limit: int = Field(default=20, ge=1, le=500)


class MonitorSettings(_StrictConfigModel):
    disk_used_percent_warn: float = Field(default=80, ge=1, le=99)
    disk_used_percent_crit: float = Field(default=90, ge=1, le=99)
    memory_used_percent_warn: float = Field(default=80, ge=1, le=99)
    memory_used_percent_crit: float = Field(default=90, ge=1, le=99)
    pending_jobs_warn: int = Field(default=500, ge=0, le=5_000_000)
    pending_jobs_crit: int = Field(default=2000, ge=0, le=5_000_000)
    pending_lag_seconds_warn: int = Field(default=1800, ge=0, le=86400)
    pending_lag_seconds_crit: int = Field(default=7200, ge=0, le=604800)
    retry_lag_seconds_warn: int = Field(default=1800, ge=0, le=86400)
    retry_lag_seconds_crit: int = Field(default=7200, ge=0, le=604800)
    database_latency_ms_warn: float = Field(default=200, ge=0, le=60000)
    database_latency_ms_crit: float = Field(default=1000, ge=0, le=60000)
    dead_letter_count_warn: int = Field(default=1, ge=0, le=1_000_000)
    dead_letter_count_crit: int = Field(default=20, ge=0, le=1_000_000)
    ingest_lag_seconds_warn: int = Field(default=1800, ge=0, le=31_536_000)
    ingest_lag_seconds_crit: int = Field(default=7200, ge=0, le=31_536_000)
    backlog_delta_1h_warn: int = Field(default=200, ge=0, le=10_000_000)
    backlog_delta_1h_crit: int = Field(default=1000, ge=0, le=10_000_000)
    collect_comments_flood_rate_warn: float = Field(default=0.2, ge=0.0, le=1.0)
    collect_comments_flood_rate_crit: float = Field(default=0.5, ge=0.0, le=1.0)
    collect_comments_rpc_rate_warn: float = Field(default=0.1, ge=0.0, le=1.0)
    collect_comments_rpc_rate_crit: float = Field(default=0.3, ge=0.0, le=1.0)
    archive_lag_seconds_warn: int = Field(default=86400, ge=0, le=31_536_000)
    archive_lag_seconds_crit: int = Field(default=259200, ge=0, le=31_536_000)
    telegram_disconnected_is_warn: bool = True


class FeaturesSettings(_StrictConfigModel):
    keyword_graph_api_enabled: bool = Field(default=False)
    keyword_graph_rollout_percent: int = Field(default=0, ge=0, le=100)


SCHEMA_BY_KEY = {
    "ingest": IngestSettings,
    "reports": ReportsSettings,
    "retention": RetentionSettings,
    "jobs": JobsSettings,
    "api": ApiSettings,
    "monitor": MonitorSettings,
    "features": FeaturesSettings,
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
