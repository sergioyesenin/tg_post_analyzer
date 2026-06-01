from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from services.jobs import JobType, enqueue_job
from services.settings_store import get_all_settings


def retention_scheduler_enabled(settings_payload: dict) -> bool:
    scheduler = settings_payload.get("scheduler", {})
    return bool(scheduler.get("enabled", True))


async def enqueue_daily_retention_jobs(
    session: AsyncSession,
    *,
    effective_settings: dict,
    now: datetime | None = None,
    retention_days: int | None = None,
    archive_batch_size: int | None = None,
    done_retention_days: int | None = None,
    dead_letter_retention_days: int | None = None,
    cleanup_batch_size: int | None = None,
) -> dict[str, int | str]:
    retention_settings = effective_settings.get("retention", {})
    jobs_settings = effective_settings.get("jobs", {})
    current = now or datetime.now(timezone.utc)
    daily_key = current.date().isoformat()

    archive_job = await enqueue_job(
        session,
        job_type=JobType.ARCHIVE_RETENTION,
        payload={
            "retention_days": int(retention_days if retention_days is not None else retention_settings.get("retention_days", 30)),
            "batch_limit": int(archive_batch_size if archive_batch_size is not None else retention_settings.get("archive_batch_size", 1000)),
        },
        run_at=current,
        priority=95,
        dedupe_key=f"archive_retention:{daily_key}",
    )
    jobs_retention_job = await enqueue_job(
        session,
        job_type=JobType.JOBS_RETENTION,
        payload={
            "done_retention_days": int(done_retention_days if done_retention_days is not None else jobs_settings.get("done_retention_days", 14)),
            "dead_letter_retention_days": int(
                dead_letter_retention_days if dead_letter_retention_days is not None else jobs_settings.get("dead_letter_retention_days", 90)
            ),
            "batch_limit": int(cleanup_batch_size if cleanup_batch_size is not None else jobs_settings.get("cleanup_batch_size", 1000)),
        },
        run_at=current,
        priority=96,
        dedupe_key=f"jobs_retention:{daily_key}",
    )
    await session.commit()

    return {
        "date": daily_key,
        "archive_job_created": int(archive_job is not None),
        "jobs_retention_job_created": int(jobs_retention_job is not None),
    }


async def dispatch_daily_retention() -> dict[str, int | str]:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
        if not retention_scheduler_enabled(effective_settings):
            return {
                "status": "disabled",
                "archive_job_created": 0,
                "jobs_retention_job_created": 0,
            }
        payload = await enqueue_daily_retention_jobs(session, effective_settings=effective_settings)
    payload["status"] = "ok"
    return payload
