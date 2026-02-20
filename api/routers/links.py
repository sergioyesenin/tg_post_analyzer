from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Event, EventPost, Post, PostLink
from deps import get_session
from schemas.linking import (
    EventDetailOut,
    EventSummaryOut,
    GraphEdgeOut,
    GraphNodeOut,
    LinkRunResponse,
    PostLinksResponse,
    RelatedGraphOut,
    RelatedPostOut,
    RelatedPostsResponse,
)
from services.linker import link_post_to_graph

router = APIRouter()

LINK_TYPE_RU = {
    "DUPLICATE": "Дубликат",
    "NEAR_DUPLICATE": "Почти дубликат",
    "SAME_EVENT": "Одно событие",
    "UPDATE": "Обновление",
    "REFUTES": "Опровержение",
    "CITES_SOURCE": "Ссылка на источник",
    "CAUSE_EFFECT": "Причина и следствие",
    "TRANSLATION": "Перевод",
    "REPLY_TO": "Ответ на пост",
    "UNRELATED": "Не связано",
}


@router.post("/posts/{post_id}/run", response_model=LinkRunResponse)
async def run_linker(post_id: int, session: AsyncSession = Depends(get_session)):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    result = await link_post_to_graph(session, post=post)
    await session.commit()
    return LinkRunResponse(**result)


@router.get("/posts/{post_id}", response_model=PostLinksResponse)
async def get_post_links(post_id: int, session: AsyncSession = Depends(get_session)):
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    links_stmt = (
        select(PostLink)
        .where(or_(PostLink.src_post_id == post_id, PostLink.dst_post_id == post_id))
        .order_by(PostLink.created_at.desc(), PostLink.id.desc())
    )
    links = (await session.execute(links_stmt)).scalars().all()
    return PostLinksResponse(post_id=post_id, links=links)


@router.get("/events", response_model=list[EventSummaryOut])
async def list_events(limit: int = 50, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Event)
        .order_by(Event.last_seen_at.desc().nullslast(), Event.id.desc())
        .limit(limit)
    )
    events = (await session.execute(stmt)).scalars().all()
    return [EventSummaryOut.model_validate(event) for event in events]


@router.get("/events/{event_id}", response_model=EventDetailOut)
async def get_event(event_id: int, session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    post_ids_stmt = (
        select(EventPost.post_id)
        .where(EventPost.event_id == event_id)
        .order_by(EventPost.linked_at.desc(), EventPost.post_id.desc())
    )
    post_ids = [row[0] for row in (await session.execute(post_ids_stmt)).all()]
    return EventDetailOut(
        event=EventSummaryOut.model_validate(event),
        post_ids=post_ids,
    )


@router.get("/posts/{post_id}/related", response_model=RelatedPostsResponse)
async def get_related_posts(post_id: int, session: AsyncSession = Depends(get_session)):
    root_post = await session.get(Post, post_id)
    if root_post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    root_links_stmt = (
        select(PostLink)
        .where(or_(PostLink.src_post_id == post_id, PostLink.dst_post_id == post_id))
        .order_by(PostLink.confidence.desc().nullslast(), PostLink.id.desc())
    )
    root_links = (await session.execute(root_links_stmt)).scalars().all()

    related_ids: set[int] = set()
    for link in root_links:
        if link.src_post_id == post_id:
            related_ids.add(link.dst_post_id)
        else:
            related_ids.add(link.src_post_id)

    node_ids = related_ids | {post_id}
    posts_stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id.in_(node_ids))
    )
    rows = (await session.execute(posts_stmt)).all()
    post_map: dict[int, tuple[Post, Channel]] = {row[0].id: (row[0], row[1]) for row in rows}

    related_posts: list[RelatedPostOut] = []
    for link in root_links:
        related_id = link.dst_post_id if link.src_post_id == post_id else link.src_post_id
        related_row = post_map.get(related_id)
        if related_row is None:
            continue
        related_post, related_channel = related_row
        text_preview = None
        if related_post.text:
            text_preview = related_post.text.splitlines()[0][:220]
        related_posts.append(
            RelatedPostOut(
                post_id=related_post.id,
                channel_id=related_post.channel_id,
                channel_username=related_channel.username,
                date=related_post.date,
                text_preview=text_preview,
                link_type=link.link_type,
                link_type_ru=LINK_TYPE_RU.get(link.link_type, link.link_type),
                confidence=link.confidence,
                direction_ru="Исходящая связь" if link.src_post_id == post_id else "Входящая связь",
            )
        )

    internal_links_stmt = (
        select(PostLink)
        .where(
            and_(
                PostLink.src_post_id.in_(node_ids),
                PostLink.dst_post_id.in_(node_ids),
            )
        )
        .order_by(PostLink.confidence.desc().nullslast(), PostLink.id.desc())
    )
    internal_links = (await session.execute(internal_links_stmt)).scalars().all()

    graph_nodes: list[GraphNodeOut] = []
    for node_id in node_ids:
        row = post_map.get(node_id)
        if row is None:
            continue
        post_obj, channel_obj = row
        label = f"Пост {post_obj.id}"
        if post_obj.text and post_obj.text.strip():
            label = post_obj.text.strip().splitlines()[0][:70]
        subtitle = f"@{channel_obj.username} | {post_obj.date.isoformat()}"
        graph_nodes.append(
            GraphNodeOut(
                id=post_obj.id,
                label=label,
                subtitle=subtitle,
                is_root=(post_obj.id == post_id),
            )
        )

    graph_edges = [
        GraphEdgeOut(
            source=link.src_post_id,
            target=link.dst_post_id,
            relation=link.link_type,
            relation_ru=LINK_TYPE_RU.get(link.link_type, link.link_type),
            confidence=link.confidence,
        )
        for link in internal_links
    ]

    return RelatedPostsResponse(
        root_post_id=post_id,
        related_posts=related_posts,
        graph=RelatedGraphOut(nodes=graph_nodes, edges=graph_edges),
    )
