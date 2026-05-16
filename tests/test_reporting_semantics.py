from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from schemas.report import EventReportPayload, PostReportPayload, ProcessReportPayload
from services.report_aggregation import build_event_report_payload, build_process_report_payload
from services import reporting


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return type("_Scalars", (), {"all": lambda self_: list(self._rows)})()


class _FakeSession:
    def __init__(self, *, get_map=None, execute_results=None):
        self.get_map = get_map or {}
        self.execute_results = list(execute_results or [])
        self.added = []

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)

    async def get(self, model, key):
        return self.get_map.get((model.__name__, key))

    def add(self, value):
        value.id = len(self.added) + 1
        self.added.append(value)

    async def flush(self):
        return None


def _canonical_openrouter_steps(*, synthesis_text: str = "Synthesis text.") -> dict:
    provenance = {
        "provider": "openrouter",
        "model": "openai/gpt-5.4",
        "executed": True,
        "success": True,
        "latency_ms": 12,
        "input_ref": "in://step",
        "input_hash": "abc",
        "output_ref": "out://step",
        "output_hash": "def",
        "fallback_used": False,
        "fallback_reason": None,
        "attempt_index": 0,
        "status": "completed",
    }
    steps = {
        step: {"status": "completed", "run_count": 1, "provenance_source": "observed", "provenance": dict(provenance)}
        for step in ("context", "routing", "expert", "public_opinion", "synthesis", "reviewer")
    }
    steps["context"]["sufficiency_components"] = {"analytical": "sufficient"}
    steps["public_opinion"]["data_status"] = "sufficient"
    steps["synthesis"]["report_text"] = synthesis_text
    steps["reviewer"]["history"] = [{"iteration": 1, "decision": "accept", "reason": "sufficient"}]
    return steps


def test_report_status_from_payload_requires_canonical_ready_evidence():
    assert reporting.report_status_from_payload({"type": "unknown_type"}) == "limited"
    assert reporting.report_status_from_payload({"type": "another_unknown_type"}) == "limited"
    assert reporting.report_status_from_payload({"status": "ready"}) == "limited"
    assert reporting.report_status_from_payload(None) == "limited"
    assert (
        reporting.report_status_from_payload(
            {
                "status": "ready",
                "meta": {
                    "multi_agent": {
                        "steps": _canonical_openrouter_steps(),
                        "review": {"history": [{"iteration": 1, "decision": "accept", "reason": "sufficient"}]},
                    }
                },
            }
        )
        == "ready"
    )


def test_report_status_from_payload_downgrades_ready_on_blocking_reviewer_defect():
    assert (
        reporting.report_status_from_payload(
            {
                "status": "ready",
                "meta": {
                    "multi_agent": {
                        "steps": _canonical_openrouter_steps(),
                        "review": {"history": [{"iteration": 1, "decision": "insufficient_data", "reason": "D3:ready_forbidden"}]},
                    }
                },
            }
        )
        == "limited"
    )


def test_report_status_from_payload_keeps_unknown_status_unchanged():
    assert reporting.report_status_from_payload({"status": "custom_status"}) == "custom_status"


def test_map_internal_post_report_to_public_payload_normalizes_public_semantics():
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "limited",
            "post_id": 42,
            "title": "draft",
            "summary": "interpretive summary that should not leak as-is",
            "comment_count": 8,
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.2, "negative": 0.2, "neutral": 0.6},
            },
            "topics": [
                {"name": "budget", "share": 0.7},
                {"name": "budget", "share": 0.6},
                {"name": "regions", "share": 0.3},
            ],
            "confidence": {"overall": "high", "reason": "internal reviewer note"},
        }
    )

    validated = PostReportPayload.model_validate(payload)

    assert validated.status == "limited"
    assert validated.summary == "Evidence is limited."
    assert [item.name for item in validated.topics] == ["budget", "regions"]
    assert validated.confidence.overall == "medium"


def test_map_internal_post_report_to_public_payload_restores_topics_from_multi_agent_public_opinion():
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 885,
            "title": "post 885",
            "summary": "internal synthesis summary",
            "comment_count": 181,
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "topics": [],
            "confidence": {"overall": "high", "reason": "deterministic_orchestrator_v1"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": _canonical_openrouter_steps(synthesis_text="internal synthesis summary"),
                    "public_opinion": {
                        "discussion_state": "polarized",
                        "signals": [
                            {"name": "comments_count", "value": 181},
                            {"name": "top_topics", "value": ["шутка", "ананас", "донер"]},
                        ],
                    },
                }
            },
        }
    )

    validated = PostReportPayload.model_validate(payload)
    assert [item.name for item in validated.topics] == ["шутка", "ананас", "донер"]
    assert validated.summary == "internal synthesis summary."


def test_post_report_payload_rejects_unknown_status_literal():
    with pytest.raises(ValidationError):
        PostReportPayload.model_validate(
            {
                "type": "post_report_v2",
                "status": "unexpected_status",
                "post_id": 42,
                "title": "draft",
                "summary": "summary",
            }
        )


