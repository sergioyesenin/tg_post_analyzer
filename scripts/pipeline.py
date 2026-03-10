from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, text
from telethon import TelegramClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.reporter import TgReportProject
from client.config import load_client_settings
from db.models import Channel, Event, Job, JobDeadLetter, Post, Process
from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.ingestion_core import IngestionCore, IngestionContext, IngestionOptions
from services.archive import run_archive_retention
from services.jobs import (
    defer_locked_job,
    JobType,
    enqueue_job,
    fetch_and_lock_jobs,
    mark_job_done,
    mark_job_failed,
    requeue_job,
)
from services.jobs_retention import run_jobs_retention
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes
from services.reporting import build_event_report_draft, build_post_report, build_process_report_draft
from services.settings_store import get_all_settings, report_config_from_settings
from services.TGqueries import update_post_comments

SKIP_CHANNEL_IDS = {}
logger = logging.getLogger(__name__)


def _clamp_positive_int(value: int | None, *, default: int, minimum: int = 1, maximum: int = 64) -> int:
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(maximum, parsed))


def _split_locked_jobs_by_type(jobs: list[Job]) -> tuple[list[Job], list[Job]]:
    collect_comments_jobs: list[Job] = []
    other_jobs: list[Job] = []
    for job in jobs:
        if job.type == JobType.COLLECT_COMMENTS:
            collect_comments_jobs.append(job)
        else:
            other_jobs.append(job)
    return collect_comments_jobs, other_jobs


async def _collect_backlog_snapshot() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Job.status, func.count())
                .group_by(Job.status)
            )
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        pending_oldest = await session.scalar(
            select(func.min(func.coalesce(Job.retry_at, Job.run_at))).where(Job.status == "pending")
        )
        dead_letters = int((await session.scalar(select(func.count()).select_from(JobDeadLetter))) or 0)
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse active channels for last N days and run no-LLM linking pipeline.")
    parser.add_argument("--days", type=int, default=3, help="How many days back to parse.")
    parser.add_argument("--max-posts-per-channel", type=int, default=100, help="Safety limit per channel.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--session-suffix", type=str, default="")
    parser.add_argument("--unique-session-per-run", action="store_true")
    parser.add_argument("--daemon", action="store_true", help="Run forever and poll channels in loop.")
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=None,
        help="Delay between daemon cycles. Overrides ingest.poll_seconds when provided.",
    )
    parser.add_argument("--job-batch-size", type=int, default=20, help="How many jobs to execute per cycle.")
    parser.add_argument("--comment-first-delay-hours", type=int, default=2)
    parser.add_argument("--comment-interval-hours", type=int, default=4)
    parser.add_argument("--comment-window-hours", type=int, default=24)
    parser.add_argument("--post-report-delay-hours", type=int, default=6)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--archive-batch-size", type=int, default=1000)
    parser.add_argument(
        "--skip-rebuild-graphs",
        action="store_true",
        help="Do not rebuild events/processes after linking run.",
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


def _is_session_locked_error(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


def _build_client(*, session_suffix: str, unique_session_per_run: bool) -> TelegramClient:
    client_settings = load_client_settings()
    session_name = "tg_analytics.session"
    suffix = session_suffix.strip()
    if suffix:
        session_name = f"{session_name}_{suffix}"
    if unique_session_per_run:
        session_name = f"{session_name}_{os.getpid()}"
    return TelegramClient(
        session=session_name,
        api_id=client_settings.api_id,
        api_hash=client_settings.api_hash,
        flood_sleep_threshold=client_settings.flood_sleep_threshold,
    )


async def _with_session_lock_retry(coro_factory, *, op_name: str, retries: int = 3, delay_sec: float = 1.5):
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_session_locked_error(exc) or attempt >= retries:
                raise
            logger.warning(
                "Telethon session locked op=%s retry=%s/%s delay_sec=%.1f",
                op_name,
                attempt,
                retries,
                delay_sec,
            )
            await asyncio.sleep(delay_sec)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{op_name} failed unexpectedly")


async def _get_active_channels() -> list[Channel]:
    async with AsyncSessionLocal() as session:
        stmt = select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id.asc())
        return list((await session.execute(stmt)).scalars().all())


async def _get_last_tg_message_id_for_channel(*, session, channel_id: int) -> int:
    stmt = select(func.max(Post.tg_message_id)).where(Post.channel_id == channel_id)
    last_value = (await session.execute(stmt)).scalar_one_or_none()
    if isinstance(last_value, int) and last_value > 0:
        return last_value
    return 0


async def _schedule_post_jobs(
    session,
    *,
    post: Post,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    post_report_delay_hours: int,
    comment_schedule_jitter_seconds: int,
) -> None:
    first_comment_at = post.date + timedelta(hours=comment_first_delay_hours)
    comment_until = post.date + timedelta(hours=comment_window_hours)
    current = first_comment_at
    scan_index = 0
    while current <= comment_until:
        jitter_seconds = random.randint(0, max(0, int(comment_schedule_jitter_seconds)))
        scheduled_at = current + timedelta(seconds=jitter_seconds)
        ts = int(scheduled_at.timestamp())
        priority = _collect_comments_job_priority(post=post, scan_index=scan_index)
        await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": post.id, "scan_index": scan_index},
            run_at=scheduled_at,
            priority=priority,
            max_attempts=8,
            dedupe_key=f"collect_comments:{post.id}:{ts}",
        )
        current = current + timedelta(hours=comment_interval_hours)
        scan_index += 1

    await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT,
        payload={"post_id": post.id},
        run_at=post.date + timedelta(hours=post_report_delay_hours),
        priority=40,
        max_attempts=5,
        dedupe_key=f"build_post_report:{post.id}",
    )


