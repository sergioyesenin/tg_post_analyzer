from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Comment, Event, EventPost, EventReport, Job, Post, Process, ProcessEvent, ProcessReport, Report
from schemas.report import PostReportPayload
from services.jobs import JOB_STATUS_DONE, JobType
from services.ingest import upsert_report
from services.report_aggregation import build_event_report_payload, build_process_report_payload
from services.settings_store import get_all_settings
from services.reporting_v2 import (
    build_event_report_v2_impl,
    generate_post_report_payload_v2,
    map_state_to_public_post_payload,
    run_post_orchestrator_v2,
)
from services.reporting_v2.steps import is_canonical_openrouter_ready_path
from services.reporting_v2.searxng_provider import SearxngRetrievalProvider


REPORT_GENERATION_FAILED_CONTENT = "STATUS: FAILED\nREASON: report_generation_failed"
REPORT_STATUS_DRAFT = "draft"
REPORT_STATUS_READY = "ready"
REPORT_STATUS_LIMITED = "limited"
REPORT_STATUS_INSUFFICIENT_DATA = "insufficient_data"
REPORT_STATUS_FAILED = "failed"
REPORT_STATUS_DEFERRED = "deferred_waiting_dependencies"
REPORT_STATUS_STALE = "stale"
POST_REPORT_REBUILD_PRIORITY = 40
AGGREGATABLE_REPORT_STATUSES = {REPORT_STATUS_READY, REPORT_STATUS_LIMITED}
DEFAULT_MIN_COMMENTS = 20
logger = logging.getLogger(__name__)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CANONICAL_READY_STEP_NAMES = ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer")
_PROVENANCE_REQUIRED_KEYS = {
    "provider",
    "model",
    "executed",
    "success",
    "latency_ms",
    "input_ref",
    "input_hash",
    "output_ref",
    "output_hash",
    "fallback_used",
    "fallback_reason",
    "attempt_index",
    "status",
}
_BLOCKING_REVIEWER_CODES = {"D3", "D4", "D6"}

