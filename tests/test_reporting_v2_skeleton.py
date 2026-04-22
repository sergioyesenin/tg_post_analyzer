from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from services import reporting
from schemas.report import PostReportPayload
from services.reporting_v2.mapper import (
    map_state_to_internal_multi_agent_trace,
    map_state_to_public_model_info,
    map_state_to_public_post_payload,
)
from services.reporting_v2.orchestrator import (
    PIPELINE_STAGE_ORDER,
    _extract_topics,
    run_context_stage,
    run_post_orchestrator_v2,
    run_public_opinion_stage,
    run_reviewer_loop,
    run_synthesis_stage,
)
from services.reporting_v2.state import (
    ModelInfoPublic,
    PipelineState,
    init_pipeline_state,
)


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


def test_init_pipeline_state_builds_safe_defaults() -> None:
    state = init_pipeline_state(
        post_id=101,
        published_at_iso="2026-04-17T10:00:00+00:00",
        post_text="Example post body",
        comments=["one", "two", "three"],
    )

    assert isinstance(state, PipelineState)
    assert state.post_id == 101
    assert state.status == "insufficient_data"
    assert state.routing.category == "general"
    assert state.routing.retrieval_hints == {}
    assert state.retrieval.required is False
    assert state.retrieval.used is False
    assert state.retrieval.status == "none"
    assert state.retrieval.decision_source == "policy"
    assert state.model_info is None
    assert state.internal_trace == {}


def test_model_info_public_is_optional_and_strict() -> None:
    info = ModelInfoPublic(provider="openai", model="gpt-4o-mini", latency_ms=120, fallback_used=False)
    assert info.provider == "openai"
    assert info.model == "gpt-4o-mini"
    assert info.latency_ms == 120
    assert info.fallback_used is False


def test_init_pipeline_state_filters_non_string_comments() -> None:
    state = init_pipeline_state(
        post_id=7,
        published_at_iso="2026-04-17T11:00:00+00:00",
        post_text="Body",
        comments=["ok", "", 123, None],  # type: ignore[list-item]
    )
    assert state.comments == ["ok", ""]


def test_run_post_orchestrator_v2_runs_stages_in_order_and_avoids_default_insufficient_data_on_material() -> None:
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=11,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text="Post body",
            comments=["comment 1", "comment 2"],
            thread_comments=[],
            views=15,
            rerun_stage=None,
        )
    )

    assert isinstance(state, PipelineState)
    assert state.internal_trace["pipeline_sequence"] == list(PIPELINE_STAGE_ORDER)
    stages = state.internal_trace.get("stages") or {}
    assert set(stages.keys()) == set(PIPELINE_STAGE_ORDER)
    assert all((stages[name] or {}).get("status") == "completed" for name in PIPELINE_STAGE_ORDER)
    assert state.status in {"ready", "limited"}
    assert state.routing.reasoning == "deterministic_orchestrator_v1"
    assert state.synthesis.summary.strip()
    assert state.reviewer.decision in {"accept", "accept_with_limitations"}
    assert state.retrieval.status == "none"
    assert state.model_info is None


def test_reviewer_loop_uses_direct_conservative_decision_for_weak_synthesis() -> None:
    state = init_pipeline_state(
        post_id=12,
        published_at_iso="2026-04-17T12:00:00+00:00",
        post_text="Post body",
        comments=["This is a substantive comment with enough detail for bounded reviewer behavior."],
    )
    state.status = "limited"
    updated = run_reviewer_loop(state, max_iterations=99)

    assert updated.reviewer.iterations >= 1
    assert len(updated.reviewer.history) >= 1
    assert updated.reviewer.history[0]["decision"] in {"rerun_branch", "revise"}
    assert updated.reviewer.history[0]["target"] == "synthesis"
    assert updated.reviewer.decision in {"accept_with_limitations", "insufficient_data"}
    assert updated.internal_trace["stages"]["reviewer"]["status"] == "completed"


