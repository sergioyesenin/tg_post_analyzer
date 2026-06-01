from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Comment, Event, EventPost, Post
from schemas.report import EventReportPayload
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
from services.reporting_v2.retrieval import run_retrieval_manager, run_retrieval_provider
from services.reporting_v2.steps import (
    SIX_STEP_SEQUENCE,
    build_step_traces,
    is_canonical_openrouter_ready_path,
    request_step_rerun,
    sync_step_provenance,
)

PIPELINE_SEQUENCE = SIX_STEP_SEQUENCE
REVIEW_MAX_ITERATIONS = 2
BLOCKING_REVIEW_DECISIONS = {"rerun_branch", "revise", "insufficient_data"}
_SENTENCE_RE = re.compile(r"[.!?]+")


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


def _extract_entry_text(value: dict[str, Any]) -> str:
    text = str(value.get("text") or "").strip()
    if text:
        return text

    empty_key_text = str(value.get("") or "").strip()
    if empty_key_text:
        return empty_key_text

    for key, raw_value in value.items():
        key_text = str(key or "").strip()
        raw_text = str(raw_value or "").strip()

        if key_text.startswith("text:") or key_text.startswith("text:**"):
            cleaned = key_text.replace("text:**", "").replace("text:", "").split("|type")[0].strip(" *:")
            if cleaned:
                return cleaned

        if len(raw_text) > 20 and key_text not in {"type", "source", "confidence"}:
            return raw_text

    return ""


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
        confidence = min(0.75, sum(float(item["confidence"]) for item in all_entries) / len(all_entries))

    raw_items_count = sum(len(group) for group in (background_raw, interpretations_raw, consequences_raw) if isinstance(group, list))
    malformed_output = raw_items_count > 0 and len(all_entries) < raw_items_count
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


