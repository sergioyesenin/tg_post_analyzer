from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from db.models import Job
from services.jobs import (
    JobType,
    enqueue_job,
    fetch_and_lock_jobs,
    mark_job_done,
    mark_job_failed,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_dedupe_blocks_duplicate_pending_and_running_jobs(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    dedupe_key = "build_post_report:101"

    async with integration_async_session_factory() as session:
        first = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 101, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert first is not None

    async with integration_async_session_factory() as session:
        duplicate_pending = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 101, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert duplicate_pending is None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-dedupe",
            limit=10,
            allowed_types={JobType.BUILD_POST_REPORT},
        )
        await session.commit()

    assert [job.id for job in locked] == [first.id]

    async with integration_async_session_factory() as session:
        duplicate_running = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 101, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert duplicate_running is None

    with integration_sync_session_factory() as session:
        jobs = session.query(Job).order_by(Job.id.asc()).all()
        assert len(jobs) == 1
        assert jobs[0].status == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_dedupe_allows_reenqueue_after_done(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    dedupe_key = "build_event_report:202"

    async with integration_async_session_factory() as session:
        first = await enqueue_job(
            session,
            job_type=JobType.BUILD_EVENT_REPORT,
            payload={"event_id": 202, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert first is not None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-done",
            limit=10,
            allowed_types={JobType.BUILD_EVENT_REPORT},
        )
        job = locked[0]
        await mark_job_done(session, job=job)
        await session.commit()

    async with integration_async_session_factory() as session:
        reenqueued = await enqueue_job(
            session,
            job_type=JobType.BUILD_EVENT_REPORT,
            payload={"event_id": 202, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert reenqueued is not None
    assert reenqueued.id != first.id

    with integration_sync_session_factory() as session:
        jobs = session.query(Job).filter(Job.dedupe_key == dedupe_key).order_by(Job.id.asc()).all()
        assert [job.status for job in jobs] == ["done", "pending"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_dedupe_keeps_retrying_job_blocked_but_allows_reenqueue_after_terminal_failure(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    dedupe_key = "build_process_report:303"

    async with integration_async_session_factory() as session:
        first = await enqueue_job(
            session,
            job_type=JobType.BUILD_PROCESS_REPORT,
            payload={"process_id": 303, "source": "test"},
            dedupe_key=dedupe_key,
            max_attempts=2,
        )
        await session.commit()

    assert first is not None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-failure",
            limit=10,
            allowed_types={JobType.BUILD_PROCESS_REPORT},
        )
        retrying_job = locked[0]
        await mark_job_failed(session, job=retrying_job, error="transient", retry_base_seconds=0, retry_max_seconds=0)
        await session.commit()

    async with integration_async_session_factory() as session:
        duplicate_pending_retry = await enqueue_job(
            session,
            job_type=JobType.BUILD_PROCESS_REPORT,
            payload={"process_id": 303, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert duplicate_pending_retry is None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-terminal",
            limit=10,
            allowed_types={JobType.BUILD_PROCESS_REPORT},
        )
        terminal_job = locked[0]
        await mark_job_failed(session, job=terminal_job, error="terminal")
        await session.commit()

    async with integration_async_session_factory() as session:
        reenqueued = await enqueue_job(
            session,
            job_type=JobType.BUILD_PROCESS_REPORT,
            payload={"process_id": 303, "source": "test"},
            dedupe_key=dedupe_key,
        )
        await session.commit()

    assert reenqueued is not None
    assert reenqueued.id != first.id

    with integration_sync_session_factory() as session:
        jobs = session.query(Job).filter(Job.dedupe_key == dedupe_key).order_by(Job.id.asc()).all()
        assert [job.status for job in jobs] == ["failed", "pending"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_and_lock_jobs_orders_due_jobs_by_priority_then_effective_due_time(
    integration_async_session_factory,
) -> None:
    now = datetime.now(timezone.utc)

    async with integration_async_session_factory() as session:
        low_priority_early = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 1, "source": "test"},
            priority=50,
            run_at=now - timedelta(minutes=10),
        )
        high_priority_later = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 2, "source": "test"},
            priority=10,
            run_at=now - timedelta(minutes=1),
        )
        same_priority_due_earlier = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 3, "source": "test"},
            priority=20,
            run_at=now - timedelta(minutes=20),
        )
        same_priority_due_later = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 4, "source": "test"},
            priority=20,
            run_at=now - timedelta(minutes=5),
        )
        await session.commit()

    assert low_priority_early is not None
    assert high_priority_later is not None
    assert same_priority_due_earlier is not None
    assert same_priority_due_later is not None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-ordering",
            limit=10,
            allowed_types={JobType.BUILD_POST_REPORT},
        )
        await session.commit()

    assert [job.id for job in locked] == [
        high_priority_later.id,
        same_priority_due_earlier.id,
        same_priority_due_later.id,
        low_priority_early.id,
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_and_lock_jobs_orders_retryable_jobs_by_retry_at_not_original_run_at(
    integration_async_session_factory,
) -> None:
    now = datetime.now(timezone.utc)

    async with integration_async_session_factory() as session:
        retrying_due_later = await enqueue_job(
            session,
            job_type=JobType.BUILD_EVENT_REPORT,
            payload={"event_id": 101, "source": "test"},
            priority=20,
            run_at=now - timedelta(hours=2),
        )
        retrying_due_earlier = await enqueue_job(
            session,
            job_type=JobType.BUILD_EVENT_REPORT,
            payload={"event_id": 102, "source": "test"},
            priority=20,
            run_at=now - timedelta(hours=1),
        )
        await session.flush()

        retrying_due_later.retry_at = now - timedelta(minutes=1)
        retrying_due_earlier.retry_at = now - timedelta(minutes=5)
        await session.commit()

    assert retrying_due_later is not None
    assert retrying_due_earlier is not None

    async with integration_async_session_factory() as session:
        locked = await fetch_and_lock_jobs(
            session,
            worker_id="worker-retry-ordering",
            limit=10,
            allowed_types={JobType.BUILD_EVENT_REPORT},
        )
        await session.commit()

    assert [job.id for job in locked] == [
        retrying_due_earlier.id,
        retrying_due_later.id,
    ]
