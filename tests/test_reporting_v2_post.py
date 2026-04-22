from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services import reporting
from services.llm.openai_client import OpenAIChatCompletionTrace
from services.reporting_v2.post_pipeline import generate_post_report_payload_v2
from services.reporting_v2.orchestrator import run_reviewer_loop
from services.reporting_v2.state import init_pipeline_state


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)


def test_reporting_v2_post_pipeline_produces_full_multi_agent_trace(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=101,
            published_at_iso="2026-04-15T10:00:00+00:00",
                post_text=(
                    "This report describes a local community initiative with operational updates, "
                    "timeline milestones, stakeholders, and execution notes. The post includes enough "
                    "context to understand causes, immediate impact, and expected follow-up actions "
                    "without requiring outside references or institutional background."
                ),
            comments=[f"comment {idx}" for idx in range(1, 8)],
            thread_comments=[],
            views=50,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "limited"
    assert multi_agent["version"] == "v1"
    assert multi_agent["status"] == "limited"
    assert set(multi_agent["steps"].keys()) == {"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"}
    assert multi_agent["retrieval"]["required"] is False
    assert multi_agent["retrieval"]["status"] == "none"
    assert multi_agent["review"]["iterations"] >= 0
    assert multi_agent["review"]["history"][-1]["decision"] == "accept_with_limitations"
    assert multi_agent["steps"]["context"]["sufficiency_components"]["article"] == "sufficient"
    assert multi_agent["steps"]["context"]["sufficiency_components"]["comment"] == "sufficient"
    assert isinstance(multi_agent["epistemic_claims"], list)
    assert all(isinstance(item, dict) for item in multi_agent["epistemic_claims"])
    assert all({"text", "type", "confidence", "source"} <= set(item.keys()) for item in multi_agent["epistemic_claims"])


def test_reporting_v2_post_pipeline_supports_internal_rerun_trace(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=102,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Post with moderate signal.",
            comments=["one", "two", "three", "four"],
            thread_comments=[],
            views=30,
            rerun_stage="expert",
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "limited"
    assert multi_agent["review"]["iterations"] == 1
    assert multi_agent["steps"]["expert"]["run_count"] == 2
    assert multi_agent["review"]["history"][0]["decision"] == "rerun_branch"
    assert multi_agent["review"]["history"][-1]["decision"] == "accept_with_limitations"


def test_reporting_v2_post_pipeline_marks_weak_signal_explicitly(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=103,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="This is a detailed event report body that contains enough textual context to avoid article insufficiency.",
            comments=["single short comment", "second short comment"],
            thread_comments=[],
            views=12,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    components = multi_agent["steps"]["context"]["sufficiency_components"]
    assert components["comment"] == "weak_signal"
    assert components["analytical"] == "limited"
    assert payload["status"] == "limited"


def test_reporting_v2_post_pipeline_retrieval_required_without_provider_is_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=104,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "Government officials discussed sanctions and cross-border implications in a high-risk context. "
                "The update references previous external decisions without full explanation."
            ),
            comments=["comment 1", "comment 2", "comment 3", "comment 4", "comment 5", "comment 6"],
            thread_comments=[],
            views=100,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert multi_agent["retrieval"]["required"] is True
    assert multi_agent["retrieval"]["used"] is False
    assert multi_agent["retrieval"]["status"] == "failed"
    assert payload["status"] != "ready"
    assert all(item["type"] != "external" for item in multi_agent["epistemic_claims"])


def test_reporting_v2_post_pipeline_reviewer_loop_caps_at_two_on_synthesis_failure() -> None:
    class _FailingAdapter:
        async def create_chat_completion(self, **kwargs):
            raise RuntimeError("boom")

    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=105,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "This report describes a local community initiative with operational updates, "
                "timeline milestones, stakeholders, and execution notes. The post includes enough "
                "context to understand causes, immediate impact, and expected follow-up actions "
                "without requiring outside references or institutional background."
            ),
            comments=[f"comment {idx}" for idx in range(1, 8)],
            thread_comments=[],
            views=200,
            llm_adapter=_FailingAdapter(),
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "insufficient_data"
    assert multi_agent["review"]["iterations"] == 2
    assert [item["decision"] for item in multi_agent["review"]["history"]] == [
        "rerun_branch",
        "rerun_branch",
        "insufficient_data",
    ]


def test_reporting_v2_post_pipeline_marks_provider_provenance_for_all_six_steps() -> None:
    class _TraceAdapter:
        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            return OpenAIChatCompletionTrace(
                content="{}",
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=15,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=106,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "This report describes a local community initiative with operational updates, "
                "timeline milestones, stakeholders, and execution notes."
            ),
            comments=[f"comment {idx}" for idx in range(1, 8)],
            thread_comments=[],
            views=200,
            llm_adapter=_TraceAdapter(),
        )
    )

    steps = payload["meta"]["multi_agent"]["steps"]
    for step_name in ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer"):
        provenance = steps[step_name]["provenance"]
        assert provenance["provider"] == "openrouter"
        assert provenance["model"] == "qwen/qwen3-coder:free"
        assert provenance["executed"] is True
        assert provenance["latency_ms"] == 15