def test_reviewer_loop_accepts_when_synthesis_summary_exists() -> None:
    state = init_pipeline_state(
        post_id=13,
        published_at_iso="2026-04-17T12:00:00+00:00",
        post_text="Post body",
        comments=["comment"],
    )
    state.status = "ready"
    state.synthesis.summary = (
        "Synthesis output is present and contains enough structured detail about the discussion, "
        "key disagreement points, and stable recurring signals from comments."
    )
    state.synthesis.report_text = (
        "The event is clearly stated. "
        "The context is sufficiently described. "
        "Public reaction appears stable and coherent. "
        "Interpretation links reactions to core dynamics. "
        "Consequences are outlined with bounded confidence."
    )
    state.synthesis.components = {
        "event": True,
        "context": True,
        "reaction": True,
        "interpretation": True,
        "consequences": True,
    }
    state.synthesis.sentence_count = 5
    state.synthesis.quality = "ok"
    updated = run_reviewer_loop(state, max_iterations=2)

    assert updated.reviewer.iterations == 1
    assert len(updated.reviewer.history) == 1
    assert updated.reviewer.history[0]["decision"] == "accept"
    assert updated.reviewer.history[0]["target"] is None
    assert updated.reviewer.history[0]["reason"] == "spec_checks_passed"
    assert updated.reviewer.decision == "accept"


def test_reviewer_loop_stays_bounded_even_with_zero_iterations() -> None:
    state = init_pipeline_state(
        post_id=14,
        published_at_iso="2026-04-17T12:00:00+00:00",
        post_text="Post body",
        comments=[],
    )
    updated = run_reviewer_loop(state, max_iterations=0)

    assert updated.reviewer.iterations == 0
    assert updated.reviewer.history == []
    assert updated.reviewer.decision == "insufficient_data"


def test_run_post_orchestrator_v2_keeps_insufficient_data_for_empty_inputs() -> None:
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=15,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text="",
            comments=["", "   "],
            thread_comments=[],
            views=None,
            rerun_stage=None,
        )
    )

    assert state.status == "insufficient_data"
    assert state.context.article_sufficiency == "insufficient"
    assert state.context.comment_sufficiency == "insufficient"
    assert state.reviewer.decision == "insufficient_data"


def test_run_post_orchestrator_v2_marks_limited_for_post_without_comments() -> None:
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=17,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text="This is a meaningful post body with enough content to pass article sufficiency thresholds.",
            comments=[],
            thread_comments=[],
            views=100,
            rerun_stage=None,
        )
    )

    assert state.context.article_sufficiency in {"limited", "sufficient"}
    assert state.context.comment_sufficiency == "insufficient"
    assert state.status == "limited"
    assert state.reviewer.decision == "accept_with_limitations"


def test_run_post_orchestrator_v2_marks_limited_for_short_post_and_few_comments() -> None:
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=18,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text="Short post text.",
            comments=["Good point, but not enough context yet.", "Need more details before strong conclusions."],
            thread_comments=[],
            views=50,
            rerun_stage=None,
        )
    )

    assert state.status == "limited"
    assert state.reviewer.decision in {"accept_with_limitations", "accept"}


def test_run_post_orchestrator_v2_marks_ready_for_substantive_post_and_comment_volume() -> None:
    comments = [f"This is a substantive comment with concrete argument number {idx} and enough detail." for idx in range(1, 13)]
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=19,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text=(
                "This post describes a complex city safety incident, outlines timeline details, and provides context "
                "for how participants interpreted responsibility and policy implications."
            ),
            comments=comments,
            thread_comments=[],
            views=500,
            rerun_stage=None,
        )
    )

    assert state.context.article_sufficiency == "sufficient"
    assert state.context.comment_sufficiency == "sufficient"
    assert state.status == "ready"
    assert state.reviewer.decision == "accept"


def test_run_post_orchestrator_v2_does_not_mark_ready_for_many_whitespace_comments() -> None:
    comments = ["   ", "\n", "\t", "  ", ""] * 30
    state = asyncio.run(
        run_post_orchestrator_v2(
            post_id=20,
            published_at_iso="2026-04-17T12:00:00+00:00",
            post_text="A sufficiently long post text exists, but comments are effectively empty noise.",
            comments=comments,
            thread_comments=[],
            views=200,
            rerun_stage=None,
        )
    )

    assert state.context.comment_sufficiency == "insufficient"
    assert state.status == "limited"
    assert state.status != "ready"