def _collect_comments_job_priority(*, post: Post, scan_index: int) -> int:
    """
    Lower value means higher priority in queue.
    Heuristic:
    - early scans are prioritized,
    - posts with stronger discussion/visibility are prioritized.
    """
    priority = 20

    if scan_index == 0:
        priority -= 2
    elif scan_index == 1:
        priority -= 1

    comments = int(post.comments_count or 0)
    if comments >= 100:
        priority -= 4
    elif comments >= 50:
        priority -= 3
    elif comments >= 20:
        priority -= 2
    elif comments >= 5:
        priority -= 1

    views = int(post.views or 0)
    if views >= 5000:
        priority -= 2
    elif views >= 1000:
        priority -= 1

    if isinstance(post.involvement, (int, float)):
        if post.involvement >= 0.20:
            priority -= 2
        elif post.involvement >= 0.10:
            priority -= 1

    return max(5, min(90, priority))


async def _process_channel(
    client: TelegramClient,
    channel: Channel,
    *,
    since_utc: datetime,
    max_posts: int,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    post_report_delay_hours: int,
    comment_schedule_jitter_seconds: int,
) -> int:
    if channel.id in SKIP_CHANNEL_IDS:
        logging.info("Skip channel id=%s (@%s): excluded by config", channel.id, channel.username)
        return 0

    logging.info("Parsing channel @%s since %s", channel.username, since_utc.isoformat())
    pipeline = NoLlmLinkingPipeline.build_default()

    async with AsyncSessionLocal() as session:
        channel_last_tg_msg_id = await _get_last_tg_message_id_for_channel(session=session, channel_id=channel.id)

    core = IngestionCore(
        tg_client=client,
        session_factory=AsyncSessionLocal,
    )
    options = IngestionOptions(
        since_utc=since_utc,
        max_posts=max_posts,
        min_tg_message_id_exclusive=channel_last_tg_msg_id,
        resolve_album_representative=True,
    )

    async def _on_post_saved(session, post, ctx: IngestionContext) -> None:
        result = await pipeline.run_for_post(session, post)
        await _schedule_post_jobs(
            session,
            post=post,
            comment_first_delay_hours=comment_first_delay_hours,
            comment_interval_hours=comment_interval_hours,
            comment_window_hours=comment_window_hours,
            post_report_delay_hours=post_report_delay_hours,
            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
        )
        logging.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, ctx.message.id, channel.username)
        logging.info(
            "Linked post id=%s verified=%s proposed=%s review=%s rejected=%s candidates=%s",
            post.id,
            result.links_verified,
            result.links_proposed,
            result.queued_for_review,
            result.links_rejected,
            result.candidates_checked,
        )

    result = await core.ingest_channel(
        channel=channel,
        options=options,
        on_post_saved=_on_post_saved,
    )
    logging.info(
        "Finished @%s processed_posts=%s stopped_reason=%s",
        channel.username,
        result.processed_posts,
        result.stopped_reason,
    )
    return result.processed_posts


