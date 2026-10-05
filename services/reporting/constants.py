from __future__ import annotations

# ── Публичные статусы отчётов ────────────────────────────────────────
REPORT_STATUS_DRAFT = "draft"
REPORT_STATUS_READY = "ready"
REPORT_STATUS_LIMITED = "limited"
REPORT_STATUS_INSUFFICIENT_DATA = "insufficient_data"
REPORT_STATUS_FAILED = "failed"
REPORT_STATUS_DEFERRED = "deferred_waiting_dependencies"
REPORT_STATUS_STALE = "stale"

# Статусы, чьи payload-ы можно агрегировать в event/process-отчёты.
AGGREGATABLE_REPORT_STATUSES = frozenset({REPORT_STATUS_READY, REPORT_STATUS_LIMITED})

# Текстовое представление "упавшего" отчёта (используется как content fallback).
REPORT_GENERATION_FAILED_CONTENT = "STATUS: FAILED\nREASON: report_generation_failed"

# Приоритеты job'ов, связанных с отчётами.
POST_REPORT_REBUILD_PRIORITY = 40

# Дефолтный порог комментариев для генерации post-отчёта.
DEFAULT_MIN_COMMENTS = 20