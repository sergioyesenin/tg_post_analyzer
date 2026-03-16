import asyncio
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import VerificationStatus
from services.events.build_events import rebuild_events


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


def test_rebuild_events_preserves_cross_window_memberships_and_root(monkeypatch) -> None:
    in_window_post = SimpleNamespace(id=2, date=datetime(2026, 3, 2), text="Second", created_at=datetime(2026, 3, 2))
    earlier_post = SimpleNamespace(id=1, date=datetime(2026, 3, 1), text="First", created_at=datetime(2026, 3, 1))
    link = SimpleNamespace(
        src_post_id=1,
        dst_post_id=2,
        status=VerificationStatus.VERIFIED,
        link_type="same_event",
        score=0.9,
        evidence_json={"edge": "1-2"},
        model_version="test",
        pipeline_version="test",
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([in_window_post]),
            _FakeScalarsResult([link]),
            _FakeRowsResult([]),
            _FakeScalarsResult([link]),
            _FakeRowsResult([]),
            _FakeScalarsResult([earlier_post, in_window_post]),
            _FakeScalarsResult([link]),
            _FakeScalarsResult([]),
        ]
    )
    inserts: list[_FakeInsertStatement] = []

    def _fake_insert(_model):
        stmt = _FakeInsertStatement()
        inserts.append(stmt)
        return stmt

    monkeypatch.setattr("services.events.build_events.insert", _fake_insert)

    rebuilt = asyncio.run(
        rebuild_events(
            session,
            date_from=datetime(2026, 3, 2),
            date_to=datetime(2026, 3, 2, 23, 59, 59),
        )
    )

    assert rebuilt == 1
    assert len(inserts) == 2
    assert {stmt.payload["post_id"] for stmt in inserts} == {1, 2}
    roles_by_post_id = {stmt.payload["post_id"]: stmt.payload["role"] for stmt in inserts}
    assert roles_by_post_id == {1: "root", 2: "context"}
