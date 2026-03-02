from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, text
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.reporter import TgReportProject
from client.config import load_client_settings
from db.models import Channel, Event, Job, Post, Process
from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.ingest import upsert_post
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
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes
from services.reporting import build_event_report_draft, build_post_report, build_process_report_draft
from services.settings_store import get_all_settings, report_config_from_settings
from services.TGqueries import update_post_comments

SKIP_CHANNEL_IDS = {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse active channels for last N days and run no-LLM linking pipeline.")
    parser.add_argument("--days", type=int, default=3, help="How many days back to parse.")
    parser.add_argument("--max-posts-per-channel", type=int, default=100, help="Safety limit per channel.")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--session-suffix", type=str, default="")
    parser.add_argument("--unique-session-per-run", action="store_true")
    parser.add_argument("--daemon", action="store_true", help="Run forever and poll channels in loop.")
    parser.add_argument("--poll-seconds", type=int, default=240, help="Delay between daemon cycles.")
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
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not _is_session_locked_error(exc) or attempt >= retries:
                raise
            logging.warning(
                "Telethon session locked during %s. Retry %s/%s after %.1fs",
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


async def _get_post_by_channel_msg(*, session, channel_id: int, tg_message_id: int) -> Post | None:
    stmt = (
        select(Post)
        .where(Post.channel_id == channel_id)
        .where(Post.tg_message_id == tg_message_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


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
    while current <= comment_until:
        jitter_seconds = random.randint(0, max(0, int(comment_schedule_jitter_seconds)))
        scheduled_at = current + timedelta(seconds=jitter_seconds)
        ts = int(scheduled_at.timestamp())
        await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": post.id},
            run_at=scheduled_at,
            priority=20,
            max_attempts=8,
            dedupe_key=f"collect_comments:{post.id}:{ts}",
        )
        current = current + timedelta(hours=comment_interval_hours)

    await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT,
        payload={"post_id": post.id},
        run_at=post.date + timedelta(hours=post_report_delay_hours),
        priority=40,
        max_attempts=5,
        dedupe_key=f"build_post_report:{post.id}",
    )


def _extract_parent_tg_message_id(message) -> int | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        return None
    parent_tg_message_id = getattr(reply_to, "reply_to_msg_id", None)
    if isinstance(parent_tg_message_id, int) and parent_tg_message_id > 0:
        return parent_tg_message_id
    return None


def _extract_comments_count(message) -> int:
    replies = getattr(message, "replies", None)
    count = getattr(replies, "replies", 0) if replies is not None else 0
    if isinstance(count, int) and count >= 0:
        return count
    return 0


async def _pick_album_representative_message(client: TelegramClient, entity, message):
    grouped_id = getattr(message, "grouped_id", None)
    if not isinstance(grouped_id, int):
        return message

    radius = 10
    candidate_ids = [msg_id for msg_id in range(message.id - radius, message.id + radius + 1) if msg_id > 0]
    if not candidate_ids:
        return message

    try:
        nearby = await _with_session_lock_retry(
            lambda: client.get_messages(entity, ids=candidate_ids),
            op_name="get_messages(album_nearby)",
        )
    except Exception:
        return message

    if not isinstance(nearby, list):
        nearby = [nearby] if nearby is not None else []

    grouped_messages: list = []
    for item in nearby:
        if item is None:
            continue
        if getattr(item, "grouped_id", None) != grouped_id:
            continue
        if getattr(item, "date", None) is None:
            continue
        grouped_messages.append(item)

    if not grouped_messages:
        return message

    # Prefer the message carrying discussion counters/caption, then keep deterministic tie-breakers.
    return max(
        grouped_messages,
        key=lambda m: (
            _extract_comments_count(m),
            1 if str(getattr(m, "message", "") or "").strip() else 0,
            -int(getattr(m, "id", 0) or 0),
        ),
    )


async def _ensure_parent_post(
    *,
    client: TelegramClient,
    session,
    channel: Channel,
    entity,
    parent_tg_message_id: int,
) -> Post | None:
    parent_post = await _get_post_by_channel_msg(
        session=session,
        channel_id=channel.id,
        tg_message_id=parent_tg_message_id,
    )
    if parent_post is not None:
        return parent_post

    try:
        parent_msg = await _with_session_lock_retry(
            lambda: client.get_messages(entity, ids=parent_tg_message_id),
            op_name=f"get_messages(parent:{parent_tg_message_id})",
        )
    except Exception:
        return None

    if isinstance(parent_msg, list):
        parent_msg = parent_msg[0] if parent_msg else None
    if parent_msg is None or getattr(parent_msg, "id", None) is None or getattr(parent_msg, "date", None) is None:
        return None

    parent_parent_tg_message_id = _extract_parent_tg_message_id(parent_msg)
    parent_parent_post_id: int | None = None
    if isinstance(parent_parent_tg_message_id, int):
        parent_parent_post = await _get_post_by_channel_msg(
            session=session,
            channel_id=channel.id,
            tg_message_id=parent_parent_tg_message_id,
        )
        if parent_parent_post is not None:
            parent_parent_post_id = parent_parent_post.id

    saved = await upsert_post(
        session,
        channel_id=channel.id,
        tg_message_id=parent_msg.id,
        parent_tg_message_id=parent_parent_tg_message_id,
        parent_post_id=parent_parent_post_id,
        date=parent_msg.date,
        text=parent_msg.message,
        views=getattr(parent_msg, "views", None),
        comments_count=_extract_comments_count(parent_msg),
        involvement=None,
    )
    await session.commit()
    return saved


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

    if channel.username.startswith("id_") and channel.username[3:].isdigit():
        peer = PeerChannel(int(channel.username[3:]))
    else:
        peer = f"@{channel.username}"

    try:
        entity = await _with_session_lock_retry(
            lambda: client.get_entity(peer),
            op_name=f"get_entity(@{channel.username})",
        )
    except Exception as exc:
        logging.warning("Skip channel @%s: entity resolve failed: %r", channel.username, exc)
        return 0

    logging.info("Parsing channel @%s since %s", channel.username, since_utc.isoformat())
    pipeline = NoLlmLinkingPipeline.build_default()
    processed = 0
    processed_grouped_ids: set[int] = set()
    async with AsyncSessionLocal() as session:
        channel_last_tg_msg_id = await _get_last_tg_message_id_for_channel(session=session, channel_id=channel.id)

    async for msg in client.iter_messages(entity):
        if processed >= max_posts:
            break
        if msg.date is None:
            continue
        if msg.date < since_utc:
            break
        grouped_id = getattr(msg, "grouped_id", None)
        if isinstance(grouped_id, int):
            if grouped_id in processed_grouped_ids:
                continue
            msg = await _pick_album_representative_message(client, entity, msg)
            processed_grouped_ids.add(grouped_id)

        if channel_last_tg_msg_id and int(msg.id or 0) <= channel_last_tg_msg_id:
            break

        parent_tg_message_id = _extract_parent_tg_message_id(msg)
        comments_count = _extract_comments_count(msg)
        async with AsyncSessionLocal() as session:
            existing = await _get_post_by_channel_msg(
                session=session,
                channel_id=channel.id,
                tg_message_id=msg.id,
            )
            if existing is not None:
                break

            parent_post_id: int | None = None
            if isinstance(parent_tg_message_id, int):
                parent_post = await _ensure_parent_post(
                    client=client,
                    session=session,
                    channel=channel,
                    entity=entity,
                    parent_tg_message_id=parent_tg_message_id,
                )
                if parent_post is not None:
                    parent_post_id = parent_post.id

            post = await upsert_post(
                session,
                channel_id=channel.id,
                tg_message_id=msg.id,
                parent_tg_message_id=parent_tg_message_id,
                parent_post_id=parent_post_id,
                date=msg.date,
                text=msg.message,
                views=getattr(msg, "views", None),
                comments_count=comments_count,
                involvement=None,
            )
            await session.commit()
            logging.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, msg.id, channel.username)

            db_post = await session.get(Post, post.id)
            if db_post is None:
                continue
            result = await pipeline.run_for_post(session, db_post)

            await _schedule_post_jobs(
                session,
                post=db_post,
                comment_first_delay_hours=comment_first_delay_hours,
                comment_interval_hours=comment_interval_hours,
                comment_window_hours=comment_window_hours,
                post_report_delay_hours=post_report_delay_hours,
                comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
            )
            await session.commit()
            logging.info(
                "Linked post id=%s verified=%s proposed=%s review=%s rejected=%s candidates=%s",
                post.id,
                result.links_verified,
                result.links_proposed,
                result.queued_for_review,
                result.links_rejected,
                result.candidates_checked,
            )
        processed += 1

    logging.info("Finished @%s processed_posts=%s", channel.username, processed)
    return processed


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
                dedupe_key=f"build_event_report:{event_id}",
            )
        for process_id in process_ids:
            await enqueue_job(
                session,
                job_type=JobType.BUILD_PROCESS_REPORT,
                payload={"process_id": process_id},
                priority=80,
                dedupe_key=f"build_process_report:{process_id}",
            )
        await session.commit()


