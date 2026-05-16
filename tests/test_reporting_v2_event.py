from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services import reporting
from services.llm.openai_client import OpenAIChatCompletionTrace
from services.reporting_v2.event_pipeline import build_event_report_v2_impl, load_event_input_bundle


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, get_map=None, execute_results=None):
        self.get_map = get_map or {}
        self.execute_results = list(execute_results or [])
        self.added = []

    async def get(self, model, key):
        return self.get_map.get((model.__name__, key))

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)

    def add(self, value):
        value.id = len(self.added) + 1
        self.added.append(value)

    async def flush(self):
        return None


def test_event_input_bundle_aggregates_root_and_comments_from_all_event_posts() -> None:
    event = type("_Event", (), {"id": 10, "title": "Event 10"})()
    session = _FakeSession(
        get_map={("Event", 10): event},
        execute_results=[
            _FakeRowsResult(
                [
                    (101, "root", None, "Root text", 2),
                    (102, "member", None, "Member text", 1),
                ]
            ),
            _FakeRowsResult(
                [
                    (101, "root comment"),
                    (102, "member comment"),
                ]
            ),
        ],
    )

    bundle = asyncio.run(load_event_input_bundle(session, event_id=10))

    assert bundle is not None
    assert bundle["root_post_id"] == 101
    assert bundle["post_ids"] == [101, 102]
    assert bundle["comments_all_posts"] == ["root comment", "member comment"]


def test_build_event_report_v2_impl_emits_multi_agent_trace_with_event_input_mode(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        return {
            "event_id": event_id,
            "event_title": "Event",
            "posts": [
                {"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 2},
                {"post_id": 102, "event_role": "member", "text": "Member text", "comments_count": 2},
            ],
            "post_ids": [101, 102],
            "root_post_id": 101,
            "root_post_text": "Root text",
            "comments_all_posts": ["c1", "c2", "c3", "c4", "c5", "c6"],
            "comments_by_post": {101: ["c1", "c2"], 102: ["c3", "c4", "c5", "c6"]},
        }

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    monkeypatch.setattr(
        "services.reporting_v2.event_pipeline.OpenAIAdapterConfig.from_settings",
        lambda: SimpleNamespace(api_key=None),
    )

    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=77))

    assert payload["status"] == "limited"
    assert payload["meta"]["multi_agent"]["version"] == "v1"
    assert payload["meta"]["multi_agent"]["steps"]["context"]["root_post_id"] == 101
    assert payload["meta"]["multi_agent"]["steps"]["context"]["comments_total"] == 6
    assert payload["meta"]["multi_agent"]["steps"]["context"]["sufficiency_components"]["comment"] == "sufficient"
    assert payload["meta"]["multi_agent"]["retrieval"]["required"] is True
    assert payload["meta"]["multi_agent"]["retrieval"]["status"] == "failed"
    assert payload["status"] != "ready"
    assert payload["meta"]["multi_agent"]["review"]["history"][-1]["decision"] == "accept_with_limitations"
    claims = payload["meta"]["multi_agent"]["epistemic_claims"]
    assert isinstance(claims, list)
    assert all({"text", "type", "confidence", "source"} <= set(item.keys()) for item in claims)
    assert all(item["type"] != "external" for item in claims)


def test_build_event_report_draft_uses_reporting_v2_event_impl(monkeypatch) -> None:
    session = _FakeSession(execute_results=[type("_Scalar", (), {"scalar_one_or_none": lambda self: None})()])

    async def _fake_build_event_report_v2_impl(*, session, event_id):
        del session
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
            "type": "event_report_v2",
            "status": "ready",
            "event_id": event_id,
            "event_title": "Event",
            "posts_count": 1,
            "source_post_reports": [101],
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "cross_post_topics": [],
            "post_dynamics": [],
            "event_trends": [],
            "risks": [],
            "anomalies": [],
            "summary": "ready",
            "confidence": {"overall": "high", "reason": "ok"},
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

    monkeypatch.setattr(reporting, "build_event_report_v2_impl", _fake_build_event_report_v2_impl)

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=77))

    assert result == {"status": "ready", "event_id": 77, "report_id": 1}
    assert session.added[0].report_json["meta"]["multi_agent"]["status"] == "ready"