async def _rebuild_event_process_graphs(*, date_from: datetime, date_to: datetime) -> None:
    async with AsyncSessionLocal() as session:
        rebuilt_events = await rebuild_events(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="no-llm-pipeline",
        )
        await session.commit()
    logging.info("Rebuilt events=%s for %s..%s", rebuilt_events, date_from.isoformat(), date_to.isoformat())

    async with AsyncSessionLocal() as session:
        rebuilt_process_edges = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="no-llm-pipeline",
        )
        await session.commit()
    logging.info(
        "Rebuilt process_edges=%s for %s..%s",
        rebuilt_process_edges,
        date_from.isoformat(),
        date_to.isoformat(),
    )


async def _enqueue_graph_report_jobs(*, date_from: datetime, date_to: datetime) -> None:
    # Deduplicate report rebuild jobs inside a short time bucket.
    # This keeps auto-refresh active while preventing excessive churn.
    bucket = date_to.replace(minute=(date_to.minute // 30) * 30, second=0, microsecond=0)
    bucket_key = bucket.strftime("%Y%m%d%H%M")
    async with AsyncSessionLocal() as session:
        event_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(Event.id).where(and_(Event.started_at >= date_from, Event.started_at <= date_to))
                )
            ).all()
        ]
        process_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(Process.id).where(and_(Process.started_at >= date_from, Process.started_at <= date_to))
                )
            ).all()
        ]

        for event_id in event_ids:
            await enqueue_job(
                session,
                job_type=JobType.BUILD_EVENT_REPORT,
                payload={"event_id": event_id},
                priority=70,
                dedupe_key=f"build_event_report:{event_id}:{bucket_key}",
            )
        for process_id in process_ids:
            await enqueue_job(
                session,
                job_type=JobType.BUILD_PROCESS_REPORT,
                payload={"process_id": process_id},
                priority=80,
                dedupe_key=f"build_process_report:{process_id}:{bucket_key}",
            )
        await session.commit()


async def _run_non_collect_job(
    *,
    job_id: int,
    worker_id: str,
    report_project: TgReportProject,
    report_config,
) -> int:
    async with AsyncSessionLocal() as session:
        db_job = await session.get(Job, job_id)
        if db_job is None:
            return 0
        try:
            if db_job.type == JobType.BUILD_POST_REPORT:
                payload = db_job.payload_json or {}
                post_id = int(payload.get("post_id"))
                result = await build_post_report(
                    session,
                    post_id=post_id,
                    report_project=report_project,
                    report_config=report_config,
                )
                logger.info("Job build_post_report post_id=%s status=%s", post_id, result.get("status"))
            elif db_job.type == JobType.BUILD_EVENT_REPORT:
                payload = db_job.payload_json or {}
                event_id = int(payload.get("event_id"))
                result = await build_event_report_draft(session, event_id=event_id)
                logger.info("Job build_event_report event_id=%s status=%s", event_id, result.get("status"))
            elif db_job.type == JobType.BUILD_PROCESS_REPORT:
                payload = db_job.payload_json or {}
                process_id = int(payload.get("process_id"))
                result = await build_process_report_draft(session, process_id=process_id)
                logger.info("Job build_process_report process_id=%s status=%s", process_id, result.get("status"))
            elif db_job.type == JobType.ARCHIVE_RETENTION:
                payload = db_job.payload_json or {}
                retention_days = int(payload.get("retention_days", 30))
                batch_limit = int(payload.get("batch_limit", 1000))
                result = await run_archive_retention(
                    session,
                    retention_days=retention_days,
                    batch_limit=batch_limit,
                )
                logger.info("Job archive_retention status=ok details=%s", result)
            elif db_job.type == JobType.JOBS_RETENTION:
                payload = db_job.payload_json or {}
                done_retention_days = int(payload.get("done_retention_days", 14))
                dead_letter_retention_days = int(payload.get("dead_letter_retention_days", 90))
                batch_limit = int(payload.get("batch_limit", 1000))
                result = await run_jobs_retention(
                    session,
                    done_retention_days=done_retention_days,
                    dead_letter_retention_days=dead_letter_retention_days,
                    batch_limit=batch_limit,
                )
                logger.info("Job jobs_retention status=ok details=%s", result)
            else:
                raise ValueError(f"Unsupported job type: {db_job.type}")

            await mark_job_done(session, job=db_job)
            await session.commit()
            return 1
        except Exception as exc:
            await mark_job_failed(
                session,
                job=db_job,
                error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
            )
            await session.commit()
            logger.exception(
                "Job failed marker=job_unexpected op=run_job job_id=%s job_type=%s worker_id=%s err=%r",
                db_job.id,
                db_job.type,
                worker_id,
                exc,
            )
            return 0


