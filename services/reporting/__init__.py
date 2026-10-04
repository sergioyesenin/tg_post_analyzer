from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Comment, Event, EventPost, EventReport, Job, Post, Process, ProcessEvent, ProcessReport, Report
from schemas.report import PostReportPayload
from services.jobs import JOB_STATUS_DONE, JobType
from services.ingest import upsert_report
from services.report_aggregation import build_process_report_payload
from services.settings_store import get_all_settings
from services.reporting_v2 import (
    build_event_report_v2_impl,
    generate_post_report_payload_v2,
    map_state_to_public_post_payload,
    run_post_orchestrator_v2,
)

from services.reporting_v2.searxng_provider import SearxngRetrievalProvider
from services.report_language import (
    ReportLanguageNormalizationError,
    iter_public_text_fields,
    normalize_report_language,
)

from services.reporting.mapping import (
    _BLOCKING_REVIEWER_CODES,
    _TOPIC_STOPWORDS_RU,
    _is_payload_dependency_ready,
    _build_public_post_summary,
    _localize_public_section_labels,
    _has_structured_expert_claims,
    map_internal_post_report_to_public_payload,
    _clean_list_text,
    _stringify_path,
    _value_by_path,
    _normalize_public_opinion_semantics,
    _trim_sentence,
    canonicalize_multi_agent_trace,
    report_status_from_payload,
    _canonicalize_multi_agent_trace,
)

from services.reporting.constants import (
    REPORT_GENERATION_FAILED_CONTENT,
    REPORT_STATUS_DEFERRED,
    REPORT_STATUS_DRAFT,
    REPORT_STATUS_FAILED,
    REPORT_STATUS_LIMITED,
    REPORT_STATUS_READY,
    REPORT_STATUS_STALE,
    REPORT_STATUS_INSUFFICIENT_DATA,
)

from services.reporting.payload import (
    _aggregate_child_coverage,
    _enrich_post_report_payload,
)

from services.reporting.staleness import (
    _build_post_report_input_signature,
    _load_post_refresh_attempt_info,
    mark_report_payload_stale,
    sync_post_report_staleness,
)

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


def _build_dependency(job_type: str, *, entity_id: int, reason: str) -> dict:
    entity_key = {
        JobType.REFRESH_COMMENTS: "post_id",
        JobType.BUILD_POST_REPORT: "post_id",
        JobType.BUILD_EVENT_REPORT: "event_id",
        JobType.BUILD_PROCESS_REPORT: "process_id",
    }.get(job_type)
    if entity_key is None:
        raise ValueError(f"Unsupported dependency job type: {job_type}")
    return {
        "job_type": job_type,
        entity_key: int(entity_id),
        "reason": reason,
    }

def validate_report_contract(payload: dict) -> ReportValidationResult:
    if not isinstance(payload, dict):
        return ReportValidationResult(ok=False, critical=True, issues=[{"code": "C0", "severity": "critical", "reason": "payload_not_dict"}])

    issues: list[dict[str, str]] = []
    summary = _clean_list_text(payload.get("summary")) or ""
    multi_agent = _canonicalize_multi_agent_trace(payload)
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


async def _post_report_readiness(session: AsyncSession, *, post: Post) -> dict:
    if not (post.text or "").strip():
        return {
            "ready": False,
            "reason": "missing_post_text",
            "dependencies": [],
            "terminal": True,
        }

    refresh_attempt = await _load_post_refresh_attempt_info(session, post_id=int(post.id))
    if refresh_attempt is None:
        return {
            "ready": False,
            "reason": "waiting_refresh_post_data",
            "dependencies": [
                _build_dependency(
                    JobType.REFRESH_COMMENTS,
                    entity_id=int(post.id),
                    reason="waiting_refresh_post_data",
                )
            ],
            "terminal": False,
        }

    return {
        "ready": True,
        "reason": "ready",
        "dependencies": [],
        "terminal": False,
        "refresh_attempt": refresh_attempt,
    }


def _render_event_or_process_text(payload: dict) -> str:
    summary = _localize_public_section_labels(str(payload.get("summary") or ""))
    return _trim_sentence(summary, fallback="Недостаточно данных для итогового описания.")


