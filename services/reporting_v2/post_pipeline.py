from __future__ import annotations

import json
from typing import Any

from schemas.report import PostReportPayload
from services.llm.openai_client import OpenAIAdapterConfig, OpenAIClientAdapter
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

PIPELINE_SEQUENCE = ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer")
PIPELINE_STEP_KEYS = ("context", "routing", "expert", "public_opinion", "synthesis")
REVIEW_MAX_ITERATIONS = 2


def _safe_text(value: str | None, *, max_len: int = 300) -> str:
    return " ".join((value or "").split())[:max_len]


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


async def _try_llm_synthesis(
    *,
    adapter: OpenAIClientAdapter,
    prompts: dict[str, str],
    post_text: str,
    comments: list[str],
    status_hint: str,
) -> dict[str, Any] | None:
    request_payload = {
        "status_hint": status_hint,
        "post_text": _safe_text(post_text, max_len=1600),
        "comments": [_safe_text(item, max_len=300) for item in comments[:30]],
    }
    content = await adapter.create_chat_completion(
        messages=[
            {"role": "system", "content": prompts["synthesis"]},
            {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    if not content:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


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
    prompt_loader: PromptLoader | None = None,
    llm_adapter: OpenAIClientAdapter | None = None,
) -> dict[str, Any]:
    del channel, thread_comments, views, job_timeout_seconds

    loader = prompt_loader or PromptLoader()
    prompts = loader.load_bundle("post")

    step_traces: dict[str, dict[str, Any]] = {
        step: {"status": "completed", "run_count": 1}
        for step in PIPELINE_STEP_KEYS
    }
    article_sufficiency = assess_article_sufficiency(text=post_text)
    comment_sufficiency = assess_comment_sufficiency(comments=comments)
    retrieval_inputs = _build_retrieval_decision_inputs(post_text=post_text, comments=comments)
    retrieval_required = decide_retrieval_required(**retrieval_inputs)
    retrieval_trace = build_retrieval_trace_without_provider(
        required=retrieval_required,
        provider_enabled=False,
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
    step_traces["context"]["sufficiency_components"] = {
        "article": article_sufficiency,
        "comment": comment_sufficiency,
        "retrieval": retrieval_sufficiency,
        "analytical": analytical_sufficiency,
    }
    step_traces["context"]["retrieval_hints"] = retrieval_inputs
    step_traces["context"]["retrieval_required"] = retrieval_required

    requested_rerun = (rerun_stage or "").strip() or None

    target_status = aggregate_public_status(
        article=article_sufficiency,
        comment=comment_sufficiency,
        retrieval=retrieval_sufficiency,
        analytical=analytical_sufficiency,
    )

    summary = "Generated by reporting_v2 pipeline."
    confidence_reason = "Deterministic fallback synthesis"

    if llm_adapter is None:
        cfg = OpenAIAdapterConfig.from_settings()
        if cfg.api_key:
            llm_adapter = OpenAIClientAdapter(cfg)

    llm_error: str | None = None
    llm_output: dict[str, Any] | None = None
    if llm_adapter is not None and target_status != "insufficient_data":
        try:
            llm_output = await _try_llm_synthesis(
                adapter=llm_adapter,
                prompts=prompts,
                post_text=post_text,
                comments=comments,
                status_hint=target_status,
            )
            if isinstance(llm_output, dict):
                summary = _safe_text(str(llm_output.get("summary") or summary), max_len=1200) or summary
                confidence_reason = _safe_text(str(llm_output.get("confidence_reason") or "LLM synthesis"), max_len=500)
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            step_traces["synthesis"]["status"] = "failed"

    review_history: list[dict[str, Any]] = []
    review_reruns = 0
    pending_rerun = requested_rerun if requested_rerun in {"context", "routing", "expert", "public_opinion", "synthesis"} else None
    pending_reason = "manual_rerun_request" if pending_rerun else ""
    if llm_error is not None and pending_rerun is None:
        pending_rerun = "synthesis"
        pending_reason = "synthesis_error"

    while pending_rerun is not None and review_reruns < REVIEW_MAX_ITERATIONS:
        step_traces[pending_rerun]["run_count"] = int(step_traces[pending_rerun].get("run_count") or 1) + 1
        step_traces[pending_rerun]["rerun_requested"] = True
        if pending_rerun != "synthesis":
            step_traces["synthesis"]["run_count"] = int(step_traces["synthesis"].get("run_count") or 1) + 1
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
        payload = _build_base_payload(
            post_id=post_id,
            published_at_iso=published_at_iso,
            post_text=post_text,
            comments=comments,
            status=target_status,
            summary=summary,
            confidence_reason=confidence_reason,
        )
        if isinstance(llm_output, dict) and isinstance(llm_output.get("topics"), list):
            payload["topics"] = llm_output.get("topics")

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
            "sources": retrieval_sources,
        },
        "review": {
            "iterations": review_reruns,
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