def test_payload_dependency_ready_accepts_limited_but_not_insufficient_data():
    assert reporting._is_payload_dependency_ready({"status": "ready"}) is True
    assert reporting._is_payload_dependency_ready({"status": "limited"}) is True
    assert reporting._is_payload_dependency_ready({"status": "insufficient_data"}) is False


def test_render_event_or_process_report_uses_compact_spec_aligned_text():
    text = reporting._render_event_or_process_text(
        {
            "event_id": 4,
            "event_title": "Event discussion",
            "summary": "Neutral overview.",
            "confidence": {"overall": "medium", "reason": "bounded evidence"},
        }
    )

    assert text == "Neutral overview."


def test_render_post_report_uses_compact_spec_aligned_text():
    text = reporting._render_post_report_text(
        {
            "title": "Post 42 discussion snapshot",
            "status": "limited",
            "summary": "Limited signal.",
            "topics": [{"name": "topic-a"}, {"name": "topic-b"}],
            "confidence": {"overall": "medium", "reason": "weak comment signal"},
        }
    )

    assert text == "Limited signal."


def test_mark_report_payload_stale_preserves_context():
    payload = {
        "type": "event_report_v2",
        "status": "ready",
        "summary": "ok",
        "meta": {"prompt_version": "event_report_v2"},
    }

    result = reporting.mark_report_payload_stale(
        payload,
        dependency_type="post_report",
        dependency_id=17,
    )

    assert result["status"] == reporting.REPORT_STATUS_STALE
    assert result["summary"] == "ok"
    assert result["meta"]["stale"] is True
    assert result["meta"]["stale_dependency_type"] == "post_report"
    assert result["meta"]["stale_dependency_id"] == 17
    assert result["meta"]["previous_status"] == "ready"
    assert "stale_marked_at" in result["meta"]


def test_build_post_report_sanitizes_internal_error(monkeypatch):
    channel = SimpleNamespace(id=7, username="test_channel")
    post = SimpleNamespace(
        id=11,
        date=reporting.datetime(2026, 3, 11, 12, 0, tzinfo=reporting.timezone.utc),
        text="post",
        views=5,
        comments_count=0,
        reactions_json=None,
    )
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([]),
        ]
    )

    async def _broken_v2(**kwargs):
        raise RuntimeError("llm exploded")

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=91)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _broken_v2)
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=SimpleNamespace(),
        )
    )

    assert result["status"] == "failed"
    assert result["technical_error"] == "RuntimeError: llm exploded"
    assert captured == {
        "post_id": 11,
        "status": "failed",
        "content": reporting.REPORT_GENERATION_FAILED_CONTENT,
        "report_json": None,
    }


def test_build_post_report_defers_until_refresh_work_unit_completed(monkeypatch):
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
        ]
    )

    async def _fake_post_readiness(_session, *, post):
        assert post.id == 11
        return {
            "ready": False,
            "reason": "waiting_refresh_post_data",
            "dependencies": [{"job_type": "refresh_comments", "post_id": 11, "reason": "waiting_refresh_post_data"}],
            "terminal": False,
        }

    monkeypatch.setattr(reporting, "_post_report_readiness", _fake_post_readiness)

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=SimpleNamespace(),
        )
    )

    assert result["status"] == reporting.REPORT_STATUS_DEFERRED
    assert result["reason"] == "waiting_refresh_post_data"
    assert result["dependencies"] == [{"job_type": "refresh_comments", "post_id": 11, "reason": "waiting_refresh_post_data"}]
    assert session.added == []


def test_post_reactions_enrichment_treats_no_reactions_as_complete_signal():
    post = SimpleNamespace(
        comments_count=0,
        reactions_json={
            "source": "telegram_refresh",
            "collected_at": "2026-04-09T12:00:00+00:00",
            "is_complete": True,
            "post_reactions": {"results": [], "state": "no_reactions"},
            "comment_reactions": {
                "status": "no_reactions",
                "comments_scanned": 0,
                "comments_with_visible_reactions": 0,
            },
        },
    )

    payload = reporting._post_reactions_enrichment(post=post, comment_rows=[])

    assert payload["reactions_coverage"]["comment_status"] == "no_reactions"
    assert payload["reactions_coverage"]["factor"] == 1.0


def test_laugh_reaction_not_treated_as_supportive_by_default() -> None:
    stance = reporting._build_audience_stance(
        {
            "comment_count": 12,
            "sentiment": {"distribution": {"positive": 0.5, "negative": 0.1, "neutral": 0.4}},
            "post_reactions": {"top_reactions": [{"label": "🤣", "count": 444}]},
            "comment_reactions": {"top_reactions": []},
            "reactions_coverage": {"factor": 0.9},
            "meta": {
                "multi_agent": {
                    "steps": {
                        "public_opinion": {
                            "discussion_state": "conflicted",
                            "data_status": "sufficient",
                            "dominant_reactions": [{"text": "скепсис и сарказм", "type": "derived", "confidence": 0.8, "source": "comments"}],
                        }
                    }
                }
            },
        }
    )
    assert stance["label"] in {"mixed", "critical", "unclear"}
    assert stance["label"] != "supportive"


