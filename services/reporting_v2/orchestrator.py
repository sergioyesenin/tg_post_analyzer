from __future__ import annotations

from typing import Any

from services.reporting_v2.state import (
    ContextOutput,
    ExpertOutput,
    PipelineState,
    PublicOpinionOutput,
    RetrievalDecisionOutput,
    ReviewerOutput,
    RoutingOutput,
    SynthesisOutput,
    init_pipeline_state,
)

PIPELINE_STAGE_ORDER = (
    "context",
    "routing",
    "retrieval",
    "expert",
    "public_opinion",
    "synthesis",
    "reviewer",
)

REVIEWER_MAX_ITERATIONS = 2


def _mark_stage(state: PipelineState, *, stage: str, status: str = "completed") -> None:
    trace = dict(state.internal_trace)
    stages = dict(trace.get("stages") or {})
    stages[stage] = {"status": status}
    trace["stages"] = stages
    state.internal_trace = trace


def run_context_stage(state: PipelineState) -> PipelineState:
    article_sufficiency = "sufficient" if state.post_text.strip() else "insufficient"
    comment_sufficiency = "limited" if len(state.comments) > 0 else "insufficient"
    state.context = ContextOutput(
        article_sufficiency=article_sufficiency,
        comment_sufficiency=comment_sufficiency,
        analytical_sufficiency="insufficient",
    )
    _mark_stage(state, stage="context")
    return state


def run_routing_stage(state: PipelineState) -> PipelineState:
    state.routing = RoutingOutput(
        category="general",
        confidence=0.0,
        reasoning="orchestrator_skeleton",
        retrieval_hints={},
    )
    _mark_stage(state, stage="routing")
    return state


def run_retrieval_decision_stage(state: PipelineState) -> PipelineState:
    state.retrieval = RetrievalDecisionOutput(
        required=False,
        used=False,
        status="none",
        decision_inputs={},
        decision_source="policy",
        sources=[],
    )
    _mark_stage(state, stage="retrieval")
    return state


def run_expert_stage(state: PipelineState) -> PipelineState:
    state.expert = ExpertOutput(claims=[])
    _mark_stage(state, stage="expert")
    return state


def run_public_opinion_stage(state: PipelineState) -> PipelineState:
    state.public_opinion = PublicOpinionOutput(
        discussion_state="unclear",
        signals=[],
    )
    _mark_stage(state, stage="public_opinion")
    return state


async def run_synthesis_stage(state: PipelineState) -> PipelineState:
    state.synthesis = SynthesisOutput(
        summary="",
        confidence_reason="orchestrator_skeleton",
    )
    _mark_stage(state, stage="synthesis")
    return state


def run_reviewer_loop(state: PipelineState, *, max_iterations: int = REVIEWER_MAX_ITERATIONS) -> PipelineState:
    bounded_iterations = max(0, min(int(max_iterations), REVIEWER_MAX_ITERATIONS))
    history: list[dict[str, Any]] = []
    has_synthesis_summary = bool((state.synthesis.summary or "").strip())
    for idx in range(bounded_iterations):
        if has_synthesis_summary:
            is_ready = str(state.status or "").strip().lower() == "ready"
            history.append(
                {
                    "iteration": idx + 1,
                    "decision": "accept" if is_ready else "accept_with_limitations",
                    "target": None,
                    "reason": "synthesis_present",
                    "confidence": 0.8 if is_ready else 0.6,
                }
            )
            break

        is_last_iteration = (idx + 1) >= bounded_iterations
        history.append(
            {
                "iteration": idx + 1,
                "decision": "insufficient_data" if is_last_iteration else "rerun_branch",
                "target": "synthesis",
                "reason": "missing_synthesis_summary",
                "confidence": 0.0,
            }
        )

    final_decision = history[-1]["decision"] if history else "insufficient_data"
    state.reviewer = ReviewerOutput(
        decision=str(final_decision),
        iterations=len(history),
        history=history,
    )
    _mark_stage(state, stage="reviewer")
    return state


async def run_post_orchestrator_v2(
    *,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
    thread_comments: list[dict[str, Any]],
    views: int | None,
    rerun_stage: str | None = None,
) -> PipelineState:
    del thread_comments, views, rerun_stage

    state = init_pipeline_state(
        post_id=post_id,
        published_at_iso=published_at_iso,
        post_text=post_text,
        comments=comments,
    )
    state.internal_trace = {
        "pipeline_sequence": list(PIPELINE_STAGE_ORDER),
    }

    state = run_context_stage(state)
    state = run_routing_stage(state)
    state = run_retrieval_decision_stage(state)
    state = run_expert_stage(state)
    state = run_public_opinion_stage(state)
    state = await run_synthesis_stage(state)
    state = run_reviewer_loop(state, max_iterations=REVIEWER_MAX_ITERATIONS)
    return state
