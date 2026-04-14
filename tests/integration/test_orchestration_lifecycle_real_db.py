from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from agents import reporter
from db.models import (
    Channel,
    Event,
    EventPost,
    EventReport,
    Job,
    JobDeadLetter,
    Post,
    PostLink,
    PostLinkType,
    Process,
    ProcessEvent,
    ProcessRelationType,
    ProcessReport,
    Report,
    VerificationStatus,
)
from schemas.linking import LinkRunResponse
from schemas.report import EventReportPayload, PostReportPayload, ProcessReportPayload
from services.reporting import sync_post_report_staleness
from services.events.build_events import rebuild_events
from services.jobs import JobType, enqueue_job
from services.processes.build_processes import rebuild_processes
from services import pipeline_runtime


def _ready_post_report_payload(*, post_id: int, summary: str) -> dict:
    return {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": post_id,
        "title": f"Post {post_id}",
        "summary": summary,
        "comment_count": 7,
        "sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.1, "negative": 0.2, "neutral": 0.7},
            "confidence": "medium",
        },
        "topics": [{"name": "topic", "share": 1.0}],
        "clusters": [],
        "time_trends": [],
        "risks": [],
        "anomalies": [],
        "representative_quotes": [],
        "confidence": {"overall": "medium", "reason": "seed"},
        "meta": {"prompt_version": "post_report_v2"},
    }


def _limited_post_report_payload(*, post_id: int, summary: str) -> dict:
    payload = _ready_post_report_payload(post_id=post_id, summary=summary)
    payload["status"] = "limited"
    payload["confidence"] = {"overall": "medium", "reason": "limited"}
    return payload


def _ready_event_report_payload(*, event_id: int, post_ids: list[int], summary: str) -> dict:
    return {
        "type": "event_report_v2",
        "status": "ready",
        "event_id": event_id,
        "event_title": f"Event {event_id}",
        "posts_count": len(post_ids),
        "source_post_reports": list(post_ids),
        "sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "medium",
        },
        "cross_post_topics": [],
        "post_dynamics": [],
        "event_trends": [],
        "risks": [],
        "anomalies": [],
        "summary": summary,
        "confidence": {"overall": "medium", "reason": "seed"},
        "meta": {"prompt_version": "event_report_v2", "source_type": "post_reports"},
    }


def _ready_process_report_payload(*, process_id: int, event_ids: list[int], summary: str) -> dict:
    return {
        "type": "process_report_v2",
        "status": "ready",
        "process_id": process_id,
        "process_title": f"Process {process_id}",
        "events_count": len(event_ids),
        "source_event_reports": list(event_ids),
        "overall_sentiment": {
            "dominant": "neutral",
            "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
            "confidence": "medium",
        },
        "stage_analysis": [],
        "process_trends": [],
        "bottlenecks": [],
        "risks": [],
        "summary": summary,
        "confidence": {"overall": "medium", "reason": "seed"},
        "meta": {"prompt_version": "process_report_v2", "source_type": "event_reports"},
    }


def _seed_event_identity_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="event_chan", title="Event Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=1001,
                    date=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
                    text="Root event post",
                    comments_count=3,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=1002,
                    date=datetime(2026, 3, 20, 12, 10, tzinfo=timezone.utc),
                    text="Context post v1",
                    comments_count=2,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add(
            PostLink(
                src_post_id=1,
                dst_post_id=2,
                link_type=PostLinkType.SAME_EVENT,
                score=0.9,
                status=VerificationStatus.VERIFIED,
                evidence_json={"reason": "seed"},
                model_version="test",
                pipeline_version="test",
            )
        )
        session.commit()


def _seed_event_split_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="event_split_chan", title="Event Split Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=1101,
                    date=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
                    text="Split root A",
                    comments_count=3,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=1102,
                    date=datetime(2026, 3, 20, 12, 5, tzinfo=timezone.utc),
                    text="Split member A",
                    comments_count=2,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=1103,
                    date=datetime(2026, 3, 20, 12, 10, tzinfo=timezone.utc),
                    text="Split root B",
                    comments_count=4,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=1104,
                    date=datetime(2026, 3, 20, 12, 15, tzinfo=timezone.utc),
                    text="Split member B",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.94,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=2,
                    dst_post_id=3,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.92,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=3,
                    dst_post_id=4,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.91,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


def _seed_process_identity_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="process_chan", title="Process Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=2001,
                    date=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    text="Event one root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=2002,
                    date=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    text="Event two root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=2003,
                    date=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    text="Event three root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    id=11,
                    title="Event 11",
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 10, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=12,
                    title="Event 12",
                    started_at=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 11, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=13,
                    title="Event 13",
                    started_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
            ]
        )
        session.add_all(
            [
                EventPost(event_id=11, post_id=1, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=12, post_id=2, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=13, post_id=3, role="root", status=VerificationStatus.VERIFIED),
            ]
        )
        session.add(
            PostLink(
                src_post_id=1,
                dst_post_id=2,
                link_type=PostLinkType.UPDATE,
                score=0.85,
                status=VerificationStatus.VERIFIED,
                evidence_json={"reason": "seed"},
                model_version="test",
                pipeline_version="test",
            )
        )
        session.commit()


