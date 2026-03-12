from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Event, EventPost, Post, PostLink, Process, ProcessEvent
from schemas.dashboard import (
    DashboardGraphEdge,
    DashboardMeta,
    DashboardSortMeta,
    DashboardWarning,
    EventGraphNode,
    ProcessGraphEvent,
    ProcessGraphMapping,
    ProcessGraphResponse,
    ProcessGraphSummary,
    ProcessesDashboardFilters,
    ProcessesDashboardItem,
    ProcessesDashboardResponse,
    ProcessesDashboardSummary,
)
from services.dashboard.common import (
    average_or_none,
    enum_value,
    load_latest_process_report_statuses,
    load_process_event_rows,
    text_preview,
    utcnow,
)


SUPPORTED_PROCESS_SORTS = ("started_at", "comments_count", "involvement", "events_count")


def _process_sort_key(item: ProcessesDashboardItem, sort_by: str):
    if sort_by == "comments_count":
        return item.comments_count
    if sort_by == "involvement":
        return item.involvement if item.involvement is not None else -1.0
    if sort_by == "events_count":
        return item.events_count
    return item.started_at


async def build_processes_dashboard(
    session: AsyncSession,
    *,
    date_from,
    date_to,
    limit: int,
    status: list[str],
    min_comments: int | None,
    sort_by: str,
    sort_order: str,
) -> ProcessesDashboardResponse:
    stmt = select(Process)
    conditions = []
    if date_from is not None:
        conditions.append(Process.started_at >= date_from)
    if date_to is not None:
        conditions.append(Process.started_at <= date_to)
    if status:
        conditions.append(Process.status.in_(status))
    if conditions:
        stmt = stmt.where(and_(*conditions))

    processes = list((await session.execute(stmt)).scalars().all())
    process_ids = [int(process.id) for process in processes]
    event_rows = await load_process_event_rows(session, process_ids)
    partial = False
    warnings: list[DashboardWarning] = []
    try:
        report_statuses = await load_latest_process_report_statuses(session, process_ids)
    except Exception:
        partial = True
        warnings.append(
            DashboardWarning(
                code="process_report_status_unavailable",
                message="Process report statuses could not be fully loaded.",
            )
        )
        report_statuses = {}

    process_event_ids: dict[int, list[int]] = defaultdict(list)
    for process_id, event_id, _relation_type, _direction, _score in event_rows:
        process_event_ids[int(process_id)].append(int(event_id))

    all_event_ids = sorted({event_id for event_ids in process_event_ids.values() for event_id in event_ids})
    event_post_rows = []
    if all_event_ids:
        event_post_rows = (
            await session.execute(
                select(EventPost.event_id, Post.id, Post.comments_count, Post.involvement)
                .join(Post, Post.id == EventPost.post_id)
                .where(EventPost.event_id.in_(all_event_ids))
            )
        ).all()
    event_posts_map: dict[int, list[tuple[int, int, float | None]]] = defaultdict(list)
    for event_id, post_id, comments_count, involvement in event_post_rows:
        event_posts_map[int(event_id)].append(
            (int(post_id), int(comments_count or 0), float(involvement) if involvement is not None else None)
        )

    items: list[ProcessesDashboardItem] = []
    for process in processes:
        event_ids = process_event_ids.get(int(process.id), [])
        comments = []
        involvements = []
        for event_id in event_ids:
            for _post_id, comments_count, involvement in event_posts_map.get(event_id, []):
                comments.append(comments_count)
                involvements.append(involvement)
        comments_count = sum(comments)
        if min_comments is not None and comments_count < min_comments:
            continue
        items.append(
            ProcessesDashboardItem(
                process_id=process.id,
                title=process.title,
                status=str(enum_value(process.status)),
                started_at=process.started_at,
                ended_at=process.ended_at,
                confidence=float(process.confidence) if process.confidence is not None else None,
                comments_count=comments_count,
                involvement=average_or_none(involvements),
                events_count=len(event_ids),
                event_ids=event_ids,
            report_status=report_statuses.get(int(process.id), "missing"),
            graph_ready=bool(event_ids),
        )
        )

    reverse = sort_order == "desc"
    items.sort(key=lambda value: (_process_sort_key(value, sort_by) is None, _process_sort_key(value, sort_by)), reverse=reverse)
    items = items[:limit]
    item_statuses = [item.report_status for item in items]

    return ProcessesDashboardResponse(
        generated_at=utcnow(),
        partial=partial,
        warnings=warnings,
        filters_applied=ProcessesDashboardFilters(
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            status=status,
            min_comments=min_comments,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        summary=ProcessesDashboardSummary(
            processes_count=len(items),
            total_events=sum(item.events_count for item in items),
            total_comments=sum(item.comments_count for item in items),
            avg_involvement=average_or_none([item.involvement for item in items]),
            draft_reports=sum(1 for status_value in item_statuses if status_value == "draft"),
            failed_reports=sum(1 for status_value in item_statuses if status_value == "failed"),
        ),
        items=items,
        meta=DashboardMeta(
            sort=DashboardSortMeta(by=sort_by, order=sort_order),
            supported_sorts=list(SUPPORTED_PROCESS_SORTS),
        ),
    )


async def build_process_graph(session: AsyncSession, *, process_id: int) -> ProcessGraphResponse | None:
    process = await session.get(Process, process_id)
    if process is None:
        return None

    process_rows = (
        await session.execute(
            select(
                ProcessEvent.event_id,
                ProcessEvent.relation_type,
                ProcessEvent.direction,
                ProcessEvent.score,
                Event.title,
                Event.status,
                Event.started_at,
                Event.ended_at,
                Event.confidence,
            )
            .join(Event, Event.id == ProcessEvent.event_id)
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()
    report_status = (await load_latest_process_report_statuses(session, [process_id])).get(process_id, "missing")
    event_ids = [int(row[0]) for row in process_rows]

    post_rows = []
    if event_ids:
        post_rows = (
            await session.execute(
                select(
                    EventPost.event_id,
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
                .where(EventPost.event_id.in_(event_ids))
                .order_by(Post.date.asc(), Post.id.asc())
            )
        ).all()

    mapping: dict[int, list[int]] = defaultdict(list)
    root_post_ids: set[int] = set()
    nodes: list[EventGraphNode] = []
    for event_id, role, post_id, channel_id, username, date, text, comments_count, views, involvement in post_rows:
        mapping[int(event_id)].append(int(post_id))
        if role == "root":
            root_post_ids.add(int(post_id))
        nodes.append(
            EventGraphNode(
                post_id=post_id,
                channel_id=channel_id,
                channel_username=username,
                date=date,
                text_preview=text_preview(text),
                comments_count=int(comments_count or 0),
                views=views,
                involvement=float(involvement) if involvement is not None else None,
                is_root=False,
            )
        )
    if not root_post_ids and nodes:
        root_post_ids.add(nodes[0].post_id)
    nodes = [node.model_copy(update={"is_root": node.post_id in root_post_ids}) for node in nodes]

    post_ids = [node.post_id for node in nodes]
    links = []
    if post_ids:
        links = (
            await session.execute(
                select(PostLink)
                .where(PostLink.src_post_id.in_(post_ids))
                .where(PostLink.dst_post_id.in_(post_ids))
                .order_by(PostLink.updated_at.desc(), PostLink.id.desc())
            )
        ).scalars().all()

    events = [
        ProcessGraphEvent(
            event_id=event_id,
            title=title,
            status=str(enum_value(event_status)),
            started_at=started_at,
            ended_at=ended_at,
            confidence=float(confidence) if confidence is not None else None,
            relation_type=str(enum_value(relation_type)),
            direction=str(enum_value(direction)),
            score=float(score) if score is not None else None,
            post_ids=mapping.get(int(event_id), []),
        )
        for event_id, relation_type, direction, score, title, event_status, started_at, ended_at, confidence in process_rows
    ]

    return ProcessGraphResponse(
        summary=ProcessGraphSummary(
            process_id=process.id,
            title=process.title,
            status=str(enum_value(process.status)),
            started_at=process.started_at,
            ended_at=process.ended_at,
            confidence=float(process.confidence) if process.confidence is not None else None,
            report_status=report_status,
            events_count=len(events),
            posts_count=len(nodes),
            comments_count=sum(node.comments_count for node in nodes),
            involvement=average_or_none([node.involvement for node in nodes]),
        ),
        events=events,
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
            for link in links
        ],
        mapping=ProcessGraphMapping(process_id=process.id, event_to_post_ids=dict(mapping)),
    )
