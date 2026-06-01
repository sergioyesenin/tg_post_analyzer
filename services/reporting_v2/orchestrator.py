from __future__ import annotations

import re
from collections import Counter
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
from services.reporting_v2.steps import execute_state_step

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
_SENTENCE_RE = re.compile(r"[.!?]+")
REVIEW_DECISIONS = {"accept", "accept_with_limitations", "rerun_branch", "revise", "insufficient_data"}
DEFECT_CODES = {"D1", "D2", "D3", "D4", "D5", "D6"}
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_]+", flags=re.UNICODE)
_TOPIC_STOPWORDS = {
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
    "когда",
    "после",
    "только",
    "очень",
    "просто",
    "который",
    "которая",
    "которые",
    "чтобы",
    "если",
    "поэтому",
    "потому",
    "тогда",
    "зачем",
    "есть",
    "тоже",
    "свою",
    "вообще",
    "этой",
    "какие",
    "меня",
    "сейчас",
    "чего",
    "такие",
}


def _mark_stage(state: PipelineState, *, stage: str, status: str = "completed") -> None:
    trace = dict(state.internal_trace)
    stages = dict(trace.get("stages") or {})
    previous = dict(stages.get(stage) or {})
    stages[stage] = {
        "status": status,
        "run_count": int(previous.get("run_count") or 0) + 1,
    }
    trace["stages"] = stages
    state.internal_trace = trace


def _clean_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _non_empty_comments(state: PipelineState) -> list[str]:
    return [_clean_text(item) for item in state.comments if _clean_text(item)]


def _token_count(value: str) -> int:
    return len(_TOKEN_RE.findall(value))


def _is_informative_comment(value: str) -> bool:
    return _token_count(value) >= 4 and len(value) >= 20


def _classify_article_sufficiency(post_text: str) -> str:
    text = _clean_text(post_text)
    if not text:
        return "insufficient"
    if len(text) < 120:
        return "limited"
    return "sufficient"


def _classify_comment_sufficiency(comments: list[str]) -> str:
    count = len(comments)
    if count == 0:
        return "insufficient"
    informative_comments = [item for item in comments if _is_informative_comment(item)]
    informative_count = len(informative_comments)
    if informative_count == 0:
        return "insufficient"
    if informative_count < 3:
        return "weak_signal"
    avg_len = sum(len(item) for item in informative_comments) / informative_count
    informative_share = informative_count / max(1, count)
    if informative_count < 8:
        return "limited"
    if avg_len < 30 or informative_share < 0.6:
        return "limited"
    return "sufficient"


def _classify_analytical_sufficiency(*, article: str, comment: str) -> str:
    if article == "insufficient" and comment == "sufficient":
        return "limited"
    if article == "insufficient" and comment in {"insufficient", "weak_signal"}:
        return "insufficient"
    if article in {"limited", "insufficient"}:
        return "limited"
    if comment in {"insufficient", "weak_signal", "limited"}:
        return "limited"
    return "sufficient"


def _derive_status_from_context(*, article: str, comment: str, analytical: str) -> str:
    if analytical == "insufficient":
        return "insufficient_data"
    if analytical == "limited" or article != "sufficient" or comment != "sufficient":
        return "limited"
    return "ready"


def _extract_topics(post_text: str, comments: list[str], *, limit: int = 3) -> list[str]:
    merged = " ".join([post_text, *comments])
    tokens = [token.lower() for token in _TOKEN_RE.findall(merged)]
    candidates = [
        token
        for token in tokens
        if len(token) >= 4 and token not in _TOPIC_STOPWORDS and not token.isdigit()
    ]
    ranked = Counter(candidates).most_common(limit)
    return [token for token, _count in ranked]


def _sentence_count(text: str) -> int:
    return len([part for part in _SENTENCE_RE.split(text) if part.strip()])