def test_build_event_report_v2_reviewer_loop_caps_at_two_on_synthesis_failure(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [
                {
                    "post_id": 101,
                    "event_role": "root",
                    "text": (
                        "This report describes a local community initiative with operational updates, "
                        "timeline milestones, stakeholders, and execution notes. The post includes enough "
                        "context to understand causes, immediate impact, and expected follow-up actions "
                        "without requiring outside references or institutional background."
                    ),
                    "comments_count": 6,
                }
            ],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": (
                "This report describes a local community initiative with operational updates, "
                "timeline milestones, stakeholders, and execution notes. The post includes enough "
                "context to understand causes, immediate impact, and expected follow-up actions "
                "without requiring outside references or institutional background."
            ),
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _FailingAdapter:
        async def create_chat_completion(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)

    payload = asyncio.run(
        build_event_report_v2_impl(
            session=object(),
            event_id=88,
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


def test_build_event_report_v2_marks_provider_provenance_for_all_six_steps(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        del session
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [{"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 6}],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": "Root text with enough detail for event summary synthesis.",
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _TraceAdapter:
        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            return OpenAIChatCompletionTrace(
                content="{}",
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=12,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=89, llm_adapter=_TraceAdapter()))

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
        assert provenance["latency_ms"] == 12
        assert provenance["input_ref"] == f"inline://{step_name}/input"
        assert isinstance(provenance["input_hash"], str) and len(provenance["input_hash"]) == 64
        assert provenance["output_ref"] == f"inline://{step_name}/output"
        assert isinstance(provenance["output_hash"], str) and len(provenance["output_hash"]) == 64
        assert provenance["fallback_used"] is False
        assert provenance["fallback_reason"] is None
        assert provenance["attempt_index"] == 0
        assert provenance["status"] == "completed"


def test_build_event_report_v2_keeps_summary_in_synthesis_step_as_source_of_truth(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        del session
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [{"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 6}],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": "Root text with enough detail for event summary synthesis.",
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _SummaryAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            self.calls += 1
            if self.calls == 5:
                content = '{"summary":"EVENT_SYNTHESIS_TEXT","confidence_reason":"llm_event"}'
            else:
                content = "{}"
            return OpenAIChatCompletionTrace(
                content=content,
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=12,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=90, llm_adapter=_SummaryAdapter()))

    synthesis = payload["meta"]["multi_agent"]["steps"]["synthesis"]
    assert payload["summary"] == "EVENT_SYNTHESIS_TEXT"
    assert synthesis["report_text"] == "EVENT_SYNTHESIS_TEXT"


def test_build_event_report_v2_normalizes_malformed_expert_output(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        del session
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [{"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 6}],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": "Root text with enough detail for event summary synthesis.",
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _MalformedExpertAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            self.calls += 1
            if self.calls == 3:
                content = (
                    '{"background":[{"":"In 2025 there were 107800 microloan contracts.","type":"fact","source":"derived","confidence":0.95}],'
                    '"interpretations":[{"text":"Loan growth can reflect financial pressure.","type":"interpretation","source":"comments","confidence":0.7}],'
                    '"consequences":[{"text":"Debt stress may increase.","type":"interpretation","source":"derived","confidence":0.55}],'
                    '"confidence":0.6,"data_status":"limited"}'
                )
            elif self.calls == 5:
                content = '{"summary":"EVENT_SYNTHESIS_TEXT","confidence_reason":"llm_event"}'
            else:
                content = "{}"
            return OpenAIChatCompletionTrace(
                content=content,
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=12,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=92, llm_adapter=_MalformedExpertAdapter()))

    expert = payload["meta"]["multi_agent"]["steps"]["expert"]["llm_expert"]
    assert expert["background"][0]["text"] == "In 2025 there were 107800 microloan contracts."
    assert expert["background"][0]["source"] == "article"
    assert expert["consequences"][0]["source"] == "article"
    assert "llm_expert_raw" in payload["meta"]["multi_agent"]["steps"]["expert"]


def test_build_event_report_v2_normalizes_cross_post_topics(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        del session
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [{"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 6}],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": "Root text with enough detail for event summary synthesis.",
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _TopicsAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            self.calls += 1
            if self.calls == 5:
                content = (
                    '{"summary":"EVENT_SYNTHESIS_TEXT",'
                    '"topics":["budget",{"name":"wages","share":"0.4"},{"text":"loans"},{"name":"budget"},{"name":""},123]}'
                )
            else:
                content = "{}"
            return OpenAIChatCompletionTrace(
                content=content,
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=12,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=93, llm_adapter=_TopicsAdapter()))

    assert payload["cross_post_topics"] == [
        {"name": "budget"},
        {"name": "wages", "share": 0.4},
        {"name": "loans"},
    ]


def test_event_reviewer_rerun_branch_triggers_real_rerun(monkeypatch) -> None:
    async def _fake_load_bundle(session, *, event_id):
        del session
        return {
            "event_id": event_id,
            "event_title": "Local Event",
            "posts": [{"post_id": 101, "event_role": "root", "text": "Root text", "comments_count": 6}],
            "post_ids": [101],
            "root_post_id": 101,
            "root_post_text": "Root text with enough detail for event summary synthesis.",
            "comments_all_posts": [f"comment {idx}" for idx in range(1, 8)],
            "comments_by_post": {101: [f"comment {idx}" for idx in range(1, 8)]},
        }

    class _ReviewerRerunAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def create_chat_completion_with_trace(self, **kwargs):
            del kwargs
            self.calls += 1
            if self.calls in {6, 8}:
                content = '{"decision":"rerun_branch","rerun_target":"expert","issues":[{"field":"expert.background","problem":"empty"}]}'
            elif self.calls in {5, 7, 9}:
                content = '{"summary":"EVENT_SYNTHESIS_TEXT","confidence_reason":"llm_event"}'
            else:
                content = "{}"
            return OpenAIChatCompletionTrace(
                content=content,
                provider="openrouter",
                model="qwen/qwen3-coder:free",
                latency_ms=12,
                fallback_used=False,
                fallback_reason=None,
                executed=True,
                success=True,
                attempt_index=0,
            )

    monkeypatch.setattr("services.reporting_v2.event_pipeline.load_event_input_bundle", _fake_load_bundle)
    adapter = _ReviewerRerunAdapter()
    payload = asyncio.run(build_event_report_v2_impl(session=object(), event_id=94, llm_adapter=adapter))

    assert adapter.calls > 6
    assert payload["status"] == "limited"
    assert payload["meta"]["multi_agent"]["steps"]["reviewer"]["decision"] != "accept"


def test_build_event_report_draft_persists_canonicalized_status(monkeypatch) -> None:
    session = _FakeSession(execute_results=[type("_Scalar", (), {"scalar_one_or_none": lambda self: None})()])

    async def _fake_build_event_report_v2_impl(*, session, event_id):
        del session
        return {
            "type": "event_report_v2",
            "status": "ready",
            "event_id": event_id,
            "event_title": "Event",
            "posts_count": 1,
            "source_post_reports": [101],
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "cross_post_topics": [],
            "post_dynamics": [],
            "event_trends": [],
            "risks": [],
            "anomalies": [],
            "summary": "ready",
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        name: {"status": "completed", "run_count": 1}
                        for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]
                    },
                    "retrieval": {"required": False, "used": False, "status": "none", "sources": []},
                    "review": {"iterations": 0, "history": []},
                }
            },
        }

    monkeypatch.setattr(reporting, "build_event_report_v2_impl", _fake_build_event_report_v2_impl)
    result = asyncio.run(reporting.build_event_report_draft(session, event_id=91))

    assert result["status"] == "limited"
    assert session.added[0].report_json["status"] == "limited"
