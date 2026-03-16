import asyncio
from types import SimpleNamespace

import pytest

from services import pipeline_runtime


class _FakeSession:
    def __init__(self, job):
        self.job = job
        self.commit_calls = 0
        self.flush_calls = 0

    async def get(self, model, job_id: int):
        if job_id == self.job.id:
            return self.job
        return None

    async def commit(self):
        self.commit_calls += 1

    async def flush(self):
        self.flush_calls += 1


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_add_channel_job_persists_result_and_marks_job_done(monkeypatch):
    job = SimpleNamespace(
        id=91,
        type="add_channel",
        status="running",
        priority=5,
        run_at=None,
        retry_at=None,
        attempts=1,
        max_attempts=3,
        locked_by="worker-1",
        locked_at=None,
        heartbeat_at=None,
        last_error=None,
        created_at=None,
        updated_at=None,
        payload_json={"username": "new_channel", "requested_by_user_id": 7},
    )
    session = _FakeSession(job)
    audit_calls = []

    async def _fake_resolve_and_upsert_channel(*, tg_client, session, raw_username):
        assert raw_username == "new_channel"
        return (
            SimpleNamespace(id=5, username="new_channel", title="New Channel"),
            {"status": "created", "channel_id": 5, "username": "new_channel", "title": "New Channel"},
        )

    async def _fake_write_audit_log(*_args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", lambda: _FakeSessionContext(session))
    monkeypatch.setattr(pipeline_runtime, "resolve_and_upsert_channel", _fake_resolve_and_upsert_channel)
    monkeypatch.setattr(pipeline_runtime, "write_audit_log", _fake_write_audit_log)

    tg_client = SimpleNamespace(operation_lock=asyncio.Lock())

    executed = await pipeline_runtime._run_add_channel_job(job=job, tg_client=tg_client, worker_id="worker-1")

    assert executed == 1
    assert session.commit_calls == 1
    assert job.status == "done"
    assert job.locked_by is None
    assert job.payload_json["_job_result"] == {
        "status": "created",
        "channel_id": 5,
        "username": "new_channel",
        "title": "New Channel",
    }
    assert audit_calls[0]["action"] == "channels.add.executed"