def test_critical_comments_override_positive_reactions() -> None:
    stance = reporting._build_audience_stance(
        {
            "comment_count": 25,
            "sentiment": {"distribution": {"positive": 0.55, "negative": 0.2, "neutral": 0.25}},
            "post_reactions": {"top_reactions": [{"label": "❤️", "count": 120}]},
            "comment_reactions": {"top_reactions": []},
            "reactions_coverage": {"factor": 0.8},
            "meta": {
                "multi_agent": {
                    "steps": {
                        "public_opinion": {
                            "discussion_state": "conflicted",
                            "data_status": "sufficient",
                            "dominant_reactions": [{"text": "скепсис, недоверие и опасения будущих налогов"}],
                        }
                    }
                }
            },
        }
    )
    assert stance["label"] in {"mixed", "critical"}
    assert stance["confidence"] in {"medium", "high"}


def test_supportive_only_when_comments_and_reactions_align() -> None:
    stance = reporting._build_audience_stance(
        {
            "comment_count": 18,
            "sentiment": {"distribution": {"positive": 0.7, "negative": 0.05, "neutral": 0.25}},
            "post_reactions": {"top_reactions": [{"label": "👍", "count": 80}, {"label": "❤️", "count": 40}]},
            "comment_reactions": {"top_reactions": []},
            "reactions_coverage": {"factor": 0.9},
            "meta": {
                "multi_agent": {
                    "steps": {
                        "public_opinion": {
                            "discussion_state": "stable",
                            "data_status": "sufficient",
                            "dominant_reactions": [{"text": "поддержка инициативы и одобрение"}],
                        }
                    }
                }
            },
        }
    )
    assert stance["label"] == "supportive"


def test_mixed_when_reactions_positive_but_comments_skeptical() -> None:
    stance = reporting._build_audience_stance(
        {
            "comment_count": 30,
            "sentiment": {"distribution": {"positive": 0.6, "negative": 0.2, "neutral": 0.2}},
            "post_reactions": {"top_reactions": [{"label": "❤️", "count": 150}]},
            "comment_reactions": {"top_reactions": []},
            "reactions_coverage": {"factor": 0.75},
            "meta": {
                "multi_agent": {
                    "steps": {
                        "public_opinion": {
                            "discussion_state": "conflicted",
                            "data_status": "sufficient",
                            "dominant_reactions": [{"text": "скепсис и сарказм по поводу инициативы"}],
                        }
                    }
                }
            },
        }
    )
    assert stance["label"] in {"mixed", "critical"}
    assert stance["label"] != "supportive"
    assert stance["confidence"] == "medium"


def test_build_post_report_persists_input_signature(monkeypatch):
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
            _FakeRowsResult([(1, None, None, 0, None, "hello", None)]),
        ]
    )

    async def _fake_generate_v2(**kwargs):
            return {
                "type": "post_report_v2",
                "status": "ready",
                "post_id": 11,
                "published_at": "2026-03-11T12:00:00+00:00",
                "title": "ok",
                "summary": "Готовый отчет",
            "comment_count": 1,
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
                        "steps": _canonical_openrouter_steps(synthesis_text="Готовый отчет"),
                    "review": {"history": [{"iteration": 1, "decision": "accept", "reason": "sufficient"}]},
                }
            },
        }

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=92)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _fake_generate_v2)
    monkeypatch.setattr(reporting, "normalize_report_language", lambda payload: asyncio.sleep(0, result=payload))
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=SimpleNamespace(),
        )
    )

    assert result["status"] in {"ready", "limited"}
    assert captured["report_json"]["meta"]["input_signature"]
    assert captured["report_json"]["meta"]["generated_at"]


def test_build_post_report_marks_status_failed_for_valid_failed_payload(monkeypatch):
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
            _FakeRowsResult([(1, None, None, 0, None, "hello", None)]),
        ]
    )

    async def _fake_generate_v2(**kwargs):
        return {
            "type": "post_report_v2",
            "status": "failed",
            "post_id": 11,
            "title": "fallback",
            "summary": "fallback",
            "comment_count": 1,
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                "confidence": "low",
            },
            "topics": [],
            "clusters": [],
            "time_trends": [],
            "risks": [],
            "anomalies": ["model_output_invalid"],
            "representative_quotes": [],
            "confidence": {"overall": "low", "reason": "model_output_invalid"},
            "meta": {
                "validation_error": "bad output",
                "multi_agent": {
                    "epistemic_labels": [],
                    "sufficiency": "insufficient",
                    "stages": {name: {"status": "completed", "run_count": 1} for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]},
                    "review_iterations": 1,
                    "final_status": "failed",
                    "orchestration": {"sequence": ["context", "routing", "expert", "public_opinion", "synthesis"]},
                },
            },
        }

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=93)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _fake_generate_v2)
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=SimpleNamespace(),
        )
    )

    assert result["status"] == "failed"
    assert result["technical_error"] == "bad output"
    assert captured["status"] == "failed"
    assert captured["content"] == reporting.REPORT_GENERATION_FAILED_CONTENT
    assert captured["report_json"]["status"] == "failed"


