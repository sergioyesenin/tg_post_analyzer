from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services import reporting
from services.llm.openai_client import OpenAIChatCompletionTrace
from services.reporting_v2.post_pipeline import generate_post_report_payload_v2
from services.reporting_v2.post_pipeline import MockRetrievalProvider
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
    assert payload["status"] in {"limited", "insufficient_data"}
    assert multi_agent["version"] == "v1"
    assert multi_agent["status"] == "limited"
    assert set(multi_agent["steps"].keys()) == {"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"}
    assert multi_agent["retrieval"]["required"] is False
    assert multi_agent["retrieval"]["status"] == "none"
    assert multi_agent["review"]["iterations"] >= 0
    assert multi_agent["review"]["history"][-1]["decision"] in {"accept_with_limitations", "insufficient_data"}
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
    assert payload["status"] in {"limited", "insufficient_data"}
    assert multi_agent["review"]["iterations"] == len(multi_agent["review"]["history"])
    assert multi_agent["steps"]["reviewer"]["rerun_iterations"] == 1
    assert multi_agent["steps"]["expert"]["run_count"] == 2
    assert multi_agent["review"]["history"][0]["decision"] == "rerun_branch"
    assert multi_agent["review"]["history"][-1]["decision"] in {"accept_with_limitations", "insufficient_data"}


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
    assert multi_agent["steps"]["reviewer"]["rerun_iterations"] == 2
    assert multi_agent["review"]["iterations"] == len(multi_agent["review"]["history"])
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
    required_keys = {
        "provider",
        "model",
        "executed",
        "success",
        "latency_ms",
        "input_ref",
        "input_hash",
        "output_ref",
        "output_hash",
        "fallback_used",
        "fallback_reason",
        "attempt_index",
        "status",
    }
    for step_name in ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer"):
        provenance = steps[step_name]["provenance"]
        assert required_keys.issubset(set(provenance.keys()))
        assert provenance["provider"] == "openrouter"
        assert provenance["model"] == "qwen/qwen3-coder:free"
        assert provenance["executed"] is True
        assert provenance["success"] is True
        assert provenance["latency_ms"] == 15
        assert provenance["input_ref"] == f"inline://{step_name}/input"
        assert isinstance(provenance["input_hash"], str) and len(provenance["input_hash"]) == 64
        assert provenance["output_ref"] == f"inline://{step_name}/output"
        assert isinstance(provenance["output_hash"], str) and len(provenance["output_hash"]) == 64
        assert provenance["fallback_used"] is False
        assert provenance["fallback_reason"] is None
        assert provenance["attempt_index"] == 0
        assert provenance["status"] == "completed"


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


