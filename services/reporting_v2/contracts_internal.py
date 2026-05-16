from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

EPISTEMIC_LABELS = frozenset(["fact", "derived", "interpretation", "external", "uncertain"])
EPISTEMIC_SOURCES = frozenset(["article", "comments", "retrieval"])
SUFFICIENCY_LABELS = frozenset(["sufficient", "limited", "weak_signal", "insufficient"])
REPORT_STATUSES = frozenset(["ready", "limited", "insufficient_data"])
FALLBACK_STATUSES = frozenset(["ready", "limited", "insufficient_data", "failed"])
RETRIEVAL_STATUSES = frozenset(["none", "success", "partial", "failed", "insufficient"])
PROVENANCE_STATUSES = frozenset(["completed", "failed", "skipped"])
STEP_KEYS = frozenset(["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"])


class EpistemicEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1)
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


class StageTrace(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    status: str | None = Field(default=None, min_length=1)
    run_count: int | None = Field(default=None, ge=0)
    provenance: StepProvenance = Field(default_factory=lambda: StepProvenance())


class StepProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str | None = None
    model: str | None = None
    executed: bool = False
    success: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
    input_ref: str | None = None
    input_hash: str | None = None
    output_ref: str | None = None
    output_hash: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    attempt_index: int = Field(default=0, ge=0)
    status: str = "skipped"


class RetrievalTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    required: bool
    used: bool
    status: str
    decision_inputs: dict[str, Any] = Field(default_factory=dict)
    decision_source: str = "policy"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    raw_results: list[dict[str, Any]] = Field(default_factory=list)


class RetrievalSourceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    tier: str
    supports: str = Field(min_length=1)
    relevance: float = Field(ge=0.0, le=1.0)


class ReviewHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    iteration: int = Field(ge=1)
    decision: str = Field(min_length=1)
    target: str | None = None
    reason: str = Field(default="", min_length=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ReviewTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    iterations: int = Field(default=0, ge=0)
    history: list[ReviewHistoryEntry] = Field(default_factory=list)


class MultiAgentMetaInternal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: str = "v1"
    status: str = "insufficient_data"
    epistemic_claims: list[EpistemicEntry] = Field(default_factory=list)
    steps: dict[str, StageTrace] = Field(default_factory=dict)
    retrieval: RetrievalTrace
    review: ReviewTrace

    @classmethod
    def model_validate(cls, obj: Any, *, strict: bool | None = None, from_attributes: bool | None = None, context: Any = None):  # type: ignore[override]
        model = super().model_validate(obj, strict=strict, from_attributes=from_attributes, context=context)
        if model.version != "v1":
            raise ValueError(f"Invalid version: {model.version}")
        if model.status not in FALLBACK_STATUSES:
            raise ValueError(f"Invalid status: {model.status}")
        if frozenset(model.steps.keys()) != STEP_KEYS:
            raise ValueError(f"Invalid steps keys: {sorted(model.steps.keys())}")
        if model.retrieval.status not in RETRIEVAL_STATUSES:
            raise ValueError(f"Invalid retrieval.status: {model.retrieval.status}")
        for step_name, step_trace in model.steps.items():
            if step_trace.provenance.status not in PROVENANCE_STATUSES:
                raise ValueError(f"Invalid provenance.status for step {step_name}: {step_trace.provenance.status}")
        if model.retrieval.used and not model.retrieval.sources:
            raise ValueError("retrieval.sources must be non-empty when retrieval.used=true")
        for idx, item in enumerate(model.retrieval.sources):
            evidence = RetrievalSourceEvidence.model_validate(item)
            if evidence.tier not in {"1", "2", "3"}:
                raise ValueError(f"Invalid retrieval source tier at index {idx}: {evidence.tier}")
        for claim in model.epistemic_claims:
            if claim.type not in EPISTEMIC_LABELS:
                raise ValueError(f"Invalid epistemic claim type: {claim.type}")
            if claim.source not in EPISTEMIC_SOURCES:
                raise ValueError(f"Invalid epistemic claim source: {claim.source}")
        _validate_epistemic_mapping(model)
        return model


def validate_multi_agent_meta(meta: Mapping[str, Any]) -> MultiAgentMetaInternal:
    return MultiAgentMetaInternal.model_validate(dict(meta))


def _validate_epistemic_mapping(model: MultiAgentMetaInternal) -> None:
    retrieval_success = model.retrieval.used and model.retrieval.status == "success"
    for claim in model.epistemic_claims:
        if claim.type == "external":
            if claim.source != "retrieval":
                raise ValueError("External claim must use retrieval source")
            if not retrieval_success:
                raise ValueError("External claim is forbidden without successful retrieval")
        if claim.type == "fact" and claim.source == "retrieval":
            raise ValueError("Fact claim cannot map to retrieval source; use external type")
        if claim.source == "retrieval" and not retrieval_success:
            raise ValueError("Retrieval-based claim is forbidden when retrieval is unavailable")
        if model.status == "insufficient_data" and claim.confidence > 0.7:
            raise ValueError("High-confidence claim is forbidden for insufficient_data status")


def assess_article_sufficiency(*, text: str) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return "insufficient"
    if len(normalized) < 120:
        return "limited"
    return "sufficient"


def assess_comment_sufficiency(*, comments: list[str]) -> str:
    normalized = [" ".join((item or "").split()) for item in comments if " ".join((item or "").split())]
    count = len(normalized)
    if count <= 0:
        return "insufficient"
    if count < 3:
        return "weak_signal"
    if count < 6:
        return "limited"
    return "sufficient"


def assess_retrieval_sufficiency(
    *,
    required: bool,
    used: bool,
    status: str,
    sources: list[dict[str, Any]],
) -> str:
    if not required:
        return "sufficient"
    if used and status == "success" and bool(sources):
        return "sufficient"
    return "insufficient"


def decide_retrieval_required(
    *,
    institutional_context: bool,
    international_context: bool,
    external_context_missing: bool,
    high_error_cost: bool,
) -> bool:
    return bool(
        institutional_context
        or international_context
        or external_context_missing
        or high_error_cost
    )


def build_retrieval_trace(
    *,
    required: bool,
    provider_enabled: bool,
    sources: list[dict[str, Any]] | None = None,
    decision_inputs: Mapping[str, Any] | None = None,
    decision_source: str = "retrieval_policy",
    status_override: str | None = None,
    quality_score: float | None = None,
    facts: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    gaps: list[str] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    raw_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_inputs = dict(decision_inputs or {})
    normalized_sources = list(sources or [])
    normalized_quality = max(0.0, min(1.0, float(quality_score or 0.0)))
    normalized_facts = list(facts or [])
    normalized_conflicts = list(conflicts or [])
    normalized_gaps = [str(item) for item in list(gaps or []) if str(item)]
    normalized_diagnostics = dict(diagnostics or {})
    normalized_raw_results = list(raw_results or [])

    if not required:
        return {
            "required": False,
            "used": False,
            "status": "none",
            "decision_inputs": normalized_inputs,
            "decision_source": decision_source,
            "sources": [],
            "quality_score": normalized_quality,
            "facts": normalized_facts,
            "conflicts": normalized_conflicts,
            "gaps": normalized_gaps,
            "diagnostics": normalized_diagnostics,
            "raw_results": normalized_raw_results,
        }

    if not provider_enabled:
        return {
            "required": True,
            "used": False,
            "status": "failed",
            "decision_inputs": normalized_inputs,
            "decision_source": decision_source,
            "sources": [],
            "quality_score": normalized_quality,
            "facts": normalized_facts,
            "conflicts": normalized_conflicts,
            "gaps": normalized_gaps,
            "diagnostics": normalized_diagnostics,
            "raw_results": normalized_raw_results,
        }

    if not normalized_sources:
        return {
            "required": True,
            "used": False,
            "status": "insufficient",
            "decision_inputs": normalized_inputs,
            "decision_source": decision_source,
            "sources": [],
            "quality_score": normalized_quality,
            "facts": normalized_facts,
            "conflicts": normalized_conflicts,
            "gaps": normalized_gaps,
            "diagnostics": normalized_diagnostics,
            "raw_results": normalized_raw_results,
        }

    final_status = str(status_override or "success")
    if final_status not in RETRIEVAL_STATUSES:
        final_status = "success"
    return {
        "required": True,
        "used": True,
        "status": final_status,
        "decision_inputs": normalized_inputs,
        "decision_source": decision_source,
        "sources": normalized_sources,
        "quality_score": normalized_quality,
        "facts": normalized_facts,
        "conflicts": normalized_conflicts,
        "gaps": normalized_gaps,
        "diagnostics": normalized_diagnostics,
        "raw_results": normalized_raw_results,
    }


def build_retrieval_trace_without_provider(
    *,
    required: bool,
    provider_enabled: bool,
    decision_inputs: Mapping[str, Any] | None = None,
    decision_source: str = "policy",
) -> dict[str, Any]:
    return build_retrieval_trace(
        required=required,
        provider_enabled=provider_enabled,
        sources=[],
        decision_inputs=decision_inputs,
        decision_source=decision_source,
    )


def assess_analytical_sufficiency(
    *,
    article: str,
    comment: str,
    retrieval: str,
) -> str:
    if article == "insufficient":
        return "insufficient"
    if article == "limited":
        return "limited"
    if retrieval == "insufficient":
        return "limited"
    if comment in {"insufficient", "limited", "weak_signal"}:
        return "limited"
    return "sufficient"


def aggregate_public_status(
    *,
    article: str,
    comment: str,
    retrieval: str,
    analytical: str,
) -> str:
    if article == "insufficient":
        return "insufficient_data"
    if analytical == "insufficient":
        return "insufficient_data"
    if "limited" in {article, retrieval, analytical}:
        return "limited"
    if comment == "weak_signal":
        return "limited"
    return "ready"
