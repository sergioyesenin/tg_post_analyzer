"""Contract-focused tests for internal meta.multi_agent schema."""

from __future__ import annotations

import pytest

from services.reporting_v2.contracts_internal import (
    EPISTEMIC_LABELS,
    FALLBACK_STATUSES,
    REPORT_STATUSES,
    STEP_KEYS,
    SUFFICIENCY_LABELS,
    validate_multi_agent_meta,
)


def _base_meta() -> dict:
    return {
        "version": "v1",
        "status": "limited",
        "epistemic_claims": [
            {"text": "Observed recurring thesis in comments.", "type": "derived", "confidence": 0.6, "source": "comments"}
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
            "decision_inputs": {},
            "decision_source": "policy",
            "sources": [],
        },
        "review": {
            "iterations": 0,
            "history": [{"iteration": 1, "decision": "accept_with_limitations", "target": None, "reason": "limited", "confidence": 0.6}],
        },
    }


def test_contract_constants_are_canonical_sets() -> None:
    assert EPISTEMIC_LABELS == frozenset({"fact", "derived", "interpretation", "external", "uncertain"})
    assert SUFFICIENCY_LABELS == frozenset({"sufficient", "limited", "weak_signal", "insufficient"})
    assert REPORT_STATUSES == frozenset({"ready", "limited", "insufficient_data"})
    assert FALLBACK_STATUSES == frozenset({"ready", "limited", "insufficient_data", "failed"})
    assert STEP_KEYS == frozenset({"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"})


def test_validate_multi_agent_meta_accepts_canonical_6_step_shape() -> None:
    validated = validate_multi_agent_meta(_base_meta())
    assert set(validated.steps.keys()) == {"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"}
    assert validated.version == "v1"


def test_validate_multi_agent_meta_rejects_legacy_stage_shape() -> None:
    payload = _base_meta()
    payload.pop("steps")
    payload["stages"] = {"context": {"status": "completed"}}
    with pytest.raises(ValueError):
        validate_multi_agent_meta(payload)


def test_validate_multi_agent_meta_rejects_missing_reviewer_step() -> None:
    payload = _base_meta()
    del payload["steps"]["reviewer"]
    with pytest.raises(ValueError, match="Invalid steps keys"):
        validate_multi_agent_meta(payload)
