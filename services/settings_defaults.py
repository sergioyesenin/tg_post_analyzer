from __future__ import annotations

from copy import deepcopy


CANONICAL_SETTINGS_DEFAULTS: dict[str, dict] = {
    "ingest": {
        "lookback_days": 3,
        "poll_seconds": 240,
        "max_posts_per_channel": 30,
        "channel_concurrency": 1,
        "comment_first_delay_hours": 2,
        "comment_interval_hours": 2,
        "comment_window_hours": 24,
        "collect_comments_sleep_min_ms": 2500,
        "collect_comments_sleep_max_ms": 4500,
        "comment_schedule_jitter_seconds": 7200,
    },
    "reports": {
        "post_report_delay_hours": 12,
        "min_comments": 20,
        "report_word_target": 350,
        "report_word_min": 200,
        "report_word_max": 500,
    },
    "retention": {
        "retention_days": 30,
        "archive_batch_size": 1000,
    },
    "jobs": {
        "job_batch_size": 20,
        "job_worker_concurrency": 2,
        "collect_comments_quota_per_run": 2,
        "ai_poll_seconds": 120,
        "ai_scheduler_limit": 200,
        "done_retention_days": 14,
        "dead_letter_retention_days": 90,
        "cleanup_batch_size": 1000,
    },
    "api": {
        "top_posts_default_limit": 20,
    },
    "scheduler": {
        "enabled": False,
        "retention_hour": 3,
        "retention_minute": 0,
    },
    "monitor": {
        "disk_used_percent_warn": 80,
        "disk_used_percent_crit": 90,
        "memory_used_percent_warn": 80,
        "memory_used_percent_crit": 90,
        "pending_jobs_warn": 500,
        "pending_jobs_crit": 2000,
        "pending_lag_seconds_warn": 1800,
        "pending_lag_seconds_crit": 7200,
        "retry_lag_seconds_warn": 1800,
        "retry_lag_seconds_crit": 7200,
        "database_latency_ms_warn": 200,
        "database_latency_ms_crit": 1000,
        "dead_letter_count_warn": 1,
        "dead_letter_count_crit": 20,
        "ingest_lag_seconds_warn": 1800,
        "ingest_lag_seconds_crit": 7200,
        "backlog_delta_1h_warn": 200,
        "backlog_delta_1h_crit": 1000,
        "collect_comments_flood_rate_warn": 0.2,
        "collect_comments_flood_rate_crit": 0.5,
        "collect_comments_rpc_rate_warn": 0.1,
        "collect_comments_rpc_rate_crit": 0.3,
        "archive_lag_seconds_warn": 86400,
        "archive_lag_seconds_crit": 259200,
        "telegram_disconnected_is_warn": True,
    },
    "features": {
        "keyword_graph_api_enabled": True,
        "keyword_graph_rollout_percent": 100,
        "scheduler_retention_v2": False,
    },
}


def get_canonical_defaults() -> dict[str, dict]:
    return deepcopy(CANONICAL_SETTINGS_DEFAULTS)


def get_default_setting(scope: str, key: str):
    return deepcopy(CANONICAL_SETTINGS_DEFAULTS[scope][key])
