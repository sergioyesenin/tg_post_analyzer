from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from client.telegram import TelegramClientHandle, build_telegram_client
from db.models import Job, JobDeadLetter
from db.session import AsyncSessionLocal
from services.jobs import JobType
from services.settings_defaults import get_default_setting
from services.settings_store import get_all_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramCycleMetrics:
    processed_posts: int
    executed_jobs: int


TelegramPipelineClient = TelegramClientHandle


def clamp_positive_int(value: int | None, *, default: int, minimum: int = 1, maximum: int = 64) -> int:
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(maximum, parsed))


def resolve_setting_value(*, settings_value, cli_value, fallback):
    if settings_value is not None:
        return settings_value
    if cli_value is not None:
        return cli_value
    return fallback


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


def build_worker_id(prefix: str) -> str:
    return f"{prefix}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def build_tg_client(*, session_suffix: str, unique_session_per_run: bool) -> TelegramPipelineClient:
    return build_telegram_client(
        session_suffix=session_suffix,
        unique_session_per_run=unique_session_per_run,
    )


async def collect_backlog_snapshot(*, allowed_types: set[str] | None = None) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        stmt = select(Job.status, func.count()).group_by(Job.status)
        if allowed_types:
            stmt = stmt.where(Job.type.in_(allowed_types))
        rows = (await session.execute(stmt)).all()

        pending_stmt = select(func.min(func.coalesce(Job.retry_at, Job.run_at))).where(Job.status == "pending")
        if allowed_types:
            pending_stmt = pending_stmt.where(Job.type.in_(allowed_types))
        pending_oldest = await session.scalar(pending_stmt)

        dead_stmt = select(func.count()).select_from(JobDeadLetter)
        if allowed_types:
            dead_stmt = dead_stmt.where(JobDeadLetter.type.in_(allowed_types))
        dead_letters = int((await session.scalar(dead_stmt)) or 0)

    counts = {str(status): int(count) for status, count in rows}
    pending_lag_seconds = 0
    if pending_oldest is not None:
        pending_lag_seconds = max(0, int((now_utc - pending_oldest).total_seconds()))
    return {
        "pending": int(counts.get("pending", 0)),
        "running": int(counts.get("running", 0)),
        "done": int(counts.get("done", 0)),
        "failed": int(counts.get("failed", 0)),
        "dead_letters": dead_letters,
        "pending_lag_seconds": pending_lag_seconds,
    }


async def has_due_priority_job(*, allowed_types: set[str], max_priority: int) -> bool:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Job.id)
            .where(Job.status == "pending")
            .where(Job.type.in_(allowed_types))
            .where(Job.priority <= max_priority)
            .where(func.coalesce(Job.retry_at, Job.run_at) <= now_utc)
            .limit(1)
        )
        job_id = await session.scalar(stmt)
    return job_id is not None


async def get_telegram_poll_seconds(*, cli_override: int | None, default: int | None = None) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    ingest_settings = effective_settings.get("ingest", {})
    resolved = resolve_setting_value(
        settings_value=ingest_settings.get("poll_seconds"),
        cli_value=cli_override,
        fallback=get_default_setting("ingest", "poll_seconds") if default is None else default,
    )
    return max(5, int(resolved))


async def get_ai_poll_seconds(*, cli_override: int | None, default: int | None = None) -> int:
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    jobs_settings = effective_settings.get("jobs", {})
    resolved = resolve_setting_value(
        settings_value=jobs_settings.get("ai_poll_seconds"),
        cli_value=cli_override,
        fallback=get_default_setting("jobs", "ai_poll_seconds") if default is None else default,
    )
    return max(5, int(resolved))


async def sleep_until_next_telegram_cycle(
    *,
    target_seconds: int,
    wake_priority_threshold: int | None = None,
) -> None:
    # Keep older callers working: wake early for any due comment refresh job by default.
    effective_wake_priority_threshold = 20 if wake_priority_threshold is None else int(wake_priority_threshold)
    remaining = max(1, int(target_seconds))
    while remaining > 0:
        if await has_due_priority_job(
            allowed_types={JobType.REFRESH_COMMENTS},
            max_priority=effective_wake_priority_threshold,
        ):
            return
        chunk = min(1, remaining)
        await asyncio.sleep(chunk)
        remaining -= chunk
