from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Event, EventPost, Post, PostLink
from schemas.dashboard import (
    DashboardChannelRef,
    DashboardGraphEdge,
    DashboardMeta,
    DashboardSortMeta,
    DashboardWarning,
    EventGraphEvent,
    EventGraphNode,
    EventGraphResponse,
    EventsDashboardFilters,
    EventsDashboardItem,
    EventsDashboardResponse,
    EventsDashboardSummary,
)
from services.dashboard.common import (
    average_or_none,
    enum_value,
    load_event_post_rows,
    load_latest_event_report_statuses,
    text_preview,
    utcnow,
)


SUPPORTED_EVENT_SORTS = ("started_at", "comments_count", "involvement", "posts_count")


def _event_sort_key(item: EventsDashboardItem, sort_by: str):
    if sort_by == "comments_count":
        return item.comments_count
    if sort_by == "involvement":
        return item.involvement if item.involvement is not None else -1.0
    if sort_by == "posts_count":
        return item.posts_count
    return item.started_at


async def build_events_dashboard(
    session: AsyncSession,
    *,
    date_from,
    date_to,
    limit: int,
    status: list[str],
    channel_ids: list[int],
    categories: list[str],
    min_comments: int | None,
    sort_by: str,
    sort_order: str,
) -> EventsDashboardResponse:
    stmt = select(Event)
    conditions = []
    if date_from is not None:
        conditions.append(Event.started_at >= date_from)
    if date_to is not None:
        conditions.append(Event.started_at <= date_to)
    if status:
        conditions.append(Event.status.in_(status))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    events = list((await session.execute(stmt)).scalars().all())
    event_ids = [int(event.id) for event in events]
    partial = False
    warnings: list[DashboardWarning] = []

    event_post_rows = await load_event_post_rows(session, event_ids)
    try:
        report_statuses = await load_latest_event_report_statuses(session, event_ids)
    except Exception:
        partial = True
        warnings.append(
            DashboardWarning(code="event_report_status_unavailable", message="Event report statuses could not be fully loaded.")
        )
        report_statuses = {}

    by_event_id: dict[int, dict] = defaultdict(
        lambda: {
            "post_ids": [],
            "root_post_id": None,
            "channels": {},
            "comments": [],
            "involvement": [],
            "categories": set(),
        }
    )
    for event_id, post_id, role, _score, channel_id, post_date, comments_count, involvement in event_post_rows:
        item = by_event_id[int(event_id)]
        item["post_ids"].append(int(post_id))
        item["channels"][int(channel_id)] = DashboardChannelRef(channel_id=int(channel_id), channel_username=None)
        item["comments"].append(int(comments_count or 0))
        item["involvement"].append(float(involvement) if involvement is not None else None)
        if item["root_post_id"] is None or role == "root":
            item["root_post_id"] = int(post_id)

    if event_ids:
        channel_rows = (
            await session.execute(
                select(EventPost.event_id, Channel.id, Channel.username, Channel.category)
                .join(Post, Post.id == EventPost.post_id)
                .join(Channel, Channel.id == Post.channel_id)
                .where(EventPost.event_id.in_(event_ids))
            )
        ).all()
        channel_map: dict[int, dict[int, DashboardChannelRef]] = defaultdict(dict)
        for event_id, channel_id, username, category in channel_rows:
            channel_map[int(event_id)][int(channel_id)] = DashboardChannelRef(channel_id=int(channel_id), channel_username=username)
            if category:
                by_event_id[int(event_id)]["categories"].add(str(category))
        for event_id, channels in channel_map.items():
            by_event_id[event_id]["channels"] = channels

    items: list[EventsDashboardItem] = []
    for event in events:
        info = by_event_id[int(event.id)]
        comments_count = sum(info["comments"])
        item = EventsDashboardItem(
            event_id=event.id,
            title=event.title,
            status=str(enum_value(event.status)),
            started_at=event.started_at,
            ended_at=event.ended_at,
            confidence=float(event.confidence) if event.confidence is not None else None,
            comments_count=comments_count,
            involvement=average_or_none(info["involvement"]),
            posts_count=len(info["post_ids"]),
            post_ids=info["post_ids"],
            root_post_id=info["root_post_id"],
            channels=list(info["channels"].values()),
            report_status=report_statuses.get(int(event.id), "missing"),
            graph_ready=bool(info["post_ids"]),
        )
        if channel_ids and not {ref.channel_id for ref in item.channels}.intersection(channel_ids):
            continue
        if categories and not info["categories"].intersection(set(categories)):
            continue
        if min_comments is not None and item.comments_count < min_comments:
            continue
        items.append(item)

    reverse = sort_order == "desc"
    items.sort(key=lambda value: (_event_sort_key(value, sort_by) is None, _event_sort_key(value, sort_by)), reverse=reverse)
    items = items[:limit]

    statuses = [item.report_status for item in items]
    summary = EventsDashboardSummary(
        events_count=len(items),
        total_linked_posts=sum(item.posts_count for item in items),
        total_comments=sum(item.comments_count for item in items),
        avg_involvement=average_or_none([item.involvement for item in items]),
        draft_reports=sum(1 for value in statuses if value == "draft"),
        ready_reports=sum(1 for value in statuses if value == "ready"),
        failed_reports=sum(1 for value in statuses if value == "failed"),
    )

    return EventsDashboardResponse(
        generated_at=utcnow(),
        partial=partial,
        warnings=warnings,
        filters_applied=EventsDashboardFilters(
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            status=status,
            channel_ids=channel_ids,
            categories=categories,
            min_comments=min_comments,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        summary=summary,
        items=items,
        meta=DashboardMeta(
            sort=DashboardSortMeta(by=sort_by, order=sort_order),
            supported_sorts=list(SUPPORTED_EVENT_SORTS),
        ),
    )


async def build_event_graph(session: AsyncSession, *, event_id: int) -> EventGraphResponse | None:
    event = await session.get(Event, event_id)
    if event is None:
        return None

    report_statuses = await load_latest_event_report_statuses(session, [event_id])
    rows = (
        await session.execute(
            select(
                EventPost.role,
                Post.id,
                Post.channel_id,
                Channel.username,
                Post.date,
                Post.text,
                Post.comments_count,
                Post.views,
                Post.involvement,
            )
            .join(Post, Post.id == EventPost.post_id)
            .join(Channel, Channel.id == Post.channel_id)
            .where(EventPost.event_id == event_id)
            .order_by(Post.date.asc(), Post.id.asc())
        )
    ).all()
    root_post_id = next((int(post_id) for role, post_id, *_rest in rows if role == "root"), None)
    if root_post_id is None and rows:
        root_post_id = int(rows[0][1])

    nodes = [
        EventGraphNode(
            post_id=post_id,
            channel_id=channel_id,
            channel_username=username,
            date=date,
            text_preview=text_preview(text),
            comments_count=int(comments_count or 0),
            views=views,
            involvement=float(involvement) if involvement is not None else None,
            is_root=int(post_id) == root_post_id,
        )
        for _role, post_id, channel_id, username, date, text, comments_count, views, involvement in rows
    ]
    post_ids = [node.post_id for node in nodes]
    edge_rows = []
    if post_ids:
        edge_rows = (
            await session.execute(
                select(PostLink)
                .where(PostLink.src_post_id.in_(post_ids))
                .where(PostLink.dst_post_id.in_(post_ids))
                .order_by(PostLink.updated_at.desc(), PostLink.id.desc())
            )
        ).scalars().all()

    return EventGraphResponse(
        event=EventGraphEvent(
            event_id=event.id,
            title=event.title,
            status=str(enum_value(event.status)),
            started_at=event.started_at,
            ended_at=event.ended_at,
            confidence=float(event.confidence) if event.confidence is not None else None,
            report_status=report_statuses.get(event_id, "missing"),
            posts_count=len(nodes),
            comments_count=sum(node.comments_count for node in nodes),
            involvement=average_or_none([node.involvement for node in nodes]),
        ),
        nodes=nodes,
        edges=[
            DashboardGraphEdge(
                link_id=link.id,
                src_post_id=link.src_post_id,
                dst_post_id=link.dst_post_id,
                link_type=str(enum_value(link.link_type)),
                direction=str(enum_value(link.direction)),
                score=float(link.score) if link.score is not None else None,
                status=str(enum_value(link.status)),
            )
            for link in edge_rows
        ],
    )