def test_reviewer_does_not_upgrade_weak_material_to_ready() -> None:
    state = init_pipeline_state(
        post_id=21,
        published_at_iso="2026-04-17T12:00:00+00:00",
        post_text="Short.",
        comments=["one brief comment"],
    )
    state.status = "limited"
    state.synthesis.summary = "Brief synthesis."
    updated = run_reviewer_loop(state, max_iterations=2)

    assert updated.reviewer.decision in {"accept_with_limitations", "insufficient_data"}
    assert all(item["decision"] != "accept" for item in updated.reviewer.history)


def test_run_post_orchestrator_v2_is_deterministic_for_same_input() -> None:
    payload_kwargs = {
        "post_id": 22,
        "published_at_iso": "2026-04-17T12:00:00+00:00",
        "post_text": (
            "A detailed post about road safety policy, liability interpretation, and repeated incidents "
            "in city transport discussions."
        ),
        "comments": [
            "The driver should slow down before crossings and anticipate fast scooter movement.",
            "Scooter users should dismount and follow crossing rules to reduce risk.",
            "Both sides carry responsibility, but enforcement is inconsistent across cases.",
            "Policy updates are needed because conflict repeats in similar incidents.",
            "Legal accountability depends on right-of-way and observed maneuver timing.",
            "Current rules are known but compliance remains weak in crowded traffic zones.",
            "Public reactions show disagreement about proportional liability and fines.",
            "Infrastructure and education could reduce repeated conflict patterns.",
        ],
        "thread_comments": [],
        "views": 321,
        "rerun_stage": None,
    }
    state_a = asyncio.run(run_post_orchestrator_v2(**payload_kwargs))
    state_b = asyncio.run(run_post_orchestrator_v2(**payload_kwargs))

    assert state_a.status == state_b.status
    assert state_a.synthesis.summary == state_b.synthesis.summary
    assert state_a.public_opinion == state_b.public_opinion


def test_run_synthesis_stage_produces_non_empty_summary_when_material_present() -> None:
    state = init_pipeline_state(
        post_id=16,
        published_at_iso="2026-04-17T12:00:00+00:00",
        post_text="A detailed post about transport safety and road behavior in city traffic.",
        comments=["Drivers should slow down before crossings.", "Scooters also must follow road rules."],
    )
    state = run_context_stage(state)
    state = run_public_opinion_stage(state)
    updated = asyncio.run(run_synthesis_stage(state))

    assert updated.synthesis.summary.strip()
    assert updated.synthesis.confidence_reason in {"deterministic_orchestrator_v1", "limited_evidence"}


def test_extract_topics_filters_high_frequency_function_words_in_ru_comments() -> None:
    topics = _extract_topics(
        "Шутка про ананас и донер в рекламе.",
        [
            "Зачем вообще есть это, зачем такая шутка.",
            "Есть спор, но ананас и донер обсуждают чаще.",
            "Шутка про ананас стала поводом для спора.",
        ],
        limit=5,
    )

    assert "зачем" not in topics
    assert "есть" not in topics
    assert any(topic in topics for topic in {"шутка", "ананас", "донер"})


def test_mapper_builds_internal_trace_without_public_model_info_mix() -> None:
    state = init_pipeline_state(
        post_id=23,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["a"],
    )
    trace = map_state_to_internal_multi_agent_trace(state)

    assert trace["version"] == "v1"
    assert trace["status"] == "insufficient_data"
    assert "model_info" not in trace
    assert set(trace.keys()) >= {
        "epistemic_claims",
        "steps",
        "retrieval",
        "review",
    }
    assert set(trace["steps"].keys()) == {"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"}


def test_mapper_public_model_info_is_optional() -> None:
    state = init_pipeline_state(
        post_id=24,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["a"],
    )
    assert map_state_to_public_model_info(state) is None

    state.model_info = ModelInfoPublic(
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=220,
        fallback_used=True,
    )
    assert map_state_to_public_model_info(state) == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "latency_ms": 220,
        "fallback_used": True,
    }


