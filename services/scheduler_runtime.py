from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.engine import make_url

from config import settings
from services.scheduler_dispatch import dispatch_daily_retention


def build_scheduler_db_url(async_db_url: str) -> str:
    parsed = make_url(async_db_url)
    if parsed.drivername == "postgresql+asyncpg":
        return parsed.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)
    if parsed.drivername == "postgres":
        return parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    if parsed.drivername == "postgresql":
        return parsed.render_as_string(hide_password=False)
    if parsed.drivername == "postgresql+psycopg2":
        return parsed.render_as_string(hide_password=False)
    else:
        return async_db_url


def build_scheduler() -> AsyncIOScheduler:
    timezone = ZoneInfo(settings.tz)
    jobstores = {
        "default": SQLAlchemyJobStore(url=build_scheduler_db_url(settings.DB_URL)),
    }
    executors = {
        "default": AsyncIOExecutor(),
    }
    return AsyncIOScheduler(jobstores=jobstores, executors=executors, timezone=timezone)


def register_periodic_jobs(scheduler: AsyncIOScheduler, *, effective_settings: dict) -> None:
    scheduler_settings = effective_settings.get("scheduler", {})
    timezone = ZoneInfo(settings.tz)
    scheduler.add_job(
        dispatch_daily_retention,
        trigger=CronTrigger(
            hour=int(scheduler_settings.get("retention_hour", 3)),
            minute=int(scheduler_settings.get("retention_minute", 0)),
            timezone=timezone,
        ),
        id="retention.daily",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
