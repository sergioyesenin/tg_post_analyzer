"""Reporting package.

Здесь только реэкспорты публичного API пакета.
Вся логика вынесена в подмодули:

- constants.py       — статусы и константы
- mapping.py         — mapping внутреннего payload в публичный
- payload.py         — enrichment payload'а (reactions, audience stance, coverage)
- staleness.py       — управление stale-состоянием отчётов
- multi_agent.py     — feature flags, retrieval provider, contract validation
- post_reports.py    — build_post_report
- event_reports.py   — build_event_report_draft
- process_reports.py — build_process_report_draft
"""
from __future__ import annotations

from services.reporting.constants import (
    DEFAULT_MIN_COMMENTS,
    REPORT_GENERATION_FAILED_CONTENT,
    REPORT_STATUS_DEFERRED,
    REPORT_STATUS_DRAFT,
    REPORT_STATUS_FAILED,
    REPORT_STATUS_INSUFFICIENT_DATA,
    REPORT_STATUS_LIMITED,
    REPORT_STATUS_READY,
    REPORT_STATUS_STALE,
)
from services.reporting.event_reports import build_event_report_draft
from services.reporting.mapping import (
    canonicalize_multi_agent_trace,
    map_internal_post_report_to_public_payload,
    report_status_from_payload,
)
from services.reporting.multi_agent import (
    ReportValidationResult,
    build_post_report_v2_payload_from_orchestrator,
    should_use_multi_agent_v2,
    validate_report_contract,
)
from services.reporting.post_reports import build_post_report
from services.reporting.process_reports import build_process_report_draft
from services.reporting.staleness import (
    mark_report_payload_stale,
    sync_post_report_staleness,
)


__all__ = [
    # constants
    "DEFAULT_MIN_COMMENTS",
    "REPORT_GENERATION_FAILED_CONTENT",
    "REPORT_STATUS_DEFERRED",
    "REPORT_STATUS_DRAFT",
    "REPORT_STATUS_FAILED",
    "REPORT_STATUS_INSUFFICIENT_DATA",
    "REPORT_STATUS_LIMITED",
    "REPORT_STATUS_READY",
    "REPORT_STATUS_STALE",
    # mapping
    "canonicalize_multi_agent_trace",
    "map_internal_post_report_to_public_payload",
    "report_status_from_payload",
    # multi_agent
    "ReportValidationResult",
    "build_post_report_v2_payload_from_orchestrator",
    "should_use_multi_agent_v2",
    "validate_report_contract",
    # post_reports
    "build_post_report",
    # event_reports
    "build_event_report_draft",
    # process_reports
    "build_process_report_draft",
    # staleness
    "mark_report_payload_stale",
    "sync_post_report_staleness",
]