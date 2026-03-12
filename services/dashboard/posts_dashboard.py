from __future__ import annotations

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Post
from schemas.dashboard import (
    DashboardMeta,
    DashboardSortMeta,
    DashboardWarning,
    PostsDashboardFilters,
    PostsDashboardItem,
    PostsDashboardResponse,
    PostsDashboardSummary,
)
from services.dashboard.common import average_or_none, load_post_link_counts, load_post_report_statuses, text_preview, utcnow


SUPPORTED_POST_SORTS = {
    "comments_count": Post.comments_count,
    "date": Post.date,
    "views": Post.views,
    "involvement": Post.involvement,
}


async def build_posts_dashboard(
    session: AsyncSession,
    *,
    date_from,
    date_to,
    limit: int,
    channel_ids: list[int],
    categories: list[str],
    min_comments: int | None,
    report_status: list[str],
    sort_by: str,
    sort_order: str,
    comments_refresh_available: bool,
) -> PostsDashboardResponse:
    partial = False
    warnings: list[DashboardWarning] = []
    sort_column = SUPPORTED_POST_SORTS[sort_by]

    stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.date >= date_from)
        .where(Post.date <= date_to)
    )
    conditions = []
    if channel_ids:
        conditions.append(Post.channel_id.in_(channel_ids))
    if categories:
        conditions.append(Channel.category.in_(categories))
    if min_comments is not None:
        conditions.append(Post.comments_count >= min_comments)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    ordered_stmt = stmt.order_by(desc(sort_column) if sort_order == "desc" else sort_column.asc(), Post.id.desc())
    if not report_status:
        ordered_stmt = ordered_stmt.limit(limit)

    rows = (await session.execute(ordered_stmt)).all()
    posts = [row[0] for row in rows]
    channels_by_post_id = {int(post.id): channel for post, channel in rows}
    post_ids = [int(post.id) for post in posts]

    try:
        report_statuses = await load_post_report_statuses(session, post_ids)
    except Exception:
        partial = True
        warnings.append(
            DashboardWarning(code="post_report_status_unavailable", message="Post report statuses could not be fully loaded.")
        )
        report_statuses = {post_id: "missing" for post_id in post_ids}

    filtered_posts = posts
    if report_status:
        allowed_statuses = {value.strip() for value in report_status if value.strip()}
        filtered_posts = [post for post in posts if report_statuses.get(int(post.id), "missing") in allowed_statuses][:limit]
        post_ids = [int(post.id) for post in filtered_posts]

    try:
        link_counts = await load_post_link_counts(session, post_ids)
    except Exception:
        partial = True
        warnings.append(DashboardWarning(code="post_link_counts_unavailable", message="Post link counts could not be fully loaded."))
        link_counts = {}

    items = []
    for post in filtered_posts:
        channel = channels_by_post_id[int(post.id)]
        status = report_statuses.get(int(post.id), "missing")
        items.append(
            PostsDashboardItem(
                post_id=post.id,
                channel_id=post.channel_id,
                channel_username=channel.username,
                channel_title=channel.title,
                channel_category=channel.category,
                date=post.date,
                text_preview=text_preview(post.text),
                comments_count=int(post.comments_count or 0),
                views=post.views,
                involvement=float(post.involvement) if post.involvement is not None else None,
                report_status=status,
                has_report=status not in {"missing", "pending"},
                comments_refresh_available=comments_refresh_available,
                links_count=link_counts.get(int(post.id)),
            )
        )

    item_statuses = [item.report_status for item in items]
    summary = PostsDashboardSummary(
        posts_count=len(items),
        total_comments=sum(item.comments_count for item in items),
        avg_involvement=average_or_none([item.involvement for item in items]),
        channels_count=len({item.channel_id for item in items}),
        reports_ready=sum(1 for status in item_statuses if status == "ready"),
        reports_missing=sum(1 for status in item_statuses if status == "missing"),
        reports_pending=sum(1 for status in item_statuses if status == "pending"),
        reports_failed=sum(1 for status in item_statuses if status == "failed"),
    )

    return PostsDashboardResponse(
        generated_at=utcnow(),
        partial=partial,
        warnings=warnings,
        filters_applied=PostsDashboardFilters(
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            channel_ids=channel_ids,
            categories=categories,
            min_comments=min_comments,
            report_status=report_status,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
        summary=summary,
        items=items,
        meta=DashboardMeta(
            sort=DashboardSortMeta(by=sort_by, order=sort_order),
            supported_sorts=list(SUPPORTED_POST_SORTS.keys()),
        ),
    )