def _build_synthesis_components(state: PipelineState) -> tuple[dict[str, str], str]:
    cleaned_comments = _non_empty_comments(state)
    comments_count = len(cleaned_comments)
    topics = _extract_topics(state.post_text, cleaned_comments, limit=3)
    topics_text = ", ".join(topics) if topics else "no stable repeated topics"
    reaction_state = state.public_opinion.discussion_state
    limitations = state.status in {"limited", "insufficient_data"}
    limited_tail = " Evidence remains limited and conclusions should be treated cautiously." if limitations else ""

    event_sentence = (
        f"The event under discussion is summarized as follows: {_clean_text(state.post_text)[:180] or 'the source post provides only minimal detail'}."
    )
    context_sentence = (
        f"Context quality is {state.context.analytical_sufficiency}, based on article sufficiency={state.context.article_sufficiency} and comment sufficiency={state.context.comment_sufficiency}."
    )
    reaction_sentence = (
        f"Public reaction is {reaction_state}, with {comments_count} usable comments and recurring topics around {topics_text}."
    )
    interpretation_sentence = (
        f"The dominant interpretation is that observed signals are {'directional' if state.status == 'ready' else 'partial'} rather than fully conclusive.{limited_tail}"
    )
    consequences_sentence = (
        "The practical consequence is that downstream decisions should rely on this report proportionally to its confidence level and may require follow-up evidence."
    )
    components = {
        "event": event_sentence,
        "context": context_sentence,
        "reaction": reaction_sentence,
        "interpretation": interpretation_sentence,
        "consequences": consequences_sentence,
    }
    report_text = " ".join(
        [
            event_sentence,
            context_sentence,
            reaction_sentence,
            interpretation_sentence,
            consequences_sentence,
        ]
    ).strip()
    return components, report_text


def _collect_reviewer_defects(state: PipelineState) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    has_material = bool(_clean_text(state.post_text)) or bool(_non_empty_comments(state))
    if not has_material:
        defects.append({"code": "D4", "reason": "no_material", "target": "context"})
    synthesis_text = _clean_text(state.synthesis.report_text or state.synthesis.summary)
    sentence_count = _sentence_count(synthesis_text)
    components = dict(state.synthesis.components or {})
    required_components = ("event", "context", "reaction", "interpretation", "consequences")
    missing_components = [name for name in required_components if components.get(name) is not True]
    if missing_components or sentence_count < 5 or sentence_count > 7:
        defects.append({"code": "D1", "reason": f"structural_missing:{','.join(missing_components) or 'sentence_count'}", "target": "synthesis"})

    if state.synthesis.quality != "ok":
        defects.append({"code": "D2", "reason": "weak_analysis", "target": "synthesis"})

    if state.context.comment_sufficiency == "weak_signal" and state.status == "ready":
        defects.append({"code": "D4", "reason": "weak_signal_marked_ready", "target": "public_opinion"})

    if state.retrieval.required and state.retrieval.status in {"failed", "insufficient", "none"} and state.status == "ready":
        defects.append({"code": "D3", "reason": "ready_without_required_retrieval", "target": "routing"})

    if state.retrieval.used and not state.retrieval.sources:
        defects.append({"code": "D5", "reason": "retrieval_used_without_sources", "target": "routing"})

        retrieval_success = (
        state.retrieval.used
        and state.retrieval.status == "success"
        and bool(state.retrieval.sources)
    )

    for item in [*state.expert.background, *state.expert.interpretations, *state.expert.consequences]:
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

    if state.status == "insufficient_data" and state.retrieval.status == "success" and state.context.analytical_sufficiency == "sufficient":
        defects.append({"code": "D6", "reason": "status_inconsistent_with_signals", "target": "synthesis"})

    return [item for item in defects if str(item.get("code")) in DEFECT_CODES]


def run_context_stage(state: PipelineState) -> PipelineState:
    cleaned_comments = _non_empty_comments(state)
    article_sufficiency = _classify_article_sufficiency(state.post_text)
    comment_sufficiency = _classify_comment_sufficiency(cleaned_comments)
    analytical_sufficiency = _classify_analytical_sufficiency(
        article=article_sufficiency,
        comment=comment_sufficiency,
    )
    state.context = ContextOutput(
        article_sufficiency=article_sufficiency,
        comment_sufficiency=comment_sufficiency,
        analytical_sufficiency=analytical_sufficiency,
    )
    _mark_stage(state, stage="context")
    return state


def run_routing_stage(state: PipelineState) -> PipelineState:
    state.routing = RoutingOutput(
        category="general",
        confidence=0.0,
        reasoning="deterministic_orchestrator_v1",
        retrieval_hints={},
    )
    _mark_stage(state, stage="routing")
    return state