async def _run_jobs(
    *,
    job_batch_size: int,
    worker_id: str,
    collect_comments_quota_per_run: int,
    tg_client: TelegramClient,
) -> int:
    report_project = TgReportProject(llm_model="ollama/llama3:8b-instruct-q4_K_M")
    executed = 0
    collect_comments_global_cooldown_until: datetime | None = None
    collect_comments_processed = 0
    collect_comments_flood_streak = 0
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
            },
        )
        await session.commit()

    for job in jobs:
        async with AsyncSessionLocal() as session:
            db_job = await session.get(Job, job.id)
            if db_job is None:
                continue
            effective_settings = await get_all_settings(session)
            report_config = report_config_from_settings(effective_settings)
            ingest_settings = effective_settings.get("ingest", {})
            cc_sleep_min_ms = int(ingest_settings.get("collect_comments_sleep_min_ms", 700))
            cc_sleep_max_ms = int(ingest_settings.get("collect_comments_sleep_max_ms", 1400))
            if cc_sleep_max_ms < cc_sleep_min_ms:
                cc_sleep_max_ms = cc_sleep_min_ms
            try:
                if db_job.type == JobType.COLLECT_COMMENTS:
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
                        logging.info(
                            "Job collect_comments post_id=%s status=%s err=%s",
                            post_id,
                            status,
                            result.get("error"),
                        )
                    else:
                        logging.info("Job collect_comments post_id=%s status=%s", post_id, status)
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
                        collect_comments_flood_streak += 1
                        retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(10, wait_seconds))
                        # Adaptive global cool-down: if flood-waits happen consecutively,
                        # increase pause to reduce repeated throttling.
                        base_cooldown_sec = max(120, wait_seconds)
                        if collect_comments_flood_streak >= 2:
                            adaptive_cooldown_sec = min(1800, base_cooldown_sec * (2 ** (collect_comments_flood_streak - 1)))
                        else:
                            adaptive_cooldown_sec = base_cooldown_sec
                        collect_comments_global_cooldown_until = datetime.now(timezone.utc) + timedelta(
                            seconds=adaptive_cooldown_sec
                        )
                        logging.warning(
                            "collect_comments flood streak=%s wait=%ss cooldown=%ss",
                            collect_comments_flood_streak,
                            wait_seconds,
                            adaptive_cooldown_sec,
                        )
                        await requeue_job(
                            session,
                            job=db_job,
                            retry_at=retry_at,
                            error=f"collect_comments:flood_wait:{wait_seconds}",
                        )
                        await session.commit()
                        if cc_sleep_max_ms > 0:
                            await asyncio.sleep(random.randint(cc_sleep_min_ms, cc_sleep_max_ms) / 1000.0)
                        continue

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
                elif db_job.type == JobType.BUILD_POST_REPORT:
                    payload = db_job.payload_json or {}
                    post_id = int(payload.get("post_id"))
                    result = await build_post_report(
                        session,
                        post_id=post_id,
                        report_project=report_project,
                        report_config=report_config,
                    )
                    logging.info("Job build_post_report post_id=%s status=%s", post_id, result.get("status"))
                elif db_job.type == JobType.BUILD_EVENT_REPORT:
                    payload = db_job.payload_json or {}
                    event_id = int(payload.get("event_id"))
                    result = await build_event_report_draft(session, event_id=event_id)
                    logging.info("Job build_event_report event_id=%s status=%s", event_id, result.get("status"))
                elif db_job.type == JobType.BUILD_PROCESS_REPORT:
                    payload = db_job.payload_json or {}
                    process_id = int(payload.get("process_id"))
                    result = await build_process_report_draft(session, process_id=process_id)
                    logging.info("Job build_process_report process_id=%s status=%s", process_id, result.get("status"))
                elif db_job.type == JobType.ARCHIVE_RETENTION:
                    payload = db_job.payload_json or {}
                    retention_days = int(payload.get("retention_days", 30))
                    batch_limit = int(payload.get("batch_limit", 1000))
                    result = await run_archive_retention(
                        session,
                        retention_days=retention_days,
                        batch_limit=batch_limit,
                    )
                    logging.info("Job archive_retention status=ok details=%s", result)
                else:
                    raise ValueError(f"Unsupported job type: {db_job.type}")

                await mark_job_done(session, job=db_job)
                await session.commit()
                executed += 1
            except Exception as exc:
                await mark_job_failed(session, job=db_job, error=repr(exc))
                await session.commit()
                logging.warning("Job failed id=%s type=%s err=%r", db_job.id, db_job.type, exc)
    return executed


