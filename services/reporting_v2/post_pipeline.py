from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Literal
import logging
import traceback
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from services.llm.model_router import ModelRouter, ModelEntry
from schemas.report import PostReportPayload
from services.llm.openai_client import OpenAIAdapterConfig, OpenAIChatCompletionTrace, OpenAIClientAdapter
from services.prompts.loader import PromptLoader
from services.reporting_v2.contracts_internal import (
    aggregate_public_status,
    assess_analytical_sufficiency,
    assess_article_sufficiency,
    assess_comment_sufficiency,
    assess_retrieval_sufficiency,
    build_retrieval_trace,
    decide_retrieval_required,
    validate_multi_agent_meta,
)
from services.reporting_v2.retrieval import run_retrieval_manager
from services.reporting_v2.steps import (
    SIX_STEP_SEQUENCE,
    apply_step_trace_envelope,
    build_step_traces,
    is_canonical_openrouter_ready_path,
    request_step_rerun,
    sync_step_provenance,
)

PIPELINE_SEQUENCE = SIX_STEP_SEQUENCE
PIPELINE_STEP_KEYS = SIX_STEP_SEQUENCE
REVIEW_MAX_ITERATIONS = 2
BLOCKING_REVIEW_DECISIONS = {"rerun_branch", "revise", "insufficient_data"}
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_]+", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?]+")

def _safe_dict(value: Any) -> dict[str, Any]:
    """Возвращает value, если это словарь, иначе пустой словарь."""
    return value if isinstance(value, dict) else {}

def _safe_text(value: str | None, *, max_len: int = 300) -> str:
    return " ".join((value or "").split())[:max_len]


def _stable_hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sentence_count(text: str) -> int:
    return len([part for part in _SENTENCE_RE.split(text) if part.strip()])


def _has_reviewer_issues(llm_reviewer: dict[str, Any] | None) -> bool:
    if not isinstance(llm_reviewer, dict):
        return False
    issues = llm_reviewer.get("issues")
    return isinstance(issues, list) and len(issues) > 0


def resolve_effective_review_decision(wrapper_decision: str, llm_reviewer: dict[str, Any] | None) -> str:
    normalized_wrapper = str(wrapper_decision or "accept_with_limitations")
    if not isinstance(llm_reviewer, dict):
        return normalized_wrapper
    llm_decision = str(llm_reviewer.get("decision") or "").strip()
    if _has_reviewer_issues(llm_reviewer) and llm_decision in BLOCKING_REVIEW_DECISIONS:
        return llm_decision
    if _has_reviewer_issues(llm_reviewer) and normalized_wrapper == "accept":
        return "revise"
    return normalized_wrapper


def _infer_reviewer_target(llm_reviewer: dict[str, Any] | None, default_target: str = "synthesis") -> str:
    explicit = str((llm_reviewer or {}).get("rerun_target") or "").strip()
    if explicit in {"context", "routing", "expert", "public_opinion", "synthesis"}:
        return explicit
    issues = (llm_reviewer or {}).get("issues")
    if isinstance(issues, list):
        for item in issues:
            if isinstance(item, str):
                lower_item = item.lower()
                if "expert" in lower_item:
                    return "expert"
                if "public_opinion" in lower_item or "public" in lower_item:
                    return "public_opinion"
                if "context" in lower_item:
                    return "context"
                continue
            # item is dict
            field = str((item or {}).get("field") or "").lower()
            problem = str((item or {}).get("problem") or "").lower()
            if "expert" in field or "malformed expert" in problem or "empty expert" in problem:
                return "expert"
            if "public_opinion" in field:
                return "public_opinion"
            if "context" in field:
                return "context"
    return default_target

def _epistemic_entry(
    *,
    text: str,
    claim_type: str,
    confidence: float,
    source: str,
) -> dict[str, Any]:
    return {
        "text": _safe_text(text, max_len=500),
        "type": claim_type,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "source": source,
    }


