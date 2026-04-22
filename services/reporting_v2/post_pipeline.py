from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from schemas.report import PostReportPayload
from services.llm.openai_client import OpenAIAdapterConfig, OpenAIChatCompletionTrace, OpenAIClientAdapter
from services.prompts.loader import PromptLoader
from services.reporting_v2.contracts_internal import (
    aggregate_public_status,
    assess_analytical_sufficiency,
    assess_article_sufficiency,
    assess_comment_sufficiency,
    assess_retrieval_sufficiency,
    build_retrieval_trace_without_provider,
    decide_retrieval_required,
    validate_multi_agent_meta,
)
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
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_]+", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"[.!?]+")


def _safe_text(value: str | None, *, max_len: int = 300) -> str:
    return " ".join((value or "").split())[:max_len]


def _sentence_count(text: str) -> int:
    return len([part for part in _SENTENCE_RE.split(text) if part.strip()])


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
    if comments_count == 0:
        discussion_state = "no_discussion"
    elif conflict_hits >= 3:
        discussion_state = "polarized"
    elif comments_count < 6:
        discussion_state = "emerging"
    else:
        discussion_state = "active"
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
        "Required external retrieval was unavailable, so external context remains unverified."
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
    if status == "insufficient_data" and ("indicates" in report_text or "supports" in report_text):
        defects.append({"code": "D4", "reason": "insufficient_data_overclaim", "target": "synthesis"})
    if retrieval_used and not retrieval_sources:
        defects.append({"code": "D5", "reason": "missing_retrieval_evidence", "target": "routing"})
    if status == "ready" and str(public_opinion.get("data_status") or "") in {"weak_signal", "insufficient"}:
        defects.append({"code": "D6", "reason": "status_vs_signal_inconsistency", "target": "public_opinion"})
    return defects
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
    if not content:
        return None, trace
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
        )
    return data, trace


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
) -> dict[str, Any]:
    del channel, thread_comments, views, job_timeout_seconds

    loader = prompt_loader or PromptLoader()
    prompts = loader.load_bundle("post")

    step_traces: dict[str, dict[str, Any]] = build_step_traces(PIPELINE_STEP_KEYS)
    article_sufficiency = assess_article_sufficiency(text=post_text)
    comment_sufficiency = assess_comment_sufficiency(comments=comments)
    retrieval_inputs = _build_retrieval_decision_inputs(post_text=post_text, comments=comments)
    retrieval_required = decide_retrieval_required(**retrieval_inputs)
    provider_enabled = bool((effective_features or {}).get("retrieval_provider_enabled", False))
    retrieval_trace = build_retrieval_trace_without_provider(
        required=retrieval_required,
        provider_enabled=provider_enabled,
        decision_inputs=retrieval_inputs,
        decision_source="policy",
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
    apply_step_trace_envelope(
        step_traces,
        step_name="context",
        mutator=lambda trace: trace.update(
            {
                "sufficiency_components": {
                    "article": article_sufficiency,
                    "comment": comment_sufficiency,
                    "retrieval": retrieval_sufficiency,
                    "analytical": analytical_sufficiency,
                },
                "retrieval_hints": retrieval_inputs,
                "retrieval_required": retrieval_required,
            }
        ),
    )
    apply_step_trace_envelope(
        step_traces,
        step_name="routing",
        mutator=lambda trace: trace.update(
            {
                "retrieval_hints": retrieval_inputs,
                "reasoning": "deterministic_policy",
            }
        ),
    )

    public_opinion_trace = _build_public_opinion_trace(
        post_text=post_text,
        comments=comments,
        comment_sufficiency=comment_sufficiency,
        analytical_sufficiency=analytical_sufficiency,
    )
    apply_step_trace_envelope(
        step_traces,
        step_name="public_opinion",
        mutator=lambda trace: trace.update(public_opinion_trace),
    )

    requested_rerun = (rerun_stage or "").strip() or None

    target_status = aggregate_public_status(
        article=article_sufficiency,
        comment=comment_sufficiency,
        retrieval=retrieval_sufficiency,
        analytical=analytical_sufficiency,
    )

    synthesis_data = _build_deterministic_synthesis(
        post_text=post_text,
        comment_count=len([item for item in comments if _safe_text(item)]),
        status=target_status,
        public_opinion=public_opinion_trace,
        retrieval_required=retrieval_required,
        retrieval_status=retrieval_status,
    )

    if llm_adapter is None:
        cfg = OpenAIAdapterConfig.from_settings()
        if cfg.api_key:
            llm_adapter = OpenAIClientAdapter(cfg)

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
                    "status_hint": target_status,
                },
            )
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

        try:
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
            _apply_step_provider_trace(step_traces=step_traces, step_name="routing", trace=routing_trace)
            if isinstance(routing_output, dict):
                apply_step_trace_envelope(
                    step_traces,
                    step_name="routing",
                    mutator=lambda trace: trace.update({"llm_routing": routing_output}),
                )
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
                    "post_text": _safe_text(post_text, max_len=1600),
                    "comments": [_safe_text(item, max_len=260) for item in comments[:20]],
                    "status_hint": target_status,
                    "analytical_sufficiency": analytical_sufficiency,
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="expert", trace=expert_trace)
            if isinstance(expert_output, dict):
                apply_step_trace_envelope(
                    step_traces,
                    step_name="expert",
                    mutator=lambda trace: trace.update({"llm_expert": expert_output}),
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
                },
            )
            _apply_step_provider_trace(step_traces=step_traces, step_name="synthesis", trace=synthesis_trace)
            if isinstance(llm_output, dict):
                synthesis_data = _normalize_synthesis_output(candidate=llm_output, fallback=synthesis_data)
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
                    "synthesis": synthesis_data,
                    "retrieval_required": retrieval_required,
                    "retrieval_status": retrieval_status,
                },
            )
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

    review_history: list[dict[str, Any]] = []
    review_reruns = 0
    pending_rerun = requested_rerun if requested_rerun in {"context", "routing", "expert", "public_opinion", "synthesis"} else None
    pending_reason = "manual_rerun_request" if pending_rerun else ""
    if llm_error is not None and pending_rerun is None:
        pending_rerun = "synthesis"
        pending_reason = "synthesis_error"

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
        if llm_error is not None and review_reruns < REVIEW_MAX_ITERATIONS:
            pending_rerun = "synthesis"
            pending_reason = "synthesis_error"
        else:
            pending_rerun = None
            pending_reason = ""

    if llm_error is None:
        reviewer_defects = _collect_reviewer_defects(
            status=target_status,
            synthesis=synthesis_data,
            public_opinion=public_opinion_trace,
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
        if target_status == "ready":
            review_decision = "accept"
        elif target_status == "limited":
            review_decision = "accept_with_limitations"
        else:
            review_decision = "insufficient_data"
        review_history.append(
            {
                "iteration": len(review_history) + 1,
                "decision": review_decision,
                "target": None,
                "reason": analytical_sufficiency,
                "confidence": 0.8 if target_status == "ready" else 0.6,
            }
        )
        final_status = target_status
        if final_status == "insufficient_data":
            synthesis_data["report_text"] = (
                "The event cannot be assessed reliably because available evidence is insufficient. "
                "Context remains incomplete and public reaction signals are too weak for a stable interpretation. "
                "Any inferred interpretation would likely overstate certainty. "
                "Consequences therefore remain conditional and should not drive definitive action. "
                "Additional source material and higher-quality discussion evidence are required."
            )
            synthesis_data["sentence_count"] = _sentence_count(synthesis_data["report_text"])
            synthesis_data["quality"] = "ok"
        elif final_status == "limited" and "limited" not in synthesis_data["report_text"].lower():
            synthesis_data["report_text"] = (
                f"{synthesis_data['report_text']} Evidence remains limited, so conclusions are explicitly bounded."
            )
            synthesis_data["sentence_count"] = _sentence_count(synthesis_data["report_text"])

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

    step_traces["reviewer"].update(
        {
            "decision": review_history[-1]["decision"] if review_history else "insufficient_data",
            "iterations": len([item for item in review_history if str(item.get("decision")) == "rerun_branch"]),
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
            "iterations": len([item for item in review_history if str(item.get("decision")) == "rerun_branch"]),
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
