from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

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


def test_report_status_from_payload_detects_legacy_draft_payloads():
    assert reporting.report_status_from_payload({"type": "event_report_draft_v1"}) == "draft"
    assert reporting.report_status_from_payload({"type": "process_report_draft_v1"}) == "draft"
    assert reporting.report_status_from_payload({"status": "ready"}) == "ready"
    assert reporting.report_status_from_payload(None) == "ready"


@pytest.mark.skip(reason="obsolete legacy text template retained only for historical reference")
def test_render_post_report_uses_obsolete_legacy_text_template():
    text = reporting._render_post_report_text(
        {
            "title": "Заголовок: Добрый поступок вызвал отклик",
            "summary": "Большинство комментариев поддерживают героя публикации.",
            "sentiment": {
                "dominant": "positive",
                "distribution": {"positive": 0.7, "negative": 0.1, "neutral": 0.2},
            },
            "topics": [{"name": "благодарность"}, {"name": "подражание примеру"}],
            "clusters": [{"name": "поддержка", "summary": "Люди хвалят поступок и желают здоровья."}],
            "time_trends": [{"summary": "В начале обсуждения доминирует одобрение."}],
            "representative_quotes": ["Молодец!", "Побольше бы таких людей."],
            "risks": ["скепсис к съемке на камеру"],
        }
    )

    assert "Краткий анализ комментариев к посту" in text
    assert "Общий эмоциональный фон" in text
    assert "2. Основные направления мысли" in text
    assert "3. Противоречия и спорные моменты" in text
    assert "4. Примеры характерных тезисов (для ориентира)" in text
    assert "Итог" in text
    assert "Тональность:" not in text


def test_render_event_or_process_report_uses_legacy_text_template():
    text = reporting._render_event_or_process_text(
        {
            "event_id": 4,
            "event_title": "Обсуждение законопроекта",
            "summary": "Сводка показывает ровный нейтральный фон.",
            "sentiment": {
                "dominant": "neutral",
                "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            },
            "cross_post_topics": [{"name": "законопроект"}],
            "post_dynamics": [{"role": "контекст", "summary": "Посты фокусируются на содержании инициативы."}],
            "event_trends": [{"summary": "Тон обсуждения остается ровным."}],
            "risks": ["propaganda"],
        }
    )

    assert "Краткий анализ комментариев к обсуждению" in text
    assert "Общий эмоциональный фон" in text
    assert "2. Основные направления мысли" in text
    assert "Итог" in text
    assert "Тональность:" not in text


def test_render_post_report_uses_legacy_text_template():
    text = reporting._render_post_report_text(
        {
            "title": "Заголовок: Добрый поступок вызвал отклик",
            "summary": "Большинство комментариев поддерживают героя публикации.",
            "sentiment": {
                "dominant": "positive",
                "distribution": {"positive": 0.7, "negative": 0.1, "neutral": 0.2},
            },
            "topics": [{"name": "благодарность"}, {"name": "подражание примеру"}],
            "clusters": [{"name": "поддержка", "summary": "Люди хвалят поступок и желают здоровья."}],
            "time_trends": [{"summary": "В начале обсуждения доминирует одобрение."}],
            "representative_quotes": ["Молодец!", "Побольше бы таких людей."],
            "risks": ["скепсис к съемке на камеру"],
        }
    )

    assert "1) Контекст поста" in text
    assert "2) Общий тон обсуждения" in text
    assert "3) Ключевые темы" in text
    assert "4) Тренды и повторяющиеся паттерны" in text
    assert "5) Репрезентативные цитаты" in text
    assert "6) Классификация комментариев" in text
    assert "7) Риски/сигналы" in text
    assert "- Итог: позитивный" in text
    assert "- По тональности:" in text
    assert "- По темам:" in text


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
    )
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([]),
        ]
    )

    class _BrokenProject:
        async def generate_post_report_payload(self, **kwargs):
            raise RuntimeError("llm exploded")

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=91)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=_BrokenProject(),
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