def _normalize_epistemic_entries(
    values: Any,
    *,
    default_type: str,
    default_source: str,
    retrieval_success: bool,
) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    entries: list[dict[str, Any]] = []

    for value in values:
        if isinstance(value, str):
            text = value
            claim_type = default_type
            source = default_source
            confidence = 0.5
        elif isinstance(value, dict):
            text = _extract_entry_text(value)
            claim_type = str(value.get("type") or default_type)
            source = str(value.get("source") or default_source)
            try:
                confidence = float(value.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
        else:
            continue

        if not _safe_text(text):
            continue

        if claim_type not in {"fact", "derived", "interpretation", "external", "uncertain"}:
            claim_type = default_type

        if source not in {"article", "comments", "retrieval"}:
            source = default_source

        if source == "retrieval" or claim_type == "external":
            if not retrieval_success:
                entries.append(
                    _epistemic_entry(
                        text=text,
                        claim_type="uncertain",
                        confidence=min(confidence, 0.35),
                        source="article",
                    )
                )
                continue

            claim_type = "external"
            source = "retrieval"

        entries.append(
            _epistemic_entry(
                text=text,
                claim_type=claim_type,
                confidence=confidence,
                source=source,
            )
        )

    return entries


def _extract_entry_text(value: dict[str, Any]) -> str:
    text = str(value.get("text") or "").strip()
    if text:
        return text

    # Some weak/free models return {"": "..."} instead of {"text": "..."}.
    empty_key_text = str(value.get("") or "").strip()
    if empty_key_text:
        return empty_key_text

    # Some malformed outputs put text inside a broken key.
    for key, raw_value in value.items():
        key_text = str(key or "").strip()
        raw_text = str(raw_value or "").strip()

        if key_text.startswith("text:") or key_text.startswith("text:**"):
            cleaned = key_text
            cleaned = cleaned.replace("text:**", "")
            cleaned = cleaned.replace("text:", "")
            cleaned = cleaned.split("|type")[0]
            cleaned = cleaned.strip(" *:")
            if cleaned:
                return cleaned

        if len(raw_text) > 20 and key_text not in {"type", "source", "confidence"}:
            return raw_text

    return ""

def _normalize_expert_output(
    *,
    candidate: dict[str, Any] | None,
    retrieval_success: bool,
    data_sufficient: bool,
) -> dict[str, Any]:
    data = dict(candidate or {})

    background_raw = data.get("background") or data.get("background_factors") or []
    interpretations_raw = data.get("interpretations") or data.get("expert_views") or []
    consequences_raw = data.get("consequences") or data.get("likely_consequences") or []

    background = _normalize_epistemic_entries(
        background_raw,
        default_type="fact",
        default_source="article",
        retrieval_success=retrieval_success,
    )
    interpretations = _normalize_epistemic_entries(
        interpretations_raw,
        default_type="interpretation",
        default_source="article",
        retrieval_success=retrieval_success,
    )
    consequences = _normalize_epistemic_entries(
        consequences_raw,
        default_type="interpretation",
        default_source="article",
        retrieval_success=retrieval_success,
    )

    all_entries = [*background, *interpretations, *consequences]

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    if not confidence and all_entries:
        confidence = min(
            0.75,
            sum(float(item["confidence"]) for item in all_entries) / len(all_entries),
        )
    raw_items_count = 0
    for raw_group in (background_raw, interpretations_raw, consequences_raw):
        if isinstance(raw_group, list):
            raw_items_count += len(raw_group)

    normalized_items_count = len(all_entries)
    malformed_output = raw_items_count > 0 and normalized_items_count < raw_items_count
    if isinstance(background_raw, str) or isinstance(interpretations_raw, str) or isinstance(consequences_raw, str):
        malformed_output = True
    for raw_group in (background_raw, interpretations_raw, consequences_raw):
        if raw_group and not isinstance(raw_group, list):
            malformed_output = True

    data_status = str(data.get("data_status") or data.get("expert_coverage") or "limited")

    if malformed_output:
        data_status = "limited"
        confidence = min(confidence, 0.55)

    allowed_types = {"fact", "derived", "interpretation", "external", "uncertain", "consequence", "forecast"}
    allowed_sources = {"article", "comments", "retrieval"}
    contract_invalid = False
    for row in all_entries:
        if not isinstance(row.get("text"), str) or not str(row.get("text")).strip():
            contract_invalid = True
            break
        if str(row.get("type") or "") not in allowed_types:
            contract_invalid = True
            break
        if str(row.get("source") or "") not in allowed_sources:
            contract_invalid = True
            break

    if (data_sufficient or data_status == "sufficient") and (not background or not interpretations or not consequences):
        contract_invalid = True
    if (data_sufficient or data_status == "sufficient") and confidence <= 0.0:
        contract_invalid = True

    if contract_invalid:
        malformed_output = True
        data_status = "limited"
        confidence = min(confidence, 0.55)

    return {
        "background": background,
        "interpretations": interpretations,
        "consequences": consequences,
        "data_status": data_status,
        "confidence": max(0.0, min(1.0, confidence)),
        "malformed_output": malformed_output,
        "contract_invalid": contract_invalid,
    }


def _build_limited_expert_fallback(*, post_text: str, comments: list[str]) -> dict[str, Any]:
    article_hint = _safe_text(post_text, max_len=220) or "The article provides only partial context."
    comments_count = len([item for item in comments if _safe_text(item, max_len=180)])
    comment_hint = (
        f"Comment stream adds {comments_count} local reactions but does not replace missing external context."
        if comments_count > 0
        else "Comments are unavailable or too sparse for strong corroboration."
    )
    return {
        "background": [
            _epistemic_entry(
                text=f"Baseline article signal: {article_hint}",
                claim_type="fact",
                confidence=0.5,
                source="article",
            )
        ],
        "interpretations": [
            _epistemic_entry(
                text="External context is limited, so interpretations remain provisional.",
                claim_type="uncertain",
                confidence=0.45,
                source="article",
            )
        ],
        "consequences": [
            _epistemic_entry(
                text=f"Downstream decisions should stay cautious and explicitly uncertain. {comment_hint}",
                claim_type="uncertain",
                confidence=0.45,
                source="comments" if comments_count > 0 else "article",
            )
        ],
        "data_status": "limited",
        "confidence": 0.5,
        "malformed_output": False,
        "contract_invalid": False,
        "limited_external_context": True,
    }


def _expert_has_structured_claims(expert: dict[str, Any]) -> bool:
    required = ("background", "interpretations", "consequences")
    for key in required:
        group = expert.get(key)
        if not isinstance(group, list) or not group:
            return False
        if not all(isinstance(item, dict) and _safe_text(str(item.get("text") or ""), max_len=500) for item in group):
            return False
    return True


def aggregate_sufficiency_status(steps: dict[str, Any]) -> Literal["sufficient", "limited", "insufficient_data"]:
    context = dict(steps.get("context") or {})
    expert = dict(steps.get("expert") or {})
    public_opinion = dict(steps.get("public_opinion") or {})
    sufficiency = dict(context.get("sufficiency_components") or {})
    article = str(sufficiency.get("article") or "")
    analytical = str(sufficiency.get("analytical") or "")

    if article == "insufficient":
        return "insufficient_data"
    if analytical == "insufficient":
        return "insufficient_data"
    if str(public_opinion.get("data_status") or "") == "weak_signal":
        return "limited"
    if str(expert.get("data_status") or "") == "limited":
        return "limited"
    for step_name in ("context", "routing", "expert", "public_opinion", "synthesis"):
        data_status = str((steps.get(step_name) or {}).get("data_status") or "")
        if data_status == "limited":
            return "limited"
    if bool(expert.get("malformed_output")) or bool(expert.get("contract_invalid")):
        return "limited"
    return "sufficient"


def _ensure_limited_summary_markers(text: str) -> str:
    base = _safe_text(text, max_len=1800)
    markers = ["по имеющимся данным", "реакция ограничена", "требует дополнительной проверки"]
    missing = [marker for marker in markers if marker not in base.lower()]
    if not missing:
        return base
    addon = ". " + ". ".join(missing) + "."
    return _safe_text((base + addon).strip(), max_len=1800)

def _extract_topics(post_text: str, comments: list[str], *, limit: int = 4) -> list[str]:
    stopwords = {
        "this",
        "that",
        "with",
        "have",
        "from",
        "about",
        "there",
        "their",
        "they",
        "were",
        "what",
    }
    merged = " ".join([_safe_text(post_text, max_len=1200), *[_safe_text(item, max_len=200) for item in comments]])
    tokens = [token.lower() for token in _TOKEN_RE.findall(merged)]
    candidates = [token for token in tokens if len(token) >= 4 and token not in stopwords and not token.isdigit()]
    ranked = Counter(candidates).most_common(limit)
    return [token for token, _count in ranked]


def _build_public_opinion_trace(*, post_text: str, comments: list[str], comment_sufficiency: str, analytical_sufficiency: str) -> dict[str, Any]:
    cleaned_comments = [_safe_text(item, max_len=280) for item in comments if _safe_text(item, max_len=280)]
    comments_count = len(cleaned_comments)
    merged = " ".join(cleaned_comments).lower()
    conflict_markers = ("must", "should", "fault", "blame", "ban", "fine", "illegal")
    conflict_hits = sum(merged.count(marker) for marker in conflict_markers)
    if comments_count == 0 or comment_sufficiency in {"insufficient", "weak_signal"}:
        discussion_state = "weak_signal"
    elif conflict_hits >= 3:
        discussion_state = "conflicted"
    elif conflict_hits > 0:
        discussion_state = "mixed"
    else:
        discussion_state = "mixed"
    topics = _extract_topics(post_text, cleaned_comments, limit=4)
    data_status = comment_sufficiency if comment_sufficiency != "sufficient" else analytical_sufficiency
    confidence = 0.25 if data_status in {"insufficient", "weak_signal"} else (0.5 if data_status == "limited" else 0.75)
    dominant_reactions = (
        [{"label": "disagreement", "share": round(min(1.0, conflict_hits / max(1, comments_count)), 4), "evidence_count": conflict_hits}]
        if conflict_hits > 0
        else []
    )
    signals: list[dict[str, Any]] = [
        {"name": "comments_count", "value": comments_count},
        {"name": "conflict_hits", "value": conflict_hits},
    ]
    if topics:
        signals.append({"name": "top_topics", "value": topics})
    return {
        "discussion_state": discussion_state,
        "main_topics": topics,
        "dominant_reactions": dominant_reactions,
        "data_status": data_status,
        "confidence": confidence,
        "signals": signals,
    }


def _build_deterministic_synthesis(
    *,
    post_text: str,
    comment_count: int,
    status: str,
    public_opinion: dict[str, Any],
    retrieval_required: bool,
    retrieval_status: str,
) -> dict[str, Any]:
    topics = list(public_opinion.get("main_topics") or [])
    topics_text = ", ".join(topics[:3]) if topics else "no stable repeated topics"
    discussion_state = str(public_opinion.get("discussion_state") or "unclear")
    limitations = status in {"limited", "insufficient_data"}
    retrieval_limited = retrieval_required and retrieval_status in {"failed", "insufficient", "none"}
    limitation_sentence = (
        "Evidence is limited, so this interpretation should be treated as provisional."
        if limitations
        else "Available evidence supports a bounded but coherent interpretation."
    )
    retrieval_sentence = (
        "Required external retrieval was unavailable, so available external context remains limited and unverified."
        if retrieval_limited
        else "No blocking external retrieval gap was detected for this synthesis."
    )
    report_text = " ".join(
        [
            f"The event centers on this post: {_safe_text(post_text, max_len=170) or 'insufficient source detail'}.",
            f"The context is evaluated as {status}, based on source detail and discussion signal quality.",
            f"Public reaction is {discussion_state}, with {comment_count} usable comments and main topics around {topics_text}.",
            f"The interpretation is that observed reactions indicate {'stable' if status == 'ready' else 'partial'} signal rather than definitive consensus. {limitation_sentence}",
            f"The consequence is that downstream actions should scale confidence to evidence quality. {retrieval_sentence}",
        ]
    ).strip()
    components = {
        "event": True,
        "context": True,
        "reaction": True,
        "interpretation": True,
        "consequences": True,
    }
    return {
        "report_text": report_text,
        "components": components,
        "sentence_count": _sentence_count(report_text),
        "quality": "ok",
        "confidence_reason": "deterministic_spec_synthesis",
    }


def _normalize_synthesis_output(*, candidate: dict[str, Any] | None, fallback: dict[str, Any]) -> dict[str, Any]:
    data = dict(candidate or {})
    report_text = _safe_text(str(data.get("report_text") or data.get("summary") or fallback["report_text"]), max_len=1800)
    sentence_count = int(data.get("sentence_count") or _sentence_count(report_text))
    components_raw = data.get("components")
    components = dict(components_raw) if isinstance(components_raw, dict) else dict(fallback["components"])
    quality = str(data.get("quality") or ("ok" if 5 <= sentence_count <= 7 else "needs_revision"))
    confidence_reason = _safe_text(str(data.get("confidence_reason") or fallback["confidence_reason"]), max_len=500)
    return {
        "report_text": report_text,
        "components": {
            "event": bool(components.get("event")),
            "context": bool(components.get("context")),
            "reaction": bool(components.get("reaction")),
            "interpretation": bool(components.get("interpretation")),
            "consequences": bool(components.get("consequences")),
        },
        "sentence_count": sentence_count,
        "quality": quality,
        "confidence_reason": confidence_reason,
    }


def _collect_reviewer_defects(
    *,
    status: str,
    synthesis: dict[str, Any],
    public_opinion: dict[str, Any],
    expert: dict[str, Any],
    retrieval_required: bool,
    retrieval_status: str,
    retrieval_used: bool,
    retrieval_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []

    components = dict(synthesis.get("components") or {})
    missing = [
        name
        for name in ("event", "context", "reaction", "interpretation", "consequences")
        if components.get(name) is not True
    ]
    sentence_count = int(synthesis.get("sentence_count") or 0)
    report_text = _safe_text(str(synthesis.get("report_text") or ""), max_len=1800).lower()

    if missing or sentence_count < 5 or sentence_count > 7:
        defects.append(
            {
                "code": "D1",
                "reason": f"structural_missing:{','.join(missing) or 'sentence_count'}",
                "target": "synthesis",
            }
        )

    if str(synthesis.get("quality") or "") != "ok":
        defects.append({"code": "D2", "reason": "weak_analysis", "target": "synthesis"})

    if retrieval_required and retrieval_status in {"failed", "insufficient", "none"} and status == "ready":
        defects.append(
            {
                "code": "D3",
                "reason": "ready_forbidden_without_required_retrieval",
                "target": "routing",
            }
        )

    if status == "insufficient_data" and ("indicates" in report_text or "supports" in report_text):
        defects.append(
            {
                "code": "D4",
                "reason": "insufficient_data_overclaim",
                "target": "synthesis",
            }
        )

    if retrieval_used and not retrieval_sources:
        defects.append(
            {
                "code": "D5",
                "reason": "missing_retrieval_evidence",
                "target": "routing",
            }
        )

    expert_entries: list[dict[str, Any]] = []
    for key in ("background", "interpretations", "consequences"):
        value = expert.get(key)
        if isinstance(value, list):
            expert_entries.extend([item for item in value if isinstance(item, dict)])

    retrieval_success = retrieval_used and retrieval_status == "success" and bool(retrieval_sources)

    for item in expert_entries:
        if str(item.get("type") or "") == "external" and not retrieval_success:
            defects.append(
                {
                    "code": "D3",
                    "reason": "external_expert_claim_without_retrieval",
                    "target": "expert",
                }
            )
            break

        if str(item.get("source") or "") == "retrieval" and not retrieval_success:
            defects.append(
                {
                    "code": "D3",
                    "reason": "retrieval_sourced_claim_without_evidence",
                    "target": "expert",
                }
            )
            break

    if bool(expert.get("malformed_output")) or bool(expert.get("contract_invalid")):
        defects.append(
            {
                "code": "D5",
                "reason": "expert_contract_invalid_or_malformed",
                "target": "expert",
            }
        )

    expert_confidence = float(expert.get("confidence") or 0.0)
    expert_status = str(expert.get("status") or "completed")
    if expert_confidence <= 0.0 and expert_status == "completed":
        defects.append(
            {
                "code": "D3",
                "reason": "expert_zero_confidence_completed",
                "target": "expert",
            }
        )

    if status == "ready" and str(public_opinion.get("data_status") or "") in {"weak_signal", "insufficient"}:
        defects.append(
            {
                "code": "D6",
                "reason": "status_vs_signal_inconsistency",
                "target": "public_opinion",
            }
        )

    return defects

def _simplify_retrieval_for_expert(retrieval_trace: dict[str, Any]) -> dict[str, Any]:
    sources = retrieval_trace.get("sources", [])[:3]
    simplified_sources = []
    for s in sources:
        supports = s.get("supports", "")
        if isinstance(supports, str):
            supports = supports[:500]  # обрезаем длинные выдержки
        simplified_sources.append({
            "title": s.get("title", "")[:100],
            "source": s.get("source", "").split("//")[-1].split("/")[0][:50],  # домен или короткое имя
            "supports": supports,
        })
    return {
        "required": retrieval_trace.get("required", False),
        "used": retrieval_trace.get("used", False),
        "status": retrieval_trace.get("status", "none"),
        "sources": simplified_sources,
    }

def _build_retrieval_decision_inputs(*, post_text: str, comments: list[str]) -> dict[str, bool]:
    normalized_post = _safe_text(post_text, max_len=2000).lower()
    normalized_comments = " ".join(_safe_text(item, max_len=200).lower() for item in comments[:10])
    merged = f"{normalized_post} {normalized_comments}".strip()
    institutional_context = any(
        token in merged
        for token in ("government", "ministry", "president", "parliament", "правительств", "министер", "президент")
    )
    international_context = any(
        token in merged
        for token in ("eu", "nato", "un ", "санкц", "международ", "foreign", "border", "global")
    )
    high_error_cost = any(
        token in merged
        for token in ("sanction", "war", "crisis", "election", "санкц", "войн", "кризис", "выбор")
    )
    external_context_missing = len(normalized_post) < 220 or any(
        token in normalized_post
        for token in ("details", "without details", "без подроб", "как сообщалось ранее", "контекст не указан")
    )
    return {
        "institutional_context": institutional_context,
        "international_context": international_context,
        "external_context_missing": external_context_missing,
        "high_error_cost": high_error_cost,
    }


def _build_epistemic_claims(
    *,
    post_text: str,
    comments: list[str],
    status: str,
    analytical_sufficiency: str,
    retrieval_used: bool,
    retrieval_status: str,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    normalized_post = _safe_text(post_text, max_len=240)
    if normalized_post:
        claims.append(
            {
                "text": normalized_post,
                "type": "fact",
                "confidence": 0.7 if status == "ready" else 0.5,
                "source": "article",
            }
        )
    if comments:
        claims.append(
            {
                "text": f"Observed recurring discussion signals in {len(comments)} comments.",
                "type": "derived",
                "confidence": 0.65 if status == "ready" else 0.5,
                "source": "comments",
            }
        )
    if analytical_sufficiency in {"limited", "insufficient"}:
        claims.append(
            {
                "text": "Interpretation remains constrained by available evidence quality.",
                "type": "interpretation",
                "confidence": 0.5,
                "source": "article",
            }
        )
    if status in {"limited", "insufficient_data"}:
        claims.append(
            {
                "text": "Some conclusions remain uncertain due to data sufficiency limits.",
                "type": "uncertain",
                "confidence": 0.4 if status == "limited" else 0.3,
                "source": "comments" if comments else "article",
            }
        )
    if retrieval_used and retrieval_status == "success":
        claims.append(
            {
                "text": "External context was incorporated from retrieval evidence.",
                "type": "external",
                "confidence": 0.6,
                "source": "retrieval",
            }
        )
    return claims


def _build_base_payload(
    *,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    status: str,
    summary: str,
    confidence_reason: str,
) -> dict[str, Any]:
    quote_candidates = [
        _safe_text(comment, max_len=180)
        for comment in comments
        if _safe_text(comment, max_len=180)
    ]
    return {
        "type": "post_report_v2",
        "status": status,
        "post_id": post_id,
        "published_at": published_at_iso,
        "title": f"Post {post_id} discussion snapshot",
        "summary": summary,
        "comment_count": len(comments),
        "sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "low" if status != "ready" else "medium",
        },
        "topics": [],
        "clusters": [],
        "time_trends": [],
        "risks": [],
        "anomalies": [],
        "representative_quotes": quote_candidates[:5],
        "confidence": {
            "overall": "low" if status == "insufficient_data" else ("medium" if status == "limited" else "high"),
            "reason": confidence_reason,
        },
    }


def _default_provider_trace(*, adapter: OpenAIClientAdapter) -> OpenAIChatCompletionTrace:
    base_url = str(getattr(getattr(adapter, "config", None), "base_url", "") or "").lower()
    provider = "openrouter" if "openrouter" in base_url else "openai_compatible"
    model = str(getattr(getattr(adapter, "config", None), "model", "") or "")
    return OpenAIChatCompletionTrace(
        content="",
        provider=provider,
        model=model,
        latency_ms=None,
        fallback_used=False,
        fallback_reason=None,
        executed=True,
        success=True,
        attempt_index=0,
    )


def _apply_step_provider_trace(
    *,
    step_traces: dict[str, dict[str, Any]],
    step_name: str,
    trace: OpenAIChatCompletionTrace,
) -> None:
    step = dict(step_traces.get(step_name) or {})
    provenance = dict(step.get("provenance") or {})
    provenance.update(
        {
            "provider": trace.provider,
            "model": trace.model,
            "executed": bool(trace.executed),
            "success": bool(trace.success),
            "latency_ms": trace.latency_ms,
            "fallback_used": bool(trace.fallback_used),
            "fallback_reason": trace.fallback_reason,
            "attempt_index": int(trace.attempt_index),
            "input_ref": trace.input_ref,
            "input_hash": trace.input_hash,
            "output_ref": trace.output_ref,
            "output_hash": trace.output_hash,
            "status": "completed" if trace.success else "failed",
        }
    )
    step["provenance"] = provenance
    if trace.success:
        step["status"] = str(step.get("status") or "completed")
    else:
        step["status"] = "failed"
    step_traces[step_name] = step


def _provider_error_trace(
    *,
    adapter: OpenAIClientAdapter,
    reason: str,
) -> OpenAIChatCompletionTrace:
    base = _default_provider_trace(adapter=adapter)
    return OpenAIChatCompletionTrace(
        content="",
        provider=base.provider,
        model=base.model,
        latency_ms=base.latency_ms,
        fallback_used=True,
        fallback_reason=reason,
        executed=True,
        success=False,
        attempt_index=base.attempt_index,
    )


async def _try_llm_json_step(
    *,
    adapter: OpenAIClientAdapter,
    step_name: str,
    prompt_text: str,
    request_payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, OpenAIChatCompletionTrace]:
    input_ref = f"inline://{step_name}/input"
    output_ref = f"inline://{step_name}/output"
    input_hash = _stable_hash(request_payload)

    default_trace = _default_provider_trace(adapter=adapter)
    trace = default_trace
    if hasattr(adapter, "create_chat_completion_with_trace"):
        trace = await adapter.create_chat_completion_with_trace(
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        content = trace.content
    else:
        content = await adapter.create_chat_completion(
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        trace = OpenAIChatCompletionTrace(
            content=content,
            provider=default_trace.provider,
            model=default_trace.model,
            latency_ms=default_trace.latency_ms,
            fallback_used=default_trace.fallback_used,
            fallback_reason=default_trace.fallback_reason,
            executed=True,
            success=True,
            attempt_index=default_trace.attempt_index,
            input_ref=input_ref,
            input_hash=input_hash,
            output_ref=output_ref,
            output_hash=_stable_hash(content),
        )
    trace = OpenAIChatCompletionTrace(
        content=trace.content,
        provider=trace.provider,
        model=trace.model,
        latency_ms=trace.latency_ms,
        fallback_used=trace.fallback_used,
        fallback_reason=trace.fallback_reason,
        executed=trace.executed,
        success=trace.success,
        attempt_index=trace.attempt_index,
        input_ref=input_ref,
        input_hash=input_hash,
        output_ref=output_ref,
        output_hash=_stable_hash(content),
    )
    if not content:
        return None, OpenAIChatCompletionTrace(
            content=content,
            provider=trace.provider,
            model=trace.model,
            latency_ms=trace.latency_ms,
            fallback_used=True,
            fallback_reason=f"{step_name}_empty_output",
            executed=True,
            success=False,
            attempt_index=trace.attempt_index,
            input_ref=input_ref,
            input_hash=input_hash,
            output_ref=output_ref,
            output_hash=_stable_hash(content),
        )
    
    # Быстрая проверка: ответ должен начинаться с '{' (JSON object)
    content_stripped = content.strip()
    if not content_stripped.startswith('{'):
        logger.warning(
            "Step %s returned content that does not start with '{': %s",
            step_name, content_stripped[:200]
        )
        return None, OpenAIChatCompletionTrace(
            content=content,
            provider=trace.provider,
            model=trace.model,
            latency_ms=trace.latency_ms,
            fallback_used=True,
            fallback_reason=f"{step_name}_malformed_not_object",
            executed=True,
            success=False,
            attempt_index=trace.attempt_index,
            input_ref=input_ref,
            input_hash=input_hash,
            output_ref=output_ref,
            output_hash=_stable_hash(content),
        )
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None, OpenAIChatCompletionTrace(
            content=content,
            provider=trace.provider,
            model=trace.model,
            latency_ms=trace.latency_ms,
            fallback_used=True,
            fallback_reason=f"{step_name}_invalid_json",
            executed=True,
            success=False,
            attempt_index=trace.attempt_index,
            input_ref=input_ref,
            input_hash=input_hash,
            output_ref=output_ref,
            output_hash=_stable_hash(content),
        )
    if not isinstance(data, dict):
        return None, OpenAIChatCompletionTrace(
            content=content,
            provider=trace.provider,
            model=trace.model,
            latency_ms=trace.latency_ms,
            fallback_used=True,
            fallback_reason=f"{step_name}_invalid_payload",
            executed=True,
            success=False,
            attempt_index=trace.attempt_index,
            input_ref=input_ref,
            input_hash=input_hash,
            output_ref=output_ref,
            output_hash=_stable_hash(content),
        )
    return data, OpenAIChatCompletionTrace(
        content=content,
        provider=trace.provider,
        model=trace.model,
        latency_ms=trace.latency_ms,
        fallback_used=trace.fallback_used,
        fallback_reason=trace.fallback_reason,
        executed=True,
        success=True,
        attempt_index=trace.attempt_index,
        input_ref=input_ref,
        input_hash=input_hash,
        output_ref=output_ref,
        output_hash=_stable_hash(content),
    )

def create_router_from_file() -> ModelRouter | None:
    file_path = os.getenv("REPORT_V2_ROUTER_MODELS_FILE")
    if not file_path:
        # Можно задать путь по умолчанию
        file_path = "services/llm/router_models.json"
    
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"Router models file not found: {path}")
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        models = []
        for item in data:
            models.append(ModelEntry(
                name=item["name"],
                provider=item["provider"],
                base_url=item["base_url"],
                api_key=item.get("api_key"),  # может быть None
                max_tokens_per_day=item.get("max_tokens_per_day", 0),
                max_requests_per_minute=item.get("max_requests_per_minute", 0),
            ))
        router = ModelRouter(models)
        logger.info(f"Loaded {len(models)} models from {path}")
        return router
    except Exception as e:
        logger.error(f"Failed to load router models from {path}: {e}")
        return None

async def generate_post_report_payload_v2(
    *,
    channel: str,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    thread_comments: list[dict],
    views: int | None,
    job_timeout_seconds: int | None = None,
    rerun_stage: str | None = None,
    effective_features: dict[str, Any] | None = None,
    prompt_loader: PromptLoader | None = None,
    llm_adapter: OpenAIClientAdapter | None = None,
    retrieval_provider: Any | None = None,
) -> dict[str, Any]:
    del channel, thread_comments, views, job_timeout_seconds
    payload = None

    try:
        loader = prompt_loader or PromptLoader()
        prompts = loader.load_bundle("post")

        step_traces: dict[str, dict[str, Any]] = build_step_traces(PIPELINE_STEP_KEYS)
        custom_search_queries = []
        article_sufficiency = assess_article_sufficiency(text=post_text)
        comment_sufficiency = assess_comment_sufficiency(comments=comments)
        retrieval_inputs = _build_retrieval_decision_inputs(post_text=post_text, comments=comments)
        force_retrieval_for_all_reports = bool(
            (effective_features or {}).get("force_retrieval_for_all_reports", True)
        )
        retrieval_required = (
            True
            if force_retrieval_for_all_reports
            else decide_retrieval_required(**retrieval_inputs)
        )
        retrieval_request = {
            "kind": "post",
            "post_id": post_id,
            "post_text": _safe_text(post_text, max_len=2400),
            "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
            "decision_inputs": retrieval_inputs,
        }

        requested_rerun = (rerun_stage or "").strip() or None

        if llm_adapter is None:
            cfg = OpenAIAdapterConfig.from_settings()
            router = None
            
            logger.info(f"Routing enabled in config: {cfg.routing_enabled}")
            
            if cfg.routing_enabled:
                file_path = os.getenv("REPORT_V2_ROUTER_MODELS_FILE")
                if not file_path:
                    # Кросс-платформенный путь по умолчанию
                    file_path = "services/llm/router_models.json"
                
                logger.info(f"Attempting to load router from: {file_path}")
                
                # Проверяем существование файла
                path = Path(file_path)
                if not path.exists():
                    logger.error(f"Router models file NOT FOUND at: {path.absolute()}")
                else:
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        models = []
                        for item in data:
                            models.append(ModelEntry(
                                name=item["name"],
                                provider=item["provider"],
                                base_url=item["base_url"],
                                api_key=item.get("api_key"),
                                max_tokens_per_day=item.get("max_tokens_per_day", 0),
                                max_requests_per_minute=item.get("max_requests_per_minute", 0),
                            ))
                        if models:
                            router = ModelRouter(models)
                            logger.info(f"✅ ModelRouter successfully loaded with {len(models)} models from {path}")
                        else:
                            logger.warning("Router file contains no models")
                    except Exception as e:
                        logger.exception(f"Failed to load router models from {path}: {e}")
            else:
                logger.info("Routing is disabled (REPORT_V2_OPENAI_ROUTING_ENABLED=false)")
            
            if cfg.api_key:
                llm_adapter = OpenAIClientAdapter(cfg, router=router)
                if router:
                    logger.info("✅ Router attached to OpenAIClientAdapter")
                else:
                    logger.info("OpenAIClientAdapter created without router (fallback to single model)")
            else:
                logger.error("No API key provided for LLM adapter")

        llm_error: str | None = None
        llm_output: dict[str, Any] | None = None
        reviewer_llm_output: dict[str, Any] | None = None
        if llm_adapter is not None:
            try:
                context_output, context_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="context",
                    prompt_text=prompts["context"],
                    request_payload={
                        "post_text": _safe_text(post_text, max_len=1600),
                        "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
                    },
                )
                context_output = _safe_dict(context_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="context", trace=context_trace)
                if isinstance(context_output, dict):
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="context",
                        mutator=lambda trace: trace.update({"llm_context": context_output}),
                    )
            except Exception as exc:
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="context",
                    trace=_provider_error_trace(adapter=llm_adapter, reason=f"context_error:{type(exc).__name__}"),
                )

            custom_search_queries = []

            try:
                routing_output, routing_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="routing",
                    prompt_text=prompts["routing"],
                    request_payload={
                        "post_text": _safe_text(post_text, max_len=1600),
                        "retrieval_hints": retrieval_inputs,
                    },
                )
                routing_output = _safe_dict(routing_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="routing", trace=routing_trace)
                
                if isinstance(routing_output, dict):
                    custom_search_queries = routing_output.get("search_queries", [])
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="routing",
                        mutator=lambda trace: trace.update({
                    "llm_routing": routing_output,
                    "search_queries": custom_search_queries,
                        }),
                    )
                    if custom_search_queries:
                        logger.info(
                            "Routing generated %d search queries for post_id=%s: %s",
                            len(custom_search_queries),
                            post_id,
                            [q.get("text") for q in custom_search_queries[:5]]
                        )
                    else:
                        logger.debug("No search_queries field in routing output for post_id=%s", post_id)
                else:
                    custom_search_queries = []
            except Exception as exc:
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="routing",
                    trace=_provider_error_trace(adapter=llm_adapter, reason=f"routing_error:{type(exc).__name__}"),
                )
                logger.warning("Routing failed for post_id=%s, error=%s, falling back to default queries", post_id, exc)
                custom_search_queries = []

            if retrieval_required:
                retrieval_params = {
                    **retrieval_request,
                    "category": str((effective_features or {}).get("retrieval_category") or "news"),
                }
                logger.info(
                    f"Initiating SearXNG retrieval for post_id={post_id}. "
                    f"Query hint/text preview: {retrieval_request.get('post_text')[:100]}..."
                )
                logger.debug(f"SearXNG retrieval full payload: {json.dumps(retrieval_params, ensure_ascii=False)}")
                try:
                    retrieval_pack = await run_retrieval_manager(
                        retrieval_provider,
                        retrieval_params,
                        custom_queries=custom_search_queries if custom_search_queries else None,
                    )
                    sources_count = len(retrieval_pack.get("sources") or [])
                    logger.info(
                        f"SearXNG retrieval completed for post_id={post_id}. "
                        f"Status: {retrieval_pack.get('status')}, Found sources: {sources_count}"
                    )
                    logger.debug(f"SearXNG raw results sample: {list(retrieval_pack.get('sources') or [])[:3]}")
                except Exception as e:
                    logger.error(f"SearXNG retrieval failed for post_id={post_id} due to error: {str(e)}", exc_info=True)
                    raise e
            else:
                logger.info(f"SearXNG retrieval skipped for post_id={post_id} (retrieval_required=False).")
                retrieval_pack = {
                    "status": "none",
                    "quality_score": 0.0,
                    "sources": [],
                    "facts": [],
                    "conflicts": [],
                    "gaps": [],
                    "diagnostics": {},
                    "raw_results": [],
                }

            retrieval_provider_sources = list(retrieval_pack.get("sources") or [])
            provider_enabled = retrieval_provider is not None or bool(
                (effective_features or {}).get("retrieval_provider_enabled", False)
            )
            retrieval_trace = build_retrieval_trace(
                required=retrieval_required,
                provider_enabled=provider_enabled,
                sources=retrieval_provider_sources,
                decision_inputs=retrieval_inputs,
                decision_source="retrieval_policy",
                status_override=str(retrieval_pack.get("status") or "success"),
                quality_score=float(retrieval_pack.get("quality_score") or 0.0),
                facts=list(retrieval_pack.get("facts") or []),
                conflicts=list(retrieval_pack.get("conflicts") or []),
                gaps=[str(item) for item in list(retrieval_pack.get("gaps") or [])],
                diagnostics=dict(retrieval_pack.get("diagnostics") or {}),
                raw_results=list(retrieval_pack.get("raw_results") or []),
            )

            retrieval_used = bool(retrieval_trace["used"])
            retrieval_status = str(retrieval_trace["status"])
            retrieval_sources = list(retrieval_trace["sources"])

            retrieval_sufficiency = assess_retrieval_sufficiency(
                required=retrieval_required,
                used=retrieval_used,
                status=retrieval_status,
                sources=retrieval_sources,
            )
            analytical_sufficiency = assess_analytical_sufficiency(
                article=article_sufficiency,
                comment=comment_sufficiency,
                retrieval=retrieval_sufficiency,
            )
            target_status = aggregate_public_status(
                article=article_sufficiency,
                comment=comment_sufficiency,
                retrieval=retrieval_sufficiency,
                analytical=analytical_sufficiency,
            )
            public_opinion_trace = _build_public_opinion_trace(
                post_text=post_text,
                comments=comments,
                comment_sufficiency=comment_sufficiency,
                analytical_sufficiency=analytical_sufficiency,
            )
            synthesis_data = _build_deterministic_synthesis(
                post_text=post_text,
                comment_count=len(comments),
                status=target_status,
                public_opinion=public_opinion_trace,
                retrieval_required=retrieval_required,
                retrieval_status=retrieval_status,
            )
            try:
                expert_output, expert_trace = await _try_llm_json_step(adapter=llm_adapter,
                        step_name="expert",
                        prompt_text=prompts["expert"],
                        request_payload={
                            "post_text": _safe_text(post_text, max_len=1600),
                            "comments": [_safe_text(item, max_len=260) for item in comments[:20]],
                            "status_hint": target_status,
                            "analytical_sufficiency": analytical_sufficiency,
                            "retrieval": _simplify_retrieval_for_expert(retrieval_trace),
                            "retrieval_instruction": "Используйте данные для поиска только тогда, когда retrieval.used имеет значение true; в противном случае не добавляйте внешние факты.",
                        },)
                expert_output = _safe_dict(expert_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="expert", trace=expert_trace)
                
                if isinstance(expert_output, dict):
                    normalized_expert = _normalize_expert_output(
                        candidate=expert_output,
                        retrieval_success=retrieval_used and retrieval_status == "success",
                        data_sufficient=analytical_sufficiency == "sufficient",
                    )
                    retrieval_limited = retrieval_status in {"failed", "insufficient"}
                    local_context_available = bool(_safe_text(post_text, max_len=120)) or any(_safe_text(item, max_len=120) for item in comments)
                    should_degrade_to_limited = retrieval_limited and local_context_available and (
                        bool(normalized_expert.get("malformed_output"))
                        or bool(normalized_expert.get("contract_invalid"))
                        or not _expert_has_structured_claims(normalized_expert)
                    )
                    if should_degrade_to_limited:
                        normalized_expert = _build_limited_expert_fallback(post_text=post_text, comments=comments)
                    elif retrieval_limited:
                        normalized_expert["confidence"] = min(float(normalized_expert.get("confidence") or 0.0), 0.55)

                    expert_completed = (
                        not bool(normalized_expert.get("malformed_output"))
                        and not bool(normalized_expert.get("contract_invalid"))
                        and _expert_has_structured_claims(normalized_expert)
                        and float(normalized_expert.get("confidence") or 0.0) > 0.0
                    )
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="expert",
                        mutator=lambda trace: trace.update(
                            {
                                "llm_expert": expert_output,
                                **normalized_expert,
                                "status": "completed" if expert_completed else "failed",
                            }
                        ),
                    )
                else:
                    # LLM вернул невалидный JSON или None – используем fallback
                    normalized_expert = _build_limited_expert_fallback(post_text=post_text, comments=comments)
                    normalized_expert["malformed_output"] = True
                    normalized_expert["contract_invalid"] = True
                    expert_completed = False
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="expert",
                        mutator=lambda trace: trace.update(
                            {
                                "llm_expert": None,
                                **normalized_expert,
                                "status": "failed",
                            }
                        ),
                    )
                    logger.warning(
                        "Expert step returned invalid JSON for post_id=%s, using fallback. trace=%s",
                        post_id, expert_trace
                    )
            except Exception as exc:
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="expert",
                    trace=_provider_error_trace(adapter=llm_adapter, reason=f"expert_error:{type(exc).__name__}"),
                )

            try:
                public_output, public_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="public_opinion",
                    prompt_text=prompts["public_opinion"],
                    request_payload={
                        "post_text": _safe_text(post_text, max_len=1400),
                        "comments": [_safe_text(item, max_len=260) for item in comments[:40]],
                        "status_hint": target_status,
                    },
                )
                public_output = _safe_dict(public_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="public_opinion", trace=public_trace)
                if isinstance(public_output, dict):
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="public_opinion",
                        mutator=lambda trace: trace.update({"llm_public_opinion": public_output}),
                    )
            except Exception as exc:
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="public_opinion",
                    trace=_provider_error_trace(adapter=llm_adapter, reason=f"public_opinion_error:{type(exc).__name__}"),
                )

            try:
                llm_output, synthesis_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="synthesis",
                    prompt_text=prompts["synthesis"],
                    request_payload={
                        "status_hint": target_status,
                        "post_text": _safe_text(post_text, max_len=1600),
                        "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
                        "retrieval": retrieval_trace,
                    },
                )
                llm_output = _safe_dict(llm_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="synthesis", trace=synthesis_trace)
                if isinstance(llm_output, dict):
                    synthesis_data = _normalize_synthesis_output(candidate=llm_output, fallback=synthesis_data)
                    logger.info("✅ synthesis_data updated from LLM for post_id=%s, preview=%s",
                                post_id, synthesis_data.get("report_text", "")[:100])
                else:
                    logger.warning("❌ LLM synthesis output invalid for post_id=%s, using fallback", post_id)
            except Exception as exc:
                llm_error = f"{type(exc).__name__}: {exc}"
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="synthesis",
                    trace=_provider_error_trace(adapter=llm_adapter, reason="synthesis_error"),
                )

            try:
                reviewer_llm_output, reviewer_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="reviewer",
                    prompt_text=prompts["reviewer"],
                    request_payload={
                        "status_hint": target_status,
                        "context": step_traces.get("context", {}),   
                        "routing": step_traces.get("routing", {}),   
                        "public_opinion": step_traces.get("public_opinion", {}),
                        "synthesis": synthesis_data,
                        "retrieval_required": retrieval_required,
                        "retrieval_status": retrieval_status,
                        "retrieval": retrieval_trace,
                        "expert": step_traces.get("expert", {}),
                    },
                )
                reviewer_llm_output = _safe_dict(reviewer_llm_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="reviewer", trace=reviewer_trace)
                if isinstance(reviewer_llm_output, dict):
                    apply_step_trace_envelope(
                        step_traces,
                        step_name="reviewer",
                        mutator=lambda trace: trace.update({"llm_reviewer": reviewer_llm_output}),
                    )
            except Exception as exc:
                _apply_step_provider_trace(
                    step_traces=step_traces,
                    step_name="reviewer",
                    trace=_provider_error_trace(adapter=llm_adapter, reason=f"reviewer_error:{type(exc).__name__}"),
                )

        llm_reviewer = reviewer_llm_output if isinstance(reviewer_llm_output, dict) else None
        effective_llm_decision = resolve_effective_review_decision("accept", llm_reviewer) if llm_error is None else ""
        llm_rerun_target = _infer_reviewer_target(llm_reviewer, default_target="synthesis")

        async def _execute_rerun_cycle(branch: str) -> None:
            nonlocal llm_error, llm_output, reviewer_llm_output, synthesis_data
            if llm_adapter is None:
                return
            try:
                if branch == "context":
                    context_output, context_trace = await _try_llm_json_step(
                        adapter=llm_adapter,
                        step_name="context",
                        prompt_text=prompts["context"],
                        request_payload={
                            "post_text": _safe_text(post_text, max_len=1600),
                            "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
                            "status_hint": target_status,
                        },
                    )
                    context_output = _safe_dict(context_output)
                    _apply_step_provider_trace(step_traces=step_traces, step_name="context", trace=context_trace)
                    if isinstance(context_output, dict):
                        apply_step_trace_envelope(step_traces, step_name="context", mutator=lambda trace: trace.update({"llm_context": context_output}))
                elif branch == "routing":
                    routing_output, routing_trace = await _try_llm_json_step(
                        adapter=llm_adapter,
                        step_name="routing",
                        prompt_text=prompts["routing"],
                        request_payload={
                            "post_text": _safe_text(post_text, max_len=1600),
                            "status_hint": target_status,
                            "retrieval_hints": retrieval_inputs,
                        },
                    )
                    routing_output = _safe_dict(routing_output)
                    _apply_step_provider_trace(step_traces=step_traces, step_name="routing", trace=routing_trace)
                    if isinstance(routing_output, dict):
                        apply_step_trace_envelope(step_traces, step_name="routing", mutator=lambda trace: trace.update({"llm_routing": routing_output}))
                elif branch == "expert":
                    expert_output, expert_trace = await _try_llm_json_step(
                        adapter=llm_adapter,
                        step_name="expert",
                        prompt_text=prompts["expert"],
                        request_payload={
                            "post_text": _safe_text(post_text, max_len=1600),
                            "comments": [_safe_text(item, max_len=260) for item in comments[:20]],
                            "status_hint": target_status,
                            "analytical_sufficiency": analytical_sufficiency,
                            "retrieval": _simplify_retrieval_for_expert(retrieval_trace),
                            "retrieval_instruction": "Используйте данные для поиска только тогда, когда retrieval.used имеет значение true; в противном случае не добавляйте внешние факты..",
                        },
                    )
                    expert_output = _safe_dict(expert_output)
                    _apply_step_provider_trace(step_traces=step_traces, step_name="expert", trace=expert_trace)
                    if isinstance(expert_output, dict):
                        normalized_expert = _normalize_expert_output(
                            candidate=expert_output,
                            retrieval_success=retrieval_used and retrieval_status == "success",
                            data_sufficient=analytical_sufficiency == "sufficient",
                        )
                        retrieval_limited = retrieval_status in {"failed", "insufficient"}
                        local_context_available = bool(_safe_text(post_text, max_len=120)) or any(_safe_text(item, max_len=120) for item in comments)
                        should_degrade_to_limited = retrieval_limited and local_context_available and (
                            bool(normalized_expert.get("malformed_output"))
                            or bool(normalized_expert.get("contract_invalid"))
                            or not _expert_has_structured_claims(normalized_expert)
                        )
                        if should_degrade_to_limited:
                            normalized_expert = _build_limited_expert_fallback(post_text=post_text, comments=comments)
                        elif retrieval_limited:
                            normalized_expert["confidence"] = min(float(normalized_expert.get("confidence") or 0.0), 0.55)

                        expert_completed = (
                            not bool(normalized_expert.get("malformed_output"))
                            and not bool(normalized_expert.get("contract_invalid"))
                            and _expert_has_structured_claims(normalized_expert)
                            and float(normalized_expert.get("confidence") or 0.0) > 0.0
                        )
                        apply_step_trace_envelope(
                            step_traces,
                            step_name="expert",
                            mutator=lambda trace: trace.update(
                                {
                                    "llm_expert": expert_output,
                                    **normalized_expert,
                                    "status": "completed" if expert_completed else "failed",
                                }
                            ),
                        )
                elif branch == "public_opinion":
                    public_output, public_trace = await _try_llm_json_step(
                        adapter=llm_adapter,
                        step_name="public_opinion",
                        prompt_text=prompts["public_opinion"],
                        request_payload={
                            "post_text": _safe_text(post_text, max_len=1400),
                            "comments": [_safe_text(item, max_len=260) for item in comments[:40]],
                            "status_hint": target_status,
                        },
                    )
                    public_output = _safe_dict(public_output)
                    _apply_step_provider_trace(step_traces=step_traces, step_name="public_opinion", trace=public_trace)
                    if isinstance(public_output, dict):
                        apply_step_trace_envelope(step_traces, step_name="public_opinion", mutator=lambda trace: trace.update({"llm_public_opinion": public_output}))

                llm_output, synthesis_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="synthesis",
                    prompt_text=prompts["synthesis"],
                    request_payload={
                        "status_hint": target_status,
                        "post_text": _safe_text(post_text, max_len=1600),
                        "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
                        "retrieval": retrieval_trace,
                    },
                )
                llm_output = _safe_dict(llm_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="synthesis", trace=synthesis_trace)
                if isinstance(llm_output, dict):
                    synthesis_data = _normalize_synthesis_output(candidate=llm_output, fallback=synthesis_data)
                    logger.info("✅ synthesis_data updated from LLM for post_id=%s, preview=%s",
                                post_id, synthesis_data.get("report_text", "")[:100])
                else:
                    logger.warning("❌ LLM synthesis output invalid for post_id=%s, using fallback", post_id)
                llm_error = None

                reviewer_llm_output, reviewer_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="reviewer",
                    prompt_text=prompts["reviewer"],
                    request_payload={
                        "status_hint": target_status,
                        "context": step_traces.get("context", {}), 
                        "routing": step_traces.get("routing", {}),
                        "public_opinion": step_traces.get("public_opinion", {}),  
                        "synthesis": synthesis_data,
                        "retrieval_required": retrieval_required,
                        "retrieval_status": retrieval_status,
                        "retrieval": retrieval_trace,
                        "expert": step_traces.get("expert", {}),
                    },
                )
                reviewer_llm_output = _safe_dict(reviewer_llm_output)
                _apply_step_provider_trace(step_traces=step_traces, step_name="reviewer", trace=reviewer_trace)
                if isinstance(reviewer_llm_output, dict):
                    apply_step_trace_envelope(step_traces, step_name="reviewer", mutator=lambda trace: trace.update({"llm_reviewer": reviewer_llm_output}))
            except Exception as exc:
                llm_error = f"{type(exc).__name__}: {exc}"

        review_history: list[dict[str, Any]] = []
        review_reruns = 0
        pending_rerun = requested_rerun if requested_rerun in {"context", "routing", "expert", "public_opinion", "synthesis"} else None
        pending_reason = "manual_rerun_request" if pending_rerun else ""

        if pending_rerun is None and llm_error is not None:
            pending_rerun = "synthesis"
            pending_reason = "synthesis_error"


        if pending_rerun is None and effective_llm_decision in ("rerun_branch", "revise"):
            pending_rerun = llm_rerun_target
            pending_reason = f"llm_reviewer_requested_{effective_llm_decision}"

        if pending_rerun is None and effective_llm_decision == "revise":
            pending_rerun = "synthesis"
            pending_reason = "revise_without_target"

        while pending_rerun is not None and review_reruns < REVIEW_MAX_ITERATIONS:
            request_step_rerun(step_traces, step_name=pending_rerun)
            if pending_rerun != "synthesis":
                request_step_rerun(step_traces, step_name="synthesis")
            review_reruns += 1
            review_history.append(
                {
                    "iteration": len(review_history) + 1,
                    "decision": "rerun_branch",
                    "target": pending_rerun,
                    "reason": pending_reason,
                    "confidence": 1.0,
                }
            )
            await _execute_rerun_cycle(pending_rerun)
            llm_reviewer = reviewer_llm_output if isinstance(reviewer_llm_output, dict) else None
            effective_llm_decision = resolve_effective_review_decision("accept", llm_reviewer) if llm_error is None else ""
            next_target = _infer_reviewer_target(llm_reviewer, default_target="synthesis")
            if llm_error is not None and review_reruns < REVIEW_MAX_ITERATIONS:
                pending_rerun = "synthesis"
                pending_reason = "synthesis_error"
            elif effective_llm_decision == "rerun_branch" and review_reruns < REVIEW_MAX_ITERATIONS:
                pending_rerun = next_target
                pending_reason = "llm_reviewer_requested_rerun"
            else:
                pending_rerun = None
                pending_reason = ""

        if pending_rerun is not None:
            target_status = "limited" if target_status == "ready" else target_status
            review_history.append(
                {
                    "iteration": len(review_history) + 1,
                    "decision": "accept_with_limitations",
                    "target": pending_rerun,
                    "reason": "rerun_limit_exhausted",
                    "confidence": 0.4,
                }
            )

        llm_reviewer_has_issues = _has_reviewer_issues(llm_reviewer)

        if llm_error is None:
            if effective_llm_decision == "revise":
                target_status = "limited" if target_status == "ready" else target_status
                review_history.append(
                    {
                        "iteration": len(review_history) + 1,
                        "decision": "revise",
                        "target": _infer_reviewer_target(llm_reviewer, default_target="synthesis"),
                        "reason": "llm_reviewer_issues",
                        "confidence": 0.45,
                    }
                )
            elif effective_llm_decision == "insufficient_data":
                target_status = "insufficient_data"
                review_history.append(
                    {
                        "iteration": len(review_history) + 1,
                        "decision": "insufficient_data",
                        "target": _infer_reviewer_target(llm_reviewer, default_target="synthesis"),
                        "reason": "llm_reviewer_issues",
                        "confidence": 0.0,
                    }
                )

            reviewer_defects = _collect_reviewer_defects(
                status=target_status,
                synthesis=synthesis_data,
                public_opinion=public_opinion_trace,
                expert=step_traces.get("expert", {}),
                retrieval_required=retrieval_required,
                retrieval_status=retrieval_status,
                retrieval_used=retrieval_used,
                retrieval_sources=retrieval_sources,
            )

            if reviewer_defects:
                primary = reviewer_defects[0]
                code = str(primary.get("code") or "")
                target = str(primary.get("target") or "")
                if code == "D1":
                    if target_status == "ready":
                        target_status = "limited"
                    review_history.append(
                        {
                            "iteration": len(review_history) + 1,
                            "decision": "rerun_branch",
                            "target": target or "synthesis",
                            "reason": f"{code}:{primary.get('reason')}",
                            "confidence": 0.4,
                        }
                    )
                    review_reruns += 1
                elif code == "D2":
                    if target_status == "ready":
                        target_status = "limited"
                    review_history.append(
                        {
                            "iteration": len(review_history) + 1,
                            "decision": "revise",
                            "target": target or "synthesis",
                            "reason": f"{code}:{primary.get('reason')}",
                            "confidence": 0.45,
                        }
                    )
                elif code in {"D3", "D4"}:
                    target_status = "insufficient_data"
                    review_history.append(
                        {
                            "iteration": len(review_history) + 1,
                            "decision": "insufficient_data",
                            "target": target or None,
                            "reason": f"{code}:{primary.get('reason')}",
                            "confidence": 0.0,
                        }
                    )
                else:
                    target_status = "limited" if target_status == "ready" else target_status
                    review_history.append(
                        {
                            "iteration": len(review_history) + 1,
                            "decision": "accept_with_limitations",
                            "target": target or None,
                            "reason": f"{code}:{primary.get('reason')}",
                            "confidence": 0.5,
                        }
                    )

            if reviewer_defects and target_status == "ready":
                target_status = "limited"
                review_history.append(
                    {
                        "iteration": len(review_history) + 1,
                        "decision": "accept_with_limitations",
                        "target": None,
                        "reason": "blocking_defects_present",
                        "confidence": 0.4,
                    }
                )

            if retrieval_required and retrieval_status in {"failed", "insufficient", "none"}:
                target_status = "limited" if target_status == "ready" else target_status

            if target_status == "ready" and not is_canonical_openrouter_ready_path(step_traces):
                target_status = "limited"
                review_history.append(
                    {
                        "iteration": len(review_history) + 1,
                        "decision": "accept_with_limitations",
                        "target": None,
                        "reason": "non_canonical_execution_path",
                        "confidence": 0.4,
                    }
                )

        if llm_error is not None:
            final_status = "insufficient_data"
            review_history.append(
                {
                    "iteration": len(review_history) + 1,
                    "decision": "insufficient_data",
                    "target": "synthesis",
                    "reason": "synthesis_error",
                    "confidence": 0.0,
                }
            )
            payload = _build_base_payload(
                post_id=post_id,
                published_at_iso=published_at_iso,
                post_text=post_text,
                comments=comments,
                status="insufficient_data",
                summary="Synthesis failed after reviewer loop; returning insufficient_data.",
                confidence_reason="model_output_invalid",
            )
            payload["anomalies"] = ["model_output_invalid"]
            payload["meta"] = {"validation_error": llm_error}
        else:
            had_blocking_review_signal = any(
                str(item.get("decision") or "") in BLOCKING_REVIEW_DECISIONS for item in review_history
            )
            had_any_issues = llm_reviewer_has_issues or bool(reviewer_defects)
            if had_blocking_review_signal and target_status == "ready":
                target_status = "limited"

            if had_any_issues:
                if target_status == "ready":
                    target_status = "limited"
                if had_blocking_review_signal:
                    review_decision = "accept_with_limitations" if target_status == "limited" else "insufficient_data"
                    review_reason = "issues_present"
                else:
                    review_decision = "accept_with_limitations" if target_status == "limited" else "insufficient_data"
                    review_reason = "issues_present"
            else:
                if target_status == "ready":
                    review_decision = "accept"
                elif target_status == "limited":
                    review_decision = "accept_with_limitations"
                else:
                    review_decision = "insufficient_data"
                review_reason = analytical_sufficiency
            if review_decision:
                review_history.append(
                    {
                        "iteration": len(review_history) + 1,
                        "decision": review_decision,
                        "target": None,
                        "reason": review_reason,
                        "confidence": 0.8 if target_status == "ready" else 0.6,
                    }
                )
            aggregated_status = aggregate_sufficiency_status(step_traces)
            if aggregated_status == "insufficient_data":
                target_status = "insufficient_data"
            elif aggregated_status == "limited" and target_status == "ready":
                target_status = "limited"

            final_status = target_status
            if had_any_issues:
                synthesis_data["quality"] = "needs_revision"
            if final_status == "limited":
                synthesis_data["report_text"] = _ensure_limited_summary_markers(str(synthesis_data.get("report_text") or ""))

            confidence_reason = str(synthesis_data.get("confidence_reason") or "deterministic_spec_synthesis")
            if final_status == "limited" and retrieval_required and retrieval_status in {"failed", "insufficient", "none"}:
                confidence_reason = "required_retrieval_unavailable"
            payload = _build_base_payload(
                post_id=post_id,
                published_at_iso=published_at_iso,
                post_text=post_text,
                comments=comments,
                status=target_status,
                summary=str(synthesis_data["report_text"]),
                confidence_reason=confidence_reason,
            )
            if isinstance(llm_output, dict) and isinstance(llm_output.get("topics"), list):
                payload["topics"] = llm_output.get("topics")
            elif public_opinion_trace.get("main_topics"):
                payload["topics"] = [{"name": topic} for topic in list(public_opinion_trace.get("main_topics") or [])]

        last_decision = review_history[-1]["decision"] if review_history else "insufficient_data"

        step_traces["reviewer"].update(
            {
                "decision": last_decision,
                "iterations": len(review_history),
                "rerun_iterations": len([item for item in review_history if str(item.get("decision")) == "rerun_branch"]),
                "history": review_history,
            }
        )

        step_traces["synthesis"].update(
            {
                "report_text": str(synthesis_data.get("report_text") or ""),
                "components": dict(synthesis_data.get("components") or {}),
                "sentence_count": int(synthesis_data.get("sentence_count") or 0),
                "quality": str(synthesis_data.get("quality") or "needs_revision"),
                "confidence_reason": str(synthesis_data.get("confidence_reason") or ""),
            }
        )
        sync_step_provenance(step_traces)

        try:
            multi_agent = {
                "version": "v1",
                "status": final_status,
                "epistemic_claims": _build_epistemic_claims(
                    post_text=post_text,
                    comments=comments,
                    status=final_status,
                    analytical_sufficiency=analytical_sufficiency,
                    retrieval_used=retrieval_used,
                    retrieval_status=retrieval_status,
                ),
                "steps": step_traces,
                "retrieval": {
                    "required": bool(retrieval_trace["required"]),
                    "used": retrieval_used,
                    "status": retrieval_status,
                    "decision_inputs": dict(retrieval_trace.get("decision_inputs") or retrieval_inputs),
                    "decision_source": str(retrieval_trace.get("decision_source") or "policy"),
                    "sources": retrieval_sources,
                },
                "review": {
                    "iterations": len(review_history),
                    "history": review_history,
                },
            }
            validated_meta = validate_multi_agent_meta(multi_agent)
            payload["meta"] = {
                **dict(payload.get("meta") or {}),
                "prompt_version": "post_report_v2",
                "pipeline": "reporting_v2",
                "multi_agent": validated_meta.model_dump(mode="python"),
            }

            validated_payload = PostReportPayload.model_validate(payload)
            return validated_payload.model_dump(mode="python")

        except Exception as final_err:
            logger.exception(
                "Fatal error in final stage of generate_post_report_payload_v2 for post_id=%s",
                post_id,
                exc_info=True
            )
            # Формируем fallback-ответ, чтобы джоб не упал
            fallback_payload = {
                "type": "post_report_v2",
                "status": "failed",
                "post_id": post_id,
                "published_at": published_at_iso,
                "title": f"Post {post_id} discussion snapshot",
                "summary": f"Report generation failed in final stage: {type(final_err).__name__}: {final_err}",
                "comment_count": len(comments),
                "confidence": {"overall": "low", "reason": "internal_error"},
                "meta": {
                    "error": str(final_err),
                    "traceback": traceback.format_exc(),
                    "original_payload_preview": str(payload)[:500] if 'payload' in locals() else None
                },
            }

            return fallback_payload
    except Exception as e:
        logger.exception(
            "FATAL: generate_post_report_payload_v2 crashed for post_id=%s",
            post_id,
            exc_info=True
        )
        # Формируем fallback-ответ, чтобы джоб не упал
        if payload is None:
            payload = {
                "type": "post_report_v2",
                "post_id": post_id,
                "published_at": published_at_iso,
                "title": f"Post {post_id} discussion snapshot",
                "comment_count": len(comments),
            }
        payload["status"] = "failed"
        payload["summary"] = f"Report generation crashed: {type(e).__name__}: {e}"
        payload["confidence"] = {"overall": "low", "reason": "internal_error"}
        payload["meta"] = {
            **payload.get("meta", {}),
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        # Добавляем недостающие поля, чтобы payload был валидным для возврата
        payload.setdefault("topics", [])
        payload.setdefault("clusters", [])
        payload.setdefault("time_trends", [])
        payload.setdefault("risks", [])
        payload.setdefault("anomalies", [])
        payload.setdefault("representative_quotes", [])
        return payload
    


class MockRetrievalProvider:
    async def retrieve(self, request: dict) -> dict:
        text = request.get("post_text") or request.get("root_post_text") or ""
        if not text:
            return {"sources": []}

        return {
            "sources": [
                {
                    "title": "Mock source for retrieval integration test",
                    "source": "mock://retrieval/test",
                    "tier": "2",
                    "supports": "Mock evidence confirms that retrieval evidence can be passed into expert and synthesis.",
                    "relevance": 0.8,
                }
            ]
        }
