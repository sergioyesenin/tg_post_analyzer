from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import String, and_, cast, desc, func, select

# Ensure project root is in sys.path when launched as:
# `python scripts/test_pipeline_run.py`
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Disable external telemetry noise/timeouts for local smoke tests.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

from config import settings
from db.models import (
    Channel,
    Event,
    EventPost,
    Post,
    PostFact,
    PostLink,
    Process,
    ProcessEvent,
    VerificationStatus,
)
from db.session import AsyncSessionLocal
from services.events.build_events import rebuild_events
from services.linking.candidates import upsert_post_facts
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline
from services.processes.build_processes import rebuild_processes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a fast end-to-end test of linking/events/processes pipeline with console logs."
    )
    parser.add_argument("--hours-back", type=int, default=24, help="How far back to sample posts.")
    parser.add_argument("--max-posts", type=int, default=6, help="Max posts to run linking for.")
    parser.add_argument("--top-k", type=int, default=10, help="Temporary candidate top-k during this run.")
    parser.add_argument(
        "--channel-limit",
        type=int,
        default=3,
        help="Max active channels to include (sorted by id).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--fallback-anytime",
        action="store_true",
        default=True,
        help="If no posts in time window, sample latest posts regardless of date.",
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)-7s | %(message)s",
    )


async def _load_active_channel_ids(limit: int) -> list[int]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Channel.id)
            .where(Channel.is_active.is_(True))
            .order_by(Channel.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [row[0] for row in rows]


async def _sample_posts(
    *,
    channel_ids: list[int],
    date_from: datetime,
    max_posts: int,
) -> list[Post]:
    if not channel_ids:
        return []
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Post)
            .where(
                and_(
                    Post.channel_id.in_(channel_ids),
                    Post.date >= date_from,
                )
            )
            .order_by(desc(Post.date))
            .limit(max_posts)
        )
        return list((await session.execute(stmt)).scalars().all())


async def _sample_posts_anytime(*, channel_ids: list[int], max_posts: int) -> list[Post]:
    if not channel_ids:
        return []
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Post)
            .where(Post.channel_id.in_(channel_ids))
            .order_by(desc(Post.date))
            .limit(max_posts)
        )
        return list((await session.execute(stmt)).scalars().all())


async def _channel_post_diagnostics(channel_ids: list[int], date_from: datetime) -> list[tuple[int, int, datetime | None, datetime | None]]:
    if not channel_ids:
        return []
    async with AsyncSessionLocal() as session:
        rows: list[tuple[int, int, datetime | None, datetime | None]] = []
        for channel_id in channel_ids:
            count_stmt = select(func.count()).select_from(Post).where(
                and_(Post.channel_id == channel_id, Post.date >= date_from)
            )
            cnt = int((await session.execute(count_stmt)).scalar_one())
            minmax_stmt = select(func.min(Post.date), func.max(Post.date)).where(Post.channel_id == channel_id)
            min_dt, max_dt = (await session.execute(minmax_stmt)).one()
            rows.append((channel_id, cnt, min_dt, max_dt))
        return rows


async def _warmup_facts(channel_ids: list[int], date_from: datetime, limit: int) -> int:
    if not channel_ids:
        return 0
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Post)
            .where(and_(Post.channel_id.in_(channel_ids), Post.date >= date_from))
            .order_by(desc(Post.date))
            .limit(limit)
        )
        posts = (await session.execute(stmt)).scalars().all()
        for post in posts:
            await upsert_post_facts(session, post)
        await session.commit()
        return len(posts)


async def _run_linking_for_posts(posts: list[Post], top_k: int) -> dict:
    pipeline = NoLlmLinkingPipeline.build_default()
    old_top_k = settings.LINKING_TOP_K
    settings.LINKING_TOP_K = top_k
    stats = Counter()
    started = time.perf_counter()

    try:
        async with AsyncSessionLocal() as session:
            for idx, post in enumerate(posts, start=1):
                t0 = time.perf_counter()
                logging.info(
                    "Linking [%s/%s] post_id=%s channel_id=%s date=%s",
                    idx,
                    len(posts),
                    post.id,
                    post.channel_id,
                    post.date.isoformat(),
                )
                db_post = await session.get(Post, post.id)
                if db_post is None:
                    logging.warning("Post id=%s not found in DB. Skipped.", post.id)
                    continue
                result = await pipeline.run_for_post(session, db_post)
                await session.commit()
                elapsed = time.perf_counter() - t0
                logging.info(
                    "Result post_id=%s | cand=%s verified=%s proposed=%s review=%s rejected=%s | %.2fs",
                    result.post_id,
                    result.candidates_checked,
                    result.links_verified,
                    result.links_proposed,
                    result.queued_for_review,
                    result.links_rejected,
                    elapsed,
                )
                stats["posts_processed"] += 1
                stats["verified"] += result.links_verified
                stats["proposed"] += result.links_proposed
                stats["needs_review"] += result.queued_for_review
                stats["rejected"] += result.links_rejected
                stats["candidates_checked"] += result.candidates_checked
    finally:
        settings.LINKING_TOP_K = old_top_k

    stats["linking_seconds"] = round(time.perf_counter() - started, 2)
    return dict(stats)


