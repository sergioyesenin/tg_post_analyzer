from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, EventPost, EventReport, Post, ProcessEvent, ProcessReport, Report
from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.ingestion_core import IngestionCore, IngestionContext, IngestionOptions
from services.jobs import JobType, enqueue_job
from services.processes.build_processes import rebuild_processes
from services.reporting import (
    REPORT_STATUS_STALE,
    mark_report_payload_stale,
)


logger = logging.getLogger(__name__)


async def enqueue_comment_refresh_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int,
    source: str,
):
    return await enqueue_job(
        session,
        job_type=JobType.REFRESH_COMMENTS,
        payload={"post_id": post_id, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=8,
        dedupe_key=None,
    )


async def enqueue_event_report_job(
    session: AsyncSession,
    *,
    event_id: int,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_EVENT_REPORT,
        payload={"event_id": event_id, "source": source, "requested_by_user_id": requested_by_user_id},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=dedupe_key,
    )


async def enqueue_process_report_job(
    session: AsyncSession,
    *,
    process_id: int,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_PROCESS_REPORT,
        payload={"process_id": process_id, "source": source, "requested_by_user_id": requested_by_user_id},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=dedupe_key,
    )


async def enqueue_post_report_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT,
        payload={"post_id": post_id, "source": source, "requested_by_user_id": requested_by_user_id},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=dedupe_key,
    )


async def enqueue_post_report_batch_job(
    session: AsyncSession,
    *,
    filters: dict,
    priority: int,
    source: str,
):
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_REPORT_BATCH,
        payload={"filters": filters, "source": source},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=3,
        dedupe_key=None,
    )


async def enqueue_post_link_job(
    session: AsyncSession,
    *,
    post_id: int,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_LINKS,
        payload={"post_id": post_id, "source": source, "requested_by_user_id": requested_by_user_id},
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=5,
        dedupe_key=dedupe_key,
    )


async def enqueue_rebuild_events_job(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.REBUILD_EVENTS,
        payload={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "source": source,
            "requested_by_user_id": requested_by_user_id,
        },
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=3,
        dedupe_key=dedupe_key,
    )


async def enqueue_rebuild_processes_job(
    session: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
    priority: int,
    source: str,
    requested_by_user_id: int | None,
    dedupe_key: str | None,
):
    return await enqueue_job(
        session,
        job_type=JobType.REBUILD_PROCESSES,
        payload={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "source": source,
            "requested_by_user_id": requested_by_user_id,
        },
        run_at=datetime.now(timezone.utc),
        priority=priority,
        max_attempts=3,
        dedupe_key=dedupe_key,
    )


async def schedule_due_post_report_jobs(
    *,
    min_age_hours: int,
    limit: int,
    priority_build_post_report: int,
) -> int:
    threshold = datetime.now(timezone.utc) - timedelta(hours=max(1, int(min_age_hours)))
    queued = 0
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Post.id)
            .outerjoin(Report, Report.post_id == Post.id)
            .where(Post.date <= threshold)
            .where(Post.last_comments_scan_at.is_not(None))
            .where(Report.id.is_(None))
            .order_by(Post.date.asc(), Post.id.asc())
            .limit(limit)
        )
        post_ids = [int(row[0]) for row in (await session.execute(stmt)).all()]
        now_utc = datetime.now(timezone.utc)
        for post_id in post_ids:
            job = await enqueue_job(
                session,
                job_type=JobType.BUILD_POST_REPORT,
                payload={"post_id": post_id, "source": "scheduler"},
                run_at=now_utc,
                priority=priority_build_post_report,
                max_attempts=5,
                dedupe_key=f"build_post_report:{post_id}",
            )
            if job is not None:
                queued += 1
        await session.commit()
    return queued


