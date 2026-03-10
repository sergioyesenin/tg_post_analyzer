from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from services.settings_defaults import CANONICAL_SETTINGS_DEFAULTS


class _StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestSettings(_StrictConfigModel):
    lookback_days: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["lookback_days"], ge=1, le=3650)
    poll_seconds: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["poll_seconds"], ge=5, le=3600)
    max_posts_per_channel: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["max_posts_per_channel"], ge=1, le=2000)
    channel_concurrency: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["channel_concurrency"], ge=1, le=8)
    comment_first_delay_hours: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["comment_first_delay_hours"], ge=1, le=24)
    comment_interval_hours: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["comment_interval_hours"], ge=1, le=24)
    comment_window_hours: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["comment_window_hours"], ge=1, le=168)
    collect_comments_sleep_min_ms: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["collect_comments_sleep_min_ms"], ge=0, le=10000)
    collect_comments_sleep_max_ms: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["collect_comments_sleep_max_ms"], ge=0, le=15000)
    comment_schedule_jitter_seconds: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["ingest"]["comment_schedule_jitter_seconds"], ge=0, le=21600)


class ReportsSettings(_StrictConfigModel):
    post_report_delay_hours: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["reports"]["post_report_delay_hours"], ge=1, le=72)
    min_comments: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["reports"]["min_comments"], ge=0, le=100000)
    report_word_target: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["reports"]["report_word_target"], ge=50, le=3000)
    report_word_min: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["reports"]["report_word_min"], ge=50, le=3000)
    report_word_max: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["reports"]["report_word_max"], ge=50, le=5000)


class RetentionSettings(_StrictConfigModel):
    retention_days: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["retention"]["retention_days"], ge=1, le=3650)
    archive_batch_size: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["retention"]["archive_batch_size"], ge=10, le=50000)


class JobsSettings(_StrictConfigModel):
    job_batch_size: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["job_batch_size"], ge=1, le=5000)
    job_worker_concurrency: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["job_worker_concurrency"], ge=1, le=16)
    collect_comments_quota_per_run: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["collect_comments_quota_per_run"], ge=1, le=5000)
    ai_poll_seconds: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["ai_poll_seconds"], ge=5, le=3600)
    ai_scheduler_limit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["ai_scheduler_limit"], ge=1, le=10000)
    done_retention_days: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["done_retention_days"], ge=1, le=3650)
    dead_letter_retention_days: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["dead_letter_retention_days"], ge=1, le=3650)
    cleanup_batch_size: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["jobs"]["cleanup_batch_size"], ge=10, le=50000)


class ApiSettings(_StrictConfigModel):
    top_posts_default_limit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["api"]["top_posts_default_limit"], ge=1, le=500)


class MonitorSettings(_StrictConfigModel):
    disk_used_percent_warn: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["disk_used_percent_warn"], ge=1, le=99)
    disk_used_percent_crit: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["disk_used_percent_crit"], ge=1, le=99)
    memory_used_percent_warn: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["memory_used_percent_warn"], ge=1, le=99)
    memory_used_percent_crit: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["memory_used_percent_crit"], ge=1, le=99)
    pending_jobs_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["pending_jobs_warn"], ge=0, le=5_000_000)
    pending_jobs_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["pending_jobs_crit"], ge=0, le=5_000_000)
    pending_lag_seconds_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["pending_lag_seconds_warn"], ge=0, le=86400)
    pending_lag_seconds_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["pending_lag_seconds_crit"], ge=0, le=604800)
    retry_lag_seconds_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["retry_lag_seconds_warn"], ge=0, le=86400)
    retry_lag_seconds_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["retry_lag_seconds_crit"], ge=0, le=604800)
    database_latency_ms_warn: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["database_latency_ms_warn"], ge=0, le=60000)
    database_latency_ms_crit: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["database_latency_ms_crit"], ge=0, le=60000)
    dead_letter_count_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["dead_letter_count_warn"], ge=0, le=1_000_000)
    dead_letter_count_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["dead_letter_count_crit"], ge=0, le=1_000_000)
    ingest_lag_seconds_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["ingest_lag_seconds_warn"], ge=0, le=31_536_000)
    ingest_lag_seconds_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["ingest_lag_seconds_crit"], ge=0, le=31_536_000)
    backlog_delta_1h_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["backlog_delta_1h_warn"], ge=0, le=10_000_000)
    backlog_delta_1h_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["backlog_delta_1h_crit"], ge=0, le=10_000_000)
    collect_comments_flood_rate_warn: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["collect_comments_flood_rate_warn"], ge=0.0, le=1.0)
    collect_comments_flood_rate_crit: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["collect_comments_flood_rate_crit"], ge=0.0, le=1.0)
    collect_comments_rpc_rate_warn: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["collect_comments_rpc_rate_warn"], ge=0.0, le=1.0)
    collect_comments_rpc_rate_crit: float = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["collect_comments_rpc_rate_crit"], ge=0.0, le=1.0)
    archive_lag_seconds_warn: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["archive_lag_seconds_warn"], ge=0, le=31_536_000)
    archive_lag_seconds_crit: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["monitor"]["archive_lag_seconds_crit"], ge=0, le=31_536_000)
    telegram_disconnected_is_warn: bool = CANONICAL_SETTINGS_DEFAULTS["monitor"]["telegram_disconnected_is_warn"]


class FeaturesSettings(_StrictConfigModel):
    keyword_graph_api_enabled: bool = Field(default=CANONICAL_SETTINGS_DEFAULTS["features"]["keyword_graph_api_enabled"])
    keyword_graph_rollout_percent: int = Field(default=CANONICAL_SETTINGS_DEFAULTS["features"]["keyword_graph_rollout_percent"], ge=0, le=100)


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
