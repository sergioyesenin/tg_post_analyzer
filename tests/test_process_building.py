import asyncio
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

from sqlalchemy.sql.dml import Delete

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import Event, LinkDirection, ProcessEvent, ProcessRelationType, VerificationStatus
from services.processes.build_processes import _build_update_components, rebuild_processes


def test_build_update_components_applies_transitivity() -> None:
    links = [
        SimpleNamespace(
            src_post_id=101,
            dst_post_id=102,
            score=0.8,
            evidence_json={"edge": "a-b"},
            model_version="test",
            pipeline_version="test",
        ),
        SimpleNamespace(
            src_post_id=201,
            dst_post_id=202,
            score=0.9,
            evidence_json={"edge": "b-c"},
            model_version="test",
            pipeline_version="test",
        ),
    ]
    post_to_event_ids = {
        101: {1},
        102: {2},
        201: {2},
        202: {3},
    }

    components, payload = _build_update_components(
        event_ids={1, 2, 3},
        post_to_event_ids=post_to_event_ids,
        links=links,
    )

    assert sorted(sorted(component) for component in components) == [[1, 2, 3]]
    assert set(payload) == {1, 2, 3}


def test_build_update_components_ignores_edges_without_cross_event_mapping() -> None:
    links = [
        SimpleNamespace(
            src_post_id=101,
            dst_post_id=102,
            score=0.8,
            evidence_json={"edge": "same-event"},
            model_version="test",
            pipeline_version="test",
        ),
    ]
    post_to_event_ids = {
        101: {1},
        102: {1},
    }

    components, payload = _build_update_components(
        event_ids={1},
        post_to_event_ids=post_to_event_ids,
        links=links,
    )

    assert components == []
    assert payload == {}


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return type("_Scalars", (), {"all": lambda self_: list(self._rows)})()

    def all(self):
        return list(self._rows)


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeInsertStatement:
    def __init__(self):
        self.payload = None
        self.conflict_ignored = False

    def values(self, **kwargs):
        self.payload = kwargs
        return self

    def on_conflict_do_nothing(self):
        self.conflict_ignored = True
        return self


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.added = []
        self.flush_calls = 0
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeRowsResult([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1
        for index, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = index


class _RoutingSession(_FakeSession):
    def __init__(self, handler):
        super().__init__(execute_results=[])
        self._handler = handler

    async def execute(self, stmt):
        self.executed.append(stmt)
        return self._handler(stmt)


def test_process_event_cardinality_is_one_row_per_process_event_pair() -> None:
    unique_names = {constraint.name for constraint in ProcessEvent.__table__.constraints if constraint.name}

    assert {"process_id", "event_id"} == {column.name for column in ProcessEvent.__table__.primary_key.columns}
    assert "uq_process_events_proc_event_relation" not in unique_names


def test_rebuild_processes_creates_single_membership_per_event(monkeypatch) -> None:
    event_a = Event(id=1, title="A", started_at=None, ended_at=None, confidence=0.4, status=VerificationStatus.VERIFIED)
    event_b = Event(id=2, title="B", started_at=None, ended_at=None, confidence=0.6, status=VerificationStatus.VERIFIED)
    link = SimpleNamespace(
        src_post_id=101,
        dst_post_id=102,
        status=VerificationStatus.VERIFIED,
        link_type="update",
        score=0.9,
        evidence_json={"edge": "a-b"},
        model_version="test",
        pipeline_version="test",
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([event_a, event_b]),
            _FakeRowsResult([]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeScalarsResult([link]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeRowsResult([]),
            _FakeScalarsResult([event_a, event_b]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeScalarsResult([link]),
        ]
    )
    inserts: list[_FakeInsertStatement] = []

    def _fake_insert(_model):
        stmt = _FakeInsertStatement()
        inserts.append(stmt)
        return stmt

    monkeypatch.setattr("services.processes.build_processes.insert", _fake_insert)

    created = asyncio.run(
        rebuild_processes(
            session,
            date_from=datetime(2026, 3, 1),
            date_to=datetime(2026, 3, 31),
        )
    )

    assert created == 2
    assert len(inserts) == 2
    assert all(stmt.conflict_ignored for stmt in inserts)
    assert {(stmt.payload["process_id"], stmt.payload["event_id"]) for stmt in inserts} == {(1, 1), (1, 2)}
    assert all(stmt.payload["relation_type"] == ProcessRelationType.UPDATE for stmt in inserts)
    assert all(stmt.payload["direction"] == LinkDirection.NONE for stmt in inserts)


def test_rebuild_processes_preserves_cross_window_event_memberships(monkeypatch) -> None:
    in_window_event = Event(
        id=2,
        title="B",
        started_at=datetime(2026, 3, 2),
        ended_at=datetime(2026, 3, 2),
        confidence=0.6,
        status=VerificationStatus.VERIFIED,
    )
    earlier_event = Event(
        id=1,
        title="A",
        started_at=datetime(2026, 3, 1),
        ended_at=datetime(2026, 3, 1),
        confidence=0.4,
        status=VerificationStatus.VERIFIED,
    )
    link = SimpleNamespace(
        src_post_id=101,
        dst_post_id=102,
        status=VerificationStatus.VERIFIED,
        link_type="update",
        score=0.9,
        evidence_json={"edge": "a-b"},
        model_version="test",
        pipeline_version="test",
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([in_window_event]),
            _FakeRowsResult([]),
            _FakeRowsResult([(102, 2)]),
            _FakeScalarsResult([link]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeRowsResult([]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeScalarsResult([link]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeRowsResult([]),
            _FakeScalarsResult([earlier_event, in_window_event]),
            _FakeRowsResult([(101, 1), (102, 2)]),
            _FakeScalarsResult([link]),
        ]
    )
    inserts: list[_FakeInsertStatement] = []

    def _fake_insert(_model):
        stmt = _FakeInsertStatement()
        inserts.append(stmt)
        return stmt

    monkeypatch.setattr("services.processes.build_processes.insert", _fake_insert)

    created = asyncio.run(
        rebuild_processes(
            session,
            date_from=datetime(2026, 3, 2),
            date_to=datetime(2026, 3, 2, 23, 59, 59),
        )
    )

    assert created == 2
    assert len(inserts) == 2
    assert {(stmt.payload["process_id"], stmt.payload["event_id"]) for stmt in inserts} == {(1, 1), (1, 2)}


def test_rebuild_processes_reuses_existing_process_id_and_updates_membership_diff(monkeypatch) -> None:
    event_a = Event(id=1, title="A", started_at=datetime(2026, 3, 10), ended_at=datetime(2026, 3, 10), confidence=0.4, status=VerificationStatus.VERIFIED)
    event_b = Event(id=2, title="B", started_at=datetime(2026, 3, 11), ended_at=datetime(2026, 3, 11), confidence=0.6, status=VerificationStatus.VERIFIED)
    event_c = Event(id=3, title="C", started_at=datetime(2026, 3, 12), ended_at=datetime(2026, 3, 12), confidence=0.7, status=VerificationStatus.VERIFIED)
    existing_process = SimpleNamespace(
        id=55,
        title="Old process",
        started_at=datetime(2026, 3, 9),
        ended_at=datetime(2026, 3, 11),
        confidence=0.1,
        status=VerificationStatus.PROPOSED,
        created_by="seed",
    )
    membership_a = SimpleNamespace(
        process_id=55,
        event_id=1,
        relation_type=ProcessRelationType.UPDATE,
        direction=LinkDirection.NONE,
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    membership_b = SimpleNamespace(
        process_id=55,
        event_id=2,
        relation_type=ProcessRelationType.UPDATE,
        direction=LinkDirection.NONE,
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    link_a = SimpleNamespace(
        src_post_id=101,
        dst_post_id=102,
        status=VerificationStatus.VERIFIED,
        link_type="update",
        score=0.9,
        evidence_json={"edge": "a-b"},
        model_version="test",
        pipeline_version="test",
    )
    link_b = SimpleNamespace(
        src_post_id=201,
        dst_post_id=202,
        status=VerificationStatus.VERIFIED,
        link_type="update",
        score=0.95,
        evidence_json={"edge": "b-c"},
        model_version="test",
        pipeline_version="test",
    )
    def _handle(stmt):
        if isinstance(stmt, _FakeInsertStatement):
            return _FakeRowsResult([])
        sql = str(stmt)
        if "SELECT events.id, events.title" in sql and "events.started_at >=" in sql:
            return _FakeScalarsResult([event_a, event_c])
        if "SELECT DISTINCT process_events.process_id" in sql:
            return _FakeRowsResult([(55,)])
        if "SELECT process_events.event_id" in sql:
            return _FakeRowsResult([(1,), (2,)])
        if "SELECT event_posts.post_id, event_posts.event_id" in sql:
            return _FakeRowsResult([(101, 1), (102, 2), (201, 2), (202, 3)])
        if "FROM post_links" in sql:
            return _FakeScalarsResult([link_a, link_b])
        if "SELECT processes.title" in sql or "SELECT processes.id, processes.title" in sql:
            return _FakeScalarsResult([existing_process])
        if "SELECT processes.id" in sql:
            return _FakeRowsResult([])
        if "SELECT process_events.process_id, process_events.event_id" in sql or "SELECT process_events.process_id," in sql:
            return _FakeScalarsResult([membership_a, membership_b])
        if "SELECT events.id, events.title" in sql and "events.id IN" in sql:
            return _FakeScalarsResult([event_a, event_b, event_c])
        raise AssertionError(f"Unhandled SQL: {sql}")

    session = _RoutingSession(_handle)
    inserts: list[_FakeInsertStatement] = []

    def _fake_insert(_model):
        stmt = _FakeInsertStatement()
        inserts.append(stmt)
        return stmt

    monkeypatch.setattr("services.processes.build_processes.insert", _fake_insert)

    created = asyncio.run(
        rebuild_processes(
            session,
            date_from=datetime(2026, 3, 10),
            date_to=datetime(2026, 3, 31),
        )
    )

    assert created == 1
    assert session.added == []
    assert existing_process.id == 55
    assert existing_process.title == "A"
    assert existing_process.status == VerificationStatus.VERIFIED
    assert membership_a.status == VerificationStatus.VERIFIED
    assert len(inserts) == 1
    assert inserts[0].payload["process_id"] == 55
    assert inserts[0].payload["event_id"] == 3


def test_rebuild_processes_preserves_stale_process_entity_and_only_clears_membership(monkeypatch) -> None:
    event_a = Event(id=1, title="Shared", started_at=datetime(2026, 3, 10), ended_at=datetime(2026, 3, 10), confidence=0.4, status=VerificationStatus.VERIFIED)
    event_b = Event(id=2, title="Shared", started_at=datetime(2026, 3, 11), ended_at=datetime(2026, 3, 11), confidence=0.6, status=VerificationStatus.VERIFIED)
    event_c = Event(id=3, title="Shared", started_at=datetime(2026, 3, 12), ended_at=datetime(2026, 3, 12), confidence=0.7, status=VerificationStatus.VERIFIED)
    process_primary = SimpleNamespace(
        id=41,
        title="Shared",
        started_at=datetime(2026, 3, 10),
        ended_at=datetime(2026, 3, 10),
        confidence=0.1,
        status=VerificationStatus.PROPOSED,
        created_by="seed",
    )
    process_absorbed = SimpleNamespace(
        id=42,
        title="Shared",
        started_at=datetime(2026, 3, 11),
        ended_at=datetime(2026, 3, 11),
        confidence=0.1,
        status=VerificationStatus.VERIFIED,
        created_by="seed",
    )
    membership_primary = SimpleNamespace(
        process_id=41,
        event_id=1,
        relation_type=ProcessRelationType.UPDATE,
        direction=LinkDirection.NONE,
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    membership_absorbed = SimpleNamespace(
        process_id=42,
        event_id=2,
        relation_type=ProcessRelationType.UPDATE,
        direction=LinkDirection.NONE,
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    link = SimpleNamespace(
        src_post_id=101,
        dst_post_id=102,
        status=VerificationStatus.VERIFIED,
        link_type="update",
        score=0.9,
        evidence_json={"edge": "a-b"},
        model_version="test",
        pipeline_version="test",
    )
    def _handle(stmt):
        if isinstance(stmt, _FakeInsertStatement):
            return _FakeRowsResult([])
        sql = str(stmt)
        if "DELETE FROM process_events" in sql:
            return _FakeRowsResult([])
        if "SELECT events.id, events.title" in sql and "events.started_at >=" in sql:
            return _FakeScalarsResult([event_a, event_b])
        if "SELECT DISTINCT process_events.process_id" in sql:
            return _FakeRowsResult([(41,), (42,)])
        if "SELECT process_events.event_id" in sql:
            return _FakeRowsResult([(1,), (2,)])
        if "SELECT event_posts.post_id, event_posts.event_id" in sql:
            return _FakeRowsResult([(101, 1), (102, 2), (202, 2), (203, 3)])
        if "FROM post_links" in sql:
            return _FakeScalarsResult([link])
        if "SELECT processes.title" in sql or "SELECT processes.id, processes.title" in sql:
            return _FakeScalarsResult([process_primary, process_absorbed])
        if "SELECT processes.id" in sql:
            return _FakeRowsResult([])
        if "SELECT process_events.process_id, process_events.event_id" in sql or "SELECT process_events.process_id," in sql:
            return _FakeScalarsResult([membership_primary, membership_absorbed])
        if "SELECT events.id, events.title" in sql and "events.id IN" in sql:
            return _FakeScalarsResult([event_a, event_b, event_c])
        raise AssertionError(f"Unhandled SQL: {sql}")

    session = _RoutingSession(_handle)
    inserts: list[_FakeInsertStatement] = []

    def _fake_insert(_model):
        stmt = _FakeInsertStatement()
        inserts.append(stmt)
        return stmt

    monkeypatch.setattr("services.processes.build_processes.insert", _fake_insert)

    created = asyncio.run(
        rebuild_processes(
            session,
            date_from=datetime(2026, 3, 10),
            date_to=datetime(2026, 3, 31),
        )
    )

    assert created == 1
    assert process_primary.id == 41
    assert process_primary.status == VerificationStatus.VERIFIED
    assert process_absorbed.id == 42
    assert process_absorbed.status == VerificationStatus.REJECTED
    assert len(inserts) == 1
    assert inserts[0].payload["process_id"] == 41
    assert inserts[0].payload["event_id"] == 2
    delete_sql = "\n".join(str(stmt) for stmt in session.executed if isinstance(stmt, Delete))
    assert "DELETE FROM process_events" in delete_sql
    assert "DELETE FROM processes" not in delete_sql