async def _run_single_cycle(client: TelegramClient, args: argparse.Namespace, worker_id: str) -> None:
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
    collect_comments_quota_per_run = int(jobs_settings.get("collect_comments_quota_per_run", 5))
    retention_days = int(retention_settings.get("retention_days", args.retention_days))
    archive_batch_size = int(retention_settings.get("archive_batch_size", args.archive_batch_size))

    channels = await _get_active_channels()
    total_processed_posts = 0
    if not channels:
        logging.warning("No active channels found.")
    else:
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
        await session.commit()

    executed_jobs = await _run_jobs(
        job_batch_size=job_batch_size,
        worker_id=worker_id,
        collect_comments_quota_per_run=collect_comments_quota_per_run,
        tg_client=client,
    )
    logging.info("Cycle done. executed_jobs=%s", executed_jobs)


async def main_async(args: argparse.Namespace) -> None:
    client = _build_client(
        session_suffix=args.session_suffix,
        unique_session_per_run=args.unique_session_per_run,
    )
    worker_id = f"pipeline-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    await _with_session_lock_retry(lambda: client.start(), op_name="client.start")
    try:
        if args.daemon:
            logging.info("Daemon mode started. worker_id=%s poll_seconds=%s", worker_id, args.poll_seconds)
            while True:
                cycle_started_at = datetime.now(timezone.utc)
                try:
                    await _run_single_cycle(client, args, worker_id)
                except Exception as exc:
                    logging.exception("Cycle failed: %r", exc)
                async with AsyncSessionLocal() as session:
                    effective_settings = await get_all_settings(session)
                ingest_settings = effective_settings.get("ingest", {})
                poll_seconds = int(ingest_settings.get("poll_seconds", args.poll_seconds))
                elapsed = (datetime.now(timezone.utc) - cycle_started_at).total_seconds()
                sleep_for = max(1, int(poll_seconds - elapsed))
                await asyncio.sleep(sleep_for)
        else:
            await _run_single_cycle(client, args, worker_id)
    finally:
        try:
            await _with_session_lock_retry(lambda: client.disconnect(), op_name="client.disconnect")
        except Exception as exc:
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