def test_mapper_public_payload_keeps_internal_and_public_fields_separate() -> None:
    state = init_pipeline_state(
        post_id=25,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["a", "b"],
    )
    state.status = "unknown-status"
    state.model_info = ModelInfoPublic(
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=180,
        fallback_used=False,
    )

    payload = map_state_to_public_post_payload(
        state=state,
        post_id=25,
        published_at_iso="2026-04-17T12:30:00+00:00",
    )

    assert payload["status"] == "limited"
    assert payload["model_info"] == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "latency_ms": 180,
        "fallback_used": False,
    }
    assert "multi_agent" in payload["meta"]
    assert "model_info" not in payload["meta"]
    assert "shadow_compare" not in payload["meta"]


@pytest.mark.parametrize(
    ("input_status", "expected_status"),
    [
        ("ready", "ready"),
        ("limited", "limited"),
        ("insufficient_data", "insufficient_data"),
        ("failed", "failed"),
        ("", "limited"),
        ("unknown-status", "limited"),
    ],
)
def test_mapper_status_normalization_for_public_payload(input_status: str, expected_status: str) -> None:
    state = init_pipeline_state(
        post_id=250,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["a", "b"],
    )
    state.status = input_status

    payload = map_state_to_public_post_payload(
        state=state,
        post_id=250,
        published_at_iso="2026-04-17T12:30:00+00:00",
    )
    assert payload["status"] == expected_status


@pytest.mark.parametrize(
    ("input_status", "expected_status"),
    [
        ("ready", "ready"),
        ("limited", "limited"),
        ("insufficient_data", "insufficient_data"),
        ("failed", "failed"),
        ("", "limited"),
        ("not-a-status", "limited"),
    ],
)
def test_mapper_status_normalization_for_internal_trace(input_status: str, expected_status: str) -> None:
    state = init_pipeline_state(
        post_id=251,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["a"],
    )
    state.status = input_status

    trace = map_state_to_internal_multi_agent_trace(state)
    assert trace["status"] == expected_status


def test_mapper_payload_is_compatible_with_existing_schema_when_model_info_absent() -> None:
    state = init_pipeline_state(
        post_id=26,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=[],
    )
    payload = map_state_to_public_post_payload(
        state=state,
        post_id=26,
        published_at_iso="2026-04-17T12:30:00+00:00",
    )
    payload_without_model_info = {key: value for key, value in payload.items() if key != "model_info"}
    validated = PostReportPayload.model_validate(payload_without_model_info)
    assert validated.post_id == 26


def test_mapper_payload_is_compatible_with_existing_schema_when_model_info_present() -> None:
    state = init_pipeline_state(
        post_id=27,
        published_at_iso="2026-04-17T12:30:00+00:00",
        post_text="Body",
        comments=["one"],
    )
    state.model_info = ModelInfoPublic(
        provider="openai",
        model="gpt-4o-mini",
        latency_ms=95,
        fallback_used=False,
    )

    payload = map_state_to_public_post_payload(
        state=state,
        post_id=27,
        published_at_iso="2026-04-17T12:30:00+00:00",
    )
    validated = PostReportPayload.model_validate(payload)
    assert validated.post_id == 27
    assert validated.model_info is not None
    assert validated.model_info.provider == "openai"
    assert validated.model_info.model == "gpt-4o-mini"
    assert validated.model_info.latency_ms == 95
    assert validated.model_info.fallback_used is False


def test_should_use_multi_agent_v2_is_default_off() -> None:
    assert reporting.should_use_multi_agent_v2(post_id=101, features=None) is False
    assert reporting.should_use_multi_agent_v2(
        post_id=101,
        features={
            "multi_agent_mode_enabled": False,
            "multi_agent_rollout_percent": 100,
        },
    ) is False
    assert reporting.should_use_multi_agent_v2(
        post_id=101,
        features={
            "multi_agent_mode_enabled": True,
            "multi_agent_rollout_percent": 0,
        },
    ) is False


def test_should_use_multi_agent_v2_can_enable_subset_and_is_deterministic() -> None:
    features = {
        "multi_agent_mode_enabled": True,
        "multi_agent_rollout_percent": 10,
    }
    # 5 % 100 = 5  -> selected when rollout=10
    assert reporting.should_use_multi_agent_v2(post_id=5, features=features) is True
    # 42 % 100 = 42 -> not selected when rollout=10
    assert reporting.should_use_multi_agent_v2(post_id=42, features=features) is False
    # Deterministic for same post_id/features
    assert reporting.should_use_multi_agent_v2(post_id=42, features=features) is False