def test_build_post_report_persists_non_ready_reviewer_downgrade_without_job_failure(monkeypatch):
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
            _FakeRowsResult([(1, None, None, 0, None, "hello", None)]),
        ]
    )

    async def _fake_generate_v2(**kwargs):
        return {
            "type": "post_report_v2",
            "status": "insufficient_data",
            "post_id": 11,
            "title": "fallback",
            "summary": "fallback",
            "comment_count": 1,
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                "confidence": "low",
            },
            "topics": [],
            "clusters": [],
            "time_trends": [],
            "risks": [],
            "anomalies": [],
            "representative_quotes": [],
            "confidence": {"overall": "low", "reason": "insufficient_data"},
            "meta": {
                "multi_agent": {
                    "epistemic_labels": [],
                    "sufficiency": "insufficient",
                    "stages": {name: {"status": "completed", "run_count": 1} for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]},
                    "review_iterations": 2,
                    "final_status": "insufficient_data",
                    "orchestration": {"sequence": ["context", "routing", "expert", "public_opinion", "synthesis"]},
                }
            },
        }

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=94)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)
    monkeypatch.setattr(reporting, "generate_post_report_payload_v2", _fake_generate_v2)
    monkeypatch.setattr(
        reporting,
        "_post_report_readiness",
        lambda _session, *, post: asyncio.sleep(0, result={"ready": True, "refresh_attempt": None}),
    )

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=SimpleNamespace(),
        )
    )

    assert result["status"] == "insufficient_data"
    assert "technical_error" not in result
    assert captured["status"] == "insufficient_data"
    assert captured["content"] != reporting.REPORT_GENERATION_FAILED_CONTENT
    assert captured["report_json"]["status"] == "insufficient_data"


def test_build_event_report_draft_persists_v2_payload_when_input_is_insufficient(monkeypatch):
    session = _FakeSession(execute_results=[_FakeScalarResult(2)])

    async def _fake_build_event_report_v2_impl(*, session, event_id):
        assert event_id == 5
        return {
            "type": "event_report_v2",
            "status": "insufficient_data",
            "event_id": 5,
            "event_title": "Event",
            "posts_count": 0,
            "source_post_reports": [],
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "cross_post_topics": [],
            "post_dynamics": [],
            "event_trends": [],
            "risks": [],
            "anomalies": [],
            "summary": "insufficient",
            "confidence": {"overall": "low", "reason": "insufficient"},
            "meta": {
                "multi_agent": {
                    "epistemic_labels": [],
                    "sufficiency": "insufficient",
                    "stages": {name: {"status": "completed", "run_count": 1} for name in ["context", "routing", "expert", "public_opinion", "synthesis", "reviewer"]},
                    "review_iterations": 1,
                    "final_status": "insufficient_data",
                    "orchestration": {"sequence": ["context", "routing", "expert", "public_opinion", "synthesis"]},
                }
            },
        }

    monkeypatch.setattr(reporting, "build_event_report_v2_impl", _fake_build_event_report_v2_impl)

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=5))

    assert result == {"status": "insufficient_data", "event_id": 5, "report_id": 1}
    assert session.added[0].report_json["status"] == "insufficient_data"
    assert session.added[0].report_json["type"] == "event_report_v2"


def test_build_process_report_draft_returns_draft_status_when_no_event_reports():
    process = SimpleNamespace(id=3, title="Process")
    session = _FakeSession(
        get_map={("Process", 3): process},
        execute_results=[
            _FakeRowsResult([]),
            _FakeRowsResult([]),
            _FakeRowsResult([]),
            _FakeRowsResult([]),
            _FakeScalarResult(None),
        ],
    )

    result = asyncio.run(reporting.build_process_report_draft(session, process_id=3))

    assert result == {"status": "draft", "process_id": 3, "report_id": 1}
    assert session.added[0].report_json["status"] == "draft"
    assert session.added[0].report_json["type"] == "process_report_v2"