async def _run_jobs(
    *,
    job_batch_size: int,
    worker_id: str,
    collect_comments_quota_per_run: int,
    tg_client: TelegramClient,
    job_worker_concurrency: int,
) -> int:
    report_project = TgReportProject(llm_model="ollama/llama3:8b-instruct-q4_K_M")
    executed = 0
    collect_comments_global_cooldown_until: datetime | None = None
    collect_comments_processed = 0
    collect_comments_flood_streak = 0

    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    report_config = report_config_from_settings(effective_settings)
    ingest_settings = effective_settings.get("ingest", {})
    cc_sleep_min_ms = int(ingest_settings.get("collect_comments_sleep_min_ms", 2500))
    cc_sleep_max_ms = int(ingest_settings.get("collect_comments_sleep_max_ms", 4500))
    if cc_sleep_max_ms < cc_sleep_min_ms:
        cc_sleep_max_ms = cc_sleep_min_ms

    async with AsyncSessionLocal() as session:
        jobs = await fetch_and_lock_jobs(
            session,
            worker_id=worker_id,
            limit=job_batch_size,
            allowed_types={
                JobType.COLLECT_COMMENTS,
                JobType.BUILD_POST_REPORT,
                JobType.BUILD_EVENT_REPORT,
                JobType.BUILD_PROCESS_REPORT,
                JobType.ARCHIVE_RETENTION,
                JobType.JOBS_RETENTION,
            },
        )
        await session.commit()

    collect_jobs, non_collect_jobs = _split_locked_jobs_by_type(jobs)

    for job in collect_jobs:
        async with AsyncSessionLocal() as session:
            db_job = await session.get(Job, job.id)
            if db_job is None:
                continue
            try:
                if collect_comments_processed >= collect_comments_quota_per_run:
                    await defer_locked_job(
                        session,
                        job=db_job,
                        retry_at=datetime.now(timezone.utc) + timedelta(seconds=60),
                        reason="collect_comments:quota_deferred",
                        preserve_attempt_budget=True,
                    )
                    await session.commit()
                    continue

                now = datetime.now(timezone.utc)
                if (
                    collect_comments_global_cooldown_until is not None
                    and now < collect_comments_global_cooldown_until
                ):
                    await asyncio.sleep(
                        (collect_comments_global_cooldown_until - now).total_seconds()
                    )
                payload = db_job.payload_json or {}
                post_id = int(payload.get("post_id"))
                collect_comments_processed += 1
                result = await update_post_comments(session, post_id, tg_client=tg_client)
                status = str(result.get("status") or "unknown")
                if status == "entity_error":
                    logger.info(
                        "Job collect_comments post_id=%s status=%s err=%s",
                        post_id,
                        status,
                        result.get("error"),
                    )
                else:
                    logger.info("Job collect_comments post_id=%s status=%s", post_id, status)
                if status == "ok":
                    collect_comments_flood_streak = 0
                    await mark_job_done(session, job=db_job)
                    await session.commit()
                    executed += 1
                    if cc_sleep_max_ms > 0:
                        await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                    continue

                if status == "no_discussion":
                    collect_comments_flood_streak = 0
                    # No discussion thread exists: remove future pending recollect jobs for this post.
                    await session.execute(
                        text(
                            "DELETE FROM jobs "
                            "WHERE type = :job_type "
                            "AND status = 'pending' "
                            "AND id <> :job_id "
                            "AND payload_json->>'post_id' = :post_id"
                        ),
                        {
                            "job_type": JobType.COLLECT_COMMENTS,
                            "job_id": db_job.id,
                            "post_id": str(post_id),
                        },
                    )
                    await mark_job_done(session, job=db_job)
                    await session.commit()
                    executed += 1
                    if cc_sleep_max_ms > 0:
                        await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                    continue

                if status == "unchanged":
                    collect_comments_flood_streak = 0
                    await mark_job_done(session, job=db_job)
                    await session.commit()
                    executed += 1
                    if cc_sleep_max_ms > 0:
                        await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                    continue

                if status == "flood_wait":
                    wait_seconds = int(result.get("wait_seconds") or 30)
                    flood_source = str(result.get("flood_source") or "unknown")
                    collect_comments_flood_streak += 1
                    now_utc = datetime.now(timezone.utc)
                    retry_at = now_utc + timedelta(seconds=max(60, wait_seconds * 4))
                    # Adaptive global cool-down: if flood-waits happen consecutively,
                    # increase pause to reduce repeated throttling.
                    base_cooldown_sec = max(300, wait_seconds * 6)
                    if collect_comments_flood_streak >= 2:
                        adaptive_cooldown_sec = min(1800, base_cooldown_sec * (2 ** (collect_comments_flood_streak - 1)))
                    else:
                        adaptive_cooldown_sec = base_cooldown_sec
                    collect_comments_global_cooldown_until = now_utc + timedelta(
                        seconds=adaptive_cooldown_sec
                    )
                    logger.warning(
                        "collect_comments flood source=%s streak=%s wait=%ss cooldown=%ss",
                        flood_source,
                        collect_comments_flood_streak,
                        wait_seconds,
                        adaptive_cooldown_sec,
                    )
                    effective_retry_at = max(retry_at, collect_comments_global_cooldown_until)
                    await requeue_job(
                        session,
                        job=db_job,
                        retry_at=effective_retry_at,
                        error=f"collect_comments:flood_wait:{wait_seconds}",
                    )
                    # Defer all other pending comment-collection jobs until cooldown expires.
                    # This lowers repeated FloodWait bursts without dropping any data.
                    await session.execute(
                        text(
                            "UPDATE jobs "
                            "SET retry_at = :retry_at "
                            "WHERE type = :job_type "
                            "AND status = 'pending' "
                            "AND id <> :job_id "
                            "AND (retry_at IS NULL OR retry_at < :retry_at)"
                        ),
                        {
                            "retry_at": collect_comments_global_cooldown_until,
                            "job_type": JobType.COLLECT_COMMENTS,
                            "job_id": db_job.id,
                        },
                    )
                    await session.commit()
                    break

                if status in {"entity_error", "rpc_error", "discussion_error"}:
                    collect_comments_flood_streak = 0
                    await mark_job_failed(
                        session,
                        job=db_job,
                        error=f"collect_comments:{status}",
                        retry_base_seconds=120,
                        retry_max_seconds=7200,
                    )
                    await session.commit()
                    if cc_sleep_max_ms > 0:
                        await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                    continue

                if status == "not_found":
                    collect_comments_flood_streak = 0
                    await mark_job_done(session, job=db_job)
                    await session.commit()
                    executed += 1
                    if cc_sleep_max_ms > 0:
                        await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                    continue

                await mark_job_failed(
                    session,
                    job=db_job,
                    error=f"collect_comments:unexpected_status:{status}",
                    retry_base_seconds=120,
                    retry_max_seconds=7200,
                )
                collect_comments_flood_streak = 0
                await session.commit()
                if cc_sleep_max_ms > 0:
                    await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                continue
            except Exception as exc:
                await mark_job_failed(
                    session,
                    job=db_job,
                    error=f"job_unexpected:{db_job.type}:{type(exc).__name__}:{exc}",
                )
                await session.commit()
                logger.exception(
                    "Job failed marker=job_unexpected op=run_job job_id=%s job_type=%s worker_id=%s err=%r",
                    db_job.id,
                    db_job.type,
                    worker_id,
                    exc,
                )

    if not non_collect_jobs:
        return executed

    parallelism = _clamp_positive_int(job_worker_concurrency, default=2, minimum=1, maximum=16)
    semaphore = asyncio.Semaphore(parallelism)

    async def _run_with_limit(job_id: int) -> int:
        async with semaphore:
            return await _run_non_collect_job(
                job_id=job_id,
                worker_id=worker_id,
                report_project=report_project,
                report_config=report_config,
            )

    results = await asyncio.gather(*[_run_with_limit(job.id) for job in non_collect_jobs])
    executed += sum(results)
    return executed