def test_build_post_report_v2_payload_from_orchestrator_is_isolated_helper(monkeypatch) -> None:
    calls = {"orchestrator": 0, "mapper": 0}

    async def _fake_orchestrator(**kwargs):
        assert kwargs["post_id"] == 501
        calls["orchestrator"] += 1
        return init_pipeline_state(
            post_id=501,
            published_at_iso="2026-04-17T12:30:00+00:00",
            post_text="Body",
            comments=["c1"],
        )

    def _fake_mapper(*, state, post_id, published_at_iso):
        assert state.post_id == 501
        assert post_id == 501
        assert published_at_iso == "2026-04-17T12:30:00+00:00"
        calls["mapper"] += 1
        return {
            "type": "post_report_v2",
            "status": "limited",
            "post_id": 501,
            "published_at": "2026-04-17T12:30:00+00:00",
            "title": "Post 501 discussion snapshot",
            "summary": "Generated by mapper mock.",
        }

    monkeypatch.setattr(reporting, "run_post_orchestrator_v2", _fake_orchestrator)
    monkeypatch.setattr(reporting, "map_state_to_public_post_payload", _fake_mapper)

    payload = asyncio.run(
        reporting.build_post_report_v2_payload_from_orchestrator(
            post_id=501,
            published_at_iso="2026-04-17T12:30:00+00:00",
            post_text="Body",
            comments=["c1"],
            thread_comments=[],
            views=9,
            rerun_stage=None,
        )
    )

    assert payload["type"] == "post_report_v2"
    assert payload["status"] == "limited"
    assert payload["post_id"] == 501
    assert payload["title"] == "Post 501 discussion snapshot"
    assert calls == {"orchestrator": 1, "mapper": 1}


def test_build_post_report_v2_payload_from_orchestrator_real_call_returns_schema_compatible_payload() -> None:
    payload = asyncio.run(
        reporting.build_post_report_v2_payload_from_orchestrator(
            post_id=601,
            published_at_iso="2026-04-17T15:30:00+00:00",
            post_text="Minimal post body",
            comments=["comment a", "comment b"],
            thread_comments=[],
            views=20,
            rerun_stage=None,
        )
    )

    validated = PostReportPayload.model_validate(payload)
    assert validated.type == "post_report_v2"
    assert validated.post_id == 601
    assert validated.status in {"ready", "limited", "insufficient_data", "failed"}


def test_build_post_report_uses_legacy_path_when_rollout_disabled(monkeypatch) -> None:
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
                    "steps": {name: {"status": "completed", "run_count": 1} for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]},
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
        return SimpleNamespace(id=95)

    async def _unexpected_orchestrator_helper(**kwargs):
        raise AssertionError(f"orchestrator helper must stay unused when rollout is disabled: {kwargs}")

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _fake_generate_v2)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(
            0,
            result={
                "multi_agent_mode_enabled": False,
                "multi_agent_rollout_percent": 100,
            },
        ),
    )
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _unexpected_orchestrator_helper)

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result["status"] == "ready"
    assert result["report_id"] == 95


def test_build_post_report_uses_v2_helper_when_rollout_gate_allows(monkeypatch) -> None:
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

    async def _unexpected_generate_v2(**kwargs):
        raise AssertionError(f"legacy generator must be bypassed when rollout allows v2: {kwargs}")

    async def _fake_orchestrator_helper(**kwargs):
        assert kwargs["post_id"] == 11
        return {
            "type": "post_report_v2",
            "status": "limited",
            "post_id": 11,
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "v2 helper title",
            "summary": "v2 helper summary",
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
            "confidence": {"overall": "low", "reason": "v2 helper"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "limited",
                    "public_opinion": {
                        "discussion_state": "active",
                        "signals": [
                            {"name": "comments_count", "value": 2},
                            {"name": "top_topics", "value": ["topic-alpha", "topic-beta"]},
                        ],
                    },
                    "routing": {"reasoning": "deterministic_orchestrator_v1"},
                    "reviewer": {"decision": "accept_with_limitations", "iterations": 1, "history": []},
                    "synthesis": {
                        "summary": "Deterministic synthesis summary based on input signals.",
                        "confidence_reason": "deterministic_orchestrator_v1",
                    },
                }
            },
        }

    async def _fake_upsert_report(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        assert status == "limited"
        assert report_json["summary"]
        assert [topic["name"] for topic in report_json["topics"]] == ["topic-alpha", "topic-beta"]
        assert report_json["meta"]["multi_agent"]["review"]["iterations"] == 1
        assert "reviewer" not in report_json["meta"]["multi_agent"]
        return SimpleNamespace(id=96)

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _unexpected_generate_v2)
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _fake_orchestrator_helper)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(
            0,
            result={
                "multi_agent_mode_enabled": True,
                "multi_agent_rollout_percent": 100,
            },
        ),
    )
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result["status"] == "limited"
    assert result["report_id"] == 96
    assert "shadow_compare" not in result