def test_build_event_report_draft_uses_v2_bridge(monkeypatch):
    session = _FakeSession(execute_results=[_FakeScalarResult(None)])

    async def _fake_build_event_report_v2_impl(*, session, event_id):
        assert event_id == 7
        return {
            "type": "event_report_v2",
            "status": "ready",
            "event_id": 7,
            "event_title": "Event",
            "posts_count": 2,
            "source_post_reports": [201, 202],
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "cross_post_topics": [],
            "post_dynamics": [],
            "event_trends": [],
            "risks": [],
            "anomalies": [],
            "summary": "ok",
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": _canonical_openrouter_steps(synthesis_text="ok"),
                    "review": {"history": [{"iteration": 1, "decision": "accept", "reason": "sufficient"}]},
                }
            },
        }

    monkeypatch.setattr(reporting, "build_event_report_v2_impl", _fake_build_event_report_v2_impl)

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=7))

    assert result == {"status": "ready", "event_id": 7, "report_id": 1}
    assert session.added[0].report_json["meta"]["multi_agent"]["status"] == "ready"


def test_build_process_report_draft_defers_when_dependencies_are_not_ready(monkeypatch):
    process = SimpleNamespace(id=9, title="Process")
    session = _FakeSession(get_map={("Process", 9): process})

    async def _fake_readiness(_session, *, process_id):
        assert process_id == 9
        return {
            "ready": False,
            "reason": "waiting_event_reports",
            "total_events": 3,
            "ready_event_reports": 1,
            "dependencies": [{"job_type": "build_event_report", "event_id": 21, "reason": "waiting_event_reports"}],
        }

    monkeypatch.setattr(reporting, "_process_report_readiness", _fake_readiness)

    result = asyncio.run(reporting.build_process_report_draft(session, process_id=9))

    assert result["status"] == reporting.REPORT_STATUS_DEFERRED
    assert result["process_id"] == 9
    assert result["reason"] == "waiting_event_reports"
    assert result["dependencies"] == [{"job_type": "build_event_report", "event_id": 21, "reason": "waiting_event_reports"}]
    assert session.added == []


def test_process_report_readiness_requires_rebuild_for_stale_event_reports():
    session = _FakeSession()

    async def _fake_snapshots(_session, *, process_id):
        assert process_id == 55
        return [
            (101, "Event 101", {"status": "ready"}, "ready"),
            (102, "Event 102", {"status": "stale"}, "stale"),
            (103, "Event 103", {"status": "ready"}, "ready"),
        ]

    reporting._load_latest_event_report_snapshots_for_process, original = (
        _fake_snapshots,
        reporting._load_latest_event_report_snapshots_for_process,
    )
    try:
        result = asyncio.run(reporting._process_report_readiness(session, process_id=55))
    finally:
        reporting._load_latest_event_report_snapshots_for_process = original

    assert result["ready"] is False
    assert result["ready_event_reports"] == 2
    assert result["required_ready_event_reports"] == 3
    assert result["reason"] == "waiting_event_reports"
    assert result["dependencies"] == [{"job_type": "build_event_report", "event_id": 102, "reason": "waiting_event_reports"}]


def test_event_report_readiness_requires_rebuild_for_stale_post_reports():
    session = _FakeSession(
        execute_results=[
            _FakeRowsResult(
                [
                    (201, "root", 25, "root text", {"status": "stale"}),
                    (202, "member", 24, "member text", {"status": "ready"}),
                    (203, "member", 31, "member text 2", {"status": "ready"}),
                ]
            ),
        ]
    )

    result = asyncio.run(reporting._event_report_readiness(session, event_id=77))

    assert result["ready"] is False
    assert result["ready_post_reports"] == 2
    assert result["required_ready_post_reports"] == 3
    assert result["root_ready"] is False
    assert result["reason"] == "waiting_post_reports"
    assert result["dependencies"] == [{"job_type": "build_post_report", "post_id": 201, "reason": "waiting_post_reports"}]


def test_process_event_loader_requires_current_non_stale_event_reports():
    session = _FakeSession(
        execute_results=[
            _FakeRowsResult([(101, "Event 101")]),
            _FakeRowsResult(
                [
                    (101, {"status": "stale", "summary": "stale"}, 3, 3003),
                    (101, {"status": "ready", "summary": "usable"}, 2, 3002),
                ]
            ),
        ]
    )

    result = asyncio.run(reporting._load_latest_event_report_payloads_for_process(session, process_id=88))

    assert result == []


def test_process_event_loader_does_not_fallback_to_post_reports_when_latest_event_reports_are_stale(monkeypatch):
    session = _FakeSession(
        execute_results=[
            _FakeRowsResult([(102, "Event 102")]),
            _FakeRowsResult([(102, {"status": "stale", "summary": "stale"}, 4, 4004)]),
        ]
    )

    async def _fake_load_post_report_payloads_for_event(_session, *, event_id):
        assert event_id == 102
        return [{"post_id": 11, "summary": "post report"}]

    monkeypatch.setattr(reporting, "_load_post_report_payloads_for_event", _fake_load_post_report_payloads_for_event)
    monkeypatch.setattr(
        reporting,
        "build_event_report_payload",
        lambda *, event_id, event_title, post_reports: {
            "status": "ready",
            "event_id": event_id,
            "event_title": event_title,
            "summary": f"rebuilt from {len(post_reports)} posts",
        },
    )

    result = asyncio.run(reporting._load_latest_event_report_payloads_for_process(session, process_id=89))

    assert result == []