def test_build_post_report_uses_reporting_v2_executor(monkeypatch) -> None:
    channel = SimpleNamespace(id=7, username="test_channel")
    post = SimpleNamespace(
        id=11,
        date=reporting.datetime(2026, 3, 11, 12, 0, tzinfo=reporting.timezone.utc),
        text="post",
        views=5,
        comments_count=2,
        reactions_json=None,
    )
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([(1, None, None, 0, None, "hello", None), (2, 1, 1, 1, None, "world", None)]),
        ]
    )

    async def _fake_generate_v2(**kwargs):
        assert kwargs["post_id"] == 11
        canonical_step = {
            "status": "completed",
            "run_count": 1,
            "provenance": {
                "provider": "openrouter",
                "model": "qwen/qwen3-coder:free",
                "executed": True,
                "success": True,
                "latency_ms": 10,
                "input_ref": None,
                "input_hash": None,
                "output_ref": None,
                "output_hash": None,
                "fallback_used": False,
                "fallback_reason": None,
                "attempt_index": 0,
                "status": "completed",
            },
        }
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 11,
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "ok",
            "summary": "done",
            "comment_count": 2,
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "topics": [],
            "clusters": [],
            "time_trends": [],
            "risks": [],
            "anomalies": [],
            "representative_quotes": [],
            "confidence": {"overall": "medium", "reason": "ok"},
                "meta": {
                    "multi_agent": {
                        "version": "v1",
                        "status": "ready",
                        "steps": {name: dict(canonical_step) for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]},
                        "retrieval": {"required": False, "used": False, "status": "none", "sources": []},
                        "review": {
                            "iterations": 0,
                            "history": [{"iteration": 1, "decision": "accept", "target": None, "reason": "ok", "confidence": 0.9}],
                        },
                }
            },
        }

    async def _fake_upsert_report(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        assert status == "ready"
        assert report_json["meta"]["multi_agent"]["status"] == "ready"
        assert report_json["meta"]["input_signature"]
        return SimpleNamespace(id=95)

    class _LegacyProject:
        async def generate_post_report_payload(self, **kwargs):
            raise AssertionError("legacy project must not be used")

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _fake_generate_v2)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=_LegacyProject(),
        )
    )

    assert result["status"] == "ready"
    assert result["report_id"] == 95


def test_acceptance_matrix_full_sufficient(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=201,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "This report describes a local community initiative with operational updates, "
                "timeline milestones, stakeholders, and execution notes. The post includes enough "
                "context to understand causes, immediate impact, and expected follow-up actions "
                "without requiring outside references or institutional background."
            ),
            comments=[f"comment {idx}" for idx in range(1, 8)],
            thread_comments=[],
            views=80,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "limited"
    assert multi_agent["status"] == "limited"
    assert multi_agent["steps"]["context"]["sufficiency_components"]["article"] == "sufficient"
    assert multi_agent["steps"]["context"]["sufficiency_components"]["comment"] == "sufficient"
    assert multi_agent["retrieval"]["status"] == "none"
    assert multi_agent["review"]["history"][-1]["decision"] == "accept_with_limitations"


def test_acceptance_matrix_weak_signal_comments(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=202,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="This is a detailed event report body that contains enough textual context to avoid article insufficiency.",
            comments=["single short comment", "second short comment"],
            thread_comments=[],
            views=12,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    components = multi_agent["steps"]["context"]["sufficiency_components"]
    assert payload["status"] == "limited"
    assert components["comment"] == "weak_signal"
    assert components["analytical"] == "limited"
    assert multi_agent["review"]["history"][-1]["decision"] == "accept_with_limitations"


def test_acceptance_matrix_retrieval_required_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=203,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "Government officials discussed sanctions and cross-border implications in a high-risk context. "
                "The update references previous external decisions without full explanation."
            ),
            comments=["comment 1", "comment 2", "comment 3", "comment 4", "comment 5", "comment 6"],
            thread_comments=[],
            views=100,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] != "ready"
    assert multi_agent["retrieval"]["required"] is True
    assert multi_agent["retrieval"]["used"] is False
    assert multi_agent["retrieval"]["status"] == "failed"
    assert all(item["type"] != "external" for item in multi_agent["epistemic_claims"])


def test_acceptance_matrix_schema_valid_partial_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=204,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Post with moderate signal.",
            comments=["one", "two", "three", "four"],
            thread_comments=[],
            views=30,
            rerun_stage="expert",
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "limited"
    assert isinstance(payload.get("summary"), str) and payload["summary"]
    assert isinstance(payload.get("title"), str) and payload["title"]
    assert multi_agent["review"]["iterations"] == 1
    assert multi_agent["review"]["history"][-1]["decision"] == "accept_with_limitations"