def test_build_post_report_falls_back_to_legacy_when_v2_payload_is_skeleton_like(monkeypatch) -> None:
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

    calls = {"legacy": 0, "v2": 0}

    async def _legacy_generator(**kwargs):
        calls["legacy"] += 1
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": kwargs["post_id"],
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "legacy title",
            "summary": "legacy summary",
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
            "confidence": {"overall": "medium", "reason": "legacy"},
            "meta": {"multi_agent": {"version": "v1", "status": "ready"}},
        }

    async def _v2_helper_skeleton_like(**kwargs):
        calls["v2"] += 1
        return {
            "type": "post_report_v2",
            "status": "insufficient_data",
            "post_id": kwargs["post_id"],
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "v2 title",
            "summary": "v2 summary",
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
            "confidence": {"overall": "low", "reason": "orchestrator"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "insufficient_data",
                    "routing": {"reasoning": "orchestrator_skeleton"},
                    "synthesis": {"summary": "", "confidence_reason": "orchestrator_skeleton"},
                }
            },
        }

    async def _fake_upsert(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        assert status == "ready"
        assert content
        assert report_json is not None
        assert report_json["meta"]["multi_agent"]["status"] == "ready"
        return SimpleNamespace(id=201)

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _legacy_generator)
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _v2_helper_skeleton_like)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert)
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(
            0,
            result={
                "multi_agent_mode_enabled": True,
                "multi_agent_rollout_percent": 100,
            },
        ),
    )
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result["status"] == "ready"
    assert result["report_id"] == 201
    assert "technical_error" not in result
    assert calls == {"legacy": 1, "v2": 1}


def test_build_post_report_falls_back_to_legacy_when_v2_persist_path_errors(monkeypatch) -> None:
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

    calls = {"legacy": 0, "v2": 0}

    async def _legacy_generator(**kwargs):
        calls["legacy"] += 1
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": kwargs["post_id"],
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "legacy title",
            "summary": "legacy summary",
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
            "confidence": {"overall": "medium", "reason": "legacy"},
            "meta": {"multi_agent": {"version": "v1", "status": "ready"}},
        }

    async def _broken_v2_helper(**_kwargs):
        calls["v2"] += 1
        raise RuntimeError("v2 exploded")

    async def _fake_upsert(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        assert status == "ready"
        assert content
        assert report_json is not None
        assert report_json["meta"]["multi_agent"]["status"] == "ready"
        return SimpleNamespace(id=199)

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _legacy_generator)
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _broken_v2_helper)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert)
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(
            0,
            result={
                "multi_agent_mode_enabled": True,
                "multi_agent_rollout_percent": 100,
            },
        ),
    )
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result["status"] == "ready"
    assert result["report_id"] == 199
    assert "technical_error" not in result
    assert "shadow_compare" not in result
    assert calls == {"legacy": 1, "v2": 1}