def _build_deterministic_synthesis(
    *,
    event_title: str,
    root_post_text: str,
    post_count: int,
    comment_count: int,
    status: str,
    retrieval_required: bool,
    retrieval_status: str,
) -> dict[str, Any]:
    title = _safe_text(event_title, max_len=140) or "Unnamed event"
    root_excerpt = _safe_text(root_post_text, max_len=180) or "insufficient source detail"
    limitations = status in {"limited", "insufficient_data"}
    retrieval_limited = retrieval_required and retrieval_status in {"failed", "insufficient", "none"}

    report_text = " ".join(
        [
            f"The event focuses on: {title}.",
            f"Root context summary: {root_excerpt}.",
            f"Signal quality is {status}, using {post_count} linked posts and {comment_count} collected comments.",
            "Public discussion suggests mixed interpretations with no single definitive consensus."
            if limitations
            else "Public discussion supports a coherent interpretation with bounded uncertainty.",
            "External retrieval required by policy was unavailable, so external context remains unverified."
            if retrieval_limited
            else "No blocking external retrieval gap was detected for this synthesis.",
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
        "confidence_reason": "deterministic_event_synthesis",
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


def _normalize_cross_post_topics(values: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        name = ""
        share: float | None = None
        if isinstance(value, str):
            name = value.strip()
        elif isinstance(value, dict):
            name = str(value.get("name") or value.get("text") or value.get("topic") or "").strip()
            raw_share = value.get("share")
            if raw_share is not None:
                try:
                    parsed = float(raw_share)
                    if 0.0 <= parsed <= 1.0:
                        share = parsed
                except (TypeError, ValueError):
                    share = None
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {"name": name}
        if share is not None:
            item["share"] = share
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized


def _collect_reviewer_defects(
    *,
    status: str,
    synthesis: dict[str, Any],
    expert: dict[str, Any],
    comment_sufficiency: str,
    retrieval_required: bool,
    retrieval_status: str,
    retrieval_used: bool,
    retrieval_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    components = dict(synthesis.get("components") or {})
    missing = [name for name in ("event", "context", "reaction", "interpretation", "consequences") if components.get(name) is not True]
    sentence_count = int(synthesis.get("sentence_count") or 0)
    report_text = _safe_text(str(synthesis.get("report_text") or ""), max_len=1800).lower()
    if missing or sentence_count < 5 or sentence_count > 7:
        defects.append({"code": "D1", "reason": f"structural_missing:{','.join(missing) or 'sentence_count'}", "target": "synthesis"})
    if str(synthesis.get("quality") or "") != "ok":
        defects.append({"code": "D2", "reason": "weak_analysis", "target": "synthesis"})
    if retrieval_required and retrieval_status in {"failed", "insufficient", "none"} and status == "ready":
        defects.append({"code": "D3", "reason": "ready_forbidden_without_required_retrieval", "target": "routing"})
    if status == "ready" and comment_sufficiency in {"weak_signal", "insufficient"}:
        defects.append({"code": "D6", "reason": "status_vs_signal_inconsistency", "target": "public_opinion"})
    if status == "insufficient_data" and ("indicates" in report_text or "supports" in report_text):
        defects.append({"code": "D4", "reason": "insufficient_data_overclaim", "target": "synthesis"})
    if retrieval_used and not retrieval_sources:
        defects.append({"code": "D5", "reason": "missing_retrieval_evidence", "target": "routing"})
    expert_entries: list[dict[str, Any]] = []
    for key in ("background", "interpretations", "consequences"):
        value = expert.get(key)
        if isinstance(value, list):
            expert_entries.extend([item for item in value if isinstance(item, dict)])
    retrieval_success = retrieval_used and retrieval_status == "success" and bool(retrieval_sources)
    for item in expert_entries:
        if str(item.get("type") or "") == "external" and not retrieval_success:
            defects.append({"code": "D3", "reason": "external_expert_claim_without_retrieval", "target": "expert"})
            break
        if str(item.get("source") or "") == "retrieval" and not retrieval_success:
            defects.append({"code": "D3", "reason": "retrieval_sourced_claim_without_evidence", "target": "expert"})
            break
    if bool(expert.get("malformed_output")) or bool(expert.get("contract_invalid")):
        defects.append({"code": "D5", "reason": "expert_contract_invalid_or_malformed", "target": "expert"})
    expert_confidence = float(expert.get("confidence") or 0.0)
    expert_status = str(expert.get("status") or "completed")
    if expert_confidence <= 0.0 and expert_status == "completed":
        defects.append({"code": "D3", "reason": "expert_zero_confidence_completed", "target": "expert"})
    return defects


def _build_retrieval_decision_inputs(*, event_title: str, root_post_text: str) -> dict[str, bool]:
    merged = f"{_safe_text(event_title, max_len=300)} {_safe_text(root_post_text, max_len=2200)}".lower()
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
    external_context_missing = len(_safe_text(root_post_text, max_len=2200)) < 260 or any(
        token in merged
        for token in ("без подроб", "details", "контекст не указан", "как сообщалось ранее")
    )
    return {
        "institutional_context": institutional_context,
        "international_context": international_context,
        "external_context_missing": external_context_missing,
        "high_error_cost": high_error_cost,
    }


def _build_epistemic_claims(
    *,
    event_title: str,
    root_post_text: str,
    comments: list[str],
    status: str,
    analytical_sufficiency: str,
    retrieval_used: bool,
    retrieval_status: str,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    normalized_title = _safe_text(event_title, max_len=140)
    if normalized_title:
        claims.append(
            {
                "text": f"Event focus: {normalized_title}",
                "type": "fact",
                "confidence": 0.7 if status == "ready" else 0.55,
                "source": "article",
            }
        )
    normalized_root = _safe_text(root_post_text, max_len=220)
    if normalized_root:
        claims.append(
            {
                "text": normalized_root,
                "type": "derived",
                "confidence": 0.65 if status == "ready" else 0.5,
                "source": "article",
            }
        )
    if comments:
        claims.append(
            {
                "text": f"Public reaction synthesized from {len(comments)} comments.",
                "type": "derived",
                "confidence": 0.6 if status == "ready" else 0.5,
                "source": "comments",
            }
        )
    if analytical_sufficiency in {"limited", "insufficient"}:
        claims.append(
            {
                "text": "Event-level interpretation is constrained by sufficiency limits.",
                "type": "interpretation",
                "confidence": 0.5,
                "source": "article",
            }
        )
    if status in {"limited", "insufficient_data"}:
        claims.append(
            {
                "text": "Some event conclusions remain uncertain.",
                "type": "uncertain",
                "confidence": 0.4 if status == "limited" else 0.3,
                "source": "comments" if comments else "article",
            }
        )
    if retrieval_used and retrieval_status == "success":
        claims.append(
            {
                "text": "External event context was incorporated from retrieval evidence.",
                "type": "external",
                "confidence": 0.6,
                "source": "retrieval",
            }
        )
    return claims


async def load_event_input_bundle(session: AsyncSession, *, event_id: int) -> dict[str, Any] | None:
    event = await session.get(Event, event_id)
    if event is None:
        return None

    post_rows = (
        await session.execute(
            select(
                EventPost.post_id,
                EventPost.role,
                Post.date,
                Post.text,
                Post.comments_count,
            )
            .join(Post, Post.id == EventPost.post_id)
            .where(EventPost.event_id == event_id)
            .order_by(EventPost.created_at.asc(), EventPost.post_id.asc())
        )
    ).all()

    posts: list[dict[str, Any]] = []
    post_ids: list[int] = []
    root_post_id: int | None = None
    root_text = ""
    for post_id, role, date, text, comments_count in post_rows:
        post_int = int(post_id)
        post_ids.append(post_int)
        role_value = str(role or "")
        posts.append(
            {
                "post_id": post_int,
                "event_role": role_value,
                "published_at": date.isoformat() if date is not None else None,
                "text": text or "",
                "comments_count": int(comments_count or 0),
            }
        )
        if root_post_id is None and role_value == "root":
            root_post_id = post_int
            root_text = text or ""

    if root_post_id is None and posts:
        root_post_id = int(posts[0]["post_id"])
        root_text = str(posts[0].get("text") or "")

    comments_by_post: dict[int, list[str]] = {post_id: [] for post_id in post_ids}
    if post_ids:
        comment_rows = (
            await session.execute(
                select(Comment.post_id, Comment.text)
                .where(Comment.post_id.in_(post_ids))
                .order_by(Comment.date.asc(), Comment.id.asc())
            )
        ).all()
        for post_id, text in comment_rows:
            normalized = _safe_text(text, max_len=500)
            if not normalized:
                continue
            comments_by_post.setdefault(int(post_id), []).append(normalized)

    all_comments: list[str] = []
    for post_id in post_ids:
        all_comments.extend(comments_by_post.get(post_id, []))

    return {
        "event_id": int(event.id),
        "event_title": event.title or f"Event {event.id}",
        "posts": posts,
        "post_ids": post_ids,
        "root_post_id": root_post_id,
        "root_post_text": root_text,
        "comments_all_posts": all_comments,
        "comments_by_post": comments_by_post,
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


async def build_event_report_v2_impl(
    *,
    session: AsyncSession,
    event_id: int,
    prompt_loader: PromptLoader | None = None,
    llm_adapter: OpenAIClientAdapter | None = None,
    retrieval_provider: Any | None = None,
) -> dict[str, Any]:
    bundle = await load_event_input_bundle(session, event_id=event_id)
    if bundle is None:
        return {"status": "not_found", "event_id": event_id}

    loader = prompt_loader or PromptLoader()
    prompts = loader.load_bundle("event")

    posts = list(bundle.get("posts") or [])
    post_ids = [int(item["post_id"]) for item in posts if isinstance(item, dict) and "post_id" in item]
    comments = list(bundle.get("comments_all_posts") or [])
    root_post_text = str(bundle.get("root_post_text") or "")
    if len(posts) <= 0:
        article_sufficiency = "insufficient"
    else:
        article_sufficiency = assess_article_sufficiency(text=root_post_text)
    comment_sufficiency = assess_comment_sufficiency(comments=comments)
    retrieval_inputs = _build_retrieval_decision_inputs(
        event_title=str(bundle.get("event_title") or ""),
        root_post_text=root_post_text,
    )
    retrieval_required = True
    retrieval_request = {
        "kind": "event",
        "event_id": event_id,
        "event_title": str(bundle.get("event_title") or ""),
        "root_post_text": _safe_text(root_post_text, max_len=2400),
        "comments": [_safe_text(item, max_len=300) for item in comments[:60]],
        "decision_inputs": retrieval_inputs,
    }
    retrieval_pack = (
        await run_retrieval_manager(
            retrieval_provider,
            {
                **retrieval_request,
                "category": "news",
            },
        )
        if retrieval_required
        else {
            "status": "none",
            "quality_score": 0.0,
            "sources": [],
            "facts": [],
            "conflicts": [],
            "gaps": [],
            "diagnostics": {},
            "raw_results": [],
        }
    )
    retrieval_provider_sources = list(retrieval_pack.get("sources") or [])
    retrieval_trace = build_retrieval_trace(
        required=retrieval_required,
        provider_enabled=retrieval_provider is not None,
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
    step_traces: dict[str, dict[str, Any]] = build_step_traces(PIPELINE_SEQUENCE)
    step_traces["context"].update(
        {
            "root_post_id": bundle.get("root_post_id"),
            "source_post_ids": post_ids,
            "comments_total": len(comments),
            "sufficiency_components": {
                "article": article_sufficiency,
                "comment": comment_sufficiency,
                "retrieval": retrieval_sufficiency,
                "analytical": analytical_sufficiency,
            },
            "retrieval_hints": retrieval_inputs,
            "retrieval_required": retrieval_required,
        }
    )

    synthesis_data = _build_deterministic_synthesis(
        event_title=str(bundle.get("event_title") or ""),
        root_post_text=root_post_text,
        post_count=len(post_ids),
        comment_count=len(comments),
        status=target_status,
        retrieval_required=retrieval_required,
        retrieval_status=retrieval_status,
    )
    summary = str(synthesis_data["report_text"])
    confidence_reason = str(synthesis_data["confidence_reason"])
    llm_error: str | None = None
    llm_output: dict[str, Any] | None = None
    reviewer_output: dict[str, Any] | None = None

    if llm_adapter is None:
        cfg = OpenAIAdapterConfig.from_settings()
        if cfg.api_key:
            llm_adapter = OpenAIClientAdapter(cfg)

    if llm_adapter is not None:
        try:
            context_output, context_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="context",
                prompt_text=prompts["context"],
                request_payload={
                    "event_title": str(bundle.get("event_title") or ""),
                    "root_post_text": _safe_text(root_post_text, max_len=1800),
                    "comments": [_safe_text(item, max_len=280) for item in comments[:60]],
                    "status_hint": target_status,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="context", trace=context_trace)
            if isinstance(context_output, dict):
                step_traces["context"]["llm_context"] = context_output
        except Exception as exc:
            _apply_step_provider_trace(
                step_traces=step_traces,
                step_name="context",
                trace=_provider_error_trace(adapter=llm_adapter, reason=f"context_error:{type(exc).__name__}"),
            )

        try:
            routing_output, routing_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="routing",
                prompt_text=prompts["routing"],
                request_payload={
                    "event_title": str(bundle.get("event_title") or ""),
                    "root_post_text": _safe_text(root_post_text, max_len=1800),
                    "status_hint": target_status,
                    "retrieval_hints": retrieval_inputs,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="routing", trace=routing_trace)
            if isinstance(routing_output, dict):
                step_traces["routing"]["llm_routing"] = routing_output
        except Exception as exc:
            _apply_step_provider_trace(
                step_traces=step_traces,
                step_name="routing",
                trace=_provider_error_trace(adapter=llm_adapter, reason=f"routing_error:{type(exc).__name__}"),
            )

        try:
            expert_output, expert_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="expert",
                prompt_text=prompts["expert"],
                request_payload={
                    "event_title": str(bundle.get("event_title") or ""),
                    "root_post_text": _safe_text(root_post_text, max_len=1800),
                    "comments": [_safe_text(item, max_len=260) for item in comments[:40]],
                    "status_hint": target_status,
                    "analytical_sufficiency": analytical_sufficiency,
                    "retrieval": retrieval_trace,
                    "retrieval_instruction": "Use retrieval evidence only when retrieval.used is true; otherwise do not add external facts.",
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="expert", trace=expert_trace)
            if isinstance(expert_output, dict):
                normalized_expert = _normalize_expert_output(
                    candidate=expert_output,
                    retrieval_success=retrieval_used and retrieval_status == "success",
                    data_sufficient=analytical_sufficiency == "sufficient",
                )
                step_traces["expert"]["llm_expert_raw"] = expert_output
                step_traces["expert"]["llm_expert"] = normalized_expert
                step_traces["expert"].update(normalized_expert)
                if bool(normalized_expert.get("contract_invalid")):
                    step_traces["expert"]["status"] = "failed"
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
                    "event_title": str(bundle.get("event_title") or ""),
                    "comments": [_safe_text(item, max_len=260) for item in comments[:80]],
                    "status_hint": target_status,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="public_opinion", trace=public_trace)
            if isinstance(public_output, dict):
                step_traces["public_opinion"]["llm_public_opinion"] = public_output
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
                    "event_title": str(bundle.get("event_title") or ""),
                    "root_post_text": _safe_text(root_post_text, max_len=1800),
                    "comments": [_safe_text(item, max_len=300) for item in comments[:60]],
                    "retrieval": retrieval_trace,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="synthesis", trace=synthesis_trace)
            if isinstance(llm_output, dict):
                synthesis_data = _normalize_synthesis_output(candidate=llm_output, fallback=synthesis_data)
                summary = str(synthesis_data["report_text"])
                confidence_reason = str(synthesis_data["confidence_reason"])
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            _apply_step_provider_trace(
                step_traces=step_traces,
                step_name="synthesis",
                trace=_provider_error_trace(adapter=llm_adapter, reason="synthesis_error"),
            )

        try:
            reviewer_output, reviewer_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="reviewer",
                prompt_text=prompts["reviewer"],
                request_payload={
                    "status_hint": target_status,
                    "summary": summary,
                    "retrieval_required": retrieval_required,
                    "retrieval_status": retrieval_status,
                    "retrieval": retrieval_trace,
                    "expert": step_traces.get("expert", {}),
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="reviewer", trace=reviewer_trace)
            if isinstance(reviewer_output, dict):
                step_traces["reviewer"]["llm_reviewer"] = reviewer_output
        except Exception as exc:
            _apply_step_provider_trace(
                step_traces=step_traces,
                step_name="reviewer",
                trace=_provider_error_trace(adapter=llm_adapter, reason=f"reviewer_error:{type(exc).__name__}"),
            )

    llm_reviewer = reviewer_output if isinstance(reviewer_output, dict) else None
    effective_llm_decision = resolve_effective_review_decision("accept", llm_reviewer) if llm_error is None else ""
    llm_rerun_target = _infer_reviewer_target(llm_reviewer, default_target="synthesis")

    async def _execute_rerun_cycle(branch: str) -> None:
        nonlocal llm_error, llm_output, reviewer_output, synthesis_data, summary, confidence_reason
        if llm_adapter is None:
            return
        try:
            if branch == "context":
                context_output, context_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="context",
                    prompt_text=prompts["context"],
                    request_payload={
                        "event_title": str(bundle.get("event_title") or ""),
                        "root_post_text": _safe_text(root_post_text, max_len=1800),
                        "comments": [_safe_text(item, max_len=280) for item in comments[:60]],
                        "status_hint": target_status,
                    },
                )
                _apply_step_provider_trace(step_traces=step_traces, step_name="context", trace=context_trace)
                if isinstance(context_output, dict):
                    step_traces["context"]["llm_context"] = context_output
            elif branch == "routing":
                routing_output, routing_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="routing",
                    prompt_text=prompts["routing"],
                    request_payload={
                        "event_title": str(bundle.get("event_title") or ""),
                        "root_post_text": _safe_text(root_post_text, max_len=1800),
                        "status_hint": target_status,
                        "retrieval_hints": retrieval_inputs,
                    },
                )
                _apply_step_provider_trace(step_traces=step_traces, step_name="routing", trace=routing_trace)
                if isinstance(routing_output, dict):
                    step_traces["routing"]["llm_routing"] = routing_output
            elif branch == "expert":
                expert_output, expert_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="expert",
                    prompt_text=prompts["expert"],
                    request_payload={
                        "event_title": str(bundle.get("event_title") or ""),
                        "root_post_text": _safe_text(root_post_text, max_len=1800),
                        "comments": [_safe_text(item, max_len=260) for item in comments[:40]],
                        "status_hint": target_status,
                        "analytical_sufficiency": analytical_sufficiency,
                        "retrieval": retrieval_trace,
                        "retrieval_instruction": "Use retrieval evidence only when retrieval.used is true; otherwise do not add external facts.",
                    },
                )
                _apply_step_provider_trace(step_traces=step_traces, step_name="expert", trace=expert_trace)
                if isinstance(expert_output, dict):
                    normalized_expert = _normalize_expert_output(
                        candidate=expert_output,
                        retrieval_success=retrieval_used and retrieval_status == "success",
                        data_sufficient=analytical_sufficiency == "sufficient",
                    )
                    step_traces["expert"]["llm_expert_raw"] = expert_output
                    step_traces["expert"]["llm_expert"] = normalized_expert
                    step_traces["expert"].update(normalized_expert)
                    if bool(normalized_expert.get("contract_invalid")):
                        step_traces["expert"]["status"] = "failed"
            elif branch == "public_opinion":
                public_output, public_trace = await _try_llm_json_step(
                    adapter=llm_adapter,
                    step_name="public_opinion",
                    prompt_text=prompts["public_opinion"],
                    request_payload={
                        "event_title": str(bundle.get("event_title") or ""),
                        "comments": [_safe_text(item, max_len=260) for item in comments[:80]],
                        "status_hint": target_status,
                    },
                )
                _apply_step_provider_trace(step_traces=step_traces, step_name="public_opinion", trace=public_trace)
                if isinstance(public_output, dict):
                    step_traces["public_opinion"]["llm_public_opinion"] = public_output

            llm_output, synthesis_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="synthesis",
                prompt_text=prompts["synthesis"],
                request_payload={
                    "status_hint": target_status,
                    "event_title": str(bundle.get("event_title") or ""),
                    "root_post_text": _safe_text(root_post_text, max_len=1800),
                    "comments": [_safe_text(item, max_len=300) for item in comments[:60]],
                    "retrieval": retrieval_trace,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="synthesis", trace=synthesis_trace)
            if isinstance(llm_output, dict):
                synthesis_data = _normalize_synthesis_output(candidate=llm_output, fallback=synthesis_data)
                summary = str(synthesis_data["report_text"])
                confidence_reason = str(synthesis_data["confidence_reason"])
            llm_error = None

            reviewer_output, reviewer_trace = await _try_llm_json_step(
                adapter=llm_adapter,
                step_name="reviewer",
                prompt_text=prompts["reviewer"],
                request_payload={
                    "status_hint": target_status,
                    "summary": summary,
                    "retrieval_required": retrieval_required,
                    "retrieval_status": retrieval_status,
                    "retrieval": retrieval_trace,
                    "expert": step_traces.get("expert", {}),
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="reviewer", trace=reviewer_trace)
            if isinstance(reviewer_output, dict):
                step_traces["reviewer"]["llm_reviewer"] = reviewer_output
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"

    review_history: list[dict[str, Any]] = []
    review_reruns = 0
    pending_rerun = "synthesis" if llm_error is not None else None
    pending_reason = "synthesis_error" if pending_rerun else ""
    if pending_rerun is None and effective_llm_decision == "rerun_branch":
        pending_rerun = llm_rerun_target
        pending_reason = "llm_reviewer_requested_rerun"

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
        llm_reviewer = reviewer_output if isinstance(reviewer_output, dict) else None
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
            expert=step_traces.get("expert", {}),
            comment_sufficiency=comment_sufficiency,
            retrieval_required=retrieval_required,
            retrieval_status=retrieval_status,
            retrieval_used=retrieval_used,
            retrieval_sources=retrieval_sources,
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
        target_status = "insufficient_data"
        review_history.append(
            {
                "iteration": len(review_history) + 1,
                "decision": "insufficient_data",
                "target": "synthesis",
                "reason": "synthesis_error",
                "confidence": 0.0,
            }
        )
        summary = "Event synthesis failed after reviewer loop; returning insufficient_data."
        confidence_reason = "model_output_invalid"
        synthesis_data = _normalize_synthesis_output(
            candidate={
                "report_text": summary,
                "quality": "needs_revision",
                "components": {
                    "event": True,
                    "context": False,
                    "reaction": False,
                    "interpretation": False,
                    "consequences": False,
                },
                "confidence_reason": confidence_reason,
            },
            fallback=synthesis_data,
        )
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
        if had_any_issues:
            synthesis_data["quality"] = "needs_revision"

    payload: dict[str, Any] = {
        "type": "event_report_v2",
        "status": target_status,
        "event_id": int(bundle["event_id"]),
        "event_title": str(bundle["event_title"]),
        "posts_count": len(post_ids),
        "source_post_reports": post_ids,
        "sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "low" if target_status != "ready" else "medium",
        },
        "cross_post_topics": _normalize_cross_post_topics(llm_output.get("topics") if isinstance(llm_output, dict) else []),
        "post_dynamics": [],
        "event_trends": [],
        "risks": [],
        "anomalies": ["model_output_invalid"] if llm_error is not None else [],
        "summary": str(synthesis_data["report_text"]),
        "confidence": {
            "overall": "low" if target_status in {"insufficient_data", "failed"} else ("medium" if target_status == "limited" else "high"),
            "reason": str(synthesis_data["confidence_reason"]),
        },
        "reactions_coverage": {
            "source": "event_posts_comments",
            "collected_at": None,
            "is_complete": False,
            "factor": 0.0,
            "comment_status": None,
            "comments_scanned": len(comments),
            "comments_with_visible_reactions": 0,
            "expected_comments": len(comments),
        },
        "audience_stance": {
            "label": "unclear",
            "confidence": "low",
            "reason": "Derived from aggregate event comments only.",
        },
    }

    step_traces["synthesis"].update(
        {
            "report_text": str(synthesis_data.get("report_text") or ""),
            "components": dict(synthesis_data.get("components") or {}),
            "sentence_count": int(synthesis_data.get("sentence_count") or 0),
            "quality": str(synthesis_data.get("quality") or "needs_revision"),
            "confidence_reason": str(synthesis_data.get("confidence_reason") or ""),
        }
    )

    step_traces["reviewer"].update(
        {
            "decision": review_history[-1]["decision"] if review_history else "insufficient_data",
            "iterations": len(review_history),
            "rerun_iterations": len([item for item in review_history if str(item.get("decision")) == "rerun_branch"]),
            "history": review_history,
        }
    )
    sync_step_provenance(step_traces)

    multi_agent = {
        "version": "v1",
        "status": target_status if target_status in {"ready", "limited", "insufficient_data", "failed"} else "failed",
        "epistemic_claims": _build_epistemic_claims(
            event_title=str(bundle.get("event_title") or ""),
            root_post_text=root_post_text,
            comments=comments,
            status=target_status,
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
        "prompt_version": "event_report_v2",
        "source_type": "event_posts_comments",
        "pipeline": "reporting_v2",
        "multi_agent": validated_meta.model_dump(mode="python"),
    }
    if llm_error is not None:
        payload["meta"]["validation_error"] = llm_error

    validated = EventReportPayload.model_validate(payload)
    return validated.model_dump(mode="python")
