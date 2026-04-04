import asyncio
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

from sqlalchemy.sql.dml import Delete

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


def test_rebuild_events_merges_disconnected_components_with_same_title(monkeypatch) -> None:
    post_one = SimpleNamespace(
        id=1,
        date=datetime(2026, 3, 25, 10, 0, 0),
        text="вќ—пёЏ Р’ Р‘РµР»Р°СЂСѓСЃРё РїРѕСЏРІРёР»СЃСЏ РЅРѕРІС‹Р№ СЃРїРѕСЃРѕР± РјРѕС€РµРЅРЅРёС‡РµСЃС‚РІР°",
        created_at=datetime(2026, 3, 25, 10, 0, 0),
    )
    post_two = SimpleNamespace(
        id=2,
        date=datetime(2026, 3, 25, 11, 0, 0),
        text="вќ—пёЏ Р’ Р‘РµР»Р°СЂСѓСЃРё РїРѕСЏРІРёР»СЃСЏ РЅРѕРІС‹Р№ СЃРїРѕСЃРѕР± РјРѕС€РµРЅРЅРёС‡РµСЃС‚РІР°",
        created_at=datetime(2026, 3, 25, 11, 0, 0),
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([post_one, post_two]),
            _FakeScalarsResult([]),
            _FakeRowsResult([]),
            _FakeScalarsResult([post_one, post_two]),
            _FakeScalarsResult([]),
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
            date_from=datetime(2026, 3, 25, 0, 0, 0),
            date_to=datetime(2026, 3, 25, 23, 59, 59),
        )
    )

    assert rebuilt == 1
    assert len(session.added) == 1
    assert session.added[0].title == "вќ—пёЏ Р’ Р‘РµР»Р°СЂСѓСЃРё РїРѕСЏРІРёР»СЃСЏ РЅРѕРІС‹Р№ СЃРїРѕСЃРѕР± РјРѕС€РµРЅРЅРёС‡РµСЃС‚РІР°"
    assert len(inserts) == 2
    assert {stmt.payload["post_id"] for stmt in inserts} == {1, 2}