@pytest.mark.parametrize(("path_name", "features"), [
    ("legacy", {"multi_agent_mode_enabled": False, "multi_agent_rollout_percent": 100}),
    ("v2", {"multi_agent_mode_enabled": True, "multi_agent_rollout_percent": 100}),
])
def test_build_post_report_uses_shared_downstream_flow_after_payload_selection(monkeypatch, path_name: str, features: dict) -> None:
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

    call_counters = {"legacy": 0, "v2": 0, "map": 0, "enrich": 0, "render": 0}

    async def _legacy_generator(**kwargs):
        call_counters["legacy"] += 1
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": kwargs["post_id"],
            "title": "legacy title",
            "summary": "legacy summary",
        }

    async def _v2_helper(**kwargs):
        call_counters["v2"] += 1
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": kwargs["post_id"],
            "title": "v2 title",
            "summary": "v2 summary",
        }

    def _map_payload(payload):
        call_counters["map"] += 1
        mapped = dict(payload or {})
        mapped["mapped_marker"] = True
        mapped.setdefault("status", "ready")
        mapped.setdefault("summary", "mapped")
        mapped.setdefault("title", "mapped")
        return mapped

    def _enrich_payload(*, payload, post, comment_rows):
        call_counters["enrich"] += 1
        enriched = dict(payload or {})
        enriched["enriched_marker"] = True
        assert post.id == 11
        assert len(comment_rows) == 2
        return enriched

    def _render_payload(payload):
        call_counters["render"] += 1
        assert payload["mapped_marker"] is True
        assert payload["enriched_marker"] is True
        return "rendered-content"

    async def _fake_upsert(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        assert status == "ready"
        assert content == "rendered-content"
        assert report_json["mapped_marker"] is True
        assert report_json["enriched_marker"] is True
        assert report_json["meta"]["input_signature"]
        assert report_json["meta"]["generated_at"]
        return SimpleNamespace(id=197)

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _legacy_generator)
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _v2_helper)
    monkeypatch.setattr(reporting, "map_internal_post_report_to_public_payload", _map_payload)
    monkeypatch.setattr(reporting, "_enrich_post_report_payload", _enrich_payload)
    monkeypatch.setattr(reporting, "_render_post_report_text", _render_payload)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert)
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(0, result=features),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result == {"status": "ready", "post_id": 11, "report_id": 197}
    assert call_counters["map"] == 1
    assert call_counters["enrich"] == 1
    assert call_counters["render"] == 1
    if path_name == "legacy":
        assert call_counters["legacy"] == 1
        assert call_counters["v2"] == 0
    else:
        assert call_counters["legacy"] == 0
        assert call_counters["v2"] == 1


def test_build_post_report_shadow_mode_keeps_legacy_persisted_and_emits_job_result_compare(monkeypatch) -> None:
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

    async def _legacy_generator(**kwargs):
        return {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": kwargs["post_id"],
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "legacy title",
            "summary": "legacy summary",
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
            "confidence": {"overall": "medium", "reason": "legacy"},
            "meta": {"multi_agent": {"version": "v1", "status": "ready"}},
        }

    async def _v2_helper(**kwargs):
        return {
            "type": "post_report_v2",
            "status": "limited",
            "post_id": kwargs["post_id"],
            "published_at": "2026-03-11T12:00:00+00:00",
            "title": "v2 title",
            "summary": "v2 summary",
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
            "confidence": {"overall": "low", "reason": "v2"},
            "meta": {"multi_agent": {"version": "v1", "status": "limited"}},
        }

    async def _fake_upsert(_session, *, post_id, status, content, report_json=None):
        assert post_id == 11
        # Legacy payload remains the persisted source of truth in shadow mode.
        assert status == "ready"
        assert report_json is not None
        assert "shadow_compare" not in (report_json.get("meta") or {})
        assert report_json.get("summary")
        return SimpleNamespace(id=198)

    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _legacy_generator)
    monkeypatch.setattr(reporting, "build_post_report_v2_payload_from_orchestrator", _v2_helper)
    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert)
    monkeypatch.setattr(
        reporting,
        "_load_reporting_feature_flags",
        lambda _session: asyncio.sleep(
            0,
            result={
                "multi_agent_mode_enabled": True,
                "multi_agent_rollout_percent": 100,
                "multi_agent_shadow_mode_enabled": True,
            },
        ),
    )
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=None,
        )
    )

    assert result["status"] == "ready"
    assert result["report_id"] == 198
    assert "shadow_compare" in result
    assert result["shadow_compare"]["legacy_status"] == "ready"
    assert result["shadow_compare"]["v2_status"] == "limited"
    assert result["shadow_compare"]["same_status"] is False