def test_build_event_report_payload_conforms_to_schema():
    payload = build_event_report_payload(
        event_id=55,
        event_title="Event 55",
        post_reports=[
            {
                "post_id": 1,
                "published_at": "2026-03-11T12:00:00+00:00",
                "summary": "first summary",
                "comment_count": 6,
                "event_role": "root",
                "topics": [{"name": "topic-a", "share": 0.7}],
                "risks": ["risk-a"],
                "anomalies": ["anomaly-a"],
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.2, "negative": 0.1, "neutral": 0.7},
                    "confidence": "medium",
                },
            },
            {
                "post_id": 2,
                "published_at": "2026-03-11T13:00:00+00:00",
                "summary": "second summary",
                "comment_count": 10,
                "event_role": "context",
                "topics": [{"name": "topic-b", "share": 0.5}],
                "risks": ["risk-b"],
                "anomalies": ["anomaly-b"],
                "sentiment": {
                    "dominant": "positive",
                    "distribution": {"positive": 0.7, "negative": 0.1, "neutral": 0.2},
                    "confidence": "high",
                },
            },
        ],
    )

    validated = EventReportPayload.model_validate(payload)

    assert validated.event_id == 55
    assert validated.posts_count == 2
    assert validated.source_post_reports == [1, 2]
    assert validated.meta["prompt_version"] == "event_report_v2"


def test_build_event_report_payload_marks_limited_when_child_reports_are_limited():
    payload = build_event_report_payload(
        event_id=56,
        event_title="Event 56",
        post_reports=[
            {
                "status": "ready",
                "post_id": 1,
                "published_at": "2026-03-11T12:00:00+00:00",
                "summary": "first summary",
                "comment_count": 12,
                "topics": [{"name": "topic-a", "share": 0.5}],
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.2, "negative": 0.1, "neutral": 0.7},
                },
            },
            {
                "status": "limited",
                "post_id": 2,
                "published_at": "2026-03-11T13:00:00+00:00",
                "summary": "second summary",
                "comment_count": 10,
                "topics": [{"name": "topic-b", "share": 0.5}],
                "sentiment": {
                    "dominant": "positive",
                    "distribution": {"positive": 0.7, "negative": 0.1, "neutral": 0.2},
                },
            },
            {
                "status": "insufficient_data",
                "post_id": 3,
                "published_at": "2026-03-11T14:00:00+00:00",
                "summary": "should be ignored",
                "comment_count": 1,
                "topics": [{"name": "topic-c", "share": 1.0}],
                "sentiment": {
                    "dominant": "negative",
                    "distribution": {"positive": 0.0, "negative": 1.0, "neutral": 0.0},
                },
            },
        ],
    )

    validated = EventReportPayload.model_validate(payload)

    assert validated.status == "limited"
    assert validated.posts_count == 2
    assert validated.source_post_reports == [1, 2]
    assert validated.confidence.overall == "medium"


def test_build_process_report_payload_conforms_to_schema():
    payload = build_process_report_payload(
        process_id=77,
        process_title="Process 77",
        event_reports=[
            {
                "event_id": 11,
                "event_title": "Event 11",
                "summary": "stage one",
                "cross_post_topics": [{"name": "topic-a", "share": 0.5}],
                "risks": ["risk-a"],
                "anomalies": ["anomaly-a"],
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.1, "negative": 0.2, "neutral": 0.7},
                    "confidence": "medium",
                },
            },
            {
                "event_id": 12,
                "event_title": "Event 12",
                "summary": "stage two",
                "cross_post_topics": [{"name": "topic-b", "share": 0.4}],
                "risks": ["risk-b"],
                "anomalies": ["anomaly-b"],
                "sentiment": {
                    "dominant": "positive",
                    "distribution": {"positive": 0.8, "negative": 0.1, "neutral": 0.1},
                    "confidence": "high",
                },
            },
        ],
    )

    validated = ProcessReportPayload.model_validate(payload)

    assert validated.process_id == 77
    assert validated.events_count == 2
    assert validated.source_event_reports == [11, 12]
    assert validated.meta["prompt_version"] == "process_report_v2"