def test_post_pipeline_keeps_synthesis_text_as_source_of_truth_without_downstream_overwrite() -> None:
    class _SynthesisAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def create_chat_completion_with_trace(self, **kwargs):
            from services.llm.openai_client import OpenAIChatCompletionTrace

            del kwargs
            self.calls += 1
            if self.calls == 5:
                content = (
                    '{"report_text":"SYNTHESIS_CANONICAL_TEXT","components":{"event":true,"context":true,'
                    '"reaction":true,"interpretation":true,"consequences":true},"sentence_count":1,'
                    '"quality":"ok","confidence_reason":"llm"}'
                )
            else:
                content = "{}"
            return OpenAIChatCompletionTrace(
                content=content,
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=11,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=306,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4"],
            thread_comments=[],
            views=55,
            llm_adapter=_SynthesisAdapter(),
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    synthesis_text = multi_agent["steps"]["synthesis"]["report_text"]
    assert synthesis_text == "SYNTHESIS_CANONICAL_TEXT"
    assert payload["summary"] == "SYNTHESIS_CANONICAL_TEXT"


class _ReviewerDecisionAdapter:
    def __init__(self, reviewer_payload: dict[str, object]) -> None:
        self.calls = 0
        self.reviewer_payload = reviewer_payload

    async def create_chat_completion_with_trace(self, **kwargs):
        from services.llm.openai_client import OpenAIChatCompletionTrace

        del kwargs
        self.calls += 1
        if self.calls == 5:
            content = (
                '{"report_text":"SYNTHESIS_CANONICAL_TEXT","components":{"event":true,"context":true,'
                '"reaction":true,"interpretation":true,"consequences":true},"sentence_count":1,'
                '"quality":"ok","confidence_reason":"llm"}'
            )
        elif self.calls == 6:
            import json

            content = json.dumps(self.reviewer_payload, ensure_ascii=False)
        else:
            content = "{}"
        return OpenAIChatCompletionTrace(
            content=content,
            provider="openrouter",
            model="qwen/qwen3-coder:free",
            latency_ms=11,
            fallback_used=False,
            fallback_reason=None,
            executed=True,
            success=True,
            attempt_index=0,
        )


class _ExpertContractAdapter:
    def __init__(self, expert_payload: dict[str, object], reviewer_payload: dict[str, object] | None = None) -> None:
        self.calls = 0
        self.expert_payload = expert_payload
        self.reviewer_payload = reviewer_payload or {"decision": "accept", "issues": []}

    async def create_chat_completion_with_trace(self, **kwargs):
        from services.llm.openai_client import OpenAIChatCompletionTrace
        import json

        del kwargs
        self.calls += 1
        if self.calls == 3:
            content = json.dumps(self.expert_payload, ensure_ascii=False)
        elif self.calls == 5:
            content = (
                '{"report_text":"SYNTHESIS_CANONICAL_TEXT","components":{"event":true,"context":true,'
                '"reaction":true,"interpretation":true,"consequences":true},"sentence_count":5,'
                '"quality":"ok","confidence_reason":"llm"}'
            )
        elif self.calls == 6:
            content = json.dumps(self.reviewer_payload, ensure_ascii=False)
        else:
            content = "{}"
        return OpenAIChatCompletionTrace(
            content=content,
            provider="openrouter",
            model="qwen/qwen3-coder:free",
            latency_ms=11,
            fallback_used=False,
            fallback_reason=None,
            executed=True,
            success=True,
            attempt_index=0,
        )


def test_reviewer_llm_rerun_branch_overrides_accept() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=501,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ReviewerDecisionAdapter(
                {
                    "decision": "rerun_branch",
                    "rerun_target": "expert",
                    "issues": [{"field": "expert.background", "problem": "empty"}],
                }
            ),
        )
    )
    review = payload["meta"]["multi_agent"]["review"]
    assert review["history"][0]["decision"] == "rerun_branch"
    assert review["history"][0]["target"] == "expert"
    assert payload["status"] == "limited"
    assert payload["meta"]["multi_agent"]["steps"]["reviewer"]["decision"] == "accept_with_limitations"


def test_reviewer_issues_prevent_plain_accept() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=502,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ReviewerDecisionAdapter(
                {
                    "decision": "accept",
                    "issues": [{"field": "public_opinion.main_topics", "problem": "empty"}],
                }
            ),
        )
    )
    decisions = [item["decision"] for item in payload["meta"]["multi_agent"]["review"]["history"]]
    assert "accept" not in decisions
    assert payload["status"] == "limited"


def test_reviewer_iterations_increment_after_rerun() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=503,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ReviewerDecisionAdapter(
                {
                    "decision": "rerun_branch",
                    "rerun_target": "synthesis",
                    "issues": [{"field": "synthesis.report_text", "problem": "weak"}],
                }
            ),
        )
    )
    assert payload["meta"]["multi_agent"]["review"]["iterations"] >= 1


def test_final_status_limited_when_rerun_limit_exhausted(monkeypatch) -> None:
    import services.reporting_v2.post_pipeline as post_pipeline_module

    monkeypatch.setattr(post_pipeline_module, "REVIEW_MAX_ITERATIONS", 0)
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=504,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ReviewerDecisionAdapter(
                {
                    "decision": "rerun_branch",
                    "rerun_target": "expert",
                    "issues": [{"field": "expert.background", "problem": "empty"}],
                }
            ),
        )
    )
    assert payload["status"] == "limited"
    assert payload["meta"]["multi_agent"]["steps"]["reviewer"]["decision"] != "accept"


def test_reviewer_malformed_expert_issue_targets_expert_and_sets_limited_quality() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=505,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ReviewerDecisionAdapter(
                {
                    "decision": "revise",
                    "issues": [{"field": "expert.background", "problem": "malformed"}],
                }
            ),
        )
    )
    review = payload["meta"]["multi_agent"]["review"]
    assert payload["status"] == "limited"
    assert payload["meta"]["multi_agent"]["steps"]["synthesis"]["quality"] == "needs_revision"
    assert payload["meta"]["multi_agent"]["steps"]["reviewer"]["decision"] == "accept_with_limitations"
    assert review["iterations"] == len(review["history"])
    assert review["history"][0]["target"] == "expert"