async def dispatch_post_report_batch(
    session: AsyncSession,
    *,
    filters: dict,
    priority_build_post_report: int,
    enqueue_post_report_job_fn,
) -> dict:
    channel_ids = [int(value) for value in (filters.get("channel_ids") or [])]
    categories = [str(value) for value in (filters.get("categories") or []) if str(value).strip()]
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    min_comments = filters.get("min_comments")
    limit = max(1, min(500, int(filters.get("limit") or 100)))

    stmt = select(Post.id).join(Channel, Channel.id == Post.channel_id).order_by(Post.date.desc(), Post.id.desc())
    conditions = []
    if channel_ids:
        conditions.append(Post.channel_id.in_(channel_ids))
    if categories:
        conditions.append(Channel.category.in_(categories))
    if date_from is not None:
        conditions.append(Post.date >= datetime.fromisoformat(str(date_from)))
    if date_to is not None:
        conditions.append(Post.date <= datetime.fromisoformat(str(date_to)))
    if min_comments is not None:
        conditions.append(Post.comments_count >= int(min_comments))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    post_ids = [int(row[0]) for row in (await session.execute(stmt.limit(limit))).all()]
    queued_job_ids: list[int] = []
    skipped_post_ids: list[int] = []
    for post_id in post_ids:
        job = await enqueue_post_report_job_fn(
            session,
            post_id=post_id,
            priority=priority_build_post_report,
            source="batch",
            dedupe_key=f"build_post_report:{post_id}",
        )
        if job is None:
            skipped_post_ids.append(post_id)
            continue
        queued_job_ids.append(int(job.id))

    return {
        "status": "queued",
        "matched_posts": len(post_ids),
        "queued_jobs": len(queued_job_ids),
        "skipped_existing": len(skipped_post_ids),
        "post_ids": post_ids,
        "job_ids": queued_job_ids,
        "filters": filters,
    }


async def enqueue_related_event_report_jobs(
    session: AsyncSession,
    *,
    post_id: int,
    source: str,
    priority_build_event_report: int,
    enqueue_event_report_job_fn,
) -> int:
    event_ids = [int(row[0]) for row in (await session.execute(select(EventPost.event_id).where(EventPost.post_id == post_id).distinct())).all()]
    queued = 0
    for event_id in event_ids:
        job = await enqueue_event_report_job_fn(
            session,
            event_id=event_id,
            priority=priority_build_event_report,
            source=source,
            dedupe_key=f"build_event_report:{event_id}",
        )
        if job is not None:
            queued += 1
    return queued


