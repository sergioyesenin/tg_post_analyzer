from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from services.dashboard import events_dashboard, posts_dashboard, processes_dashboard


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return type("_Scalars", (), {"all": lambda self_: list(self._rows)})()


class _FakeScalarLinks:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return type("_Scalars", (), {"all": lambda self_: list(self._rows)})()


class _FakeSession:
    def __init__(self, *, execute_results=None, get_map=None):
        self.execute_results = list(execute_results or [])
        self.get_map = get_map or {}

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("Unexpected execute() call")
        return self.execute_results.pop(0)

    async def get(self, model, key):
        return self.get_map.get((model.__name__, key))


def test_posts_dashboard_filters_report_status_and_marks_partial(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    post_ready = SimpleNamespace(id=10, channel_id=1, date=now, text="ready post", comments_count=15, views=100, involvement=0.1)
    post_missing = SimpleNamespace(id=11, channel_id=2, date=now, text="missing post", comments_count=8, views=50, involvement=0.05)
    channel_a = SimpleNamespace(id=1, username="chan_a", title="A", category="news")
    channel_b = SimpleNamespace(id=2, username="chan_b", title="B", category="news")
    session = _FakeSession(execute_results=[_FakeRowsResult([(post_ready, channel_a), (post_missing, channel_b)])])

    async def _fake_report_statuses(_session, post_ids):
        assert post_ids == [10, 11]
        return {10: "ready", 11: "missing"}

    async def _broken_link_counts(_session, post_ids):
        assert post_ids == [10]
        raise RuntimeError("links unavailable")

    monkeypatch.setattr(posts_dashboard, "load_post_report_statuses", _fake_report_statuses)
    monkeypatch.setattr(posts_dashboard, "load_post_link_counts", _broken_link_counts)
    monkeypatch.setattr(posts_dashboard, "utcnow", lambda: now)

    payload = asyncio.run(
        posts_dashboard.build_posts_dashboard(
            session,
            date_from=now,
            date_to=now,
            limit=20,
            channel_ids=[],
            categories=[],
            min_comments=None,
            report_status=["ready"],
            sort_by="comments_count",
            sort_order="desc",
            comments_refresh_available=True,
        )
    )

    assert payload.partial is True
    assert payload.summary.posts_count == 1
    assert payload.summary.reports_ready == 1
    assert payload.summary.reports_missing == 0
    assert payload.items[0].post_id == 10
    assert payload.items[0].report_status == "ready"
    assert payload.warnings[0].code == "post_link_counts_unavailable"


def test_events_dashboard_returns_empty_snapshot(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession(execute_results=[_FakeScalarsResult([])])
    monkeypatch.setattr(events_dashboard, "utcnow", lambda: now)
    monkeypatch.setattr(events_dashboard, "load_event_post_rows", lambda _session, _ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(events_dashboard, "load_latest_event_report_statuses", lambda _session, _ids: asyncio.sleep(0, result={}))

    payload = asyncio.run(
        events_dashboard.build_events_dashboard(
            session,
            date_from=None,
            date_to=None,
            limit=20,
            status=[],
            channel_ids=[],
            categories=[],
            min_comments=None,
            sort_by="started_at",
            sort_order="desc",
        )
    )

    assert payload.summary.events_count == 0
    assert payload.items == []
    assert payload.partial is False


def test_processes_dashboard_sorts_by_comments_desc_and_keeps_draft(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    process_a = SimpleNamespace(id=1, title="P1", status="proposed", started_at=now, ended_at=None, confidence=0.9)
    process_b = SimpleNamespace(id=2, title="P2", status="proposed", started_at=now, ended_at=None, confidence=0.8)
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([process_a, process_b]),
            _FakeRowsResult([(1, 101, "related", "src_to_dst", 0.7), (2, 102, "related", "src_to_dst", 0.5)]),
            _FakeRowsResult([(101, 1001, 30, 0.3), (102, 1002, 10, 0.1)]),
        ]
    )

    async def _fake_statuses(_session, process_ids):
        assert process_ids == [1, 2]
        return {1: "draft", 2: "failed"}

    monkeypatch.setattr(processes_dashboard, "load_latest_process_report_statuses", _fake_statuses)
    monkeypatch.setattr(processes_dashboard, "utcnow", lambda: now)

    payload = asyncio.run(
        processes_dashboard.build_processes_dashboard(
            session,
            date_from=None,
            date_to=None,
            limit=20,
            status=[],
            min_comments=None,
            sort_by="comments_count",
            sort_order="desc",
        )
    )

    assert [item.process_id for item in payload.items] == [1, 2]
    assert payload.items[0].report_status == "draft"
    assert payload.summary.draft_reports == 1
    assert payload.summary.failed_reports == 1


def test_event_graph_payload_shape(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    event = SimpleNamespace(id=5, title="Event", status="proposed", started_at=now, ended_at=None, confidence=0.87)
    link = SimpleNamespace(
        id=77,
        src_post_id=101,
        dst_post_id=102,
        link_type="related",
        direction="src_to_dst",
        score=0.81,
        status="verified",
    )
    session = _FakeSession(
        get_map={("Event", 5): event},
        execute_results=[
            _FakeRowsResult(
                [
                    ("root", 101, 1, "channel_a", now, "root text", 50, 1000, 0.2),
                    ("context", 102, 1, "channel_a", now, "child text", 20, 500, 0.1),
                ]
            ),
            _FakeScalarLinks([link]),
        ],
    )

    async def _fake_statuses(_session, event_ids):
        assert event_ids == [5]
        return {5: "draft"}

    monkeypatch.setattr(events_dashboard, "load_latest_event_report_statuses", _fake_statuses)

    payload = asyncio.run(events_dashboard.build_event_graph(session, event_id=5))

    assert payload is not None
    assert payload.event.report_status == "draft"
    assert payload.nodes[0].is_root is True
    assert payload.edges[0].link_id == 77


def test_process_graph_payload_shape(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    process = SimpleNamespace(id=5, title="Process", status="verified", started_at=now, ended_at=None, confidence=0.87)
    link = SimpleNamespace(
        id=88,
        src_post_id=101,
        dst_post_id=102,
        link_type="update",
        direction="src_to_dst",
        score=0.76,
        status="verified",
    )
    session = _FakeSession(
        get_map={("Process", 5): process},
        execute_results=[
            _FakeRowsResult(
                [
                    (11, "update", "none", 0.91, "Event A", "verified", now, None, 0.8),
                    (12, "update", "none", 0.87, "Event B", "verified", now, None, 0.7),
                ]
            ),
            _FakeRowsResult(
                [
                    (11, "root", 101, 1, "channel_a", now, "root text", 40, 1000, 0.2),
                    (12, "context", 102, 1, "channel_a", now, "child text", 10, 500, 0.1),
                ]
            ),
            _FakeScalarLinks([link]),
        ],
    )

    async def _fake_statuses(_session, process_ids):
        assert process_ids == [5]
        return {5: "draft"}

    monkeypatch.setattr(processes_dashboard, "load_latest_process_report_statuses", _fake_statuses)

    payload = asyncio.run(processes_dashboard.build_process_graph(session, process_id=5))

    assert payload is not None
    assert payload.summary.report_status == "draft"
    assert payload.summary.events_count == 2
    assert payload.events[0].event_id == 11
    assert payload.mapping.event_to_post_ids == {11: [101], 12: [102]}
    assert payload.edges[0].link_id == 88


def test_process_graph_deduplicates_shared_posts_across_events(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    process = SimpleNamespace(id=9, title="Process", status="verified", started_at=now, ended_at=None, confidence=0.77)
    session = _FakeSession(
        get_map={("Process", 9): process},
        execute_results=[
            _FakeRowsResult(
                [
                    (11, "update", "none", 0.91, "Event A", "verified", now, None, 0.8),
                    (12, "update", "none", 0.87, "Event B", "verified", now, None, 0.7),
                ]
            ),
            _FakeRowsResult(
                [
                    (11, "root", 101, 1, "channel_a", now, "shared root", 40, 1000, 0.2),
                    (12, "context", 101, 1, "channel_a", now, "shared root", 40, 1000, 0.2),
                ]
            ),
            _FakeScalarLinks([]),
        ],
    )

    async def _fake_statuses(_session, process_ids):
        assert process_ids == [9]
        return {9: "draft"}

    monkeypatch.setattr(processes_dashboard, "load_latest_process_report_statuses", _fake_statuses)

    payload = asyncio.run(processes_dashboard.build_process_graph(session, process_id=9))

    assert payload is not None
    assert payload.summary.posts_count == 1
    assert len(payload.nodes) == 1
    assert payload.mapping.event_to_post_ids == {11: [101], 12: [101]}


def test_processes_dashboard_deduplicates_shared_posts_in_comments_aggregation(monkeypatch):
    now = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    process = SimpleNamespace(id=1, title="P1", status="proposed", started_at=now, ended_at=None, confidence=0.9)
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([process]),
            _FakeRowsResult([(1, 101, "related", "src_to_dst", 0.7), (1, 102, "related", "src_to_dst", 0.5)]),
            _FakeRowsResult([(101, 1001, 30, 0.3), (102, 1001, 30, 0.3)]),
        ]
    )

    async def _fake_statuses(_session, process_ids):
        assert process_ids == [1]
        return {1: "draft"}

    monkeypatch.setattr(processes_dashboard, "load_latest_process_report_statuses", _fake_statuses)
    monkeypatch.setattr(processes_dashboard, "utcnow", lambda: now)

    payload = asyncio.run(
        processes_dashboard.build_processes_dashboard(
            session,
            date_from=None,
            date_to=None,
            limit=20,
            status=[],
            min_comments=None,
            sort_by="comments_count",
            sort_order="desc",
        )
    )

    assert payload.items[0].comments_count == 30