def test_expert_rejects_malformed_background_string() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=506,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter({"background": ":[{", "interpretations": [], "consequences": [], "confidence": 0.0}),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert payload["status"] in {"limited", "insufficient_data"}
    if payload["meta"]["multi_agent"]["retrieval"]["status"] in {"failed", "insufficient"}:
        assert expert["status"] == "completed"
        assert expert["data_status"] == "limited"
    else:
        assert expert["malformed_output"] is True
        assert expert["status"] == "failed"


def test_expert_rejects_empty_claims_when_data_sufficient() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=507,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [],
                    "interpretations": [],
                    "consequences": [],
                    "data_status": "sufficient",
                    "confidence": 0.0,
                }
            ),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    if payload["meta"]["multi_agent"]["retrieval"]["status"] in {"failed", "insufficient"}:
        assert expert["status"] == "completed"
        assert expert["data_status"] == "limited"
        assert len(expert["background"]) > 0
    else:
        assert expert["contract_invalid"] is True
    assert payload["status"] in {"limited", "insufficient_data"}


def test_expert_accepts_structured_epistemic_claims() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=508,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Факт", "type": "fact", "confidence": 0.8, "source": "article"}],
                    "interpretations": [{"text": "Интерпретация", "type": "interpretation", "confidence": 0.7, "source": "comments"}],
                    "consequences": [{"text": "Последствие", "type": "consequence", "confidence": 0.7, "source": "article"}],
                    "data_status": "sufficient",
                    "confidence": 0.75,
                }
            ),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert expert["malformed_output"] is False
    assert expert["contract_invalid"] is False


def test_invalid_expert_blocks_plain_accept() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=509,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter({"background": ":[{", "interpretations": [], "consequences": [], "confidence": 0.0}),
        )
    )
    decisions = [item["decision"] for item in payload["meta"]["multi_agent"]["review"]["history"]]
    assert "accept" not in decisions


def test_expert_limited_when_retrieval_insufficient_but_article_present() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=510,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed article with clear local facts but no externally verified context.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter({"background": ":[{", "interpretations": [], "consequences": [], "confidence": 0.0}),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert payload["meta"]["multi_agent"]["retrieval"]["status"] in {"failed", "insufficient"}
    assert payload["status"] == "limited"
    assert expert["status"] == "completed"
    assert expert["data_status"] == "limited"
    assert len(expert["background"]) > 0
    assert len(expert["interpretations"]) > 0
    assert len(expert["consequences"]) > 0


def test_expert_failed_when_output_malformed() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=511,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="",
            comments=[],
            thread_comments=[],
            views=55,
            effective_features={"force_retrieval_for_all_reports": False},
            retrieval_provider=MockRetrievalProvider(),
            llm_adapter=_ExpertContractAdapter({"background": ":[{", "interpretations": [], "consequences": [], "confidence": 0.0}),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert expert["malformed_output"] is True
    assert expert["status"] == "failed"


def test_expert_completed_limited_requires_non_empty_claims() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=512,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Article has enough local context for cautious fallback analysis.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [],
                    "interpretations": [],
                    "consequences": [],
                    "data_status": "limited",
                    "confidence": 0.0,
                }
            ),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert expert["status"] == "completed"
    assert len(expert["background"]) > 0
    assert len(expert["interpretations"]) > 0
    assert len(expert["consequences"]) > 0


def test_expert_confidence_capped_when_retrieval_failed() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=513,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed article but retrieval likely unavailable in this environment.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Fact", "type": "fact", "confidence": 0.95, "source": "article"}],
                    "interpretations": [{"text": "Interpretation", "type": "interpretation", "confidence": 0.95, "source": "article"}],
                    "consequences": [{"text": "Consequence", "type": "uncertain", "confidence": 0.95, "source": "article"}],
                    "data_status": "limited",
                    "confidence": 0.95,
                }
            ),
        )
    )
    expert = payload["meta"]["multi_agent"]["steps"]["expert"]
    assert payload["meta"]["multi_agent"]["retrieval"]["status"] in {"failed", "insufficient"}
    assert float(expert["confidence"]) <= 0.55


def test_synthesis_mentions_limited_external_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=514,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Policy-heavy post referencing external decisions without full detail.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
        )
    )
    summary = str(payload.get("summary") or "").lower()
    assert payload["meta"]["multi_agent"]["retrieval"]["status"] in {"failed", "insufficient"}
    assert "limited external context" in summary or "external context remains limited" in summary