async def mark_related_event_reports_stale(session: AsyncSession, *, post_id: int) -> int:
    rows = (
        await session.execute(
            select(EventReport)
            .where(
                EventReport.id.in_(
                    select(EventReport.id)
                    .join(EventPost, EventPost.event_id == EventReport.event_id)
                    .where(EventPost.post_id == post_id)
                    .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
                    .distinct(EventReport.event_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    for report in rows:
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(payload, dependency_type="post_report", dependency_id=post_id)
        marked += 1
    if marked:
        await session.flush()
    return marked


async def enqueue_related_process_report_jobs(
    session: AsyncSession,
    *,
    event_id: int,
    source: str,
    priority_build_process_report: int,
    enqueue_process_report_job_fn,
) -> int:
    process_ids = [
        int(row[0])
        for row in (await session.execute(select(ProcessEvent.process_id).where(ProcessEvent.event_id == event_id).distinct())).all()
    ]
    queued = 0
    for process_id in process_ids:
        job = await enqueue_process_report_job_fn(
            session,
            process_id=process_id,
            priority=priority_build_process_report,
            source=source,
            dedupe_key=f"build_process_report:{process_id}",
        )
        if job is not None:
            queued += 1
    return queued


async def mark_related_process_reports_stale(session: AsyncSession, *, event_id: int) -> int:
    rows = (
        await session.execute(
            select(ProcessReport)
            .where(
                ProcessReport.id.in_(
                    select(ProcessReport.id)
                    .join(ProcessEvent, ProcessEvent.process_id == ProcessReport.process_id)
                    .where(ProcessEvent.event_id == event_id)
                    .order_by(ProcessReport.process_id.asc(), ProcessReport.version.desc(), ProcessReport.id.desc())
                    .distinct(ProcessReport.process_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    for report in rows:
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(payload, dependency_type="event_report", dependency_id=event_id)
        marked += 1
    if marked:
        await session.flush()
    return marked


async def get_active_channels() -> list[Channel]:
    async with AsyncSessionLocal() as session:
        stmt = select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id.asc())
        return list((await session.execute(stmt)).scalars().all())


async def get_last_tg_message_id_for_channel(*, session: AsyncSession, channel_id: int) -> int:
    stmt = select(func.max(Post.tg_message_id)).where(Post.channel_id == channel_id)
    last_value = (await session.execute(stmt)).scalar_one_or_none()
    if isinstance(last_value, int) and last_value > 0:
        return last_value
    return 0


def collect_comments_job_priority(*, post: Post, scan_index: int) -> int:
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


def split_jobs_for_telegram_worker(jobs: list) -> tuple[list, list]:
    comment_jobs: list = []
    other_jobs: list = []
    for job in jobs:
        if job.type in {JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS}:
            comment_jobs.append(job)
        else:
            other_jobs.append(job)
    return comment_jobs, other_jobs


async def schedule_post_jobs(
    session: AsyncSession,
    *,
    post: Post,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    comment_schedule_jitter_seconds: int,
    priority_build_post_links: int,
    collect_comments_job_priority_fn,
) -> None:
    await enqueue_job(
        session,
        job_type=JobType.BUILD_POST_LINKS,
        payload={"post_id": post.id},
        run_at=datetime.now(timezone.utc),
        priority=priority_build_post_links,
        max_attempts=5,
        dedupe_key=f"build_post_links:{post.id}",
    )

    first_comment_at = post.date + timedelta(hours=comment_first_delay_hours)
    comment_until = post.date + timedelta(hours=comment_window_hours)
    current = first_comment_at
    scan_index = 0
    while current <= comment_until:
        jitter_seconds = random.randint(0, max(0, int(comment_schedule_jitter_seconds)))
        scheduled_at = current + timedelta(seconds=jitter_seconds)
        ts = int(scheduled_at.timestamp())
        await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": post.id, "scan_index": scan_index, "source": "scheduler"},
            run_at=scheduled_at,
            priority=collect_comments_job_priority_fn(post=post, scan_index=scan_index),
            max_attempts=8,
            dedupe_key=f"collect_comments:{post.id}:{ts}",
        )
        current = current + timedelta(hours=comment_interval_hours)
        scan_index += 1


async def process_channel(
    client,
    channel: Channel,
    *,
    since_utc: datetime,
    max_posts: int,
    comment_first_delay_hours: int,
    comment_interval_hours: int,
    comment_window_hours: int,
    comment_schedule_jitter_seconds: int,
    skip_channel_ids: dict[int, str],
    priority_build_post_links: int,
    collect_comments_job_priority_fn,
) -> int:
    if channel.id in skip_channel_ids:
        logger.info("Skip channel id=%s (@%s): excluded by config", channel.id, channel.username)
        return 0

    logger.info("Parsing channel @%s since %s", channel.username, since_utc.isoformat())
    async with AsyncSessionLocal() as session:
        channel_last_tg_msg_id = await get_last_tg_message_id_for_channel(session=session, channel_id=channel.id)

    core = IngestionCore(tg_client=client, session_factory=AsyncSessionLocal)
    options = IngestionOptions(
        since_utc=since_utc,
        max_posts=max_posts,
        min_tg_message_id_exclusive=channel_last_tg_msg_id,
        resolve_album_representative=True,
    )

    async def _on_post_saved(session: AsyncSession, post: Post, ctx: IngestionContext) -> None:
        await schedule_post_jobs(
            session,
            post=post,
            comment_first_delay_hours=comment_first_delay_hours,
            comment_interval_hours=comment_interval_hours,
            comment_window_hours=comment_window_hours,
            comment_schedule_jitter_seconds=comment_schedule_jitter_seconds,
            priority_build_post_links=priority_build_post_links,
            collect_comments_job_priority_fn=collect_comments_job_priority_fn,
        )
        logger.info("Saved post id=%s tg_msg_id=%s channel=@%s", post.id, ctx.message.id, channel.username)

    async with client.operation_lock:
        result = await core.ingest_channel(channel=channel, options=options, on_post_saved=_on_post_saved)
    logger.info("Finished @%s processed_posts=%s stopped_reason=%s", channel.username, result.processed_posts, result.stopped_reason)
    return result.processed_posts


async def rebuild_event_process_graphs(*, date_from: datetime, date_to: datetime, created_by: str) -> None:
    async with AsyncSessionLocal() as session:
        rebuilt_events = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by=created_by)
        await session.commit()
    logger.info("Rebuilt events=%s for %s..%s", rebuilt_events, date_from.isoformat(), date_to.isoformat())

    async with AsyncSessionLocal() as session:
        rebuilt_process_edges = await rebuild_processes(session, date_from=date_from, date_to=date_to, created_by=created_by)
        await session.commit()
    logger.info(
        "Rebuilt process_edges=%s for %s..%s",
        rebuilt_process_edges,
        date_from.isoformat(),
        date_to.isoformat(),
    )