def run_retrieval_decision_stage(state: PipelineState) -> PipelineState:
    merged = f"{_clean_text(state.post_text)} {' '.join(_non_empty_comments(state)[:10])}".lower()
    required = any(
        token in merged
        for token in ("government", "ministry", "president", "parliament", "sanction", "war", "election", "nato", "international")
    )
    state.retrieval = RetrievalDecisionOutput(
        required=required,
        used=False,
        status="failed" if required else "none",
        decision_inputs={"required_by_policy": required},
        decision_source="policy",
        sources=[],
    )
    _mark_stage(state, stage="retrieval")
    return state


def _entry(text: str, claim_type: str, confidence: float, source: str) -> dict[str, Any]:
    return {
        "text": text,
        "type": claim_type,
        "confidence": max(0.0, min(1.0, confidence)),
        "source": source,
    }


def run_expert_stage(state: PipelineState) -> PipelineState:
    background: list[dict[str, Any]] = []

    if _clean_text(state.post_text):
        background.append(
            _entry(
                _clean_text(state.post_text)[:240],
                "fact",
                0.65,
                "article",
            )
        )

    if state.retrieval.used and state.retrieval.status == "success":
        for source in state.retrieval.sources[:3]:
            if isinstance(source, dict) and source.get("supports"):
                background.append(
                    _entry(
                        str(source.get("supports")),
                        "external",
                        0.7,
                        "retrieval",
                    )
                )

    interpretations = [
        _entry(
            "Interpretation is bounded by the available article, comments, and retrieval evidence.",
            "interpretation",
            0.55 if state.status != "ready" else 0.7,
            "article",
        )
    ]

    consequences = [
        _entry(
            "Consequences should be treated cautiously unless retrieval evidence and discussion signals are sufficient.",
            "uncertain" if state.status != "ready" else "interpretation",
            0.45 if state.status != "ready" else 0.6,
            "article",
        )
    ]

    state.expert = ExpertOutput(
        background=background,
        interpretations=interpretations,
        consequences=consequences,
        data_status=(
            "limited"
            if state.retrieval.required and not state.retrieval.used
            else state.context.analytical_sufficiency
        ),
        confidence=0.55 if state.status != "ready" else 0.7,
        claims=[*background, *interpretations, *consequences],
    )

    _mark_stage(state, stage="expert")
    return state


def run_public_opinion_stage(state: PipelineState) -> PipelineState:
    cleaned_comments = _non_empty_comments(state)
    comments_count = len(cleaned_comments)
    merged_comments = " ".join(cleaned_comments).lower()
    conflict_markers = ("виноват", "виноваты", "должен", "должны", "запрет", "штраф", "наруш")
    conflict_hits = sum(merged_comments.count(marker) for marker in conflict_markers)
    if comments_count == 0 or state.context.comment_sufficiency in {"insufficient", "weak_signal"}:
        discussion_state = "weak_signal"
    elif conflict_hits >= 3:
        discussion_state = "conflicted"
    elif conflict_hits > 0:
        discussion_state = "mixed"
    else:
        discussion_state = "mixed"
    topics = _extract_topics(state.post_text, cleaned_comments, limit=3)
    signals: list[dict[str, Any]] = [
        {"name": "comments_count", "value": comments_count},
        {"name": "conflict_hits", "value": conflict_hits},
    ]
    if topics:
        signals.append({"name": "top_topics", "value": topics})
    data_status = state.context.comment_sufficiency
    confidence = 0.25 if data_status in {"insufficient", "weak_signal"} else (0.5 if data_status == "limited" else 0.75)
    dominant_reactions = (
        [{"label": "disagreement", "share": round(min(1.0, conflict_hits / max(1, comments_count)), 4), "evidence_count": conflict_hits}]
        if conflict_hits > 0
        else []
    )
    state.public_opinion = PublicOpinionOutput(
        discussion_state=discussion_state,
        signals=signals,
        main_topics=topics,
        dominant_reactions=dominant_reactions,
        data_status=data_status,
        confidence=confidence,
    )
    _mark_stage(state, stage="public_opinion")
    return state


