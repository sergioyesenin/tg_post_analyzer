from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Comment, Event, EventPost, Post
from schemas.report import EventReportPayload
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
REVIEW_MAX_ITERATIONS = 2


def _safe_text(value: str | None, *, max_len: int = 300) -> str:
    return " ".join((value or "").split())[:max_len]


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


async def _try_llm_synthesis(
    *,
    adapter: OpenAIClientAdapter,
    prompts: dict[str, str],
    event_title: str,
    root_post_text: str,
    comments: list[str],
    status_hint: str,
) -> dict[str, Any] | None:
    request_payload = {
        "status_hint": status_hint,
        "event_title": event_title,
        "root_post_text": _safe_text(root_post_text, max_len=1800),
        "comments": [_safe_text(item, max_len=300) for item in comments[:60]],
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


async def build_event_report_v2_impl(
    *,
    session: AsyncSession,
    event_id: int,
    prompt_loader: PromptLoader | None = None,
    llm_adapter: OpenAIClientAdapter | None = None,
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
    target_status = aggregate_public_status(
        article=article_sufficiency,
        comment=comment_sufficiency,
        retrieval=retrieval_sufficiency,
        analytical=analytical_sufficiency,
    )
    step_traces: dict[str, dict[str, Any]] = {
        "context": {
            "status": "completed",
            "run_count": 1,
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
        },
        "routing": {"status": "completed", "run_count": 1},
        "expert": {"status": "completed", "run_count": 1},
        "public_opinion": {"status": "completed", "run_count": 1},
        "synthesis": {"status": "completed", "run_count": 1},
    }

    summary = (
        f"Event analysis built from root post {bundle.get('root_post_id')} and comments across {len(post_ids)} posts."
    )
    confidence_reason = "Deterministic event synthesis"
    llm_error: str | None = None
    llm_output: dict[str, Any] | None = None

    if llm_adapter is None:
        cfg = OpenAIAdapterConfig.from_settings()
        if cfg.api_key:
            llm_adapter = OpenAIClientAdapter(cfg)

    if llm_adapter is not None and target_status != "insufficient_data":
        try:
            llm_output = await _try_llm_synthesis(
                adapter=llm_adapter,
                prompts=prompts,
                event_title=str(bundle.get("event_title") or ""),
                root_post_text=root_post_text,
                comments=comments,
                status_hint=target_status,
            )
            if isinstance(llm_output, dict):
                summary = _safe_text(str(llm_output.get("summary") or summary), max_len=1500) or summary
                confidence_reason = _safe_text(str(llm_output.get("confidence_reason") or "LLM event synthesis"), max_len=500)
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            step_traces["synthesis"]["status"] = "failed"

    review_history: list[dict[str, Any]] = []
    review_reruns = 0
    pending_rerun = "synthesis" if llm_error is not None else None
    pending_reason = "synthesis_error" if pending_rerun else ""

    while pending_rerun is not None and review_reruns < REVIEW_MAX_ITERATIONS:
        step_traces[pending_rerun]["run_count"] = int(step_traces[pending_rerun].get("run_count") or 1) + 1
        step_traces[pending_rerun]["rerun_requested"] = True
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
    else:
        if target_status == "ready":
            review_decision = "accept"
        elif target_status == "limited":
            review_decision = "accept_with_limitations"
        else:
            review_decision = "insufficient_data"
        review_history.append(
            {
                "iteration": 1,
                "decision": review_decision,
                "target": None,
                "reason": analytical_sufficiency,
                "confidence": 0.8 if target_status == "ready" else 0.6,
            }
        )

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
        "cross_post_topics": list(llm_output.get("topics") or []) if isinstance(llm_output, dict) else [],
        "post_dynamics": [],
        "event_trends": [],
        "risks": [],
        "anomalies": ["model_output_invalid"] if llm_error is not None else [],
        "summary": summary,
        "confidence": {
            "overall": "low" if target_status in {"insufficient_data", "failed"} else ("medium" if target_status == "limited" else "high"),
            "reason": confidence_reason,
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
            "sources": retrieval_sources,
        },
        "review": {
            "iterations": review_reruns,
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