def test_any_limited_step_makes_final_limited() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=515,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing for sufficient article.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Факт", "type": "fact", "confidence": 0.8, "source": "article"}],
                    "interpretations": [{"text": "Интерпретация", "type": "interpretation", "confidence": 0.7, "source": "article"}],
                    "consequences": [{"text": "Последствие", "type": "uncertain", "confidence": 0.7, "source": "article"}],
                    "data_status": "limited",
                    "confidence": 0.7,
                }
            ),
            retrieval_provider=MockRetrievalProvider(),
            effective_features={"force_retrieval_for_all_reports": False},
        )
    )
    assert payload["meta"]["multi_agent"]["steps"]["expert"]["data_status"] == "limited"
    assert payload["status"] == "limited"


def test_weak_signal_public_opinion_makes_final_limited(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.reporting_v2.post_pipeline._build_public_opinion_trace",
        lambda **kwargs: {
            "discussion_state": "weak_signal",
            "main_topics": [],
            "dominant_reactions": [],
            "data_status": "weak_signal",
            "confidence": 0.25,
            "signals": [{"name": "comments_count", "value": 2}],
        },
    )
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=516,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with enough detail for article sufficiency.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Факт", "type": "fact", "confidence": 0.8, "source": "article"}],
                    "interpretations": [{"text": "Интерпретация", "type": "interpretation", "confidence": 0.7, "source": "article"}],
                    "consequences": [{"text": "Последствие", "type": "uncertain", "confidence": 0.7, "source": "article"}],
                    "data_status": "sufficient",
                    "confidence": 0.75,
                }
            ),
            retrieval_provider=MockRetrievalProvider(),
            effective_features={"force_retrieval_for_all_reports": False},
        )
    )
    assert payload["meta"]["multi_agent"]["steps"]["public_opinion"]["data_status"] == "weak_signal"
    assert payload["status"] == "limited"


def test_insufficient_article_stops_pipeline() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=517,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="",
            comments=["c1", "c2", "c3", "c4", "c5", "c6"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter({"background": [], "interpretations": [], "consequences": [], "confidence": 0.0}),
            retrieval_provider=MockRetrievalProvider(),
            effective_features={"force_retrieval_for_all_reports": False},
        )
    )
    assert payload["meta"]["multi_agent"]["steps"]["context"]["sufficiency_components"]["article"] == "insufficient"
    assert payload["status"] == "insufficient_data"


def test_confidence_not_high_when_expert_limited() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=518,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing for sufficient article.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Факт", "type": "fact", "confidence": 0.8, "source": "article"}],
                    "interpretations": [{"text": "Интерпретация", "type": "interpretation", "confidence": 0.7, "source": "article"}],
                    "consequences": [{"text": "Последствие", "type": "uncertain", "confidence": 0.7, "source": "article"}],
                    "data_status": "limited",
                    "confidence": 0.72,
                }
            ),
            retrieval_provider=MockRetrievalProvider(),
            effective_features={"force_retrieval_for_all_reports": False},
        )
    )
    assert payload["meta"]["multi_agent"]["steps"]["expert"]["data_status"] == "limited"
    assert payload["confidence"]["overall"] != "high"


def test_limited_status_reflected_in_summary_text() -> None:
    payload = asyncio.run(
        generate_post_report_payload_v2(
            channel="@demo",
            post_id=519,
            published_at_iso="2026-04-15T10:00:00+00:00",
            post_text="Detailed post body with context and clear event framing for sufficient article.",
            comments=["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            thread_comments=[],
            views=55,
            llm_adapter=_ExpertContractAdapter(
                {
                    "background": [{"text": "Факт", "type": "fact", "confidence": 0.8, "source": "article"}],
                    "interpretations": [{"text": "Интерпретация", "type": "interpretation", "confidence": 0.7, "source": "article"}],
                    "consequences": [{"text": "Последствие", "type": "uncertain", "confidence": 0.7, "source": "article"}],
                    "data_status": "limited",
                    "confidence": 0.72,
                }
            ),
            retrieval_provider=MockRetrievalProvider(),
            effective_features={"force_retrieval_for_all_reports": False},
        )
    )
    summary = str(payload.get("summary") or "").lower()
    assert payload["status"] == "limited"
    assert "по имеющимся данным" in summary
    assert "реакция ограничена" in summary
    assert "требует дополнительной проверки" in summary