def test_build_process_report_payload_marks_limited_when_child_events_are_limited():
    payload = build_process_report_payload(
        process_id=78,
        process_title="Process 78",
        event_reports=[
            {
                "status": "ready",
                "event_id": 11,
                "event_title": "Event 11",
                "summary": "stage one",
                "cross_post_topics": [{"name": "topic-a", "share": 0.5}],
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.1, "negative": 0.2, "neutral": 0.7},
                },
            },
            {
                "status": "limited",
                "event_id": 12,
                "event_title": "Event 12",
                "summary": "stage two",
                "cross_post_topics": [{"name": "topic-b", "share": 0.4}],
                "sentiment": {
                    "dominant": "positive",
                    "distribution": {"positive": 0.8, "negative": 0.1, "neutral": 0.1},
                },
            },
            {
                "status": "insufficient_data",
                "event_id": 13,
                "event_title": "Event 13",
                "summary": "ignored",
                "cross_post_topics": [{"name": "topic-c", "share": 1.0}],
                "sentiment": {
                    "dominant": "negative",
                    "distribution": {"positive": 0.0, "negative": 1.0, "neutral": 0.0},
                },
            },
        ],
    )

    validated = ProcessReportPayload.model_validate(payload)

    assert validated.status == "limited"
    assert validated.events_count == 2
    assert validated.source_event_reports == [11, 12]
    assert validated.confidence.overall == "medium"


def test_failed_post_report_payload_remains_schema_compatible():
    payload = {
        "type": "post_report_v2",
        "status": "failed",
        "post_id": 11,
        "title": "fallback",
        "summary": "fallback",
        "comment_count": 1,
        "sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "low",
        },
        "topics": [],
        "clusters": [],
        "time_trends": [],
        "risks": [],
        "anomalies": ["model_output_invalid"],
        "representative_quotes": [],
        "confidence": {"overall": "low", "reason": "model_output_invalid"},
        "meta": {"validation_error": "bad output", "prompt_version": "post_report_v2"},
    }

    validated = PostReportPayload.model_validate(payload)

    assert validated.status == "failed"
    assert validated.meta["validation_error"] == "bad output"




def test_map_internal_post_report_to_public_payload_canonicalizes_multi_agent_review_shape():
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "limited",
            "post_id": 777,
            "title": "post 777",
            "summary": "raw summary",
            "comment_count": 3,
            "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0}},
            "confidence": {"overall": "medium", "reason": "raw"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "limited",
                    "context": {"article_sufficiency": "limited"},
                    "routing": {"reasoning": "deterministic"},
                    "expert": {"claims": []},
                    "public_opinion": {"signals": []},
                    "synthesis": {"summary": "raw synthesis"},
                    "reviewer": {"decision": "accept_with_limitations", "iterations": 1, "history": []},
                }
            },
        }
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert "reviewer" not in multi_agent
    assert "review" in multi_agent
    assert set(multi_agent["steps"].keys()) == {"context", "routing", "expert", "public_opinion", "synthesis", "reviewer"}
    assert multi_agent["steps"]["reviewer"]["provenance_source"] == "default_filled"


def test_public_opinion_uses_llm_topics_over_keywords() -> None:
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 991,
            "title": "post 991",
            "summary": "summary",
            "comment_count": 42,
            "topics": [],
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        **_canonical_openrouter_steps(),
                        "public_opinion": {
                            "status": "completed",
                            "run_count": 1,
                            "signals": [{"name": "top_topics", "value": ["если", "надо", "налог"]}],
                            "llm_public_opinion": {"main_topics": [":need_for_cat_registration", ":tax_and_financial_concerns"]},
                        },
                    },
                }
            },
        }
    )
    assert [item["name"] for item in payload["topics"]] == [
        "сомнения в необходимости регистрации кошек",
        "опасения будущих налогов и платежей",
    ]


def test_public_opinion_maps_enum_topics_to_russian() -> None:
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 992,
            "title": "post 992",
            "summary": "summary",
            "topics": [],
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        **_canonical_openrouter_steps(),
                        "public_opinion": {
                            "status": "completed",
                            "run_count": 1,
                            "llm_public_opinion": {
                                ":main_topics": [
                                    ":need_for_cat_registration",
                                    ":tax_and_financial_concerns",
                                    ":enforcement_and_penalties",
                                    ":absurdity_of_registering_other_pets",
                                ]
                            },
                        },
                    },
                }
            },
        }
    )
    assert [item["name"] for item in payload["topics"]] == [
        "сомнения в необходимости регистрации кошек",
        "опасения будущих налогов и платежей",
        "вопросы о штрафах и практическом контроле",
        "саркастические сравнения с регистрацией других животных",
    ]


def test_public_opinion_filters_stopwords_from_keyword_fallback() -> None:
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 993,
            "title": "post 993",
            "summary": "summary",
            "topics": [],
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        **_canonical_openrouter_steps(),
                        "public_opinion": {
                            "status": "completed",
                            "run_count": 1,
                            "signals": [{"name": "top_topics", "value": ["если", "надо", "это", "что", "налог", "штраф"]}],
                        },
                    },
                }
            },
        }
    )
    assert [item["name"] for item in payload["topics"]] == ["налог", "штраф"]