def test_acceptance_matrix_terminal_insufficient_data() -> None:
    class _FailingAdapter:
        async def create_chat_completion(self, **kwargs):
            raise RuntimeError("boom")

    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=205,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "This report describes a local community initiative with operational updates, "
                "timeline milestones, stakeholders, and execution notes. The post includes enough "
                "context to understand causes, immediate impact, and expected follow-up actions "
                "without requiring outside references or institutional background."
            ),
            comments=[f"comment {idx}" for idx in range(1, 8)],
            thread_comments=[],
            views=200,
            llm_adapter=_FailingAdapter(),
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "insufficient_data"
    assert multi_agent["review"]["iterations"] == 2
    assert multi_agent["review"]["history"][-1]["decision"] == "insufficient_data"
    assert multi_agent["status"] == "insufficient_data"


def test_reviewer_defect_d1_missing_reaction_triggers_rerun_branch() -> None:
    state = init_pipeline_state(
        post_id=301,
        published_at_iso="2026-04-15T10:00:00+00:00",
        post_text="Detailed post text with enough context for analysis.",
        comments=["Useful comment with stable argument."],
    )
    state.status = "limited"
    state.synthesis.report_text = (
        "The event is described. "
        "The context is partially available. "
        "Interpretation is tentative. "
        "Consequences are provisional."
    )
    state.synthesis.components = {
        "event": True,
        "context": True,
        "reaction": False,
        "interpretation": True,
        "consequences": True,
    }
    state.synthesis.sentence_count = 4
    state.synthesis.quality = "needs_revision"

    updated = run_reviewer_loop(state, max_iterations=1)
    assert updated.reviewer.history[0]["decision"] == "rerun_branch"
    assert updated.reviewer.history[0]["target"] == "synthesis"


def test_reviewer_defect_d2_weak_analysis_triggers_revise() -> None:
    state = init_pipeline_state(
        post_id=302,
        published_at_iso="2026-04-15T10:00:00+00:00",
        post_text="Detailed post text with enough context for analysis.",
        comments=["Useful comment with stable argument."],
    )
    state.status = "limited"
    state.synthesis.report_text = (
        "The event is described. "
        "Context is present. "
        "Public reaction is present. "
        "Interpretation is weak and generic. "
        "Consequences are unclear."
    )
    state.synthesis.components = {
        "event": True,
        "context": True,
        "reaction": True,
        "interpretation": True,
        "consequences": True,
    }
    state.synthesis.sentence_count = 5
    state.synthesis.quality = "needs_revision"

    updated = run_reviewer_loop(state, max_iterations=2)
    assert updated.reviewer.history[0]["decision"] in {"revise", "rerun_branch"}


def test_public_opinion_is_structured_for_repeated_theses(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=303,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post text about transport policy and liability.",
            comments=[
                "Drivers should slow down near crossings and respect right-of-way.",
                "Drivers should slow down near crossings and respect right-of-way.",
                "Scooter users should follow crossing rules and reduce speed.",
                "Scooter users should follow crossing rules and reduce speed.",
                "Enforcement must improve to reduce repeated conflicts.",
                "Enforcement must improve to reduce repeated conflicts.",
            ],
            thread_comments=[],
            views=80,
        )
    )

    po = payload["meta"]["multi_agent"]["steps"]["public_opinion"]
    assert isinstance(po["dominant_reactions"], list)
    if po["dominant_reactions"]:
        assert isinstance(po["dominant_reactions"][0], dict)
        assert "label" in po["dominant_reactions"][0]
    assert isinstance(po["main_topics"], list)


def test_retrieval_required_without_provider_downgrades_confidence_in_public_mapping(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=304,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text=(
                "Government ministry statement references sanctions and cross-border negotiations "
                "without full external context."
            ),
            comments=["signal one", "signal two", "signal three", "signal four", "signal five", "signal six"],
            thread_comments=[],
            views=120,
            effective_features={"retrieval_provider_enabled": False},
        )
    )

    mapped = reporting.map_internal_post_report_to_public_payload(payload)
    assert mapped["status"] == "limited"
    assert mapped["confidence"]["overall"] in {"low", "medium"}
    assert "retrieval" in mapped["confidence"]["reason"].lower() or "external" in mapped["confidence"]["reason"].lower()


def test_public_summary_for_insufficient_data_is_not_masked_as_full_analysis() -> None:
    mapped = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "insufficient_data",
            "post_id": 305,
            "title": "sample",
            "summary": "Some summary",
            "comment_count": 0,
            "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0}},
            "confidence": {"overall": "high", "reason": "bad"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "insufficient_data",
                    "steps": {
                        "context": {"status": "completed", "run_count": 1},
                        "routing": {"status": "completed", "run_count": 1},
                        "expert": {"status": "completed", "run_count": 1},
                        "public_opinion": {"status": "completed", "run_count": 1},
                        "synthesis": {"status": "completed", "run_count": 1, "report_text": "too optimistic"},
                        "reviewer": {"status": "completed", "run_count": 1},
                    },
                    "retrieval": {"required": False, "used": False, "status": "none", "decision_inputs": {}, "decision_source": "policy", "sources": []},
                    "review": {"iterations": 0, "history": []},
                }
            },
        }
    )

    assert mapped["status"] == "insufficient_data"
    assert mapped["summary"] == "too optimistic."
