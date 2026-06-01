from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.reporting_v2.contracts_internal import (
    MultiAgentMetaInternal,
    aggregate_public_status,
    assess_analytical_sufficiency,
    assess_article_sufficiency,
    assess_comment_sufficiency,
    assess_retrieval_sufficiency,
    validate_multi_agent_meta,
)


def test_validate_multi_agent_meta_accepts_valid_payload() -> None:
    payload = {
        "version": "v1",
        "status": "ready",
        "epistemic_claims": [
            {"text": "Event happened", "type": "fact", "confidence": 0.7, "source": "article"},
            {"text": "Discussion trend observed", "type": "derived", "confidence": 0.6, "source": "comments"},
        ],
        "steps": {
            "context": {"status": "completed", "run_count": 1},
            "routing": {"status": "completed", "run_count": 1},
            "expert": {"status": "completed", "run_count": 1},
            "public_opinion": {"status": "completed", "run_count": 1},
            "synthesis": {"status": "completed", "run_count": 1},
            "reviewer": {"status": "completed", "run_count": 1},
        },
        "retrieval": {
            "required": False,
            "used": False,
            "status": "none",
            "sources": [],
        },
        "review": {
            "iterations": 0,
            "history": [
                {
                    "iteration": 1,
                    "decision": "accept",
                    "target": None,
                    "reason": "sufficient",
                    "confidence": 0.9,
                }
            ],
        },
    }

    validated = validate_multi_agent_meta(payload)

    assert validated.version == "v1"
    assert validated.status == "ready"
    assert validated.epistemic_claims[0].type == "fact"
    assert validated.steps["context"].status == "completed"
    assert validated.retrieval.status == "none"


def test_multi_agent_schema_rejects_legacy_shape() -> None:
    with pytest.raises(ValidationError):
        MultiAgentMetaInternal.model_validate(
            {
                "sufficiency": "limited",
                "stages": {},
                "review_iterations": 0,
                "final_status": "limited",
            }
        )


def test_multi_agent_schema_rejects_invalid_structure() -> None:
    with pytest.raises(ValueError, match="Invalid steps keys"):
        validate_multi_agent_meta(
            {
                "version": "v1",
                "status": "limited",
                "steps": {
                    "context": {"status": "completed"},
                    "routing": {"status": "completed"},
                    "expert": {"status": "completed"},
                    "synthesis": {"status": "completed"},
                },
                "retrieval": {"required": False, "used": False, "status": "none", "sources": []},
                "review": {"iterations": 0, "history": []},
            }
        )


def test_multi_agent_schema_rejects_invalid_epistemic_claim_type_and_source() -> None:
    payload = {
        "version": "v1",
        "status": "limited",
        "epistemic_claims": [
            {"text": "Claim", "type": "unknown", "confidence": 0.5, "source": "article"},
        ],
        "steps": {
            "context": {"status": "completed"},
            "routing": {"status": "completed"},
            "expert": {"status": "completed"},
            "public_opinion": {"status": "completed"},
            "synthesis": {"status": "completed"},
            "reviewer": {"status": "completed"},
        },
        "retrieval": {"required": False, "used": False, "status": "none", "sources": []},
        "review": {"iterations": 0, "history": []},
    }
    with pytest.raises(ValueError, match="Invalid epistemic claim type"):
        validate_multi_agent_meta(payload)

    payload["epistemic_claims"] = [
        {"text": "Claim", "type": "fact", "confidence": 0.5, "source": "unknown_source"},
    ]
    with pytest.raises(ValueError, match="Invalid epistemic claim source"):
        validate_multi_agent_meta(payload)


def test_multi_agent_schema_rejects_invalid_epistemic_mapping_transitions() -> None:
    payload = {
        "version": "v1",
        "status": "limited",
        "epistemic_claims": [
            {"text": "External context", "type": "external", "confidence": 0.6, "source": "retrieval"},
        ],
        "steps": {
            "context": {"status": "completed"},
            "routing": {"status": "completed"},
            "expert": {"status": "completed"},
            "public_opinion": {"status": "completed"},
            "synthesis": {"status": "completed"},
            "reviewer": {"status": "completed"},
        },
        "retrieval": {"required": True, "used": False, "status": "failed", "sources": []},
        "review": {"iterations": 0, "history": []},
    }
    with pytest.raises(ValueError, match="External claim is forbidden"):
        validate_multi_agent_meta(payload)

    payload["epistemic_claims"] = [
        {"text": "Too confident", "type": "uncertain", "confidence": 0.95, "source": "article"},
    ]
    payload["status"] = "insufficient_data"
    payload["retrieval"] = {"required": False, "used": False, "status": "none", "sources": []}
    with pytest.raises(ValueError, match="High-confidence claim is forbidden"):
        validate_multi_agent_meta(payload)