def test_public_opinion_exports_dominant_reactions() -> None:
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 994,
            "title": "post 994",
            "summary": "summary",
            "topics": [],
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        **_canonical_openrouter_steps(),
                        "public_opinion": {
                            "status": "completed",
                            "run_count": 1,
                            "llm_public_opinion": {
                                ":main_topics": [":need_for_cat_registration"],
                                ":dominant_reactions": [":skepticism", ":sarcasm"],
                            },
                        },
                    },
                }
            },
        }
    )
    reactions = payload["meta"]["multi_agent"]["steps"]["public_opinion"]["dominant_reactions"]
    assert isinstance(reactions, list)
    assert len(reactions) >= 2
    assert reactions[0]["type"] == "derived"
    assert reactions[0]["source"] == "comments"


def test_public_opinion_marks_keyword_only_as_weak_signal() -> None:
    payload = reporting.map_internal_post_report_to_public_payload(
        {
            "type": "post_report_v2",
            "status": "ready",
            "post_id": 995,
            "title": "post 995",
            "summary": "summary",
            "topics": [],
            "confidence": {"overall": "high", "reason": "ok"},
            "meta": {
                "multi_agent": {
                    "version": "v1",
                    "status": "ready",
                    "steps": {
                        **_canonical_openrouter_steps(),
                        "public_opinion": {
                            "status": "completed",
                            "run_count": 1,
                            "signals": [{"name": "top_topics", "value": ["налог", "штраф"]}],
                        },
                    },
                }
            },
        }
    )
    po = payload["meta"]["multi_agent"]["steps"]["public_opinion"]
    assert po["data_status"] == "weak_signal"


def test_contract_rejects_english_summary() -> None:
    payload = {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1201,
        "title": "post",
        "summary": "This is an english summary only.",
        "comment_count": 10,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.1, "negative": 0.1, "neutral": 0.8}},
        "topics": [{"name": "тема"}],
        "confidence": {"overall": "medium", "reason": "ok"},
        "meta": {"multi_agent": {"version": "v1", "status": "ready", "steps": _canonical_openrouter_steps(synthesis_text="This is english.")}},
    }
    result = reporting.validate_report_contract(payload)
    assert result.critical is True
    assert any(item["code"] == "C2" for item in result.issues)


def test_contract_rejects_accept_with_reviewer_issues() -> None:
    steps = _canonical_openrouter_steps(synthesis_text="Краткий русский синтез.")
    steps["reviewer"]["decision"] = "accept"
    steps["reviewer"]["llm_reviewer"] = {"issues": [{"field": "expert.background", "problem": "empty"}]}
    payload = {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1202,
        "title": "post",
        "summary": "Краткий русский синтез.",
        "comment_count": 10,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.1, "negative": 0.1, "neutral": 0.8}},
        "topics": [{"name": "тема"}],
        "confidence": {"overall": "medium", "reason": "ok"},
        "meta": {"multi_agent": {"version": "v1", "status": "ready", "steps": steps}},
    }
    result = reporting.validate_report_contract(payload)
    assert any(item["code"] == "C6" for item in result.issues)


def test_contract_rejects_empty_expert_claims() -> None:
    steps = _canonical_openrouter_steps(synthesis_text="Краткий русский синтез.")
    steps["expert"] = {"status": "completed", "run_count": 1, "background": [], "interpretations": [], "consequences": []}
    payload = {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1203,
        "title": "post",
        "summary": "Краткий русский синтез.",
        "comment_count": 10,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.1, "negative": 0.1, "neutral": 0.8}},
        "topics": [{"name": "тема"}],
        "confidence": {"overall": "medium", "reason": "ok"},
        "meta": {"multi_agent": {"version": "v1", "status": "ready", "steps": steps}},
    }
    result = reporting.validate_report_contract(payload)
    assert any(item["code"] == "C5" for item in result.issues)


def test_contract_rejects_stopword_topics() -> None:
    payload = {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1204,
        "title": "post",
        "summary": "Краткий русский синтез.",
        "comment_count": 10,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.1, "negative": 0.1, "neutral": 0.8}},
        "topics": [{"name": "если"}, {"name": "надо"}],
        "confidence": {"overall": "medium", "reason": "ok"},
        "meta": {"multi_agent": {"version": "v1", "status": "ready", "steps": _canonical_openrouter_steps(synthesis_text="Краткий русский синтез.")}},
    }
    result = reporting.validate_report_contract(payload)
    assert any(item["code"] == "C7" for item in result.issues)


def test_contract_downgrades_high_confidence_when_limited() -> None:
    steps = _canonical_openrouter_steps(synthesis_text="Краткий русский синтез.")
    steps["expert"]["data_status"] = "limited"
    payload = {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1205,
        "title": "post",
        "summary": "Краткий русский синтез.",
        "comment_count": 10,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.1, "negative": 0.1, "neutral": 0.8}},
        "topics": [{"name": "тема"}],
        "confidence": {"overall": "high", "reason": "overclaim"},
        "meta": {"multi_agent": {"version": "v1", "status": "ready", "steps": steps}},
    }
    result = reporting.validate_report_contract(payload)
    assert any(item["code"] == "C8" for item in result.issues)
