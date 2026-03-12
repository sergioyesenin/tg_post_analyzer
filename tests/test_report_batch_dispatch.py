from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services import pipeline_runtime


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        return _FakeRowsResult(self.rows)


def test_dispatch_post_report_batch_enqueues_deduped_child_jobs(monkeypatch):
    session = _FakeSession(rows=[(11,), (12,), (13,)])
    enqueued = []

    async def _fake_enqueue_post_report_job(_session, *, post_id: int, priority: int, source: str, dedupe_key: str | None):
        enqueued.append(
            {
                "post_id": post_id,
                "priority": priority,
                "source": source,
                "dedupe_key": dedupe_key,
            }
        )
        if post_id == 12:
            return None
        return SimpleNamespace(id=post_id + 1000)

    monkeypatch.setattr(pipeline_runtime, "enqueue_post_report_job", _fake_enqueue_post_report_job)

    result = asyncio.run(
        pipeline_runtime.dispatch_post_report_batch(
            session,
            filters={
                "channel_ids": [7],
                "categories": ["regional"],
                "date_from": None,
                "date_to": None,
                "min_comments": 3,
                "limit": 50,
            },
        )
    )

    assert session.execute_calls == 1
    assert result == {
        "status": "queued",
        "matched_posts": 3,
        "queued_jobs": 2,
        "skipped_existing": 1,
        "post_ids": [11, 12, 13],
        "job_ids": [1011, 1013],
        "filters": {
            "channel_ids": [7],
            "categories": ["regional"],
            "date_from": None,
            "date_to": None,
            "min_comments": 3,
            "limit": 50,
        },
    }
    assert enqueued == [
        {
            "post_id": 11,
            "priority": pipeline_runtime.PRIORITY_BUILD_POST_REPORT,
            "source": "batch",
            "dedupe_key": "build_post_report:11",
        },
        {
            "post_id": 12,
            "priority": pipeline_runtime.PRIORITY_BUILD_POST_REPORT,
            "source": "batch",
            "dedupe_key": "build_post_report:12",
        },
        {
            "post_id": 13,
            "priority": pipeline_runtime.PRIORITY_BUILD_POST_REPORT,
            "source": "batch",
            "dedupe_key": "build_post_report:13",
        },
    ]