async def _rebuild_graphs(date_from: datetime, date_to: datetime) -> dict:
    async with AsyncSessionLocal() as session:
        t0 = time.perf_counter()
        rebuilt_events = await rebuild_events(session, date_from=date_from, date_to=date_to)
        await session.commit()
        t1 = time.perf_counter()

    async with AsyncSessionLocal() as session:
        rebuilt_process_edges = await rebuild_processes(session, date_from=date_from, date_to=date_to)
        await session.commit()
        t2 = time.perf_counter()

    return {
        "rebuilt_events": rebuilt_events,
        "rebuilt_process_edges": rebuilt_process_edges,
        "events_seconds": round(t1 - t0, 2),
        "processes_seconds": round(t2 - t1, 2),
    }


def _spans_are_valid(evidence_json: dict | None) -> bool:
    if not isinstance(evidence_json, dict):
        return False
    spans = evidence_json.get("spans")
    if not isinstance(spans, list) or not spans:
        return False
    has_src = any(isinstance(item, dict) and item.get("post") == "src" and item.get("quote") for item in spans)
    has_dst = any(isinstance(item, dict) and item.get("post") == "dst" and item.get("quote") for item in spans)
    return has_src and has_dst


async def _audit_and_report(date_from: datetime, date_to: datetime, run_started_at: datetime) -> dict:
    async with AsyncSessionLocal() as session:
        totals = {}
        for model, name in [
            (PostFact, "post_facts"),
            (PostLink, "post_links"),
            (Event, "events"),
            (EventPost, "event_posts"),
            (Process, "processes"),
            (ProcessEvent, "process_events"),
        ]:
            count_stmt = select(func.count()).select_from(model)
            totals[name] = int((await session.execute(count_stmt)).scalar_one())

        status_stmt = (
            select(PostLink.status, func.count())
            .where(PostLink.created_at >= date_from, PostLink.created_at <= date_to)
            .group_by(PostLink.status)
        )
        status_rows = (await session.execute(status_stmt)).all()
        link_status = {str(row[0]): int(row[1]) for row in status_rows}

        pipeline_stmt = (
            select(PostLink.pipeline_version, func.count())
            .group_by(PostLink.pipeline_version)
            .order_by(func.count().desc())
        )
        pipeline_rows = (await session.execute(pipeline_stmt)).all()
        pipeline_versions = {str(row[0]): int(row[1]) for row in pipeline_rows}

        risky_stmt = (
            select(PostLink)
            .where(
                cast(PostLink.status, String).in_(["verified", "proposed", "needs_review"])
            )
            .order_by(PostLink.updated_at.desc())
            .limit(500)
        )
        links = (await session.execute(risky_stmt)).scalars().all()
        invalid_spans = [link for link in links if not _spans_are_valid(link.evidence_json)]

        current_run_links_stmt = (
            select(PostLink)
            .where(
                PostLink.created_at >= run_started_at,
                PostLink.pipeline_version == settings.LINKING_PIPELINE_VERSION,
            )
            .order_by(PostLink.created_at.desc())
        )
        current_run_links = (await session.execute(current_run_links_stmt)).scalars().all()
        current_run_invalid_spans = [link for link in current_run_links if not _spans_are_valid(link.evidence_json)]

        same_event_without_anchor = []
        for link in links:
            if str(link.link_type) != "PostLinkType.SAME_EVENT" and getattr(link.link_type, "value", None) != "same_event":
                continue
            evidence = link.evidence_json or {}
            anchors = evidence.get("anchors", {}) if isinstance(evidence, dict) else {}
            shared = anchors.get("shared_entities", []) if isinstance(anchors, dict) else []
            if not shared:
                same_event_without_anchor.append(link)

        events_stmt = (
            select(Event.id, Event.status, func.count(EventPost.post_id))
            .join(EventPost, EventPost.event_id == Event.id)
            .where(Event.started_at >= date_from, Event.started_at <= date_to)
            .group_by(Event.id, Event.status)
            .order_by(Event.id.desc())
            .limit(20)
        )
        events_preview = (await session.execute(events_stmt)).all()

        processes_stmt = (
            select(Process.id, Process.status, func.count(ProcessEvent.event_id))
            .outerjoin(ProcessEvent, ProcessEvent.process_id == Process.id)
            .where(Process.started_at >= date_from, Process.started_at <= date_to)
            .group_by(Process.id, Process.status)
            .order_by(Process.id.desc())
            .limit(20)
        )
        processes_preview = (await session.execute(processes_stmt)).all()

        return {
            "totals": totals,
            "link_status": link_status,
            "pipeline_versions": pipeline_versions,
            "invalid_spans_count": len(invalid_spans),
            "current_run_links_count": len(current_run_links),
            "current_run_invalid_spans_count": len(current_run_invalid_spans),
            "same_event_without_anchor_count": len(same_event_without_anchor),
            "events_preview": events_preview,
            "processes_preview": processes_preview,
        }


