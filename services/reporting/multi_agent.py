"""Многоагентная логика reporting: feature flags, retrieval provider,
shadow compare, контракт-валидация.

Здесь только чистые функции и работа с feature flags из settings.
Никаких обращений к jobs и очередям.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.report import PostReportPayload
from services.reporting.constants import (
    REPORT_STATUS_READY,
)
from services.reporting.mapping import (
    _BLOCKING_REVIEWER_CODES,
    _TOPIC_STOPWORDS_RU,
    _clean_list_text,
    _has_structured_expert_claims,
    canonicalize_multi_agent_trace,
)
from services.reporting_v2 import (
    map_state_to_public_post_payload,
    run_post_orchestrator_v2,
)
from services.reporting_v2.searxng_provider import SearxngRetrievalProvider
from services.settings_store import get_all_settings


logger = logging.getLogger(__name__)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


@dataclass(frozen=True)
class ReportValidationResult:
    ok: bool
    critical: bool
    issues: list[dict[str, str]]


def _build_retrieval_provider(features: dict[str, Any] | None) -> SearxngRetrievalProvider | None:
    features = features if isinstance(features, dict) else {}

    enabled = bool(features.get("retrieval_provider_enabled", True))
    if not enabled:
        return None

    base_url = str(features.get("searxng_base_url") or "http://searxng:8080").strip()
    if not base_url:
        return None

    return SearxngRetrievalProvider(
        base_url=base_url,
        timeout_seconds=float(features.get("retrieval_timeout_seconds", 8.0)),
        max_results=int(features.get("retrieval_max_results", 6)),
        fetch_pages=bool(features.get("retrieval_fetch_pages", False)),
    )


def should_use_multi_agent_v2(
    *,
    post_id: int,
    features: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(features, dict):
        return False

    enabled = bool(features.get("multi_agent_mode_enabled", False))
    if not enabled:
        return False

    try:
        rollout_percent = int(features.get("multi_agent_rollout_percent", 0))
    except (TypeError, ValueError):
        return False
    rollout_percent = max(0, min(rollout_percent, 100))
    if rollout_percent <= 0:
        return False
    if rollout_percent >= 100:
        return True

    deterministic_bucket = abs(int(post_id)) % 100
    return deterministic_bucket < rollout_percent


def _is_multi_agent_shadow_mode_enabled(*, features: dict[str, Any] | None) -> bool:
    if not isinstance(features, dict):
        return False
    return bool(features.get("multi_agent_shadow_mode_enabled", False))


def _summary_preview(value: Any, *, max_len: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    return normalized[:max_len]


def _build_shadow_compare_payload(*, legacy_payload: dict, v2_payload: dict) -> dict[str, Any]:
    legacy_status = str(legacy_payload.get("status") or "")
    v2_status = str(v2_payload.get("status") or "")
    legacy_summary_preview = _summary_preview(legacy_payload.get("summary"))
    v2_summary_preview = _summary_preview(v2_payload.get("summary"))
    return {
        "legacy_status": legacy_status,
        "v2_status": v2_status,
        "legacy_summary_preview": legacy_summary_preview,
        "v2_summary_preview": v2_summary_preview,
        "same_status": legacy_status == v2_status,
        "same_summary": legacy_summary_preview == v2_summary_preview,
    }


async def _load_reporting_feature_flags(session: AsyncSession) -> dict[str, Any]:
    try:
        settings_payload = await get_all_settings(session)
    except Exception:
        return {}
    features = settings_payload.get("features")
    return features if isinstance(features, dict) else {}


async def build_post_report_v2_payload_from_orchestrator(
    *,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    thread_comments: list[dict[str, Any]],
    views: int | None,
    rerun_stage: str | None,
) -> dict:
    state = await run_post_orchestrator_v2(
        post_id=post_id,
        published_at_iso=published_at_iso,
        post_text=post_text,
        comments=comments,
        thread_comments=thread_comments,
        views=views,
        rerun_stage=rerun_stage,
    )
    payload = map_state_to_public_post_payload(
        state=state,
        post_id=post_id,
        published_at_iso=published_at_iso,
    )
    validated = PostReportPayload.model_validate(payload)
    return validated.model_dump(mode="python")


def validate_report_contract(payload: dict) -> ReportValidationResult:
    if not isinstance(payload, dict):
        return ReportValidationResult(ok=False, critical=True, issues=[{"code": "C0", "severity": "critical", "reason": "payload_not_dict"}])

    issues: list[dict[str, str]] = []
    summary = _clean_list_text(payload.get("summary")) or ""
    multi_agent = canonicalize_multi_agent_trace(payload)
    steps = dict((multi_agent.get("steps") or {}) if isinstance(multi_agent, dict) else {})
    synthesis = dict(steps.get("synthesis") or {})
    synthesis_text = _clean_list_text(synthesis.get("report_text") or synthesis.get("summary")) or ""
    if not summary and not synthesis_text:
        issues.append({"code": "C1", "severity": "critical", "reason": "empty_summary_and_synthesis"})

    language_meta = dict((payload.get("meta") or {}).get("language_normalization") or {})
    language_status = str(language_meta.get("status") or "")
    if not _CYRILLIC_RE.search(summary or synthesis_text) and language_status not in {"success", "partial"}:
        issues.append({"code": "C2", "severity": "critical", "reason": "summary_not_russian_and_not_normalized"})

    components = dict(synthesis.get("components") or {})
    for comp in ("event", "context", "reaction", "interpretation", "consequences"):
        if components.get(comp) is not True:
            issues.append({"code": "C3", "severity": "critical", "reason": f"missing_component:{comp}"})
            break

    retrieval = dict(multi_agent.get("retrieval") or {}) if isinstance(multi_agent, dict) else {}
    if bool(retrieval.get("used")) and not list(retrieval.get("sources") or []):
        issues.append({"code": "C4", "severity": "critical", "reason": "retrieval_used_without_sources"})

    expert = dict(steps.get("expert") or {})
    if str(expert.get("status") or "") == "completed" and not _has_structured_expert_claims(expert):
        issues.append({"code": "C5", "severity": "critical", "reason": "expert_completed_without_structured_claims"})

    reviewer = dict(steps.get("reviewer") or {})
    llm_reviewer = dict(reviewer.get("llm_reviewer") or {})
    reviewer_issues = list(llm_reviewer.get("issues") or [])
    final_decision = str(reviewer.get("decision") or "")
    if reviewer_issues and final_decision == "accept":
        issues.append({"code": "C6", "severity": "critical", "reason": "plain_accept_with_reviewer_issues"})

    topics = list(payload.get("topics") or [])
    topic_names = [str(item.get("name") or "").strip().lower() for item in topics if isinstance(item, dict)]
    if topic_names and all(name in _TOPIC_STOPWORDS_RU for name in topic_names):
        issues.append({"code": "C7", "severity": "critical", "reason": "topics_only_stopwords"})

    confidence = dict(payload.get("confidence") or {})
    confidence_overall = str(confidence.get("overall") or "")
    po = dict(steps.get("public_opinion") or {})
    has_limited_branch = any(
        str((steps.get(step) or {}).get("data_status") or "") in {"limited", "weak_signal"}
        for step in ("context", "expert", "public_opinion", "synthesis")
    )
    malformed_branch = bool(expert.get("malformed_output")) or bool(expert.get("contract_invalid"))
    if confidence_overall == "high" and (has_limited_branch or malformed_branch):
        issues.append({"code": "C8", "severity": "critical", "reason": "high_confidence_for_limited_or_malformed"})

    status = str(payload.get("status") or "")
    review_history = list((multi_agent.get("review") or {}).get("history") or []) if isinstance(multi_agent, dict) else []
    unresolved_blocking = any(
        str(item.get("decision") or "") in {"rerun_branch", "revise", "insufficient_data"}
        or str(item.get("reason") or "").split(":", 1)[0] in _BLOCKING_REVIEWER_CODES
        for item in review_history
        if isinstance(item, dict)
    )
    if status == REPORT_STATUS_READY and unresolved_blocking:
        issues.append({"code": "C9", "severity": "critical", "reason": "ready_with_unresolved_blocking_defects"})

    critical = any(item.get("severity") == "critical" for item in issues)
    return ReportValidationResult(ok=len(issues) == 0, critical=critical, issues=issues)