def _render_post_report_text(payload: dict) -> str:
    return _build_public_post_summary(payload)



async def build_post_report(
    session: AsyncSession,
    *,
    post_id: int,
    job_timeout_seconds: int | None = None
) -> dict:
    post_result = await session.execute(
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = post_result.first()
    if row is None:
        return {"status": "not_found", "post_id": post_id}

    post, channel = row
    readiness = await _post_report_readiness(session, post=post)
    if not readiness.get("ready"):
        status = REPORT_STATUS_FAILED if readiness.get("terminal") else REPORT_STATUS_DEFERRED
        return {
            "status": status,
            "post_id": post.id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    comments_result = await session.execute(
        select(
            Comment.tg_message_id,
            Comment.parent_tg_message_id,
            Comment.thread_root_tg_message_id,
            Comment.depth,
            Comment.date,
            Comment.text,
            Comment.reactions_json,
        )
        .where(Comment.post_id == post.id)
        .order_by(Comment.date.asc(), Comment.id.asc())
    )
    comment_rows = comments_result.all()
    input_signature = _build_post_report_input_signature(post=post, comment_rows=comment_rows)

    comments: list[str] = []
    thread_comments: list[dict] = []
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, reactions_json in comment_rows:
        if not text or not text.strip():
            continue
        comments.append(text)
        normalized_parent_id = parent_tg_message_id
        if thread_root_tg_message_id is not None and parent_tg_message_id == thread_root_tg_message_id:
            normalized_parent_id = None
        thread_comments.append(
            {
                "id": tg_message_id,
                "parent_id": normalized_parent_id,
                "depth": depth,
                "date": date.isoformat() if date is not None else None,
                "text": text,
            }
        )

    channel_label = f"@{channel.username}" if channel.username else f"channel:{channel.id}"
    status = REPORT_STATUS_READY
    report_json: dict | None = None
    shadow_compare: dict[str, Any] | None = None
    try:
        features = await _load_reporting_feature_flags(session)
        use_multi_agent_v2 = should_use_multi_agent_v2(post_id=int(post.id), features=features)
        shadow_mode_enabled = _is_multi_agent_shadow_mode_enabled(features=features)
        logger.info(
            "build_post_report path decision post_id=%s use_multi_agent_v2=%s shadow_mode_enabled=%s",
            post.id,
            use_multi_agent_v2,
            shadow_mode_enabled,
        )
        retrieval_provider = _build_retrieval_provider(features)

        report_json = await generate_post_report_payload_v2(
        channel=channel_label,
        post_id=post.id,
        published_at_iso=post.date.isoformat(),
        post_text=post.text or "",
        comments=comments,
        thread_comments=thread_comments,
        views=post.views,
        job_timeout_seconds=job_timeout_seconds,
        effective_features=features,
        retrieval_provider=retrieval_provider,
        )
        logger.info(
            "build_post_report selected path post_id=%s",
            post.id
        )
        report_json = map_internal_post_report_to_public_payload(report_json)
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)

        report_json = _enrich_post_report_payload(payload=report_json, post=post, comment_rows=comment_rows)
        report_json.setdefault("post_id", post.id)
        report_json.setdefault("published_at", post.date.isoformat())
        report_json["meta"] = {
            **dict(report_json.get("meta") or {}),
            "input_signature": input_signature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refresh_attempt": readiness.get("refresh_attempt"),
        }
        report_json = PostReportPayload.model_validate(report_json).model_dump(mode="python")
        pre_normalization_payload = dict(report_json)
        pre_normalization_status = str(report_json.get("status") or "")
        try:
            report_json = await normalize_report_language(report_json)
            translated_fields: list[str] = []
            for path, _text in list(iter_public_text_fields(report_json)):
                before_text = _value_by_path(pre_normalization_payload, path)
                after_text = _value_by_path(report_json, path)
                if isinstance(before_text, str) and isinstance(after_text, str) and before_text != after_text:
                    translated_fields.append(_stringify_path(path))
            if translated_fields:
                logger.warning(
                    "report language normalized",
                    extra={
                        "post_id": post.id,
                        "fields": translated_fields,
                        "source_lang": "en_or_mixed",
                        "target_lang": "ru",
                    },
                )
        except ReportLanguageNormalizationError as language_exc:
            logger.warning("Post report language normalization was partial post_id=%s err=%s", post.id, language_exc)
            report_json["status"] = REPORT_STATUS_LIMITED
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "language_normalization": {
                    "status": "partial",
                    "error": str(language_exc),
                },
            }
            logger.warning(
                "report status downgraded",
                extra={
                    "post_id": post.id,
                    "from_status": pre_normalization_status or "unknown",
                    "to_status": str(report_json.get("status") or REPORT_STATUS_LIMITED),
                    "issues": ["language_normalization_partial"],
                },
            )
        except Exception as language_exc:
            logger.warning("Post report language normalization failed post_id=%s err=%s", post.id, language_exc)
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "language_normalization": {
                    "status": "failed",
                    "error": f"{type(language_exc).__name__}: {language_exc}",
                },
            }
        contract_result = validate_report_contract(report_json)
        if contract_result.issues:
            logger.warning(
                "report validation issues detected",
                extra={
                    "post_id": post.id,
                    "critical": contract_result.critical,
                    "issues": contract_result.issues,
                },
            )
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "validation": {
                    "ok": contract_result.ok,
                    "critical": contract_result.critical,
                    "issues": contract_result.issues,
                },
            }
        if contract_result.critical:
            previous_status = str(report_json.get("status") or "")
            report_json["status"] = REPORT_STATUS_LIMITED
            confidence_payload = dict(report_json.get("confidence") or {})
            confidence_payload["overall"] = "low" if any(item.get("code") in {"C1", "C3", "C5", "C9"} for item in contract_result.issues) else "medium"
            confidence_payload["reason"] = "contract_validator_downgrade"
            report_json["confidence"] = confidence_payload
            logger.warning(
                "report status downgraded",
                extra={
                    "post_id": post.id,
                    "from_status": previous_status or "unknown",
                    "to_status": REPORT_STATUS_LIMITED,
                    "issues": [str(item.get("reason") or item.get("code") or "validation_issue") for item in contract_result.issues],
                },
            )
        report_json = PostReportPayload.model_validate(report_json).model_dump(mode="python")
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)
        if status != str(report_json.get("status") or ""):
            logger.info(
                "report final status resolved",
                extra={
                    "post_id": post.id,
                    "payload_status": str(report_json.get("status") or ""),
                    "resolved_status": status,
                    "reason": "report_status_from_payload",
                },
            )
        if status == REPORT_STATUS_FAILED:
            content = REPORT_GENERATION_FAILED_CONTENT
            technical_error = str((report_json.get("meta") or {}).get("validation_error") or "invalid_model_output")
        else:
            content = _render_post_report_text(report_json)
            technical_error = None
    except Exception as exc:
        status = REPORT_STATUS_FAILED
        content = REPORT_GENERATION_FAILED_CONTENT
        technical_error = f"{type(exc).__name__}: {exc}"

    report = await upsert_report(
        session,
        post_id=post.id,
        status=status,
        content=content,
        report_json=report_json,
    )
    result = {"status": status, "post_id": post.id, "report_id": report.id}
    if technical_error is not None:
        result["technical_error"] = technical_error
    if shadow_compare is not None:
        result["shadow_compare"] = shadow_compare
    return result