def test_build_post_report_persists_input_signature(monkeypatch):
    channel = SimpleNamespace(id=7, username="test_channel")
    post = SimpleNamespace(
        id=11,
        date=reporting.datetime(2026, 3, 11, 12, 0, tzinfo=reporting.timezone.utc),
        text="post",
        views=5,
        comments_count=2,
    )
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([(1, None, None, 0, None, "hello")]),
        ]
    )

    class _Project:
        async def generate_post_report_payload(self, **kwargs):
            return {"status": "ready", "title": "ok", "summary": "done"}

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=92)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=_Project(),
        )
    )

    assert result["status"] == "ready"
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
    )
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([(1, None, None, 0, None, "hello")]),
        ]
    )

    class _Project:
        async def generate_post_report_payload(self, **kwargs):
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
                "meta": {"validation_error": "bad output"},
            }

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content, report_json=None):
        captured.update({"post_id": post_id, "status": status, "content": content, "report_json": report_json})
        return SimpleNamespace(id=93)

    monkeypatch.setattr(reporting, "upsert_report", _fake_upsert_report)

    result = asyncio.run(
        reporting.build_post_report(
            session,
            post_id=11,
            report_project=_Project(),
        )
    )

    assert result["status"] == "failed"
    assert result["technical_error"] == "bad output"
    assert captured["status"] == "failed"
    assert captured["content"] == reporting.REPORT_GENERATION_FAILED_CONTENT
    assert captured["report_json"]["status"] == "failed"


def test_build_event_report_draft_returns_draft_status_when_no_post_reports():
    event = SimpleNamespace(id=5, title="Event")
    session = _FakeSession(
        get_map={("Event", 5): event},
        execute_results=[
            _FakeRowsResult([]),
            _FakeRowsResult([]),
            _FakeScalarResult(2),
        ],
    )

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=5))

    assert result == {"status": "draft", "event_id": 5, "report_id": 1}
    assert session.added[0].report_json["status"] == "draft"
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
            _FakeRowsResult([]),
            _FakeScalarResult(None),
        ],
    )

    result = asyncio.run(reporting.build_process_report_draft(session, process_id=3))

    assert result == {"status": "draft", "process_id": 3, "report_id": 1}
    assert session.added[0].report_json["status"] == "draft"
    assert session.added[0].report_json["type"] == "process_report_v2"


def test_build_event_report_draft_defers_when_dependencies_are_not_ready(monkeypatch):
    event = SimpleNamespace(id=7, title="Event")
    session = _FakeSession(get_map={("Event", 7): event})

    async def _fake_readiness(_session, *, event_id):
        assert event_id == 7
        return {"ready": False, "reason": "waiting_post_reports", "total_posts": 4, "ready_post_reports": 1}

    monkeypatch.setattr(reporting, "_event_report_readiness", _fake_readiness)

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=7))

    assert result["status"] == reporting.REPORT_STATUS_DEFERRED
    assert result["event_id"] == 7
    assert result["reason"] == "waiting_post_reports"
    assert session.added == []


def test_build_process_report_draft_defers_when_dependencies_are_not_ready(monkeypatch):
    process = SimpleNamespace(id=9, title="Process")
    session = _FakeSession(get_map={("Process", 9): process})

    async def _fake_readiness(_session, *, process_id):
        assert process_id == 9
        return {"ready": False, "reason": "waiting_event_reports", "total_events": 3, "ready_event_reports": 1}

    monkeypatch.setattr(reporting, "_process_report_readiness", _fake_readiness)

    result = asyncio.run(reporting.build_process_report_draft(session, process_id=9))

    assert result["status"] == reporting.REPORT_STATUS_DEFERRED
    assert result["process_id"] == 9
    assert result["reason"] == "waiting_event_reports"
    assert session.added == []


def test_process_report_readiness_ignores_latest_stale_event_reports():
    session = _FakeSession()

    async def _fake_resolve(_session, *, process_id):
        assert process_id == 55
        return ([{"event_id": 101}, {"event_id": 103}], 3)

    reporting._resolve_process_event_payloads, original = _fake_resolve, reporting._resolve_process_event_payloads
    try:
        result = asyncio.run(reporting._process_report_readiness(session, process_id=55))
    finally:
        reporting._resolve_process_event_payloads = original

    assert result["ready"] is False
    assert result["ready_event_reports"] == 2
    assert result["required_ready_event_reports"] == 3
    assert result["reason"] == "waiting_event_reports"


def test_event_report_readiness_ignores_latest_stale_post_reports():
    session = _FakeSession(
        execute_results=[
            _FakeRowsResult(
                [
                    (201, "root", 25, {"status": "stale"}),
                    (202, "member", 24, {"status": "ready"}),
                    (203, "member", 31, {"status": "ready"}),
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


def test_process_event_loader_ignores_latest_stale_report_and_uses_previous_non_stale():
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

    assert result == [{"status": "ready", "summary": "usable", "event_id": 101, "event_title": "Event 101"}]


def test_process_event_loader_falls_back_to_post_reports_when_latest_event_reports_are_stale(monkeypatch):
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

    assert result == [
        {
            "status": "ready",
            "event_id": 102,
            "event_title": "Event 102",
            "summary": "rebuilt from 1 posts",
        }
    ]


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