def _seed_process_split_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="process_split_chan", title="Process Split Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=2101,
                    date=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    text="Split process event one root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=2102,
                    date=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    text="Split process event two root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=2103,
                    date=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    text="Split process event three root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=2104,
                    date=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    text="Split process event four root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    id=21,
                    title="Process Split Event 21",
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 10, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=22,
                    title="Process Split Event 22",
                    started_at=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 11, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=23,
                    title="Process Split Event 23",
                    started_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=24,
                    title="Process Split Event 24",
                    started_at=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 13, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
            ]
        )
        session.add_all(
            [
                EventPost(event_id=21, post_id=1, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=22, post_id=2, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=23, post_id=3, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=24, post_id=4, role="root", status=VerificationStatus.VERIFIED),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.UPDATE,
                    score=0.93,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=2,
                    dst_post_id=3,
                    link_type=PostLinkType.UPDATE,
                    score=0.92,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=3,
                    dst_post_id=4,
                    link_type=PostLinkType.UPDATE,
                    score=0.91,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


def _seed_process_merge_preference_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="process_merge_chan", title="Process Merge Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=2201,
                    date=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    text="Merge process event one root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=2202,
                    date=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    text="Merge process event two root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=2203,
                    date=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    text="Merge process event three root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=2204,
                    date=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    text="Merge process event four root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=5,
                    channel_id=1,
                    tg_message_id=2205,
                    date=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
                    text="Merge process event five root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    id=31,
                    title="Process Merge Event 31",
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 10, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=32,
                    title="Process Merge Event 32",
                    started_at=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 11, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=33,
                    title="Process Merge Event 33",
                    started_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=34,
                    title="Process Merge Event 34",
                    started_at=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 13, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=35,
                    title="Process Merge Event 35",
                    started_at=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 14, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
            ]
        )
        session.add_all(
            [
                EventPost(event_id=31, post_id=1, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=32, post_id=2, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=33, post_id=3, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=34, post_id=4, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=35, post_id=5, role="root", status=VerificationStatus.VERIFIED),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.UPDATE,
                    score=0.94,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=2,
                    dst_post_id=3,
                    link_type=PostLinkType.UPDATE,
                    score=0.93,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=4,
                    dst_post_id=5,
                    link_type=PostLinkType.UPDATE,
                    score=0.92,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


def _seed_process_unverified_update_links_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(
            Channel(
                id=1,
                username="process_unverified_chan",
                title="Process Unverified Chan",
                category="news",
                is_active=True,
            )
        )
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=2301,
                    date=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    text="Verified process root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=2302,
                    date=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    text="Verified process member",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=2303,
                    date=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    text="Proposed-only candidate",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=2304,
                    date=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    text="Rejected-only candidate",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    id=41,
                    title="Process Verified Event 41",
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 10, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=42,
                    title="Process Verified Event 42",
                    started_at=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 11, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=43,
                    title="Process Proposed Event 43",
                    started_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=44,
                    title="Process Rejected Event 44",
                    started_at=datetime(2026, 3, 21, 13, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 13, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
            ]
        )
        session.add_all(
            [
                EventPost(event_id=41, post_id=1, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=42, post_id=2, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=43, post_id=3, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=44, post_id=4, role="root", status=VerificationStatus.VERIFIED),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.UPDATE,
                    score=0.95,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "verified seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=2,
                    dst_post_id=3,
                    link_type=PostLinkType.UPDATE,
                    score=0.99,
                    status=VerificationStatus.PROPOSED,
                    evidence_json={"reason": "proposed should not connect"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=3,
                    dst_post_id=4,
                    link_type=PostLinkType.UPDATE,
                    score=0.98,
                    status=VerificationStatus.REJECTED,
                    evidence_json={"reason": "rejected should not connect"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


def _seed_process_nonempty_scope_without_verified_edges_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(
            Channel(
                id=1,
                username="process_noop_scope_chan",
                title="Process Noop Scope Chan",
                category="news",
                is_active=True,
            )
        )
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=2401,
                    date=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
                    text="Existing process event",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=2402,
                    date=datetime(2026, 3, 21, 15, 0, tzinfo=timezone.utc),
                    text="Proposed-only event",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=2403,
                    date=datetime(2026, 3, 21, 16, 0, tzinfo=timezone.utc),
                    text="Rejected-only event",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    id=51,
                    title="Noop Scope Event 51",
                    started_at=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 14, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=52,
                    title="Noop Scope Event 52",
                    started_at=datetime(2026, 3, 21, 15, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 15, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
                Event(
                    id=53,
                    title="Noop Scope Event 53",
                    started_at=datetime(2026, 3, 21, 16, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 3, 21, 16, 5, tzinfo=timezone.utc),
                    confidence=0.8,
                    status=VerificationStatus.VERIFIED,
                    created_by="test",
                ),
            ]
        )
        session.add_all(
            [
                EventPost(event_id=51, post_id=1, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=52, post_id=2, role="root", status=VerificationStatus.VERIFIED),
                EventPost(event_id=53, post_id=3, role="root", status=VerificationStatus.VERIFIED),
            ]
        )
        session.add(
            Process(
                id=60,
                title="Existing Candidate Process",
                started_at=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 3, 21, 14, 5, tzinfo=timezone.utc),
                confidence=0.75,
                status=VerificationStatus.VERIFIED,
                created_by="test",
            )
        )
        session.add(
            ProcessEvent(
                process_id=60,
                event_id=51,
                relation_type=ProcessRelationType.UPDATE,
                status=VerificationStatus.VERIFIED,
            )
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.UPDATE,
                    score=0.94,
                    status=VerificationStatus.PROPOSED,
                    evidence_json={"reason": "proposed should not expand process"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=2,
                    dst_post_id=3,
                    link_type=PostLinkType.UPDATE,
                    score=0.93,
                    status=VerificationStatus.REJECTED,
                    evidence_json={"reason": "rejected should not create process"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


def _seed_cascade_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="cascade_chan", title="Cascade Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=3001,
                date=datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc),
                text="Cascade root post",
                comments_count=7,
                analyzer_version="v1",
            )
        )
        session.add(
            Report(
                id=1,
                post_id=1,
                status="ready",
                content="old post report",
                report_json={
                    **_ready_post_report_payload(post_id=1, summary="old post report"),
                    "meta": {
                        "prompt_version": "post_report_v2",
                        "input_signature": "outdated-signature",
                        "current_input_signature": "outdated-signature",
                    },
                },
            )
        )
        session.add(
            Event(
                id=10,
                title="Cascade Event",
                started_at=datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 3, 22, 9, 5, tzinfo=timezone.utc),
                confidence=0.8,
                status=VerificationStatus.VERIFIED,
                created_by="test",
            )
        )
        session.add(EventPost(event_id=10, post_id=1, role="root", status=VerificationStatus.VERIFIED))
        session.add(
            EventReport(
                event_id=10,
                version=1,
                report_text="old event report",
                report_json=_ready_event_report_payload(event_id=10, post_ids=[1], summary="old event report"),
            )
        )
        session.add(
            Process(
                id=20,
                title="Cascade Process",
                started_at=datetime(2026, 3, 22, 9, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 3, 22, 9, 5, tzinfo=timezone.utc),
                confidence=0.75,
                status=VerificationStatus.VERIFIED,
                created_by="test",
            )
        )
        session.add(
            ProcessEvent(
                process_id=20,
                event_id=10,
                relation_type=ProcessRelationType.UPDATE,
                status=VerificationStatus.VERIFIED,
            )
        )
        session.add(
            ProcessReport(
                process_id=20,
                version=1,
                report_text="old process report",
                report_json=_ready_process_report_payload(process_id=20, event_ids=[10], summary="old process report"),
            )
        )
        session.commit()


def _seed_async_rebuild_fixture(session_factory) -> None:
    with session_factory() as session:
        session.add(Channel(id=1, username="job_chan", title="Job Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=4001,
                    date=datetime(2026, 3, 23, 8, 0, tzinfo=timezone.utc),
                    text="Event A root",
                    comments_count=2,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=4002,
                    date=datetime(2026, 3, 23, 8, 5, tzinfo=timezone.utc),
                    text="Event A member",
                    comments_count=2,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=4003,
                    date=datetime(2026, 3, 23, 9, 0, tzinfo=timezone.utc),
                    text="Event B root",
                    comments_count=2,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=4004,
                    date=datetime(2026, 3, 23, 9, 5, tzinfo=timezone.utc),
                    text="Event B member",
                    comments_count=2,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.9,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=3,
                    dst_post_id=4,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.9,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=1,
                    dst_post_id=3,
                    link_type=PostLinkType.UPDATE,
                    score=0.88,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_events_keeps_stable_event_identity_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    _seed_event_identity_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 20, 23, 59, tzinfo=timezone.utc)

    async with integration_async_session_factory() as session:
        rebuilt = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert rebuilt == 1

    with integration_sync_session_factory() as session:
        event = session.execute(select(Event)).scalar_one()
        initial_event_id = int(event.id)
        assert {
            row.post_id for row in session.execute(select(EventPost).where(EventPost.event_id == initial_event_id)).scalars().all()
        } == {1, 2}

        session.add(
            Post(
                id=3,
                channel_id=1,
                tg_message_id=1003,
                date=datetime(2026, 3, 20, 12, 20, tzinfo=timezone.utc),
                text="Context post v2",
                comments_count=4,
                analyzer_version="v1",
            )
        )
        session.execute(
            delete(PostLink).where(
                PostLink.src_post_id == 1,
                PostLink.dst_post_id == 2,
                PostLink.link_type == PostLinkType.SAME_EVENT,
            )
        )
        session.add(
            PostLink(
                src_post_id=1,
                dst_post_id=3,
                link_type=PostLinkType.SAME_EVENT,
                score=0.93,
                status=VerificationStatus.VERIFIED,
                evidence_json={"reason": "updated"},
                model_version="test",
                pipeline_version="test",
            )
        )
        session.commit()

    async with integration_async_session_factory() as session:
        rebuilt_again = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert rebuilt_again == 2

    with integration_sync_session_factory() as session:
        events = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        assert initial_event_id in {int(event.id) for event in events}
        memberships = session.execute(select(EventPost).where(EventPost.event_id == initial_event_id)).scalars().all()
        assert {int(row.post_id) for row in memberships} == {1, 3}
        assert next(event for event in events if int(event.id) == initial_event_id).status == VerificationStatus.VERIFIED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_events_split_preserves_one_existing_event_id_and_creates_one_new_event(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given one existing event with a stable identity spanning four posts in one verified component.
    _seed_event_split_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 20, 23, 59, tzinfo=timezone.utc)

    async with integration_async_session_factory() as session:
        initial_rebuilt = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert initial_rebuilt == 1

    with integration_sync_session_factory() as session:
        initial_event = session.execute(select(Event)).scalar_one()
        stable_event_id = int(initial_event.id)
        initial_memberships = session.execute(select(EventPost).where(EventPost.event_id == stable_event_id)).scalars().all()
        assert {int(row.post_id) for row in initial_memberships} == {1, 2, 3, 4}

        # When the verified graph changes and the old component splits into two valid components.
        session.execute(
            delete(PostLink).where(
                PostLink.src_post_id == 2,
                PostLink.dst_post_id == 3,
                PostLink.link_type == PostLinkType.SAME_EVENT,
            )
        )
        session.commit()

    async with integration_async_session_factory() as session:
        rebuilt_after_split = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert rebuilt_after_split == 2

    with integration_sync_session_factory() as session:
        # Then one event keeps the old id, the second gets a new id, and memberships stay lossless and non-overlapping.
        events = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        event_memberships = session.execute(select(EventPost).order_by(EventPost.event_id.asc(), EventPost.post_id.asc())).scalars().all()

        membership_by_event_id: dict[int, set[int]] = {}
        for row in event_memberships:
            membership_by_event_id.setdefault(int(row.event_id), set()).add(int(row.post_id))

        active_membership_by_event_id = {
            int(event.id): membership_by_event_id.get(int(event.id), set())
            for event in events
            if event.status == VerificationStatus.VERIFIED
        }

        assert stable_event_id in active_membership_by_event_id
        assert active_membership_by_event_id[stable_event_id] in ({1, 2}, {3, 4})
        assert len(active_membership_by_event_id) == 2

        new_event_ids = set(active_membership_by_event_id) - {stable_event_id}
        assert len(new_event_ids) == 1
        new_event_id = next(iter(new_event_ids))
        assert new_event_id != stable_event_id
        assert active_membership_by_event_id[new_event_id] in ({1, 2}, {3, 4})

        all_active_post_ids = set().union(*active_membership_by_event_id.values())
        assert all_active_post_ids == {1, 2, 3, 4}
        assert active_membership_by_event_id[stable_event_id].isdisjoint(active_membership_by_event_id[new_event_id])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_events_empty_window_is_safe_noop_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given existing event/process state that lives completely outside the target rebuild window.
    _seed_cascade_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 25, 23, 59, tzinfo=timezone.utc)

    with integration_sync_session_factory() as session:
        event_before = session.execute(select(Event).where(Event.id == 10)).scalar_one()
        event_memberships_before = session.execute(
            select(EventPost).where(EventPost.event_id == 10).order_by(EventPost.post_id.asc())
        ).scalars().all()
        process_before = session.execute(select(Process).where(Process.id == 20)).scalar_one()
        process_memberships_before = session.execute(
            select(ProcessEvent).where(ProcessEvent.process_id == 20).order_by(ProcessEvent.event_id.asc())
        ).scalars().all()

        event_snapshot_before = {
            "id": int(event_before.id),
            "title": event_before.title,
            "started_at": event_before.started_at,
            "ended_at": event_before.ended_at,
            "confidence": event_before.confidence,
            "status": event_before.status,
        }
        event_membership_snapshot_before = [
            (int(row.event_id), int(row.post_id), row.role, row.status) for row in event_memberships_before
        ]
        process_snapshot_before = {
            "id": int(process_before.id),
            "title": process_before.title,
            "started_at": process_before.started_at,
            "ended_at": process_before.ended_at,
            "confidence": process_before.confidence,
            "status": process_before.status,
        }
        process_membership_snapshot_before = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_before
        ]

    # When rebuild_events runs for a window that contains no source posts.
    async with integration_async_session_factory() as session:
        rebuilt = await rebuild_events(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert rebuilt == 0

    with integration_sync_session_factory() as session:
        # Then the operation is a safe noop: entities outside the window keep the same identity, status, and memberships.
        event_after = session.execute(select(Event).where(Event.id == 10)).scalar_one()
        event_memberships_after = session.execute(
            select(EventPost).where(EventPost.event_id == 10).order_by(EventPost.post_id.asc())
        ).scalars().all()
        process_after = session.execute(select(Process).where(Process.id == 20)).scalar_one()
        process_memberships_after = session.execute(
            select(ProcessEvent).where(ProcessEvent.process_id == 20).order_by(ProcessEvent.event_id.asc())
        ).scalars().all()

        event_snapshot_after = {
            "id": int(event_after.id),
            "title": event_after.title,
            "started_at": event_after.started_at,
            "ended_at": event_after.ended_at,
            "confidence": event_after.confidence,
            "status": event_after.status,
        }
        event_membership_snapshot_after = [
            (int(row.event_id), int(row.post_id), row.role, row.status) for row in event_memberships_after
        ]
        process_snapshot_after = {
            "id": int(process_after.id),
            "title": process_after.title,
            "started_at": process_after.started_at,
            "ended_at": process_after.ended_at,
            "confidence": process_after.confidence,
            "status": process_after.status,
        }
        process_membership_snapshot_after = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_after
        ]

        assert event_snapshot_after == event_snapshot_before
        assert event_membership_snapshot_after == event_membership_snapshot_before
        assert process_snapshot_after == process_snapshot_before
        assert process_membership_snapshot_after == process_membership_snapshot_before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_empty_scope_is_safe_noop_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given existing process state that lives completely outside the target rebuild scope.
    _seed_cascade_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 25, 23, 59, tzinfo=timezone.utc)

    with integration_sync_session_factory() as session:
        process_before = session.execute(select(Process).where(Process.id == 20)).scalar_one()
        process_memberships_before = session.execute(
            select(ProcessEvent).where(ProcessEvent.process_id == 20).order_by(ProcessEvent.event_id.asc())
        ).scalars().all()

        process_snapshot_before = {
            "id": int(process_before.id),
            "title": process_before.title,
            "started_at": process_before.started_at,
            "ended_at": process_before.ended_at,
            "confidence": process_before.confidence,
            "status": process_before.status,
        }
        process_membership_snapshot_before = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_before
        ]

    # When rebuild_processes runs for a scope that contains no seed events and no rebuildable process graph.
    async with integration_async_session_factory() as session:
        created_memberships = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships == 0

    with integration_sync_session_factory() as session:
        # Then the operation is a safe noop: the existing process outside scope keeps the same identity, status, and memberships.
        process_after = session.execute(select(Process).where(Process.id == 20)).scalar_one()
        process_memberships_after = session.execute(
            select(ProcessEvent).where(ProcessEvent.process_id == 20).order_by(ProcessEvent.event_id.asc())
        ).scalars().all()

        process_snapshot_after = {
            "id": int(process_after.id),
            "title": process_after.title,
            "started_at": process_after.started_at,
            "ended_at": process_after.ended_at,
            "confidence": process_after.confidence,
            "status": process_after.status,
        }
        process_membership_snapshot_after = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_after
        ]

        assert process_snapshot_after == process_snapshot_before
        assert process_membership_snapshot_after == process_membership_snapshot_before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_keeps_stable_process_identity_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    _seed_process_identity_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 21, 23, 59, tzinfo=timezone.utc)

    async with integration_async_session_factory() as session:
        created_memberships = await rebuild_processes(session, date_from=date_from, date_to=date_to, created_by="integration")
        await session.commit()

    assert created_memberships == 2

    with integration_sync_session_factory() as session:
        process = session.execute(select(Process)).scalar_one()
        initial_process_id = int(process.id)
        assert {
            row.event_id for row in session.execute(select(ProcessEvent).where(ProcessEvent.process_id == initial_process_id)).scalars().all()
        } == {11, 12}

        session.execute(
            delete(PostLink).where(
                PostLink.src_post_id == 1,
                PostLink.dst_post_id == 2,
                PostLink.link_type == PostLinkType.UPDATE,
            )
        )
        session.add(
            PostLink(
                src_post_id=1,
                dst_post_id=3,
                link_type=PostLinkType.UPDATE,
                score=0.9,
                status=VerificationStatus.VERIFIED,
                evidence_json={"reason": "updated"},
                model_version="test",
                pipeline_version="test",
            )
        )
        session.commit()

    async with integration_async_session_factory() as session:
        created_memberships_again = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships_again == 1

    with integration_sync_session_factory() as session:
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        assert [int(process.id) for process in processes] == [initial_process_id]
        memberships = session.execute(select(ProcessEvent).where(ProcessEvent.process_id == initial_process_id)).scalars().all()
        assert {int(row.event_id) for row in memberships} == {11, 13}
        assert processes[0].status == VerificationStatus.VERIFIED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_split_preserves_one_existing_process_id_and_creates_one_new_process(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given one existing process with a stable identity spanning four events in one verified update chain.
    _seed_process_split_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 21, 23, 59, tzinfo=timezone.utc)

    async with integration_async_session_factory() as session:
        initial_created_memberships = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert initial_created_memberships == 3

    with integration_sync_session_factory() as session:
        initial_process = session.execute(select(Process)).scalar_one()
        stable_process_id = int(initial_process.id)
        initial_memberships = session.execute(select(ProcessEvent).where(ProcessEvent.process_id == stable_process_id)).scalars().all()
        assert {int(row.event_id) for row in initial_memberships} == {21, 22, 23, 24}

        # When the verified update topology changes and the old process splits into two valid components.
        session.execute(
            delete(PostLink).where(
                PostLink.src_post_id == 2,
                PostLink.dst_post_id == 3,
                PostLink.link_type == PostLinkType.UPDATE,
            )
        )
        session.commit()

    async with integration_async_session_factory() as session:
        created_memberships_after_split = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships_after_split == 2

    with integration_sync_session_factory() as session:
        # Then one process keeps the old id, the second gets a new id, and event memberships stay lossless and non-overlapping.
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships = session.execute(select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())).scalars().all()

        membership_by_process_id: dict[int, set[int]] = {}
        for row in process_memberships:
            membership_by_process_id.setdefault(int(row.process_id), set()).add(int(row.event_id))

        active_membership_by_process_id = {
            int(process.id): membership_by_process_id.get(int(process.id), set())
            for process in processes
            if process.status == VerificationStatus.VERIFIED
        }

        assert stable_process_id in active_membership_by_process_id
        assert active_membership_by_process_id[stable_process_id] in ({21, 22}, {23, 24})
        assert len(active_membership_by_process_id) == 2

        new_process_ids = set(active_membership_by_process_id) - {stable_process_id}
        assert len(new_process_ids) == 1
        new_process_id = next(iter(new_process_ids))
        assert new_process_id != stable_process_id
        assert active_membership_by_process_id[new_process_id] in ({21, 22}, {23, 24})

        all_active_event_ids = set().union(*active_membership_by_process_id.values())
        assert all_active_event_ids == {21, 22, 23, 24}
        assert active_membership_by_process_id[stable_process_id].isdisjoint(active_membership_by_process_id[new_process_id])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_merge_preserves_identity_of_process_with_greater_overlap_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    _seed_process_merge_preference_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 21, 23, 59, tzinfo=timezone.utc)

    async with integration_async_session_factory() as session:
        initial_created_memberships = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert initial_created_memberships == 3

    with integration_sync_session_factory() as session:
        initial_process_memberships = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()
        membership_by_process_id: dict[int, set[int]] = {}
        for row in initial_process_memberships:
            membership_by_process_id.setdefault(int(row.process_id), set()).add(int(row.event_id))

        assert len(membership_by_process_id) == 2
        primary_process_id = next(process_id for process_id, event_ids in membership_by_process_id.items() if event_ids == {31, 32, 33})
        secondary_process_id = next(process_id for process_id, event_ids in membership_by_process_id.items() if event_ids == {34, 35})

        session.add(
            PostLink(
                src_post_id=3,
                dst_post_id=4,
                link_type=PostLinkType.UPDATE,
                score=0.95,
                status=VerificationStatus.VERIFIED,
                evidence_json={"reason": "merge"},
                model_version="test",
                pipeline_version="test",
            )
        )
        session.commit()

    async with integration_async_session_factory() as session:
        created_memberships_after_merge = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships_after_merge == 2

    with integration_sync_session_factory() as session:
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()

        active_membership_by_process_id: dict[int, set[int]] = {}
        for row in process_memberships:
            process = next(process for process in processes if int(process.id) == int(row.process_id))
            if process.status == VerificationStatus.VERIFIED:
                active_membership_by_process_id.setdefault(int(row.process_id), set()).add(int(row.event_id))

        assert active_membership_by_process_id == {primary_process_id: {31, 32, 33, 34, 35}}
        assert next(process for process in processes if int(process.id) == secondary_process_id).status == VerificationStatus.REJECTED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_ignores_proposed_and_rejected_update_links_when_building_process_graph_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given four real events where one verified update edge forms an existing process,
    # while the only other update links are PROPOSED or REJECTED.
    _seed_process_unverified_update_links_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 21, 23, 59, tzinfo=timezone.utc)

    # When rebuild_processes rebuilds the observable process graph from the database state.
    async with integration_async_session_factory() as session:
        created_memberships = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships == 2

    with integration_sync_session_factory() as session:
        # Then only the VERIFIED edge contributes to active process membership:
        # no new process is created from unverified links and no existing process expands through them.
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()

        membership_by_process_id: dict[int, set[int]] = {}
        for row in process_memberships:
            membership_by_process_id.setdefault(int(row.process_id), set()).add(int(row.event_id))

        active_membership_by_process_id = {
            int(process.id): membership_by_process_id.get(int(process.id), set())
            for process in processes
            if process.status == VerificationStatus.VERIFIED
        }

        assert active_membership_by_process_id and len(active_membership_by_process_id) == 1
        assert next(iter(active_membership_by_process_id.values())) == {41, 42}
        assert {int(row.event_id) for row in process_memberships} == {41, 42}
        assert all(process.status == VerificationStatus.VERIFIED for process in processes)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_processes_nonempty_scope_without_verified_update_edges_is_safe_noop_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given a non-empty scope with real events and an existing process candidate,
    # but no VERIFIED update edges that can justify a rebuild or expansion.
    _seed_process_nonempty_scope_without_verified_edges_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 21, 23, 59, tzinfo=timezone.utc)

    with integration_sync_session_factory() as session:
        processes_before = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships_before = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()

        process_snapshot_before = [
            {
                "id": int(process.id),
                "title": process.title,
                "started_at": process.started_at,
                "ended_at": process.ended_at,
                "confidence": process.confidence,
                "status": process.status,
            }
            for process in processes_before
        ]
        membership_snapshot_before = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_before
        ]

    # When rebuild_processes runs over that non-empty but non-rebuildable scope.
    async with integration_async_session_factory() as session:
        created_memberships = await rebuild_processes(
            session,
            date_from=date_from,
            date_to=date_to,
            created_by="integration",
        )
        await session.commit()

    assert created_memberships == 0

    with integration_sync_session_factory() as session:
        # Then the graph remains unchanged: no false process is created and the existing candidate is not expanded.
        processes_after = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships_after = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()

        process_snapshot_after = [
            {
                "id": int(process.id),
                "title": process.title,
                "started_at": process.started_at,
                "ended_at": process.ended_at,
                "confidence": process.confidence,
                "status": process.status,
            }
            for process in processes_after
        ]
        membership_snapshot_after = [
            (int(row.process_id), int(row.event_id), row.relation_type, row.status) for row in process_memberships_after
        ]

        assert process_snapshot_after == process_snapshot_before
        assert membership_snapshot_after == membership_snapshot_before
        assert [int(process.id) for process in processes_after] == [60]
        assert [(int(row.process_id), int(row.event_id)) for row in process_memberships_after] == [(60, 51)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_ai_jobs_marks_downstream_stale_without_auto_cascade_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cascade_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 1, "source": "integration"},
            dedupe_key="build_post_report:1",
        )
        await session.commit()

    assert job is not None

    class _FakeReportProject:
        async def generate_post_report_payload(self, **kwargs):
            return {
                **_ready_post_report_payload(post_id=int(kwargs["post_id"]), summary="fresh post report"),
                "comment_count": 7,
            }

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)
    monkeypatch.setattr(
        pipeline_runtime.TgReportProject,
        "from_settings",
        staticmethod(lambda: _FakeReportProject()),
    )

    first = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-1", job_worker_concurrency=1)
    second = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-2", job_worker_concurrency=1)
    third = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-3", job_worker_concurrency=1)

    assert (first, second, third) == (1, 0, 0)

    with integration_sync_session_factory() as session:
        post_report = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        event_reports = session.execute(select(EventReport).where(EventReport.event_id == 10).order_by(EventReport.version.asc())).scalars().all()
        process_reports = (
            session.execute(select(ProcessReport).where(ProcessReport.process_id == 20).order_by(ProcessReport.version.asc())).scalars().all()
        )
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()

        PostReportPayload.model_validate(post_report.report_json)
        assert post_report.report_json["summary"] == "fresh post report"
        assert post_report.report_json["meta"]["input_signature"]
        assert len(event_reports) == 1
        EventReportPayload.model_validate(event_reports[0].report_json)
        assert event_reports[0].report_json["status"] == "stale"
        assert len(process_reports) == 1
        ProcessReportPayload.model_validate(process_reports[0].report_json)
        assert process_reports[0].report_json["status"] == "stale"
        assert [job.type for job in jobs] == [JobType.BUILD_POST_REPORT]
        assert all(job.status == "done" for job in jobs)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_ai_jobs_contains_invalid_post_report_output_without_false_downstream_ready_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real post -> event -> process report chain that was marked stale after the post inputs changed,
    # and a report build was manually queued.
    _seed_cascade_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        staleness_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:invalid_ai_output",
            dependency_type="comments_refresh",
            dependency_id=1,
        )
        await session.commit()

    assert staleness_result["status"] == "stale_marked"
    assert staleness_result["enqueued"] is False
    assert staleness_result["event_reports_marked_stale"] == 1
    assert staleness_result["process_reports_marked_stale"] == 1

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 1, "source": "integration:invalid_ai_output"},
            dedupe_key="build_post_report:1",
        )
        await session.commit()

    assert queued_job is not None

    async def _fake_acompletion(**_kwargs):
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {
                            "message": type(
                                "_Msg",
                                (),
                                {
                                    "content": "not valid json at all",
                                },
                            )()
                        },
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)
    monkeypatch.setattr(pipeline_runtime, "report_config_from_settings", lambda _settings: reporter.ReportConfig(min_comments=0))

    # When the real AI worker path executes the queued post report build job.
    first = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-invalid-1", job_worker_concurrency=1)
    second = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-invalid-2", job_worker_concurrency=1)
    third = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-invalid-3", job_worker_concurrency=1)

    assert (first, second, third) == (1, 0, 0)

    with integration_sync_session_factory() as session:
        # Then the failed report outcome is persisted and observable, while the worker lock is cleared.
        post_report = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        event_reports = session.execute(select(EventReport).where(EventReport.event_id == 10).order_by(EventReport.version.asc())).scalars().all()
        process_reports = (
            session.execute(select(ProcessReport).where(ProcessReport.process_id == 20).order_by(ProcessReport.version.asc())).scalars().all()
        )

        PostReportPayload.model_validate(post_report.report_json)

        assert post_report.status == "failed"
        assert post_report.content == pipeline_runtime.reporting_module.REPORT_GENERATION_FAILED_CONTENT
        assert post_report.report_json is not None
        assert post_report.report_json["status"] == "failed"
        assert post_report.report_json["post_id"] == 1
        assert post_report.report_json["meta"]["input_signature"]
        assert post_report.report_json["meta"]["generated_at"]

        assert len(jobs) == 1
        failed_job = jobs[0]
        assert failed_job.type == JobType.BUILD_POST_REPORT
        assert failed_job.status == "done"
        assert failed_job.locked_by is None
        assert failed_job.locked_at is None
        assert failed_job.heartbeat_at is None
        assert failed_job.last_error is None
        assert failed_job.attempts == 1
        assert failed_job.payload_json["_job_result"]["status"] == "failed"
        assert failed_job.payload_json["_job_result"]["report_id"] == post_report.id
        assert failed_job.payload_json["_job_result"]["post_id"] == 1

        # And no false-ready downstream cascade is produced from the failed post rebuild.
        assert len(event_reports) == 1
        assert event_reports[0].report_json["status"] == "stale"
        assert len(process_reports) == 1
        assert process_reports[0].report_json["status"] == "stale"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_ai_jobs_persists_limited_post_report_without_false_downstream_ready_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_cascade_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        staleness_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:limited_post_report",
            dependency_type="comments_refresh",
            dependency_id=1,
        )
        await session.commit()

    assert staleness_result["status"] == "stale_marked"
    assert staleness_result["event_reports_marked_stale"] == 1
    assert staleness_result["process_reports_marked_stale"] == 1

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_REPORT,
            payload={"post_id": 1, "source": "integration:limited_post_report"},
            dedupe_key="build_post_report:1",
        )
        await session.commit()

    assert queued_job is not None

    class _FakeReportProject:
        async def generate_post_report_payload(self, **kwargs):
            return _limited_post_report_payload(post_id=int(kwargs["post_id"]), summary="limited public summary")

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)
    monkeypatch.setattr(
        pipeline_runtime.TgReportProject,
        "from_settings",
        staticmethod(lambda: _FakeReportProject()),
    )

    first = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-limited-1", job_worker_concurrency=1)
    second = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-limited-2", job_worker_concurrency=1)
    third = await pipeline_runtime.run_ai_jobs(job_batch_size=10, worker_id="ai-int-limited-3", job_worker_concurrency=1)

    assert (first, second, third) == (1, 0, 0)

    with integration_sync_session_factory() as session:
        post_report = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        event_reports = session.execute(select(EventReport).where(EventReport.event_id == 10).order_by(EventReport.version.asc())).scalars().all()
        process_reports = (
            session.execute(select(ProcessReport).where(ProcessReport.process_id == 20).order_by(ProcessReport.version.asc())).scalars().all()
        )
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()

        PostReportPayload.model_validate(post_report.report_json)
        assert post_report.status == "limited"
        assert post_report.report_json["status"] == "limited"
        assert post_report.report_json["summary"]
        assert post_report.report_json["meta"]["input_signature"]
        assert len(event_reports) == 1
        assert event_reports[0].report_json["status"] == "stale"
        assert len(process_reports) == 1
        assert process_reports[0].report_json["status"] == "stale"
        assert [job.type for job in jobs] == [JobType.BUILD_POST_REPORT]
        assert all(job.status == "done" for job in jobs)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_post_report_staleness_is_idempotent_when_rebuild_job_is_already_pending_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given a real post/event/process cascade where the first staleness sync already marked descendants stale.
    _seed_cascade_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        first_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:staleness_sync",
            dependency_type="comments_refresh",
            dependency_id=1,
        )
        await session.commit()

    assert first_result["status"] == "stale_marked"
    assert first_result["enqueued"] is False
    assert first_result["stale_marked"] is True
    assert first_result["event_reports_marked_stale"] == 1
    assert first_result["process_reports_marked_stale"] == 1

    with integration_sync_session_factory() as session:
        jobs_before = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        post_report_before = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        event_reports_before = session.execute(select(EventReport).where(EventReport.event_id == 10)).scalars().all()
        process_reports_before = session.execute(select(ProcessReport).where(ProcessReport.process_id == 20)).scalars().all()

        assert jobs_before == []
        assert post_report_before.report_json["status"] == "stale"
        assert event_reports_before[0].report_json["status"] == "stale"
        assert process_reports_before[0].report_json["status"] == "stale"

        post_report_stale_marked_at_before = post_report_before.report_json["meta"]["stale_marked_at"]
        event_report_stale_marked_at_before = event_reports_before[0].report_json["meta"]["stale_marked_at"]
        process_report_stale_marked_at_before = process_reports_before[0].report_json["meta"]["stale_marked_at"]

    # When the same staleness sync is triggered again for the same effective input state.
    async with integration_async_session_factory() as session:
        second_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:staleness_sync",
            dependency_type="comments_refresh",
            dependency_id=1,
        )
        await session.commit()

    # Then the observable DB state stays idempotent: no duplicate job, no extra descendant transitions, no rewritten stale marks.
    assert second_result["status"] == "unchanged"
    assert second_result["changed"] is False
    assert second_result["stale_marked"] is False
    assert second_result["enqueued"] is False

    with integration_sync_session_factory() as session:
        jobs_after = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        post_report_after = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        event_reports_after = session.execute(select(EventReport).where(EventReport.event_id == 10)).scalars().all()
        process_reports_after = session.execute(select(ProcessReport).where(ProcessReport.process_id == 20)).scalars().all()

        assert jobs_after == []

        assert len(event_reports_after) == 1
        assert len(process_reports_after) == 1

        assert post_report_after.report_json["status"] == "stale"
        assert event_reports_after[0].report_json["status"] == "stale"
        assert process_reports_after[0].report_json["status"] == "stale"

        assert post_report_after.report_json["meta"]["stale_marked_at"] == post_report_stale_marked_at_before
        assert event_reports_after[0].report_json["meta"]["stale_marked_at"] == event_report_stale_marked_at_before
        assert process_reports_after[0].report_json["meta"]["stale_marked_at"] == process_report_stale_marked_at_before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_post_report_staleness_re_marks_current_report_without_creating_job_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
) -> None:
    # Given the first real cascade already marked descendants stale without creating a rebuild job.
    _seed_cascade_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        first_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:staleness_sync",
            dependency_type="comments_refresh",
            dependency_id=1,
        )
        await session.commit()

    assert first_result["status"] == "stale_marked"
    assert first_result["enqueued"] is False

    with integration_sync_session_factory() as session:
        post = session.get(Post, 1)
        assert post is not None
        post.text = f"{post.text}\nUpdated after first stale cascade"
        jobs_before = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        event_report_before = session.execute(select(EventReport).where(EventReport.event_id == 10)).scalar_one()
        process_report_before = session.execute(select(ProcessReport).where(ProcessReport.process_id == 20)).scalar_one()
        event_stale_marked_at_before = event_report_before.report_json["meta"]["stale_marked_at"]
        process_stale_marked_at_before = process_report_before.report_json["meta"]["stale_marked_at"]
        assert jobs_before == []
        session.commit()

    # When inputs change again before any manual rebuild request is made.
    async with integration_async_session_factory() as session:
        second_result = await sync_post_report_staleness(
            session,
            post_id=1,
            source="integration:staleness_sync",
            dependency_type="post_inputs",
            dependency_id=1,
        )
        await session.commit()

    # Then no job is created, descendants are not stale-marked again, and the current report is re-marked against the new input signature.
    assert second_result["status"] == "stale_marked"
    assert second_result["changed"] is True
    assert second_result["enqueued"] is False
    assert second_result["event_reports_marked_stale"] == 0
    assert second_result["process_reports_marked_stale"] == 0

    with integration_sync_session_factory() as session:
        jobs_after = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        post_report_after = session.execute(select(Report).where(Report.post_id == 1)).scalar_one()
        event_report_after = session.execute(select(EventReport).where(EventReport.event_id == 10)).scalar_one()
        process_report_after = session.execute(select(ProcessReport).where(ProcessReport.process_id == 20)).scalar_one()

        assert jobs_after == []
        assert post_report_after.report_json["status"] == "stale"
        assert event_report_after.report_json["status"] == "stale"
        assert process_report_after.report_json["status"] == "stale"
        assert event_report_after.report_json["meta"]["stale_marked_at"] == event_stale_marked_at_before
        assert process_report_after.report_json["meta"]["stale_marked_at"] == process_stale_marked_at_before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_rebuild_jobs_persist_results_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given source posts and verified links that require real rebuild-events and rebuild-processes jobs
    # before the graph can exist in the database.
    _seed_async_rebuild_fixture(integration_sync_session_factory)
    date_from = datetime(2026, 3, 23, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 23, 23, 59, tzinfo=timezone.utc)

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)
    tg_client = SimpleNamespace(operation_lock=asyncio.Lock())

    async with integration_async_session_factory() as session:
        rebuild_events_job = await enqueue_job(
            session,
            job_type=JobType.REBUILD_EVENTS,
            payload={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "source": "integration"},
            dedupe_key=f"rebuild_events:{date_from.isoformat()}:{date_to.isoformat()}",
        )
        await session.commit()

    assert rebuild_events_job is not None

    # When the worker executes the rebuild-events job through the normal telegram-job runner path.
    executed_events = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-int-1",
        collect_comments_quota_per_run=5,
        tg_client=tg_client,
        job_worker_concurrency=1,
    )

    assert executed_events == 1

    async with integration_async_session_factory() as session:
        rebuild_processes_job = await enqueue_job(
            session,
            job_type=JobType.REBUILD_PROCESSES,
            payload={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "source": "integration"},
            dedupe_key=f"rebuild_processes:{date_from.isoformat()}:{date_to.isoformat()}",
        )
        await session.commit()

    assert rebuild_processes_job is not None

    # And the worker then executes the rebuild-processes job through the same public runner path.
    executed_processes = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-int-2",
        collect_comments_quota_per_run=5,
        tg_client=tg_client,
        job_worker_concurrency=1,
    )

    assert executed_processes == 1

    with integration_sync_session_factory() as session:
        # Then both jobs reach externally visible terminal success,
        # persist their public results, release worker locks,
        # and the rebuilt graph matches the ready link reality in the database.
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        events = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        event_memberships = session.execute(select(EventPost).order_by(EventPost.event_id.asc(), EventPost.post_id.asc())).scalars().all()
        process_memberships = session.execute(select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())).scalars().all()

        membership_by_event_id: dict[int, set[int]] = {}
        for row in event_memberships:
            membership_by_event_id.setdefault(int(row.event_id), set()).add(int(row.post_id))

        assert [job.status for job in jobs] == ["done", "done"]
        assert [job.type for job in jobs] == [JobType.REBUILD_EVENTS, JobType.REBUILD_PROCESSES]
        assert all(job.locked_by is None for job in jobs)
        assert all(job.locked_at is None for job in jobs)
        assert all(job.heartbeat_at is None for job in jobs)
        assert all(job.retry_at is None for job in jobs)
        assert all(job.last_error is None for job in jobs)
        assert jobs[0].payload_json["_job_result"]["rebuilt_events"] == 2
        assert jobs[1].payload_json["_job_result"]["rebuilt_process_edges"] == 2
        assert len(events) == 2
        assert {frozenset(post_ids) for post_ids in membership_by_event_id.values()} == {frozenset({1, 2}), frozenset({3, 4})}
        assert len(processes) == 1
        assert {int(row.event_id) for row in process_memberships} == {events[0].id, events[1].id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rebuild_events_job_exception_clears_running_state_and_allows_new_cycle_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real rebuild-events job that will be locked and run by the worker with a dedupe key.
    date_from = datetime(2026, 3, 24, 0, 0, tzinfo=timezone.utc)
    date_to = datetime(2026, 3, 24, 23, 59, tzinfo=timezone.utc)
    dedupe_key = f"rebuild_events:{date_from.isoformat()}:{date_to.isoformat()}"

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _boom_rebuild_events(_session, *, date_from, date_to, created_by):
        del _session, date_from, date_to, created_by
        raise RuntimeError("rebuild failed")

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "rebuild_events", _boom_rebuild_events)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.REBUILD_EVENTS,
            payload={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "source": "integration"},
            dedupe_key=dedupe_key,
            max_attempts=1,
        )
        await session.commit()

    assert queued_job is not None

    # When the worker runs the job and rebuild_events raises an exception.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-failure-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed == 0

    # Then the job does not stay running, its lock is cleared, failure is persisted,
    # and a new lifecycle can start with the same dedupe key.
    with integration_sync_session_factory() as session:
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 1
        failed_job = jobs[0]
        assert failed_job.type == JobType.REBUILD_EVENTS
        assert failed_job.status == "failed"
        assert failed_job.locked_by is None
        assert failed_job.locked_at is None
        assert failed_job.heartbeat_at is None
        assert failed_job.retry_at is None
        assert failed_job.last_error

    async with integration_async_session_factory() as session:
        reenqueued_job = await enqueue_job(
            session,
            job_type=JobType.REBUILD_EVENTS,
            payload={"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "source": "integration-retry"},
            dedupe_key=dedupe_key,
            max_attempts=1,
        )
        await session.commit()

    assert reenqueued_job is not None
    assert reenqueued_job.id != queued_job.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_link_job_exception_clears_running_state_and_unblocks_following_cycle_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real build-post-links job with a dedupe key and an existing post that will be picked up by the worker.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="link_failure_chan", title="Link Failure Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=5001,
                date=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                text="Link failure root post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    dedupe_key = "build_post_links:1"
    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    class _BrokenPipeline:
        async def run_for_post(self, _session, _post):
            raise RuntimeError("link execution failed")

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(
        pipeline_runtime.NoLlmLinkingPipeline,
        "build_default",
        classmethod(lambda cls: _BrokenPipeline()),
    )

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_LINKS,
            payload={"post_id": 1, "source": "integration"},
            dedupe_key=dedupe_key,
            max_attempts=1,
        )
        await session.commit()

    assert queued_job is not None

    # When the worker runs the link job and the link execution raises an exception.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-link-failure-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed == 0
    assert await pipeline_runtime.count_incomplete_link_jobs() == 0

    # Then the job does not stay running, its lock is cleared, failure is externally visible,
    # and a new lifecycle can start with the same dedupe key.
    with integration_sync_session_factory() as session:
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 1
        failed_job = jobs[0]
        assert failed_job.type == JobType.BUILD_POST_LINKS
        assert failed_job.status == "failed"
        assert failed_job.locked_by is None
        assert failed_job.locked_at is None
        assert failed_job.heartbeat_at is None
        assert failed_job.retry_at is None
        assert failed_job.last_error

    async with integration_async_session_factory() as session:
        reenqueued_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_LINKS,
            payload={"post_id": 1, "source": "integration-retry"},
            dedupe_key=dedupe_key,
            max_attempts=1,
        )
        await session.commit()

    assert reenqueued_job is not None
    assert reenqueued_job.id != queued_job.id
    assert await pipeline_runtime.count_incomplete_link_jobs() == 1

    class _SuccessfulPipeline:
        async def run_for_post(self, _session, _post):
            return SimpleNamespace(
                model_dump=lambda: {
                    "post_id": 1,
                    "links_verified": 0,
                    "links_proposed": 0,
                    "links_rejected": 0,
                    "candidates_checked": 0,
                    "verify_checked": 0,
                    "critic_checked": 0,
                    "queued_for_review": 0,
                }
            )

    monkeypatch.setattr(
        pipeline_runtime.NoLlmLinkingPipeline,
        "build_default",
        classmethod(lambda cls: _SuccessfulPipeline()),
    )

    executed_retry = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-link-failure-int-2",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed_retry == 1
    assert await pipeline_runtime.count_incomplete_link_jobs() == 0

    with integration_sync_session_factory() as session:
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 2
        assert jobs[0].status == "failed"
        assert jobs[1].status == "done"
        assert jobs[1].locked_by is None
        assert jobs[1].locked_at is None
        assert jobs[1].heartbeat_at is None
        assert jobs[1].last_error is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comment_job_flood_wait_stays_retryable_and_is_not_lost_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real collect-comments job for an existing post that will hit a FloodWait condition during execution.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="comment_flood_chan", title="Comment Flood Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=7001,
                date=datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc),
                text="Comment flood target post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "flood_wait", "wait_seconds": 7, "flood_source": "iter_comments"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": 1, "source": "scheduler"},
            max_attempts=5,
        )
        await session.commit()

    assert queued_job is not None

    # When the telegram job runner executes the comment job through the normal worker path.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-flood-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed == 0

    with integration_sync_session_factory() as session:
        # Then the job is not lost: it is not marked done, not terminally failed,
        # and is returned to a retryable pending lifecycle with its lock released.
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 1
        retryable_job = jobs[0]
        assert retryable_job.type == JobType.COLLECT_COMMENTS
        assert retryable_job.status == "pending"
        assert retryable_job.retry_at is not None
        assert retryable_job.locked_by is None
        assert retryable_job.locked_at is None
        assert retryable_job.heartbeat_at is None
        assert retryable_job.attempts == 1
        assert retryable_job.retry_at > retryable_job.run_at
        assert retryable_job.last_error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comment_job_repeated_flood_wait_remains_visible_retryable_across_cycles_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real collect-comments job whose lower layer keeps returning FloodWait across multiple worker cycles.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="comment_repeat_flood_chan", title="Comment Repeat Flood Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=7003,
                date=datetime(2026, 3, 27, 10, 30, tzinfo=timezone.utc),
                text="Comment repeated-flood target post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "flood_wait", "wait_seconds": 7, "flood_source": "iter_comments"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": 1, "source": "scheduler"},
            max_attempts=5,
        )
        await session.commit()

    assert queued_job is not None

    # When the normal telegram worker runs the same retryable job through two execution cycles.
    first = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-repeat-flood-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    with integration_sync_session_factory() as session:
        job_after_first = session.execute(select(Job).where(Job.id == queued_job.id)).scalar_one()
        first_retry_at = job_after_first.retry_at
        assert first_retry_at is not None
        job_after_first.retry_at = datetime(2026, 3, 27, 10, 31, tzinfo=timezone.utc)
        session.commit()

    second = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-repeat-flood-int-2",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert first == 0
    assert second == 0

    with integration_sync_session_factory() as session:
        # Then the job remains observable and retryable across repeated cycles instead of being lost or marked done.
        retried_job = session.execute(select(Job).where(Job.id == queued_job.id)).scalar_one()
        assert retried_job.type == JobType.COLLECT_COMMENTS
        assert retried_job.status == "pending"
        assert retried_job.retry_at is not None
        assert retried_job.retry_at > first_retry_at
        assert retried_job.locked_by is None
        assert retried_job.locked_at is None
        assert retried_job.heartbeat_at is None
        assert retried_job.last_error
        assert retried_job.attempts == 2
        assert (retried_job.payload_json or {}).get("_job_result", {}).get("status") == "flood_wait"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comment_job_unknown_status_does_not_silently_succeed_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real comment job whose lower layer returns an unsupported status.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="comment_unknown_chan", title="Comment Unknown Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=7002,
                date=datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc),
                text="Comment unknown-status target post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "new_retryable_status", "error": "future status"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": 1, "source": "api"},
            max_attempts=5,
        )
        await session.commit()

    assert queued_job is not None

    # When the job runner executes the comment job through the normal worker path.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-unknown-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed == 0

    with integration_sync_session_factory() as session:
        # Then the system does not silently treat the unsupported status as success:
        # the job remains in a visible non-success retryable lifecycle state.
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 1
        retryable_job = jobs[0]
        assert retryable_job.type == JobType.COLLECT_COMMENTS
        assert retryable_job.status == "pending"
        assert retryable_job.retry_at is not None
        assert retryable_job.locked_by is None
        assert retryable_job.locked_at is None
        assert retryable_job.heartbeat_at is None
        assert retryable_job.attempts == 1
        assert retryable_job.retry_at > retryable_job.run_at
        assert retryable_job.last_error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_comment_job_retryable_rpc_errors_eventually_reach_terminal_failure_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real refresh-comments job whose lower layer keeps returning a retryable RPC/API failure.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="comment_exhaust_chan", title="Comment Exhaust Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=7004,
                date=datetime(2026, 3, 27, 11, 30, tzinfo=timezone.utc),
                text="Comment exhaustion target post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "rpc_error", "error": "temporary upstream failure"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.REFRESH_COMMENTS,
            payload={"post_id": 1, "source": "api"},
            max_attempts=2,
        )
        await session.commit()

    assert queued_job is not None

    # When the worker executes every allowed retry cycle until the attempt budget is exhausted.
    first = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-exhaust-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    with integration_sync_session_factory() as session:
        job_after_first = session.execute(select(Job).where(Job.id == queued_job.id)).scalar_one()
        assert job_after_first.status == "pending"
        assert job_after_first.retry_at is not None
        job_after_first.retry_at = datetime(2026, 3, 27, 11, 31, tzinfo=timezone.utc)
        session.commit()

    second = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-exhaust-int-2",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert first == 0
    assert second == 0

    with integration_sync_session_factory() as session:
        # Then the job reaches a terminal visible failure instead of staying infinitely retryable or running.
        exhausted_job = session.execute(select(Job).where(Job.id == queued_job.id)).scalar_one()
        dead_letters = session.execute(select(JobDeadLetter).where(JobDeadLetter.source_job_id == queued_job.id)).scalars().all()

        assert exhausted_job.type == JobType.REFRESH_COMMENTS
        assert exhausted_job.status == "failed"
        assert exhausted_job.retry_at is None
        assert exhausted_job.locked_by is None
        assert exhausted_job.locked_at is None
        assert exhausted_job.heartbeat_at is None
        assert exhausted_job.attempts == 2
        assert exhausted_job.last_error
        assert (exhausted_job.payload_json or {}).get("_job_result", {}).get("status") == "rpc_error"

        assert len(dead_letters) == 1
        dead_letter = dead_letters[0]
        assert dead_letter.type == JobType.REFRESH_COMMENTS
        assert dead_letter.source_job_id == queued_job.id
        assert dead_letter.attempts == 2
        assert dead_letter.max_attempts == 2
        assert dead_letter.last_error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_triggered_comment_refresh_rpc_error_stays_retryable_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real API-triggered refresh-comments job whose lower layer hits a temporary external RPC/API error.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="comment_rpc_chan", title="Comment RPC Chan", category="news", is_active=True))
        session.add(
            Post(
                id=1,
                channel_id=1,
                tg_message_id=7003,
                date=datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc),
                text="Comment rpc target post",
                comments_count=0,
                analyzer_version="v1",
            )
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "rpc_error", "error": "rpc failed"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.REFRESH_COMMENTS,
            payload={"post_id": 1, "source": "api"},
            max_attempts=5,
        )
        await session.commit()

    assert queued_job is not None

    # When the job runner executes the API-triggered refresh job through the normal worker path.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-comment-rpc-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    assert executed == 0

    with integration_sync_session_factory() as session:
        # Then the job remains retryable: it is not marked done and not treated as terminally completed.
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        assert len(jobs) == 1
        retryable_job = jobs[0]
        assert retryable_job.type == JobType.REFRESH_COMMENTS
        assert retryable_job.status == "pending"
        assert retryable_job.retry_at is not None
        assert retryable_job.locked_by is None
        assert retryable_job.locked_at is None
        assert retryable_job.heartbeat_at is None
        assert retryable_job.attempts == 1
        assert retryable_job.retry_at > retryable_job.run_at
        assert retryable_job.last_error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mixed_queue_does_not_starve_non_comment_jobs_when_comment_work_turns_retryable_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a mixed queue with one critical non-comment link job and one comment job
    # whose execution becomes heavier/retryable because the lower layer hits FloodWait.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="mixed_queue_chan", title="Mixed Queue Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=7004,
                    date=datetime(2026, 3, 27, 13, 0, tzinfo=timezone.utc),
                    text="Link job source post",
                    comments_count=0,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=7005,
                    date=datetime(2026, 3, 27, 13, 5, tzinfo=timezone.utc),
                    text="Link job target post",
                    comments_count=0,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=7006,
                    date=datetime(2026, 3, 27, 13, 10, tzinfo=timezone.utc),
                    text="Comment job target post",
                    comments_count=0,
                    analyzer_version="v1",
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {"ingest": {"collect_comments_sleep_min_ms": 0, "collect_comments_sleep_max_ms": 0}}

    class _SuccessfulLinkPipeline:
        async def run_for_post(self, session, post):
            assert int(post.id) == 1
            session.add(
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.UPDATE,
                    score=0.91,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "mixed-queue-link"},
                    model_version="test",
                    pipeline_version="test",
                )
            )
            return LinkRunResponse(
                post_id=1,
                links_verified=1,
                links_proposed=0,
                links_rejected=0,
                candidates_checked=0,
                verify_checked=0,
                critic_checked=0,
                queued_for_review=0,
            )

    async def _fake_update_post_comments(_session, _post_id, tg_client=None):
        del _session, _post_id, tg_client
        return {"status": "flood_wait", "wait_seconds": 7, "flood_source": "iter_comments"}

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(
        pipeline_runtime.NoLlmLinkingPipeline,
        "build_default",
        classmethod(lambda cls: _SuccessfulLinkPipeline()),
    )
    monkeypatch.setattr(pipeline_runtime, "update_post_comments", _fake_update_post_comments)

    async with integration_async_session_factory() as session:
        link_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_LINKS,
            payload={"post_id": 1, "source": "integration"},
            dedupe_key="build_post_links:1",
        )
        comment_job = await enqueue_job(
            session,
            job_type=JobType.COLLECT_COMMENTS,
            payload={"post_id": 3, "source": "scheduler"},
            max_attempts=5,
        )
        await session.commit()

    assert link_job is not None
    assert comment_job is not None

    # When the worker executes one mixed telegram-job cycle.
    executed = await pipeline_runtime.run_telegram_jobs(
        job_batch_size=10,
        worker_id="tg-mixed-queue-int-1",
        collect_comments_quota_per_run=5,
        tg_client=SimpleNamespace(operation_lock=asyncio.Lock()),
        job_worker_concurrency=1,
    )

    with integration_sync_session_factory() as session:
        # Then the non-comment job is not starved by heavier comment work:
        # the link job reaches a visible successful outcome while the comment job stays retryable.
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        links = session.execute(select(PostLink).order_by(PostLink.id.asc())).scalars().all()

        assert len(jobs) == 2
        link_job_after = next(job for job in jobs if job.type == JobType.BUILD_POST_LINKS)
        comment_job_after = next(job for job in jobs if job.type == JobType.COLLECT_COMMENTS)

        assert link_job_after.status == "done"
        assert link_job_after.locked_by is None
        assert link_job_after.locked_at is None
        assert link_job_after.heartbeat_at is None
        assert link_job_after.retry_at is None
        assert link_job_after.last_error is None

        assert comment_job_after.status == "pending"
        assert comment_job_after.retry_at is not None
        assert comment_job_after.locked_by is None
        assert comment_job_after.locked_at is None
        assert comment_job_after.heartbeat_at is None
        assert comment_job_after.last_error

        assert {
            (int(link.src_post_id), int(link.dst_post_id), link.link_type, link.status)
            for link in links
        } == {
            (1, 2, PostLinkType.UPDATE, VerificationStatus.VERIFIED),
        }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_telegram_cycle_does_not_rebuild_graph_while_link_jobs_are_still_incomplete_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given source posts and verified links that would form an event/process graph if rebuild ran now,
    # but an incomplete build-post-links job still exists so the link phase is not yet drained.
    _seed_async_rebuild_fixture(integration_sync_session_factory)

    async with integration_async_session_factory() as session:
        pending_link_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_LINKS,
            payload={"post_id": 4, "source": "integration"},
            dedupe_key="build_post_links:4",
        )
        await session.commit()

    assert pending_link_job is not None

    with integration_sync_session_factory() as session:
        events_before = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        processes_before = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        event_memberships_before = session.execute(select(EventPost).order_by(EventPost.event_id.asc(), EventPost.post_id.asc())).scalars().all()
        process_memberships_before = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()
        pending_jobs_before = session.execute(
            select(Job).where(Job.type == JobType.BUILD_POST_LINKS).order_by(Job.id.asc())
        ).scalars().all()

        assert events_before == []
        assert processes_before == []
        assert event_memberships_before == []
        assert process_memberships_before == []
        assert len(pending_jobs_before) == 1
        assert pending_jobs_before[0].status == "pending"

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {
            "ingest": {
                "lookback_days": 30,
                "max_posts_per_channel": 10,
                "comment_first_delay_hours": 2,
                "comment_interval_hours": 2,
                "comment_window_hours": 24,
                "comment_schedule_jitter_seconds": 0,
                "collect_comments_sleep_min_ms": 0,
                "collect_comments_sleep_max_ms": 0,
            },
            "jobs": {
                "job_batch_size": 10,
                "collect_comments_quota_per_run": 1,
                "done_retention_days": 14,
                "dead_letter_retention_days": 90,
                "cleanup_batch_size": 1000,
                "job_worker_concurrency": 1,
            },
            "retention": {
                "retention_days": 30,
                "archive_batch_size": 1000,
            },
        }

    async def _fake_get_active_channels():
        return [SimpleNamespace(id=1, username="graph-pending-link")]

    async def _fake_process_channel(_client, _channel, **_kwargs):
        return 1

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "_get_active_channels", _fake_get_active_channels)
    monkeypatch.setattr(pipeline_runtime, "_process_channel", _fake_process_channel)
    monkeypatch.setattr(pipeline_runtime, "run_telegram_link_jobs_until_idle", lambda **_kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "run_telegram_jobs", lambda **_kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "retention_scheduler_enabled", lambda _settings: True)

    # When the telegram cycle runs while the link queue is still incomplete.
    result = await pipeline_runtime.run_telegram_cycle(
        client=object(),
        days=30,
        max_posts_per_channel_arg=10,
        comment_first_delay_hours_arg=2,
        comment_interval_hours_arg=2,
        comment_window_hours_arg=24,
        job_batch_size_arg=10,
        retention_days_arg=30,
        archive_batch_size_arg=1000,
        skip_rebuild_graphs=False,
        worker_id="worker-pending-links-int",
    )

    assert result.processed_posts == 1
    assert result.executed_jobs == 0

    with integration_sync_session_factory() as session:
        # Then rebuild is externally blocked: no premature graph mutation appears in the database,
        # and the system still exposes that the link phase is not ready yet via the pending job.
        events_after = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        processes_after = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        event_memberships_after = session.execute(select(EventPost).order_by(EventPost.event_id.asc(), EventPost.post_id.asc())).scalars().all()
        process_memberships_after = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()
        pending_jobs_after = session.execute(
            select(Job).where(Job.type == JobType.BUILD_POST_LINKS).order_by(Job.id.asc())
        ).scalars().all()

        assert events_after == []
        assert processes_after == []
        assert event_memberships_after == []
        assert process_memberships_after == []
        assert len(pending_jobs_after) == 1
        assert pending_jobs_after[0].id == pending_jobs_before[0].id
        assert pending_jobs_after[0].status == "pending"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_telegram_cycle_applies_link_results_before_rebuilding_graph_against_real_db(
    integration_async_session_factory,
    integration_sync_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given source posts and pre-existing same-event evidence where the graph is still empty before the cycle,
    # and the pending link job needs to contribute the missing verified update edge that makes the process graph rebuildable.
    with integration_sync_session_factory() as session:
        session.add(Channel(id=1, username="cycle_graph_chan", title="Cycle Graph Chan", category="news", is_active=True))
        session.add_all(
            [
                Post(
                    id=1,
                    channel_id=1,
                    tg_message_id=6001,
                    date=datetime(2026, 3, 26, 8, 0, tzinfo=timezone.utc),
                    text="Cycle event A root",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=2,
                    channel_id=1,
                    tg_message_id=6002,
                    date=datetime(2026, 3, 26, 8, 5, tzinfo=timezone.utc),
                    text="Cycle event A member",
                    comments_count=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=3,
                    channel_id=1,
                    tg_message_id=6003,
                    date=datetime(2026, 3, 26, 9, 0, tzinfo=timezone.utc),
                    text="Cycle event B root",
                    comments_count=1,
                    parent_post_id=1,
                    analyzer_version="v1",
                ),
                Post(
                    id=4,
                    channel_id=1,
                    tg_message_id=6004,
                    date=datetime(2026, 3, 26, 9, 5, tzinfo=timezone.utc),
                    text="Cycle event B member",
                    comments_count=1,
                    analyzer_version="v1",
                ),
            ]
        )
        session.add_all(
            [
                PostLink(
                    src_post_id=1,
                    dst_post_id=2,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.9,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
                PostLink(
                    src_post_id=3,
                    dst_post_id=4,
                    link_type=PostLinkType.SAME_EVENT,
                    score=0.9,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "seed"},
                    model_version="test",
                    pipeline_version="test",
                ),
            ]
        )
        session.commit()

    async with integration_async_session_factory() as session:
        queued_job = await enqueue_job(
            session,
            job_type=JobType.BUILD_POST_LINKS,
            payload={"post_id": 3, "source": "integration"},
            dedupe_key="build_post_links:3",
        )
        await session.commit()

    assert queued_job is not None

    with integration_sync_session_factory() as session:
        links_before = session.execute(select(PostLink).order_by(PostLink.id.asc())).scalars().all()
        assert session.execute(select(Event)).scalars().all() == []
        assert session.execute(select(Process)).scalars().all() == []
        assert {
            (int(link.src_post_id), int(link.dst_post_id), link.link_type, link.status)
            for link in links_before
        } == {
            (1, 2, PostLinkType.SAME_EVENT, VerificationStatus.VERIFIED),
            (3, 4, PostLinkType.SAME_EVENT, VerificationStatus.VERIFIED),
        }

    monkeypatch.setattr(pipeline_runtime, "AsyncSessionLocal", integration_async_session_factory)

    async def _fake_get_all_settings(_session):
        return {
            "ingest": {
                "lookback_days": 30,
                "max_posts_per_channel": 10,
                "comment_first_delay_hours": 2,
                "comment_interval_hours": 2,
                "comment_window_hours": 24,
                "comment_schedule_jitter_seconds": 0,
                "collect_comments_sleep_min_ms": 0,
                "collect_comments_sleep_max_ms": 0,
            },
            "jobs": {
                "job_batch_size": 10,
                "collect_comments_quota_per_run": 1,
                "done_retention_days": 14,
                "dead_letter_retention_days": 90,
                "cleanup_batch_size": 1000,
                "job_worker_concurrency": 1,
            },
            "retention": {
                "retention_days": 30,
                "archive_batch_size": 1000,
            },
        }

    class _CycleLinkPipeline:
        async def run_for_post(self, session, post):
            assert int(post.id) == 3
            session.add(
                PostLink(
                    src_post_id=post.parent_post_id,
                    dst_post_id=post.id,
                    link_type=PostLinkType.UPDATE,
                    score=0.88,
                    status=VerificationStatus.VERIFIED,
                    evidence_json={"reason": "cycle link"},
                    model_version="test",
                    pipeline_version="test",
                )
            )
            return LinkRunResponse(
                post_id=3,
                links_verified=1,
                links_proposed=0,
                links_rejected=0,
                candidates_checked=0,
                verify_checked=0,
                critic_checked=0,
                queued_for_review=0,
            )

    monkeypatch.setattr(pipeline_runtime, "get_all_settings", _fake_get_all_settings)
    monkeypatch.setattr(pipeline_runtime, "_get_active_channels", lambda: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(
        pipeline_runtime.NoLlmLinkingPipeline,
        "build_default",
        classmethod(lambda cls: _CycleLinkPipeline()),
    )
    monkeypatch.setattr(pipeline_runtime, "run_telegram_jobs", lambda **_kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(pipeline_runtime, "retention_scheduler_enabled", lambda _settings: True)

    # When the telegram cycle runs through the real link-job drain and rebuild path.
    result = await pipeline_runtime.run_telegram_cycle(
        client=object(),
        days=30,
        max_posts_per_channel_arg=10,
        comment_first_delay_hours_arg=2,
        comment_interval_hours_arg=2,
        comment_window_hours_arg=24,
        job_batch_size_arg=10,
        retention_days_arg=30,
        archive_batch_size_arg=1000,
        skip_rebuild_graphs=False,
        worker_id="worker-cycle-graph-int",
    )

    assert result.processed_posts == 0

    with integration_sync_session_factory() as session:
        # Then the cycle finishes in the post-link reality: verified links are stored first,
        # and the rebuilt graph reflects those applied link results.
        links = session.execute(select(PostLink).order_by(PostLink.id.asc())).scalars().all()
        jobs = session.execute(select(Job).order_by(Job.id.asc())).scalars().all()
        events = session.execute(select(Event).order_by(Event.id.asc())).scalars().all()
        event_memberships = session.execute(select(EventPost).order_by(EventPost.event_id.asc(), EventPost.post_id.asc())).scalars().all()
        processes = session.execute(select(Process).order_by(Process.id.asc())).scalars().all()
        process_memberships = session.execute(
            select(ProcessEvent).order_by(ProcessEvent.process_id.asc(), ProcessEvent.event_id.asc())
        ).scalars().all()
        membership_by_event_id: dict[int, set[int]] = {}
        for row in event_memberships:
            membership_by_event_id.setdefault(int(row.event_id), set()).add(int(row.post_id))

        assert {(int(link.src_post_id), int(link.dst_post_id), link.link_type, link.status) for link in links} == {
            (1, 2, PostLinkType.SAME_EVENT, VerificationStatus.VERIFIED),
            (3, 4, PostLinkType.SAME_EVENT, VerificationStatus.VERIFIED),
            (1, 3, PostLinkType.UPDATE, VerificationStatus.VERIFIED),
        }
        assert [job.status for job in jobs] == ["done"]
        assert jobs[0].type == JobType.BUILD_POST_LINKS
        assert jobs[0].locked_by is None
        assert jobs[0].locked_at is None
        assert jobs[0].heartbeat_at is None
        assert jobs[0].retry_at is None
        assert jobs[0].last_error is None
        assert len(events) == 2
        assert {frozenset(post_ids) for post_ids in membership_by_event_id.values()} == {frozenset({1, 2}), frozenset({3, 4})}
        assert len(processes) == 1
        assert {int(row.event_id) for row in process_memberships} == {int(events[0].id), int(events[1].id)}