def test_sufficiency_model_component_evaluators_and_aggregation() -> None:
    assert assess_article_sufficiency(text="") == "insufficient"
    assert assess_article_sufficiency(text="Short context.") == "limited"
    assert assess_article_sufficiency(text="A" * 130) == "sufficient"

    assert assess_comment_sufficiency(comments=[]) == "insufficient"
    assert assess_comment_sufficiency(comments=["one", "two"]) == "weak_signal"
    assert assess_comment_sufficiency(comments=["one", "two", "three", "four"]) == "limited"
    assert assess_comment_sufficiency(comments=["1", "2", "3", "4", "5", "6"]) == "sufficient"

    assert assess_retrieval_sufficiency(required=False, used=False, status="none", sources=[]) == "sufficient"
    assert assess_retrieval_sufficiency(required=True, used=False, status="none", sources=[]) == "insufficient"
    assert assess_retrieval_sufficiency(required=True, used=True, status="success", sources=[{"source": "x"}]) == "sufficient"

    analytical = assess_analytical_sufficiency(article="sufficient", comment="weak_signal", retrieval="sufficient")
    assert analytical == "limited"
    assert aggregate_public_status(
        article="sufficient",
        comment="weak_signal",
        retrieval="sufficient",
        analytical=analytical,
    ) == "limited"

    with pytest.raises(ValueError, match="retrieval.sources must be non-empty"):
        validate_multi_agent_meta(
            {
                "version": "v1",
                "status": "ready",
                "steps": {
                    "context": {"status": "completed"},
                    "routing": {"status": "completed"},
                    "expert": {"status": "completed"},
                    "public_opinion": {"status": "completed"},
                    "synthesis": {"status": "completed"},
                    "reviewer": {"status": "completed"},
                },
                "retrieval": {"required": True, "used": True, "status": "success", "sources": []},
                "review": {"iterations": 0, "history": []},
            }
        )


def test_multi_agent_schema_validates_retrieval_source_evidence() -> None:
    payload = {
        "version": "v1",
        "status": "limited",
        "steps": {
            "context": {"status": "completed"},
            "routing": {"status": "completed"},
            "expert": {"status": "completed"},
            "public_opinion": {"status": "completed"},
            "synthesis": {"status": "completed"},
            "reviewer": {"status": "completed"},
        },
        "retrieval": {
            "required": True,
            "used": True,
            "status": "success",
            "sources": [
                {
                    "title": "Official bulletin",
                    "source": "gov.example",
                    "tier": "1",
                    "supports": "institutional context",
                    "relevance": 0.92,
                }
            ],
        },
        "review": {"iterations": 0, "history": []},
    }
    validated = validate_multi_agent_meta(payload)
    assert validated.retrieval.sources[0]["tier"] == "1"

    bad_payload = {
        **payload,
        "retrieval": {
            **payload["retrieval"],
            "sources": [
                {
                    "title": "Unknown blog",
                    "source": "blog.example",
                    "tier": "4",
                    "supports": "speculation",
                    "relevance": 0.4,
                }
            ],
        },
    }
    with pytest.raises(ValueError, match="Invalid retrieval source tier"):
        validate_multi_agent_meta(bad_payload)


def test_acceptance_matrix_schema_valid_partial_fallback_contract() -> None:
    payload = {
        "version": "v1",
        "status": "limited",
        "epistemic_claims": [
            {"text": "Context exists", "type": "fact", "confidence": 0.6, "source": "article"},
            {"text": "Signal is weak", "type": "uncertain", "confidence": 0.45, "source": "comments"},
        ],
        "steps": {
            "context": {"status": "completed", "run_count": 1},
            "routing": {"status": "completed", "run_count": 1},
            "expert": {"status": "completed", "run_count": 2},
            "public_opinion": {"status": "completed", "run_count": 1},
            "synthesis": {"status": "completed", "run_count": 1},
            "reviewer": {"status": "completed", "run_count": 1},
        },
        "retrieval": {"required": False, "used": False, "status": "none", "sources": []},
        "review": {
            "iterations": 1,
            "history": [
                {"iteration": 1, "decision": "rerun", "target": "expert", "reason": "needs evidence", "confidence": 0.62},
                {
                    "iteration": 2,
                    "decision": "accept_with_limitations",
                    "target": None,
                    "reason": "weak signal remains",
                    "confidence": 0.58,
                },
            ],
        },
    }

    validated = validate_multi_agent_meta(payload)
    assert validated.status == "limited"
    assert validated.review.iterations == 1
    assert validated.review.history[-1].decision == "accept_with_limitations"