def _build_retrieval_provider(features: dict[str, Any] | None) -> SearxngRetrievalProvider | None:
    features = features if isinstance(features, dict) else {}

    enabled = bool(features.get("retrieval_provider_enabled", True))
    if not enabled:
        return None

    base_url = str(features.get("searxng_base_url") or "http://host.docker.internal:8088").strip()
    if not base_url:
        return None

    return SearxngRetrievalProvider(
        base_url=base_url,
        timeout_seconds=float(features.get("retrieval_timeout_seconds", 8.0)),
        max_results=int(features.get("retrieval_max_results", 6)),
        fetch_pages=bool(features.get("retrieval_fetch_pages", True)),
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


def _is_orchestrator_v2_payload_skeleton_like(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    multi_agent = (payload.get("meta") or {}).get("multi_agent")
    if not isinstance(multi_agent, dict):
        return False
    steps = multi_agent.get("steps") if isinstance(multi_agent.get("steps"), dict) else {}
    routing = steps.get("routing") if isinstance(steps.get("routing"), dict) else multi_agent.get("routing")
    synthesis = steps.get("synthesis") if isinstance(steps.get("synthesis"), dict) else multi_agent.get("synthesis")
    routing_reasoning = ""
    synthesis_confidence_reason = ""
    synthesis_report_text = ""
    if isinstance(routing, dict):
        routing_reasoning = str(routing.get("reasoning") or "").strip().lower()
    if isinstance(synthesis, dict):
        synthesis_confidence_reason = str(synthesis.get("confidence_reason") or "").strip().lower()
        synthesis_report_text = str(synthesis.get("report_text") or synthesis.get("summary") or "").strip().lower()
    return (
        routing_reasoning == "orchestrator_skeleton"
        or synthesis_confidence_reason == "orchestrator_skeleton"
        or synthesis_report_text in {"", "generated by reporting_v2 mapper skeleton."}
    )


def _extract_step_payload(multi_agent: dict, step: str) -> dict[str, Any]:
    steps = multi_agent.get("steps")
    if isinstance(steps, dict) and isinstance(steps.get(step), dict):
        return dict(steps.get(step) or {})
    legacy_stages = multi_agent.get("stages")
    if isinstance(legacy_stages, dict) and isinstance(legacy_stages.get(step), dict):
        return dict(legacy_stages.get(step) or {})
    legacy = multi_agent.get(step)
    return dict(legacy or {}) if isinstance(legacy, dict) else {}


def _default_step_provenance(*, step_payload: dict[str, Any]) -> dict[str, Any]:
    status = str(step_payload.get("status") or "skipped")
    normalized_status = status if status in {"completed", "failed", "skipped"} else "skipped"
    run_count = int(step_payload.get("run_count") or 1)
    existing = step_payload.get("provenance")
    base = dict(existing or {})
    base.setdefault("provider", None)
    base.setdefault("model", None)
    base.setdefault("executed", False)
    base.setdefault("success", False)
    base.setdefault("latency_ms", None)
    base.setdefault("input_ref", None)
    base.setdefault("input_hash", None)
    base.setdefault("output_ref", None)
    base.setdefault("output_hash", None)
    base.setdefault("fallback_used", False)
    base.setdefault("fallback_reason", None)
    base.setdefault("attempt_index", max(0, run_count - 1) if normalized_status != "skipped" else 0)
    base["status"] = normalized_status
    return base


def _canonicalize_multi_agent_trace(payload: dict) -> dict:
    multi_agent = ((payload.get("meta") or {}).get("multi_agent") or {})
    if not isinstance(multi_agent, dict) or not multi_agent:
        return {}

    context_step = _extract_step_payload(multi_agent, "context")
    routing_step = _extract_step_payload(multi_agent, "routing")
    expert_step = _extract_step_payload(multi_agent, "expert")
    public_opinion_step = _extract_step_payload(multi_agent, "public_opinion")
    synthesis_step = _extract_step_payload(multi_agent, "synthesis")
    reviewer_step = _extract_step_payload(multi_agent, "reviewer")
    review = multi_agent.get("review")
    if not isinstance(review, dict):
        legacy_reviewer = dict(multi_agent.get("reviewer") or {})
        review = {
            "iterations": int(legacy_reviewer.get("iterations") or 0),
            "history": list(legacy_reviewer.get("history") or []),
        }
    if not reviewer_step and isinstance(multi_agent.get("reviewer"), dict):
        reviewer_step = dict(multi_agent.get("reviewer") or {})
    reviewer_step = {
        "status": str(reviewer_step.get("status") or "completed"),
        "run_count": int(reviewer_step.get("run_count") or 1),
        "decision": str(reviewer_step.get("decision") or review.get("decision") or ""),
        "iterations": int(
            reviewer_step.get("iterations")
            or review.get("iterations")
            or len([item for item in list(review.get("history") or []) if str((item or {}).get("decision")) == "rerun_branch"])
        ),
        "history": list(reviewer_step.get("history") or review.get("history") or []),
        **reviewer_step,
    }
    if not reviewer_step["decision"]:
        history = list(reviewer_step.get("history") or [])
        if history:
            reviewer_step["decision"] = str((history[-1] or {}).get("decision") or "insufficient_data")
        else:
            reviewer_step["decision"] = "insufficient_data"

    canonical = {
        "version": str(multi_agent.get("version") or "v1"),
        "status": str(
            multi_agent.get("status")
            or multi_agent.get("final_status")
            or payload.get("status")
            or REPORT_STATUS_LIMITED
        ),
        "epistemic_claims": list(multi_agent.get("epistemic_claims") or expert_step.get("claims") or []),
        "steps": {
            "context": {"status": str(context_step.get("status") or "completed"), "run_count": int(context_step.get("run_count") or 1), **context_step},
            "routing": {"status": str(routing_step.get("status") or "completed"), "run_count": int(routing_step.get("run_count") or 1), **routing_step},
            "expert": {"status": str(expert_step.get("status") or "completed"), "run_count": int(expert_step.get("run_count") or 1), **expert_step},
            "public_opinion": {"status": str(public_opinion_step.get("status") or "completed"), "run_count": int(public_opinion_step.get("run_count") or 1), **public_opinion_step},
            "synthesis": {"status": str(synthesis_step.get("status") or "completed"), "run_count": int(synthesis_step.get("run_count") or 1), **synthesis_step},
            "reviewer": reviewer_step,
        },
        "retrieval": {
            "required": bool((multi_agent.get("retrieval") or {}).get("required", False)),
            "used": bool((multi_agent.get("retrieval") or {}).get("used", False)),
            "status": str((multi_agent.get("retrieval") or {}).get("status") or "none"),
            "decision_inputs": dict((multi_agent.get("retrieval") or {}).get("decision_inputs") or {}),
            "decision_source": str((multi_agent.get("retrieval") or {}).get("decision_source") or "policy"),
            "sources": list((multi_agent.get("retrieval") or {}).get("sources") or []),
        },
        "review": {
            "iterations": int(
                review.get("iterations")
                or len([item for item in list(review.get("history") or []) if str((item or {}).get("decision")) == "rerun_branch"])
            ),
            "history": list(review.get("history") or []),
        },
    }
    for step_name, step_payload in list((canonical.get("steps") or {}).items()):
        if isinstance(step_payload, dict):
            if isinstance(step_payload.get("provenance"), dict):
                step_payload["provenance_source"] = "observed"
            else:
                step_payload["provenance_source"] = "default_filled"
            step_payload["provenance"] = _default_step_provenance(step_payload=step_payload)
            canonical["steps"][step_name] = step_payload
    return canonical


def canonicalize_multi_agent_trace(payload: dict) -> dict:
    return _canonicalize_multi_agent_trace(payload)


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


def _is_payload_dependency_ready(payload: dict | None) -> bool:
    status = report_status_from_payload(payload, fallback="")
    return status in AGGREGATABLE_REPORT_STATUSES


def _serialize_report_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_public_confidence(payload: dict) -> dict:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    multi_agent = _canonicalize_multi_agent_trace(payload)
    retrieval = dict((multi_agent.get("retrieval") or {}) if isinstance(multi_agent, dict) else {})
    retrieval_required = bool(retrieval.get("required"))
    retrieval_status = str(retrieval.get("status") or "none")

    confidence = dict(payload.get("confidence") or {})
    current_overall = str(confidence.get("overall") or "medium").strip().lower()
    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        confidence["overall"] = "low"
        confidence["reason"] = "Insufficient data for a reliable analytical conclusion."
    elif status == REPORT_STATUS_LIMITED:
        confidence["overall"] = "medium" if current_overall == "high" else (current_overall or "medium")
        confidence["reason"] = "Conclusions are limited by evidence volume and signal stability."
    else:
        confidence["overall"] = current_overall if current_overall in {"low", "medium", "high"} else "medium"

    if retrieval_required and retrieval_status in {"failed", "insufficient", "none"}:
        confidence["overall"] = "low" if status != REPORT_STATUS_READY else "medium"
        confidence["reason"] = "Required external retrieval was unavailable; confidence is downgraded."
    return confidence


def _normalize_public_topics(payload: dict) -> list[dict]:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        return []

    topics = payload.get("topics")
    if not isinstance(topics, list) or not topics:
        topics = _extract_topics_from_multi_agent_public_opinion(payload)
    if not isinstance(topics, list):
        return []

    normalized: list[dict] = []
    seen: set[str] = set()
    for item in topics:
        if isinstance(item, dict):
            name = _clean_list_text(item.get("name"))
            share = item.get("share")
        elif isinstance(item, str):
            name = _clean_list_text(item)
            share = None
        else:
            continue
        if not name or name in seen:
            continue
        next_item = {"name": name}
        try:
            if share is not None:
                next_item["share"] = max(0.0, min(1.0, float(share)))
        except (TypeError, ValueError):
            pass
        normalized.append(next_item)
        seen.add(name)
        if len(normalized) >= 5:
            break
    return normalized


def _extract_topics_from_multi_agent_public_opinion(payload: dict) -> list[str]:
    multi_agent = _canonicalize_multi_agent_trace(payload)
    if not isinstance(multi_agent, dict):
        return []
    public_opinion = ((multi_agent.get("steps") or {}).get("public_opinion") or {})
    if not isinstance(public_opinion, dict):
        return []
    main_topics = public_opinion.get("main_topics")
    if isinstance(main_topics, list) and main_topics:
        out = [_clean_list_text(item) for item in main_topics if isinstance(item, str)]
        return [item for item in out if item][:5]
    signals = public_opinion.get("signals")
    if not isinstance(signals, list):
        return []

    extracted: list[str] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        if str(signal.get("name") or "").strip().lower() != "top_topics":
            continue
        value = signal.get("value")
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, str):
                continue
            name = _clean_list_text(item)
            if name and name not in extracted:
                extracted.append(name)
            if len(extracted) >= 5:
                return extracted
    return extracted


def _build_public_post_summary(payload: dict) -> str:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    multi_agent = _canonicalize_multi_agent_trace(payload)
    synthesis = ((multi_agent.get("steps") or {}).get("synthesis") or {})
    synthesis_text = _clean_list_text(synthesis.get("report_text") or synthesis.get("summary"))
    if synthesis_text:
        sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(synthesis_text) if item.strip()]
        if sentences:
            return " ".join(item if item.endswith((".", "!", "?")) else f"{item}." for item in sentences)
        return synthesis_text

    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        return "Insufficient data."
    if status == REPORT_STATUS_LIMITED:
        return "Evidence is limited."
    if status == REPORT_STATUS_FAILED:
        return "Report generation failed."
    return "Report generated."