async def build_event_report_draft(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict:
    payload = await build_event_report_v2_impl(session=session, event_id=event_id)
    if payload.get("status") == "not_found":
        return {"status": "not_found", "event_id": event_id}
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    payload = dict(payload or {})
    payload["status"] = status

    last_version = (
        await session.execute(
            select(EventReport.version)
            .where(EventReport.event_id == event_id)
            .order_by(EventReport.version.desc(), EventReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = EventReport(
        event_id=event_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "event_id": event_id, "report_id": report.id}


async def _load_latest_event_report_snapshots_for_process(session: AsyncSession, *, process_id: int) -> list[tuple[int, str | None, dict | None, str]]:
    event_rows = (
        await session.execute(
            select(ProcessEvent.event_id, Event.title)
            .join(Event, Event.id == ProcessEvent.event_id)
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()
    rows = (
        await session.execute(
            select(
                EventReport.event_id,
                EventReport.report_json,
                EventReport.version,
                EventReport.id,
            )
            .where(
                EventReport.event_id.in_(
                    select(ProcessEvent.event_id).where(ProcessEvent.process_id == process_id)
                )
            )
            .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
        )
    ).all()
    latest_by_event_id: dict[int, dict | None] = {}
    for event_id, report_json, _version, _report_id in rows:
        latest_by_event_id.setdefault(int(event_id), report_json if isinstance(report_json, dict) else None)

    snapshots: list[tuple[int, str | None, dict | None, str]] = []
    for event_id, event_title in event_rows:
        payload = latest_by_event_id.get(int(event_id))
        snapshots.append(
            (
                int(event_id),
                event_title,
                dict(payload) if isinstance(payload, dict) else None,
                report_status_from_payload(payload, fallback=""),
            )
        )
    return snapshots


async def _load_latest_event_report_payloads_for_process(session: AsyncSession, *, process_id: int) -> list[dict]:
    payloads: list[dict] = []
    for event_id, event_title, payload, _status in await _load_latest_event_report_snapshots_for_process(session, process_id=process_id):
        if not _is_payload_dependency_ready(payload):
            continue
        selected_payload = dict(payload or {})
        selected_payload.setdefault("event_id", int(event_id))
        selected_payload.setdefault("event_title", event_title)
        payloads.append(selected_payload)
    return payloads

async def _process_report_readiness(session: AsyncSession, *, process_id: int) -> dict:
    snapshots = await _load_latest_event_report_snapshots_for_process(session, process_id=process_id)
    total_events = len(snapshots)
    if total_events == 0:
        return {
            "ready": True,
            "reason": "no_events",
            "total_events": 0,
            "ready_event_reports": 0,
            "required_ready_event_reports": 0,
        }
    ready_event_reports = 0
    blocked_events = 0
    dependencies: list[dict] = []
    for event_id, _event_title, payload, status in snapshots:
        if _is_payload_dependency_ready(payload):
            ready_event_reports += 1
        elif status in {"", REPORT_STATUS_STALE}:
            dependencies.append(
                _build_dependency(
                    JobType.BUILD_EVENT_REPORT,
                    entity_id=int(event_id),
                    reason="waiting_event_reports",
                )
            )
        else:
            blocked_events += 1
    required_ready = max(1, math.ceil(total_events * 0.7))
    ready = ready_event_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else ("blocked_event_reports" if blocked_events > 0 and not dependencies else "waiting_event_reports"),
        "total_events": total_events,
        "ready_event_reports": ready_event_reports,
        "required_ready_event_reports": required_ready,
        "blocked_event_reports": blocked_events,
        "dependencies": dependencies,
    }


async def build_process_report_draft(
    session: AsyncSession,
    *,
    process_id: int,
) -> dict:
    process = await session.get(Process, process_id)
    if process is None:
        return {"status": "not_found", "process_id": process_id}

    readiness = await _process_report_readiness(session, process_id=process_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "process_id": process_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    event_payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    if not event_payloads:
        payload = {
            "type": "process_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "process_id": process_id,
            "process_title": process.title,
            "events_count": int(readiness.get("total_events") or 0),
            "source_event_reports": [],
            "summary": "Р”Р»СЏ РїСЂРѕС†РµСЃСЃР° РїРѕРєР° РЅРµС‚ РіРѕС‚РѕРІС‹С… РѕС‚С‡РµС‚РѕРІ РїРѕ СЃРѕР±С‹С‚РёСЏРј РёР»Рё РїРѕСЃС‚Р°Рј.",
            "meta": {"prompt_version": "process_report_v2", "source_type": "event_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_process_report_payload(
            process_id=process_id,
            process_title=process.title,
            event_reports=event_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    coverage, stance = _aggregate_child_coverage(event_payloads)
    payload["reactions_coverage"] = coverage
    payload["audience_stance"] = stance
    payload["meta"] = {
        **dict(payload.get("meta") or {}),
        "coverage_factor": coverage.get("factor"),
    }

    last_version = (
        await session.execute(
            select(ProcessReport.version)
            .where(ProcessReport.process_id == process_id)
            .order_by(ProcessReport.version.desc(), ProcessReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = ProcessReport(
        process_id=process_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "process_id": process_id, "report_id": report.id}