async def _run_single_cycle(client: TelegramClient, args: argparse.Namespace, worker_id: str) -> None:
    cycle_started_at_perf = time.perf_counter()
    backlog_before = await _collect_backlog_snapshot()
    since_utc = datetime.now(timezone.utc) - timedelta(days=args.days)
    async with AsyncSessionLocal() as session:
        effective_settings = await get_all_settings(session)
    ingest_settings = effective_settings.get("ingest", {})
    reports_settings = effective_settings.get("reports", {})
    jobs_settings = effective_settings.get("jobs", {})
    retention_settings = effective_settings.get("retention", {})

    max_posts_per_channel = int(ingest_settings.get("max_posts_per_channel", args.max_posts_per_channel))
    comment_first_delay_hours = int(ingest_settings.get("comment_first_delay_hours", args.comment_first_delay_hours))
    comment_interval_hours = int(ingest_settings.get("comment_interval_hours", args.comment_interval_hours))
    comment_window_hours = int(ingest_settings.get("comment_window_hours", args.comment_window_hours))
    comment_schedule_jitter_seconds = int(
        ingest_settings.get("comment_schedule_jitter_seconds", 7200)
    )
    post_report_delay_hours = int(reports_settings.get("post_report_delay_hours", args.post_report_delay_hours))
    job_batch_size = int(jobs_settings.get("job_batch_size", args.job_batch_size))
    collect_comments_quota_per_run = int(jobs_settings.get("collect_comments_quota_per_run", 2))
    done_retention_days = int(jobs_settings.get("done_retention_days", 14))
    dead_letter_retention_days = int(jobs_settings.get("dead_letter_retention_days", 90))
    cleanup_batch_size = int(jobs_settings.get("cleanup_batch_size", 1000))
    channel_concurrency = _clamp_positive_int(ingest_settings.get("channel_concurrency"), default=2, minimum=1, maximum=8)
    job_worker_concurrency = _clamp_positive_int(jobs_settings.get("job_worker_concurrency"), default=2, minimum=1, maximum=16)
    retention_days = int(retention_settings.get("retention_days", args.retention_days))
    archive_batch_size = int(retention_settings.get("archive_batch_size", args.archive_batch_size))

    channels = await _get_active_channels()
    total_processed_posts = 0
    if not channels:
        logging.warning("No active channels found.")
    else:
        logger.info(
            "Cycle channel scheduling channels=%s channel_concurrency=%s",
            len(channels),
            channel_concurrency,
        )
        if channel_concurrency <= 1 or len(channels) <= 1:
            for channel in channels:
                processed_in_channel = await _process_channel(
                    client,
                    channel,
                    since_utc=since_utc,
                    max_posts=max_posts_per_channel,
                    comment_first_delay_hours=comment_first_delay_hours,
                    comment_interval_hours=comment_interval_hours,
                    comment_window_hours=comment_window_hours,
                    post_report_delay_hours=post_report_delay_hours,
                    comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
                )
                total_processed_posts += processed_in_channel
        else:
            semaphore = asyncio.Semaphore(channel_concurrency)

            async def _process_channel_with_limit(channel: Channel) -> int:
                async with semaphore:
                    try:
                        return await _process_channel(
                            client,
                            channel,
                            since_utc=since_utc,
                            max_posts=max_posts_per_channel,
                            comment_first_delay_hours=comment_first_delay_hours,
                            comment_interval_hours=comment_interval_hours,
                            comment_window_hours=comment_window_hours,
                            post_report_delay_hours=post_report_delay_hours,
                            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
                        )
                    except Exception as exc:
                        logger.exception(
                            "Channel processing failed marker=channel_unexpected channel_id=%s channel_username=%s err=%r",
                            channel.id,
                            channel.username,
                            exc,
                        )
                        return 0

            processed_by_channel = await asyncio.gather(*[_process_channel_with_limit(channel) for channel in channels])
            total_processed_posts = sum(processed_by_channel)

    if not args.skip_rebuild_graphs and total_processed_posts > 0:
        await _rebuild_event_process_graphs(
            date_from=since_utc,
            date_to=datetime.now(timezone.utc),
        )
        await _enqueue_graph_report_jobs(
            date_from=since_utc,
            date_to=datetime.now(timezone.utc),
        )
    elif not args.skip_rebuild_graphs:
        logging.info("Skip rebuild: no new posts in this cycle.")

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        daily_key = now.date().isoformat()
        await enqueue_job(
            session,
            job_type=JobType.ARCHIVE_RETENTION,
            payload={"retention_days": retention_days, "batch_limit": archive_batch_size},
            run_at=now,
            priority=95,
            dedupe_key=f"archive_retention:{daily_key}",
        )
        await enqueue_job(
            session,
            job_type=JobType.JOBS_RETENTION,
            payload={
                "done_retention_days": done_retention_days,
                "dead_letter_retention_days": dead_letter_retention_days,
                "batch_limit": cleanup_batch_size,
            },
            run_at=now,
            priority=96,
            dedupe_key=f"jobs_retention:{daily_key}",
        )
        await session.commit()

    executed_jobs = await _run_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        collect_comments_quota_per_run=collect_comments_quota_per_run,
        tg_client=client,
        job_worker_concurrency=job_worker_concurrency,
    )
    backlog_after = await _collect_backlog_snapshot()
    cycle_took_sec = max(0.001, time.perf_counter() - cycle_started_at_perf)
    posts_per_sec = round(total_processed_posts / cycle_took_sec, 3)
    jobs_per_sec = round(executed_jobs / cycle_took_sec, 3)
    logger.info(
        "Cycle metrics marker=cycle_metrics worker_id=%s took_sec=%.3f processed_posts=%s executed_jobs=%s posts_per_sec=%.3f jobs_per_sec=%.3f backlog_before=%s backlog_after=%s channel_concurrency=%s job_worker_concurrency=%s",
        worker_id,
        cycle_took_sec,
        total_processed_posts,
        executed_jobs,
        posts_per_sec,
        jobs_per_sec,
        backlog_before,
        backlog_after,
        channel_concurrency,
        job_worker_concurrency,
    )