async def _run(args: argparse.Namespace) -> None:
    now = datetime.now(timezone.utc)
    run_started_at = now
    date_from = now - timedelta(hours=args.hours_back)
    date_to = now

    logging.info("Pipeline smoke test started.")
    logging.info(
        "Window: %s .. %s | max_posts=%s | top_k=%s",
        date_from.isoformat(),
        date_to.isoformat(),
        args.max_posts,
        args.top_k,
    )

    channel_ids = await _load_active_channel_ids(args.channel_limit)
    logging.info("Active channels selected: %s", channel_ids)
    if not channel_ids:
        logging.error("No active channels in DB. Stop.")
        return
    diagnostics = await _channel_post_diagnostics(channel_ids, date_from)
    for channel_id, cnt, min_dt, max_dt in diagnostics:
        logging.info(
            "Channel %s | posts_in_window=%s | oldest=%s | newest=%s",
            channel_id,
            cnt,
            min_dt.isoformat() if min_dt else None,
            max_dt.isoformat() if max_dt else None,
        )

    warmed = await _warmup_facts(channel_ids, date_from, limit=max(30, args.max_posts * 10))
    logging.info("Warm-up facts complete: %s posts indexed into post_facts.", warmed)

    posts = await _sample_posts(channel_ids=channel_ids, date_from=date_from, max_posts=args.max_posts)
    logging.info("Sampled posts for linking: %s", [p.id for p in posts])
    if not posts:
        if args.fallback_anytime:
            logging.warning("No posts in selected window. Fallback to latest posts regardless of date.")
            posts = await _sample_posts_anytime(channel_ids=channel_ids, max_posts=args.max_posts)
            logging.info("Fallback sampled posts: %s", [p.id for p in posts])
        if not posts:
            logging.error("No posts found for selected channels. Stop.")
            return

    linking_stats = await _run_linking_for_posts(posts, top_k=args.top_k)
    logging.info("Linking summary: %s", linking_stats)

    rebuild_stats = await _rebuild_graphs(date_from=date_from, date_to=date_to)
    logging.info("Rebuild summary: %s", rebuild_stats)

    audit = await _audit_and_report(date_from=date_from, date_to=date_to, run_started_at=run_started_at)
    logging.info("DB totals: %s", audit["totals"])
    logging.info("Link statuses in window: %s", audit["link_status"])
    logging.info("Post links by pipeline_version: %s", audit["pipeline_versions"])
    logging.info("Audit invalid spans count: %s", audit["invalid_spans_count"])
    logging.info(
        "Current run links: %s | current run invalid spans: %s",
        audit["current_run_links_count"],
        audit["current_run_invalid_spans_count"],
    )
    logging.info("Audit same_event without shared_entities count: %s", audit["same_event_without_anchor_count"])

    logging.info("Events preview (event_id, status, post_count):")
    for row in audit["events_preview"]:
        logging.info("  %s", row)
    logging.info("Processes preview (process_id, status, edge_count):")
    for row in audit["processes_preview"]:
        logging.info("  %s", row)

    if audit["current_run_invalid_spans_count"] > 0:
        logging.warning("Potential hallucination risk: there are links without valid src/dst evidence spans.")
    else:
        logging.info("Evidence span check passed for sampled recent links.")
    logging.info("Pipeline smoke test finished.")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
