from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelInfoPublic(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    fallback_used: bool | None = None


class ContextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    article_sufficiency: str = "insufficient"
    comment_sufficiency: str = "insufficient"
    analytical_sufficiency: str = "insufficient"


class RoutingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: str = "general"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    retrieval_hints: dict[str, Any] = Field(default_factory=dict)


class RetrievalDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    required: bool = False
    used: bool = False
    status: str = "none"
    decision_inputs: dict[str, Any] = Field(default_factory=dict)
    decision_source: str = "policy"
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ExpertOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    background: list[dict[str, Any]] = Field(default_factory=list)
    interpretations: list[dict[str, Any]] = Field(default_factory=list)
    consequences: list[dict[str, Any]] = Field(default_factory=list)
    data_status: str = "insufficient"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Backward-compatible aggregate list.
    # Mapper/reporting code can still read expert.claims,
    # but new pipeline code should prefer structured sections above.
    claims: list[dict[str, Any]] = Field(default_factory=list)


class PublicOpinionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    discussion_state: str = "unclear"
    signals: list[dict[str, Any]] = Field(default_factory=list)
    main_topics: list[str] = Field(default_factory=list)
    dominant_reactions: list[dict[str, Any]] = Field(default_factory=list)
    data_status: str = "insufficient"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = ""
    report_text: str = ""
    components: dict[str, bool] = Field(default_factory=dict)
    sentence_count: int = Field(default=0, ge=0)
    quality: str = "needs_revision"
    confidence_reason: str = ""


class ReviewerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decision: str = "insufficient_data"
    iterations: int = Field(default=0, ge=0)
    history: list[dict[str, Any]] = Field(default_factory=list)


class PipelineState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    post_id: int
    published_at_iso: str
    post_text: str
    comments: list[str] = Field(default_factory=list)
    status: str = "insufficient_data"

    context: ContextOutput = Field(default_factory=ContextOutput)
    routing: RoutingOutput = Field(default_factory=RoutingOutput)
    retrieval: RetrievalDecisionOutput = Field(default_factory=RetrievalDecisionOutput)
    expert: ExpertOutput = Field(default_factory=ExpertOutput)
    public_opinion: PublicOpinionOutput = Field(default_factory=PublicOpinionOutput)
    synthesis: SynthesisOutput = Field(default_factory=SynthesisOutput)
    reviewer: ReviewerOutput = Field(default_factory=ReviewerOutput)

    model_info: ModelInfoPublic | None = None
    internal_trace: dict[str, Any] = Field(default_factory=dict)


def init_pipeline_state(
    *,
    post_id: int,
    published_at_iso: str,
    post_text: str,
    comments: list[str],
) -> PipelineState:
    normalized_comments = [item for item in comments if isinstance(item, str)]
    return PipelineState(
        post_id=post_id,
        published_at_iso=published_at_iso,
        post_text=post_text,
        comments=normalized_comments,
    )
