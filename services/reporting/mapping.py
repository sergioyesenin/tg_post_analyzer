"""Mapping внутреннего multi-agent payload в публичный post_report_v2.

Здесь только чистые преобразования словарей. Никаких обращений к БД,
к Telegram, к jobs. Если что-то из этого понадобится — это признак,
что функция должна жить в другом модуле.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from services.reporting.constants import (
    AGGREGATABLE_REPORT_STATUSES,
    REPORT_STATUS_FAILED,
    REPORT_STATUS_INSUFFICIENT_DATA,
    REPORT_STATUS_LIMITED,
    REPORT_STATUS_READY,
)
from services.reporting_v2.steps import is_canonical_openrouter_ready_path


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
_TOPIC_STOPWORDS_RU = frozenset({"если", "надо", "это", "что", "как", "все", "там", "уже"})
_PUBLIC_TOPIC_STOPWORDS = frozenset({"если", "надо", "это", "что", "как", "все", "там", "уже"})
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_EN_TO_RU_SECTION_LABELS = {
    "Context:": "Контекст:",
    "Public reaction:": "Общественная реакция:",
    "Interpretation:": "Интерпретация:",
    "Consequences:": "Последствия:",
    "Outlook:": "Возможное развитие:",
    "Post reactions": "Реакции на пост",
    "Comment reactions": "Реакции на комментарии",
    "Audience stance": "Позиция аудитории",
}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

def _is_payload_dependency_ready(payload: dict | None) -> bool:
    status = report_status_from_payload(payload, fallback="")
    return status in AGGREGATABLE_REPORT_STATUSES

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
    public_opinion = _normalize_public_opinion_semantics(public_opinion)
    main_topics = public_opinion.get("main_topics")
    if isinstance(main_topics, list) and main_topics:
        out = [_clean_list_text(item) for item in main_topics if isinstance(item, str)]
        return [item for item in out if item][:5]
    return _extract_keyword_topics_from_public_signals(public_opinion)


def _build_public_post_summary(payload: dict) -> str:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    multi_agent = _canonicalize_multi_agent_trace(payload)
    synthesis = ((multi_agent.get("steps") or {}).get("synthesis") or {})
    synthesis_text = _clean_list_text(synthesis.get("report_text") or synthesis.get("summary"))
    if synthesis_text:
        synthesis_text = _localize_public_section_labels(synthesis_text)
        sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(synthesis_text) if item.strip()]
        if sentences:
            return " ".join(item if item.endswith((".", "!", "?")) else f"{item}." for item in sentences)
        return synthesis_text

    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        return "Недостаточно данных."
    if status == REPORT_STATUS_LIMITED:
        return "Доказательная база ограничена."
    if status == REPORT_STATUS_FAILED:
        return "Не удалось сформировать отчет."
    return "Отчет сформирован."


def _localize_public_section_labels(text: str | None) -> str:
    normalized = str(text or "")
    for en_label, ru_label in _EN_TO_RU_SECTION_LABELS.items():
        normalized = normalized.replace(en_label, ru_label)
    return normalized


def _has_structured_expert_claims(expert: dict[str, Any]) -> bool:
    for key in ("background", "interpretations", "consequences"):
        value = expert.get(key)
        if not isinstance(value, list) or not value:
            return False
        for item in value:
            if not isinstance(item, dict):
                return False
            if not _clean_list_text(item.get("text")):
                return False
    return True

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


def _stringify_path(path: tuple[str | int, ...]) -> str:
    return ".".join(str(part) for part in path)


def _value_by_path(payload: dict[str, Any], path: tuple[str | int, ...]) -> str | None:
    cur: Any = payload
    for key in path:
        if isinstance(key, int):
            if not isinstance(cur, list) or key >= len(cur):
                return None
            cur = cur[key]
        else:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
    return cur if isinstance(cur, str) else None

def _strip_enum_prefix(value: str) -> str:
    return str(value or "").strip().lstrip(":").strip()


def _normalized_llm_public_opinion(public_opinion: dict[str, Any]) -> dict[str, Any]:
    raw = public_opinion.get("llm_public_opinion")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        out[_strip_enum_prefix(str(key)).lower()] = value
    return out


def _extract_keyword_topics_from_public_signals(public_opinion: dict[str, Any]) -> list[str]:
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
            topic = _clean_list_text(item)
            if not topic:
                continue
            if topic.strip().lower() in _PUBLIC_TOPIC_STOPWORDS:
                continue
            if topic not in extracted:
                extracted.append(topic)
            if len(extracted) >= 5:
                return extracted
    return extracted


def _map_llm_topic_to_ru(value: str) -> str | None:
    normalized = _strip_enum_prefix(value)
    if not normalized:
        return None
    enum_key = normalized.lower()
    return _clean_list_text(normalized)


def _map_llm_reaction_to_claim(value: str) -> dict[str, Any] | None:
    normalized = _strip_enum_prefix(value)
    if not normalized:
        return None
    enum_key = normalized.lower()
    text, confidence = normalized, 0.65
    return {
        "text": text,
        "type": "derived",
        "confidence": max(0.0, min(1.0, float(confidence))),
        "source": "comments",
    }


def _normalize_public_opinion_semantics(public_opinion: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(public_opinion)
    llm_po = _normalized_llm_public_opinion(public_opinion)
    llm_topics_raw = llm_po.get("main_topics")
    llm_reactions_raw = llm_po.get("dominant_reactions")

    semantic_topics: list[str] = []
    if isinstance(llm_topics_raw, list):
        for item in llm_topics_raw:
            if not isinstance(item, str):
                continue
            mapped = _map_llm_topic_to_ru(item)
            if mapped and mapped not in semantic_topics:
                semantic_topics.append(mapped)
            if len(semantic_topics) >= 5:
                break

    dominant_reactions: list[dict[str, Any]] = []
    if isinstance(llm_reactions_raw, list):
        for item in llm_reactions_raw:
            if not isinstance(item, str):
                continue
            mapped = _map_llm_reaction_to_claim(item)
            if mapped and mapped not in dominant_reactions:
                dominant_reactions.append(mapped)
            if len(dominant_reactions) >= 5:
                break

    if semantic_topics:
        normalized["main_topics"] = semantic_topics
    else:
        keyword_topics = _extract_keyword_topics_from_public_signals(public_opinion)
        if keyword_topics:
            normalized["main_topics"] = keyword_topics
            normalized["data_status"] = "weak_signal"

    if dominant_reactions:
        normalized["dominant_reactions"] = dominant_reactions
    return normalized

def _trim_sentence(text: str | None, *, fallback: str) -> str:
    value = _clean_list_text(text)
    if not value:
        return fallback
    return value if value[-1] in ".!?" else f"{value}."

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
    legacy_public_opinion = multi_agent.get("public_opinion")
    if isinstance(legacy_public_opinion, dict):
        merged_public_opinion = dict(legacy_public_opinion)
        if isinstance(public_opinion_step, dict):
            merged_public_opinion.update(public_opinion_step)
        public_opinion_step = merged_public_opinion
    if isinstance(public_opinion_step, dict):
        public_opinion_step = _normalize_public_opinion_semantics(public_opinion_step)
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