async def run_synthesis_stage(state: PipelineState) -> PipelineState:
    components, report_text = _build_synthesis_components(state)
    sentence_count = _sentence_count(report_text)
    quality = "ok" if 5 <= sentence_count <= 7 else "needs_revision"
    limitations_required = state.status in {"limited", "insufficient_data"}
    has_limitations_phrase = (
        "limited" in report_text.lower()
        or "cautious" in report_text.lower()
        or "insufficient" in report_text.lower()
    )
    if limitations_required and not has_limitations_phrase:
        quality = "needs_revision"
    confidence_reason = "deterministic_orchestrator_v1" if state.status == "ready" else "limited_evidence"
    state.synthesis = SynthesisOutput(
        summary=report_text,
        report_text=report_text,
        components={key: True for key in components},
        sentence_count=sentence_count,
        quality=quality,
        confidence_reason=confidence_reason,
    )
    _mark_stage(state, stage="synthesis")
    return state


def run_reviewer_loop(state: PipelineState, *, max_iterations: int = REVIEWER_MAX_ITERATIONS) -> PipelineState:
    bounded_iterations = max(0, min(int(max_iterations), REVIEWER_MAX_ITERATIONS))
    history: list[dict[str, Any]] = []
    decision = "insufficient_data"
    defects = _collect_reviewer_defects(state)
    
    for idx in range(bounded_iterations):
        if not defects:
            decision = "accept" if state.status == "ready" else "accept_with_limitations"
            history.append(
                {
                    "iteration": idx + 1,
                    "decision": decision,
                    "target": None,
                    "reason": "spec_checks_passed",
                    "confidence": 0.85 if decision == "accept" else 0.65,
                }
            )
            break

        primary = defects[0]
        code = str(primary.get("code"))
        target = str(primary.get("target") or "")
        if code == "D1":
            next_decision = "rerun_branch"
        elif code == "D2":
            next_decision = "revise"
        elif code in {"D3", "D4", "D6"}:
            next_decision = "insufficient_data" if state.status == "insufficient_data" else "accept_with_limitations"
        else:
            next_decision = "rerun_branch"
        history.append(
            {
                "iteration": idx + 1,
                "decision": next_decision,
                "target": target or None,
                "reason": f"{code}:{primary.get('reason')}",
                "confidence": 0.45,
            }
        )
        decision = next_decision
        if next_decision in {"accept", "accept_with_limitations", "insufficient_data"}:
            break

    if decision == "rerun_branch" and bounded_iterations > 0:
        decision = "insufficient_data"
        history.append(
            {
                "iteration": len(history) + 1,
                "decision": "insufficient_data",
                "target": None,
                "reason": "review_budget_exhausted",
                "confidence": 0.0,
            }
        )

    if not history:
        decision = "insufficient_data"

    state.reviewer = ReviewerOutput(
        decision=str(decision if decision in REVIEW_DECISIONS else "insufficient_data"),
        iterations=max(0, len(history) - 1 if history and history[-1]["reason"] == "review_budget_exhausted" else len(history)),
        history=history,
    )
    if state.reviewer.decision == "insufficient_data":
        state.status = "insufficient_data"
    elif state.reviewer.decision in {"accept_with_limitations", "revise", "rerun_branch"} and state.status == "ready":
        state.status = "limited"
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

    state = await execute_state_step(state=state, step_name="context", handler=run_context_stage)
    state.status = _derive_status_from_context(
        article=state.context.article_sufficiency,
        comment=state.context.comment_sufficiency,
        analytical=state.context.analytical_sufficiency,
    )
    state = await execute_state_step(state=state, step_name="routing", handler=run_routing_stage)
    state = await execute_state_step(state=state, step_name="retrieval", handler=run_retrieval_decision_stage)
    state = await execute_state_step(state=state, step_name="expert", handler=run_expert_stage)
    state = await execute_state_step(state=state, step_name="public_opinion", handler=run_public_opinion_stage)
    state = await execute_state_step(state=state, step_name="synthesis", handler=run_synthesis_stage)
    state = await execute_state_step(
        state=state,
        step_name="reviewer",
        handler=lambda current_state: run_reviewer_loop(
            current_state,
            max_iterations=REVIEWER_MAX_ITERATIONS,
        ),
    )
    return state