def map_internal_post_report_to_public_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload

    public_payload = dict(payload)
    canonical_multi_agent = _canonicalize_multi_agent_trace(public_payload)
    if canonical_multi_agent:
        public_payload["meta"] = {
            **dict(public_payload.get("meta") or {}),
            "multi_agent": canonical_multi_agent,
        }
    public_payload["status"] = report_status_from_payload(public_payload, fallback=REPORT_STATUS_READY)
    public_payload["topics"] = _normalize_public_topics(public_payload)
    public_payload["confidence"] = _normalize_public_confidence(public_payload)
    public_payload["summary"] = _build_public_post_summary(public_payload)
    return public_payload


def _sentiment_label_ru(value: str | None) -> str:
    mapping = {
        "positive": "позитивный",
        "negative": "негативный",
        "neutral": "нейтральный",
        "mixed": "смешанный",
        "stable": "стабильный",
    }
    normalized = str(value or "").strip().lower()
    return mapping.get(normalized, normalized or "нейтральный")


def _share_to_percent(value: object) -> str:
    try:
        return f"{round(float(value or 0.0) * 100, 1):g}%"
    except (TypeError, ValueError):
        return "0%"


def _clean_list_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text or None


def _collect_topic_names(items: object, *, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        name = None
        if isinstance(item, dict):
            name = _clean_list_text(item.get("name"))
        elif isinstance(item, str):
            name = _clean_list_text(item)
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _collect_text_items(items: object, *, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = _clean_list_text(item.get("summary") or item.get("trend") or item.get("name"))
        else:
            text = _clean_list_text(item)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _trim_sentence(text: str | None, *, fallback: str) -> str:
    value = _clean_list_text(text)
    if not value:
        return fallback
    return value if value[-1] in ".!?" else f"{value}."


def _signature_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _build_post_report_input_signature(
    *,
    post: Post,
    comment_rows: list[tuple],
) -> str:
    payload = {
        "post": {
            "id": int(post.id),
            "date": _signature_timestamp(post.date),
            "text": post.text or "",
            "views": int(post.views) if post.views is not None else None,
            "comments_count": int(post.comments_count or 0),
            "reactions_json": post.reactions_json if isinstance(post.reactions_json, dict) else None,
        },
        "comments": [
            {
                "tg_message_id": int(tg_message_id),
                "parent_tg_message_id": int(parent_tg_message_id) if parent_tg_message_id is not None else None,
                "thread_root_tg_message_id": int(thread_root_tg_message_id) if thread_root_tg_message_id is not None else None,
                "depth": int(depth or 0),
                "date": _signature_timestamp(date),
                "text": text or "",
                "reactions_json": reactions_json if isinstance(reactions_json, dict) else None,
            }
            for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, reactions_json in comment_rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _load_post_comment_rows_for_signature(session: AsyncSession, *, post_id: int) -> list[tuple]:
    return (
        await session.execute(
            select(
                Comment.tg_message_id,
                Comment.parent_tg_message_id,
                Comment.thread_root_tg_message_id,
                Comment.depth,
                Comment.date,
                Comment.text,
                Comment.reactions_json,
            )
            .where(Comment.post_id == post_id)
            .order_by(Comment.date.asc(), Comment.id.asc())
        )
    ).all()


async def compute_post_report_input_signature(
    session: AsyncSession,
    *,
    post_id: int,
    post: Post | None = None,
) -> str | None:
    post_row = post or await session.get(Post, post_id)
    if post_row is None:
        return None
    comment_rows = await _load_post_comment_rows_for_signature(session, post_id=post_row.id)
    return _build_post_report_input_signature(post=post_row, comment_rows=comment_rows)


async def _load_post_refresh_attempt_info(session: AsyncSession, *, post_id: int) -> dict | None:
    row = (
        await session.execute(
            select(Job.type, Job.updated_at)
            .where(Job.type.in_((JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS)))
            .where(Job.status == JOB_STATUS_DONE)
            .where(Job.payload_json["post_id"].astext == str(post_id))
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    job_type, updated_at = row
    return {
        "source": str(job_type),
        "collected_at": updated_at.isoformat() if updated_at is not None else None,
        "is_complete": False,
    }


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
    return _trim_sentence(payload.get("summary"), fallback="Insufficient narrative details in synthesized output.")


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_reaction_items(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    items: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        reaction_obj = item.get("reaction")
        label = None
        if isinstance(reaction_obj, dict):
            label = _clean_list_text(reaction_obj.get("emoticon") or reaction_obj.get("title") or reaction_obj.get("_"))
        if not label:
            label = _clean_list_text(item.get("reaction_type"))
        if not label:
            continue
        items.append({"label": label, "count": _safe_int(item.get("count"))})
    return items


def _summarize_reaction_items(items: list[dict], *, limit: int = 5) -> dict:
    total_count = sum(_safe_int(item.get("count")) for item in items)
    ordered = sorted(items, key=lambda item: (-_safe_int(item.get("count")), str(item.get("label") or "")))
    return {
        "total_count": total_count,
        "distinct_count": len([item for item in ordered if _safe_int(item.get("count")) > 0]),
        "top_reactions": [
            {
                "label": str(item.get("label") or ""),
                "count": _safe_int(item.get("count")),
                "share": round((_safe_int(item.get("count")) / total_count), 4) if total_count > 0 else 0.0,
            }
            for item in ordered[:limit]
        ],
    }


def _post_reactions_enrichment(*, post: Post, comment_rows: list[tuple]) -> dict:
    post_payload = post.reactions_json if isinstance(post.reactions_json, dict) else {}
    comment_meta = post_payload.get("comment_reactions") if isinstance(post_payload, dict) else {}
    post_reactions = _summarize_reaction_items(
        _extract_reaction_items(post_payload.get("post_reactions") if isinstance(post_payload, dict) else None)
    )
    comment_reactions = _summarize_reaction_items(
        [
            item
            for _tg_message_id, _parent_tg_message_id, _thread_root_tg_message_id, _depth, _date, _text, reactions_json in comment_rows
            for item in _extract_reaction_items(reactions_json if isinstance(reactions_json, dict) else None)
        ]
    )
    expected_comments = max(
        _safe_int(post.comments_count),
        len(comment_rows),
        _safe_int(comment_meta.get("comments_scanned") if isinstance(comment_meta, dict) else 0),
    )
    comments_scanned = _safe_int(comment_meta.get("comments_scanned") if isinstance(comment_meta, dict) else 0)
    is_complete = bool(post_payload.get("is_complete")) if isinstance(post_payload, dict) else False
    comment_status = str(comment_meta.get("status") or "") if isinstance(comment_meta, dict) else ""
    factor = 1.0 if is_complete else 0.0
    if expected_comments > 0 and comments_scanned > 0:
        factor = max(factor, min(1.0, comments_scanned / expected_comments))
    if comment_status == "no_reactions":
        factor = 1.0
    elif comment_status == "partial":
        factor = min(factor, 0.7) if factor > 0 else 0.5
    elif comment_status == "unavailable":
        factor = min(factor, 0.35) if factor > 0 else 0.2
    return {
        "post_reactions": post_reactions,
        "comment_reactions": comment_reactions,
        "reactions_coverage": {
            "source": post_payload.get("source") if isinstance(post_payload, dict) else None,
            "collected_at": post_payload.get("collected_at") if isinstance(post_payload, dict) else None,
            "is_complete": is_complete,
            "factor": round(max(0.0, min(1.0, factor)), 4),
            "comment_status": comment_status or None,
            "comments_scanned": comments_scanned,
            "comments_with_visible_reactions": _safe_int(comment_meta.get("comments_with_visible_reactions") if isinstance(comment_meta, dict) else 0),
            "expected_comments": expected_comments,
        },
    }


def _build_audience_stance(payload: dict) -> dict:
    sentiment = payload.get("sentiment") or payload.get("overall_sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    positive = _safe_float(distribution.get("positive"))
    negative = _safe_float(distribution.get("negative"))
    neutral = _safe_float(distribution.get("neutral"))
    positive_reaction_count = 0
    critical_reaction_count = 0
    for source_payload in (payload.get("post_reactions") or {}, payload.get("comment_reactions") or {}):
        for item in list(source_payload.get("top_reactions") or []):
            label = str(item.get("label") or "")
            count = _safe_int(item.get("count"))
            if label in {"👍", "❤", "❤️", "🔥", "👏", "🙏", "😁", "👌", "💯"}:
                positive_reaction_count += count
            elif label in {"👎", "🤬", "😡", "💩", "🤮", "😢", "😭"}:
                critical_reaction_count += count
    if max(positive, negative) < 0.2 and neutral >= 0.6:
        label = "neutral"
    elif abs(positive - negative) <= 0.15 and positive >= 0.2 and negative >= 0.2:
        label = "mixed"
    elif positive > negative:
        label = "supportive"
    elif negative > positive:
        label = "critical"
    else:
        label = "unclear"
    if positive_reaction_count > critical_reaction_count * 1.5 and positive_reaction_count >= 3:
        label = "supportive"
    elif critical_reaction_count > positive_reaction_count * 1.5 and critical_reaction_count >= 3:
        label = "critical"
    coverage_factor = _safe_float((payload.get("reactions_coverage") or {}).get("factor"))
    confidence = "high" if coverage_factor >= 0.85 else "medium" if coverage_factor >= 0.45 else "low"
    return {
        "label": label,
        "confidence": confidence,
        "reason": (
            f"Тональность: позитив {_share_to_percent(positive)}, негатив {_share_to_percent(negative)}, нейтрально {_share_to_percent(neutral)}. "
            f"Поддерживающих reactions: {positive_reaction_count}, критических: {critical_reaction_count}."
        ),
    }


def _format_reactions_summary_line(title: str, summary: dict) -> str:
    top = list(summary.get("top_reactions") or [])
    if not top:
        return f"- {title}: выраженных reactions нет."
    return f"- {title}: " + ", ".join(f"{item.get('label')} {_safe_int(item.get('count'))}" for item in top[:5]) + "."


def _format_reactions_coverage_line(payload: dict) -> str:
    coverage = payload.get("reactions_coverage") or {}
    return (
        f"- Покрытие reactions: {_share_to_percent(coverage.get('factor'))}; "
        f"comment reactions status={coverage.get('comment_status') or 'unknown'}; "
        f"scanned={_safe_int(coverage.get('comments_scanned'))}/{_safe_int(coverage.get('expected_comments'))}."
    )


def _enrich_post_report_payload(*, payload: dict, post: Post, comment_rows: list[tuple]) -> dict:
    enriched = dict(payload)
    reactions = _post_reactions_enrichment(post=post, comment_rows=comment_rows)
    enriched["post_reactions"] = reactions["post_reactions"]
    enriched["comment_reactions"] = reactions["comment_reactions"]
    enriched["reactions_coverage"] = reactions["reactions_coverage"]
    enriched["audience_stance"] = _build_audience_stance(enriched)
    meta = dict(enriched.get("meta") or {})
    meta["coverage_factor"] = reactions["reactions_coverage"]["factor"]
    enriched["meta"] = meta
    return enriched


def _aggregate_child_coverage(payloads: list[dict]) -> tuple[dict, dict]:
    if not payloads:
        return (
            {
                "source": "child_reports",
                "collected_at": None,
                "is_complete": False,
                "factor": 0.0,
                "comment_status": None,
                "comments_scanned": 0,
                "comments_with_visible_reactions": 0,
                "expected_comments": 0,
            },
            {
                "label": "unclear",
                "confidence": "low",
                "reason": "Недостаточно дочерних отчетов для оценки позиции аудитории.",
            },
        )
    factor = round(sum(_safe_float((item.get("reactions_coverage") or {}).get("factor")) for item in payloads) / len(payloads), 4)
    stance_counts = {"supportive": 0, "critical": 0, "mixed": 0, "neutral": 0, "unclear": 0}
    for item in payloads:
        stance_counts[str((item.get("audience_stance") or {}).get("label") or "unclear")] += 1
    label = max(stance_counts.items(), key=lambda pair: pair[1])[0]
    confidence = "high" if factor >= 0.85 else "medium" if factor >= 0.45 else "low"
    return (
        {
            "source": "child_reports",
            "collected_at": None,
            "is_complete": factor >= 0.99,
            "factor": factor,
            "comment_status": "aggregated",
            "comments_scanned": 0,
            "comments_with_visible_reactions": 0,
            "expected_comments": 0,
        },
        {
            "label": label,
            "confidence": confidence,
            "reason": f"Агрегация по дочерним отчетам: supportive={stance_counts['supportive']}, critical={stance_counts['critical']}, mixed={stance_counts['mixed']}, neutral={stance_counts['neutral']}.",
        },
    )


def _render_post_report_text(payload: dict) -> str:
    return _build_public_post_summary(payload)


def _contains_blocking_reviewer_signal(multi_agent: dict[str, Any]) -> bool:
    review = multi_agent.get("review")
    review_history = list(review.get("history") or []) if isinstance(review, dict) else []
    reviewer_step = ((multi_agent.get("steps") or {}).get("reviewer") or {})
    reviewer_history = list(reviewer_step.get("history") or []) if isinstance(reviewer_step, dict) else []
    history = [*review_history, *reviewer_history]
    for item in history:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "")
        reason = str(item.get("reason") or "")
        if decision == "insufficient_data":
            return True
        defect_code = reason.split(":", 1)[0].strip()
        if defect_code in _BLOCKING_REVIEWER_CODES:
            return True
        if "blocking_defects_present" in reason:
            return True
    return False


def _has_sufficient_ready_evidence(multi_agent: dict[str, Any]) -> bool:
    steps = multi_agent.get("steps")
    if not isinstance(steps, dict):
        return False
    context = steps.get("context")
    if not isinstance(context, dict):
        return False
    sufficiency_components = context.get("sufficiency_components")
    if isinstance(sufficiency_components, dict):
        if str(sufficiency_components.get("analytical") or "") != "sufficient":
            return False
    public_opinion = steps.get("public_opinion")
    if isinstance(public_opinion, dict):
        data_status = str(public_opinion.get("data_status") or "")
        if data_status in {"weak_signal", "insufficient"}:
            return False
    return True


def _is_canonical_openrouter_ready_payload(payload: dict | None) -> bool:
    multi_agent = _canonicalize_multi_agent_trace(payload or {})
    if not isinstance(multi_agent, dict) or not multi_agent:
        return False
    steps = multi_agent.get("steps")
    if not isinstance(steps, dict):
        return False
    for step_name in _CANONICAL_READY_STEP_NAMES:
        step_payload = steps.get(step_name)
        if not isinstance(step_payload, dict):
            return False
        if str(step_payload.get("provenance_source") or "") != "observed":
            return False
        provenance = step_payload.get("provenance")
        if not isinstance(provenance, dict):
            return False
        if not _PROVENANCE_REQUIRED_KEYS.issubset(set(provenance.keys())):
            return False
    if not is_canonical_openrouter_ready_path(steps):
        return False
    if _contains_blocking_reviewer_signal(multi_agent):
        return False
    if not _has_sufficient_ready_evidence(multi_agent):
        return False
    return True


def report_status_from_payload(payload: dict | None, *, fallback: str = REPORT_STATUS_READY) -> str:
    if not isinstance(payload, dict):
        return REPORT_STATUS_LIMITED if fallback == REPORT_STATUS_READY else fallback
    status = payload.get("status")
    resolved = status if isinstance(status, str) and status else fallback
    if resolved != REPORT_STATUS_READY:
        return resolved
    if _is_canonical_openrouter_ready_payload(payload):
        return REPORT_STATUS_READY
    return REPORT_STATUS_LIMITED


def mark_report_payload_stale(
    payload: dict | None,
    *,
    dependency_type: str,
    dependency_id: int,
) -> dict:
    next_payload = dict(payload or {})
    previous_status = report_status_from_payload(next_payload, fallback=REPORT_STATUS_READY)
    meta = dict(next_payload.get("meta") or {})
    next_payload["status"] = REPORT_STATUS_STALE
    next_payload["meta"] = {
        **meta,
        "stale": True,
        "stale_dependency_type": dependency_type,
        "stale_dependency_id": int(dependency_id),
        "stale_marked_at": meta.get("stale_marked_at") or datetime.now(timezone.utc).isoformat(),
        "previous_status": meta.get("previous_status") or previous_status,
    }
    return next_payload


async def _mark_related_event_reports_stale_for_post(session: AsyncSession, *, post_id: int) -> tuple[int, list[int]]:
    rows = (
        await session.execute(
            select(EventReport)
            .where(
                EventReport.id.in_(
                    select(EventReport.id)
                    .join(EventPost, EventPost.event_id == EventReport.event_id)
                    .where(EventPost.post_id == post_id)
                    .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
                    .distinct(EventReport.event_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    event_ids: list[int] = []
    for report in rows:
        event_ids.append(int(report.event_id))
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="post_report",
            dependency_id=post_id,
        )
        marked += 1
    if marked:
        await session.flush()
    return marked, event_ids


async def _mark_related_process_reports_stale_for_events(session: AsyncSession, *, event_ids: list[int]) -> int:
    if not event_ids:
        return 0
    rows = (
        await session.execute(
            select(ProcessReport)
            .where(
                ProcessReport.id.in_(
                    select(ProcessReport.id)
                    .join(ProcessEvent, ProcessEvent.process_id == ProcessReport.process_id)
                    .where(ProcessEvent.event_id.in_(event_ids))
                    .order_by(ProcessReport.process_id.asc(), ProcessReport.version.desc(), ProcessReport.id.desc())
                    .distinct(ProcessReport.process_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    for report in rows:
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="event_report",
            dependency_id=int(event_ids[0]),
        )
        marked += 1
    if marked:
        await session.flush()
    return marked


async def sync_post_report_staleness(
    session: AsyncSession,
    *,
    post_id: int,
    source: str,
    dependency_type: str = "post_inputs",
    dependency_id: int | None = None,
) -> dict:
    post = await session.get(Post, post_id)
    if post is None:
        return {"status": "not_found", "post_id": post_id}

    report = (
        await session.execute(select(Report).where(Report.post_id == post_id))
    ).scalar_one_or_none()
    min_comments = DEFAULT_MIN_COMMENTS
    if report is None and int(post.comments_count or 0) < min_comments:
        return {
            "status": "ignored_below_min_comments",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    current_signature = await compute_post_report_input_signature(session, post_id=post_id, post=post)
    if current_signature is None:
        return {"status": "not_found", "post_id": post_id}

    report_payload = report.report_json if report is not None and isinstance(report.report_json, dict) else {}
    report_meta = dict(report_payload.get("meta") or {})
    stored_signature = report_meta.get("current_input_signature") or report_meta.get("input_signature")
    if stored_signature == current_signature:
        return {
            "status": "unchanged",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    stale_marked = False
    event_reports_marked = 0
    process_reports_marked = 0
    if report is not None and isinstance(report.report_json, dict):
        next_payload = mark_report_payload_stale(
            report.report_json,
            dependency_type=dependency_type,
            dependency_id=dependency_id if dependency_id is not None else post_id,
        )
        next_meta = dict(next_payload.get("meta") or {})
        next_meta["previous_input_signature"] = report_meta.get("input_signature")
        next_meta["current_input_signature"] = current_signature
        next_payload["meta"] = next_meta
        report.report_json = next_payload
        stale_marked = True
        event_reports_marked, event_ids = await _mark_related_event_reports_stale_for_post(session, post_id=post_id)
        process_reports_marked = await _mark_related_process_reports_stale_for_events(session, event_ids=event_ids)

    return {
        "status": "stale_marked" if stale_marked else "changed",
        "post_id": post_id,
        "changed": True,
        "stale_marked": stale_marked,
        "event_reports_marked_stale": event_reports_marked,
        "process_reports_marked_stale": process_reports_marked,
        "enqueued": False,
        "job_id": None,
        "input_signature": current_signature,
        "source": source,
    }


async def build_post_report(
    session: AsyncSession,
    *,
    post_id: int,
    report_project: Any = None,
    report_config: Any = None,
    job_timeout_seconds: int | None = None,
    rerun_stage: str | None = None,
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
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, _reactions_json in comment_rows:
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
        del report_project
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

        legacy_kwargs = {
            "channel": channel_label,
            "post_id": post.id,
            "published_at_iso": post.date.isoformat(),
            "post_text": post.text or "",
            "comments": comments,
            "thread_comments": thread_comments,
            "views": post.views,
            "job_timeout_seconds": job_timeout_seconds,
            "rerun_stage": rerun_stage,
            "effective_features": features,
            "retrieval_provider": retrieval_provider,
        }
        v2_kwargs = {
            "post_id": post.id,
            "published_at_iso": post.date.isoformat(),
            "post_text": post.text or "",
            "comments": comments,
            "thread_comments": thread_comments,
            "views": post.views,
            "rerun_stage": rerun_stage,
        }
        selected_path = "legacy_rollout_disabled"
        fallback_reason: str | None = None
        if shadow_mode_enabled:
            selected_path = "llm_pipeline_shadow_mode"
            report_json = await generate_post_report_payload_v2(**legacy_kwargs)

            # Orchestrator оставляем только как диагностический shadow path.
            if use_multi_agent_v2:
                try:
                    v2_shadow_payload = await build_post_report_v2_payload_from_orchestrator(**v2_kwargs)
                    shadow_compare = _build_shadow_compare_payload(
                        legacy_payload=report_json,
                        v2_payload=v2_shadow_payload,
                    )
                except Exception as shadow_exc:
                    shadow_compare = {
                        "error": f"{type(shadow_exc).__name__}: {shadow_exc}",
                    }

        elif use_multi_agent_v2:
            selected_path = "llm_pipeline_persisted"
            report_json = await generate_post_report_payload_v2(**legacy_kwargs)

        else:
            selected_path = "llm_pipeline_default"
            report_json = await generate_post_report_payload_v2(**legacy_kwargs)
        logger.info(
            "build_post_report selected path post_id=%s selected_path=%s fallback_reason=%s",
            post.id,
            selected_path,
            fallback_reason,
        )
        report_json = map_internal_post_report_to_public_payload(report_json)
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)

        multi_agent = ((report_json or {}).get("meta") or {}).get("multi_agent") or {}
        steps = multi_agent.get("steps") if isinstance(multi_agent, dict) else {}
        synth = steps.get("synthesis") if isinstance(steps, dict) else {}
        prov = synth.get("provenance") if isinstance(synth, dict) else {}

        logger.info(
            "post report provenance post_id=%s provider=%s model=%s success=%s fallback_used=%s status=%s",
            post.id,
            prov.get("provider"),
            prov.get("model"),
            prov.get("success"),
            prov.get("fallback_used"),
            prov.get("status"),
        )
        report_json = _enrich_post_report_payload(payload=report_json, post=post, comment_rows=comment_rows)
        report_json.setdefault("post_id", post.id)
        report_json.setdefault("published_at", post.date.isoformat())
        report_json["meta"] = {
            **dict(report_json.get("meta") or {}),
            "input_signature": input_signature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refresh_attempt": readiness.get("refresh_attempt"),
        }
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


async def _load_post_report_payloads_for_event(session: AsyncSession, *, event_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(Report.report_json, Report.post_id, EventPost.role, Post.date)
            .join(EventPost, EventPost.post_id == Report.post_id)
            .join(Post, Post.id == Report.post_id)
            .where(EventPost.event_id == event_id)
            .where(Report.report_json.is_not(None))
            .order_by(Post.date.asc(), Report.id.asc())
        )
    ).all()
    payloads: list[dict] = []
    for report_json, post_id, role, post_date in rows:
        if not isinstance(report_json, dict):
            continue
        if not _is_payload_dependency_ready(report_json):
            continue
        payload = dict(report_json)
        payload.setdefault("post_id", int(post_id))
        payload["event_role"] = role
        payload.setdefault("published_at", post_date.isoformat() if post_date is not None else None)
        payloads.append(payload)
    return payloads


async def _event_report_readiness(session: AsyncSession, *, event_id: int) -> dict:
    min_comments = DEFAULT_MIN_COMMENTS
    rows = (
        await session.execute(
            select(EventPost.post_id, EventPost.role, Post.comments_count, Post.text, Report.report_json)
            .join(Post, Post.id == EventPost.post_id)
            .outerjoin(Report, Report.post_id == EventPost.post_id)
            .where(EventPost.event_id == event_id)
            .order_by(EventPost.created_at.asc(), EventPost.post_id.asc())
        )
    ).all()
    total_posts = len(rows)
    if total_posts == 0:
        return {
            "ready": True,
            "reason": "no_posts",
            "total_posts": 0,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "root_ready": True,
        }

    eligible_posts = 0
    ready_post_reports = 0
    root_ready = False
    dependencies: list[dict] = []
    blocked_posts = 0
    for post_id, role, comments_count, post_text, report_json in rows:
        eligible = int(comments_count or 0) >= min_comments
        has_text = bool(str(post_text or "").strip())
        has_report = _is_payload_dependency_ready(report_json if isinstance(report_json, dict) else None)
        status = report_status_from_payload(report_json if isinstance(report_json, dict) else None, fallback="")
        if eligible:
            eligible_posts += 1
            if has_report:
                ready_post_reports += 1
            elif has_text and status in {"", REPORT_STATUS_STALE}:
                dependencies.append(
                    _build_dependency(
                        JobType.BUILD_POST_REPORT,
                        entity_id=int(post_id),
                        reason="waiting_post_reports",
                    )
                )
            else:
                blocked_posts += 1
        if role == "root":
            root_ready = has_report or not eligible

    if eligible_posts == 0:
        return {
            "ready": True,
            "reason": "no_eligible_posts",
            "total_posts": total_posts,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "required_ready_post_reports": 0,
            "root_ready": True,
        }

    required_ready = max(1, math.ceil(eligible_posts * 0.7))
    ready = root_ready and ready_post_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else ("blocked_post_reports" if blocked_posts > 0 and not dependencies else "waiting_post_reports"),
        "total_posts": total_posts,
        "eligible_posts": eligible_posts,
        "ready_post_reports": ready_post_reports,
        "required_ready_post_reports": required_ready,
        "root_ready": root_ready,
        "blocked_post_reports": blocked_posts,
        "dependencies": dependencies,
    }


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


async def _resolve_process_event_payloads(session: AsyncSession, *, process_id: int) -> tuple[list[dict], int]:
    payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    event_ids = [
        int(row[0])
        for row in (
            await session.execute(
                select(ProcessEvent.event_id)
                .where(ProcessEvent.process_id == process_id)
                .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
            )
        ).all()
    ]
    return payloads, len(event_ids)


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
            "summary": "Для процесса пока нет готовых отчетов по событиям или постам.",
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







