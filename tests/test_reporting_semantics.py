from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_build_post_report_sanitizes_internal_error(monkeypatch):
    channel = SimpleNamespace(id=7, username="test_channel")
    post = SimpleNamespace(id=11, date=SimpleNamespace(isoformat=lambda: "2026-03-11T12:00:00+00:00"), text="post", views=5)
    session = _FakeSession(
        execute_results=[
            type("_PostResult", (), {"first": lambda self_: (post, channel)})(),
            _FakeRowsResult([]),
        ]
    )

    class _BrokenProject:
        async def generate_report(self, **kwargs):
            raise RuntimeError("llm exploded")

    captured = {}

    async def _fake_upsert_report(session, *, post_id, status, content):
        captured.update({"post_id": post_id, "status": status, "content": content})
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
    }


def test_build_event_report_draft_returns_draft_status():
    event = SimpleNamespace(id=5, title="Event")
    session = _FakeSession(
        get_map={("Event", 5): event},
        execute_results=[
            _FakeRowsResult([SimpleNamespace(id=101), SimpleNamespace(id=102)]),
            _FakeScalarResult(2),
        ],
    )

    result = asyncio.run(reporting.build_event_report_draft(session, event_id=5))

    assert result == {"status": "draft", "event_id": 5, "report_id": 1}
    assert session.added[0].report_json["status"] == "draft"
    assert session.added[0].report_json["type"] == "event_report_draft_v1"


def test_build_process_report_draft_returns_draft_status():
    process = SimpleNamespace(id=3, title="Process")
    session = _FakeSession(
        get_map={("Process", 3): process},
        execute_results=[
            _FakeRowsResult([(10, "related", 0.7)]),
            _FakeScalarResult(None),
        ],
    )

    result = asyncio.run(reporting.build_process_report_draft(session, process_id=3))

    assert result == {"status": "draft", "process_id": 3, "report_id": 1}
    assert session.added[0].report_json["status"] == "draft"
    assert session.added[0].report_json["type"] == "process_report_draft_v1"