def test_rebuild_events_reuses_existing_event_id_and_updates_membership_diff(monkeypatch) -> None:
    post_one = SimpleNamespace(id=1, date=datetime(2026, 3, 20, 10, 0, 0), text="Alpha", created_at=datetime(2026, 3, 20, 10, 0, 0))
    post_two = SimpleNamespace(id=2, date=datetime(2026, 3, 20, 11, 0, 0), text="Beta", created_at=datetime(2026, 3, 20, 11, 0, 0))
    post_three = SimpleNamespace(id=3, date=datetime(2026, 3, 20, 12, 0, 0), text="Gamma", created_at=datetime(2026, 3, 20, 12, 0, 0))
    existing_event = SimpleNamespace(
        id=77,
        title="Old title",
        started_at=datetime(2026, 3, 20, 9, 0, 0),
        ended_at=datetime(2026, 3, 20, 11, 0, 0),
        confidence=0.2,
        status=VerificationStatus.PROPOSED,
        created_by="seed",
    )
    membership_one = SimpleNamespace(
        event_id=77,
        post_id=1,
        role="root",
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    membership_two = SimpleNamespace(
        event_id=77,
        post_id=2,
        role="context",
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    link_a = SimpleNamespace(
        src_post_id=1,
        dst_post_id=3,
        status=VerificationStatus.VERIFIED,
        link_type="same_event",
        score=0.9,
        evidence_json={"edge": "1-3"},
        model_version="test",
        pipeline_version="test",
    )
    link_b = SimpleNamespace(
        src_post_id=2,
        dst_post_id=3,
        status=VerificationStatus.VERIFIED,
        link_type="same_event",
        score=0.9,
        evidence_json={"edge": "2-3"},
        model_version="test",
        pipeline_version="test",
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([post_one, post_three]),
            _FakeScalarsResult([link_a, link_b]),
            _FakeRowsResult([(77,)]),
            _FakeRowsResult([(1,), (2,)]),
            _FakeScalarsResult([link_a, link_b]),
            _FakeRowsResult([(77,)]),
            _FakeRowsResult([(1,), (2,)]),
            _FakeScalarsResult([post_one, post_two, post_three]),
            _FakeScalarsResult([link_a, link_b]),
            _FakeScalarsResult([]),
            _FakeScalarsResult([existing_event]),
            _FakeScalarsResult([membership_one, membership_two]),
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
            date_from=datetime(2026, 3, 20, 0, 0, 0),
            date_to=datetime(2026, 3, 20, 23, 59, 59),
        )
    )

    assert rebuilt == 1
    assert session.added == []
    assert existing_event.id == 77
    assert existing_event.title == "Alpha"
    assert existing_event.status == VerificationStatus.VERIFIED
    assert membership_one.role == "root"
    assert membership_one.status == VerificationStatus.VERIFIED
    assert len(inserts) == 1
    assert inserts[0].payload["event_id"] == 77
    assert inserts[0].payload["post_id"] == 3


def test_rebuild_events_preserves_stale_event_entity_and_only_clears_membership(monkeypatch) -> None:
    post_one = SimpleNamespace(id=1, date=datetime(2026, 3, 21, 10, 0, 0), text="Shared title", created_at=datetime(2026, 3, 21, 10, 0, 0))
    post_two = SimpleNamespace(id=2, date=datetime(2026, 3, 21, 11, 0, 0), text="Shared title", created_at=datetime(2026, 3, 21, 11, 0, 0))
    event_primary = SimpleNamespace(
        id=41,
        title="Shared title",
        started_at=datetime(2026, 3, 21, 10, 0, 0),
        ended_at=datetime(2026, 3, 21, 11, 0, 0),
        confidence=0.2,
        status=VerificationStatus.PROPOSED,
        created_by="seed",
    )
    event_absorbed = SimpleNamespace(
        id=42,
        title="Shared title",
        started_at=datetime(2026, 3, 21, 11, 0, 0),
        ended_at=datetime(2026, 3, 21, 11, 0, 0),
        confidence=0.2,
        status=VerificationStatus.VERIFIED,
        created_by="seed",
    )
    membership_primary = SimpleNamespace(
        event_id=41,
        post_id=1,
        role="root",
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    membership_absorbed = SimpleNamespace(
        event_id=42,
        post_id=2,
        role="root",
        evidence_json={"anchors": {}},
        score=0.1,
        status=VerificationStatus.PROPOSED,
        model_version="old",
        pipeline_version="old",
    )
    session = _FakeSession(
        execute_results=[
            _FakeScalarsResult([post_one, post_two]),
            _FakeScalarsResult([]),
            _FakeRowsResult([(41,), (42,)]),
            _FakeRowsResult([(1,), (2,)]),
            _FakeScalarsResult([]),
            _FakeRowsResult([(41,), (42,)]),
            _FakeRowsResult([(1,), (2,)]),
            _FakeScalarsResult([post_one, post_two]),
            _FakeScalarsResult([]),
            _FakeScalarsResult([]),
            _FakeScalarsResult([event_primary, event_absorbed]),
            _FakeScalarsResult([membership_primary, membership_absorbed]),
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
            date_from=datetime(2026, 3, 21, 0, 0, 0),
            date_to=datetime(2026, 3, 21, 23, 59, 59),
        )
    )

    assert rebuilt == 1
    assert event_primary.id == 41
    assert event_primary.status == VerificationStatus.VERIFIED
    assert event_absorbed.id == 42
    assert event_absorbed.status == VerificationStatus.REJECTED
    assert len(inserts) == 1
    assert inserts[0].payload["event_id"] == 41
    assert inserts[0].payload["post_id"] == 2
    delete_sql = "\n".join(str(stmt) for stmt in session.executed if isinstance(stmt, Delete))
    assert "DELETE FROM event_posts" in delete_sql
    assert "DELETE FROM events" not in delete_sql