async def main_async(args: argparse.Namespace) -> None:
    client = _build_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    worker_id = f"pipeline-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    await _with_session_lock_retry(lambda: client.start(), op_name="client.start")
    try:
        if args.daemon:
            logging.info("Daemon mode started. worker_id=%s poll_seconds_arg=%s", worker_id, args.poll_seconds)
            while True:
                cycle_started_at = datetime.now(timezone.utc)
                try:
                    await _run_single_cycle(client, args, worker_id)
                except Exception as exc:
                    logger.exception("Cycle failed marker=cycle_unexpected op=run_cycle worker_id=%s err=%r", worker_id, exc)
                async with AsyncSessionLocal() as session:
                    effective_settings = await get_all_settings(session)
                ingest_settings = effective_settings.get("ingest", {})
                poll_seconds_from_settings = int(ingest_settings.get("poll_seconds", 240))
                poll_seconds = int(args.poll_seconds) if args.poll_seconds is not None else poll_seconds_from_settings
                poll_seconds = max(5, poll_seconds)
                elapsed = (datetime.now(timezone.utc) - cycle_started_at).total_seconds()
                sleep_for = max(1, int(poll_seconds - elapsed))
                await asyncio.sleep(sleep_for)
        else:
            await _run_single_cycle(client, args, worker_id)
    finally:
        try:
            await _with_session_lock_retry(lambda: client.disconnect(), op_name="client.disconnect")
        except sqlite3.OperationalError as exc:
            if _is_session_locked_error(exc):
                logging.warning("Telethon session is locked during disconnect, ignored: %r", exc)
            else:
                raise


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
