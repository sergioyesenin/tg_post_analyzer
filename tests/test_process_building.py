import asyncio
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

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
            _FakeRowsResult([]),
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
