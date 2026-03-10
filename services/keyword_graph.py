from __future__ import annotations

import re
import time
from collections import deque
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import String, and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import ReportConfig, TgReportProject
from db.models import Channel, Post, PostLink
from schemas.keyword_graph import (
    GraphBuildRequest,
    GraphBuildResponse,
    GraphEdgeOut,
    GraphNodeOut,
    GraphReportRequest,
    GraphReportResponse,
    KeywordSearchItem,
    KeywordSearchRequest,
    KeywordSearchResponse,
)

try:
    from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, Segmenter

    _NATASHA_AVAILABLE = True
except Exception:
    _NATASHA_AVAILABLE = False


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_segmenter = None
_morph_vocab = None
_morph_tagger = None
_natasha_init_failed = False


def _safe_preview(text: str | None, limit: int = 220) -> str | None:
    if not text:
        return None
    compact = " ".join(text.split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _normalize_query_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def _get_natasha_components():
    global _segmenter, _morph_vocab, _morph_tagger, _natasha_init_failed
    if not _NATASHA_AVAILABLE or _natasha_init_failed:
        return None
    if _segmenter is not None:
        return _segmenter, _morph_vocab, _morph_tagger
    try:
        emb = NewsEmbedding()
        _segmenter = Segmenter()
        _morph_vocab = MorphVocab()
        _morph_tagger = NewsMorphTagger(emb)
    except Exception:
        _natasha_init_failed = True
        return None
    return _segmenter, _morph_vocab, _morph_tagger


def _lemmatize_with_natasha(text: str) -> list[str]:
    components = _get_natasha_components()
    if components is None:
        return _tokenize(text)
    segmenter, morph_vocab, morph_tagger = components
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    out: list[str] = []
    for token in doc.tokens:
        try:
            token.lemmatize(morph_vocab)
            lemma = (token.lemma or token.text or "").lower().strip()
        except Exception:
            lemma = (token.text or "").lower().strip()
        if not lemma:
            continue
        if not TOKEN_RE.fullmatch(lemma):
            continue
        out.append(lemma)
    return out


def build_search_lemmas(text: str | None) -> list[str]:
    raw = " ".join(_lemmatize_with_natasha(text or ""))
    values = _tokenize(raw)
    seen: set[str] = set()
    out: list[str] = []
    for token in values:
        if len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _extract_search_lemmas(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    values = payload.get("search_lemmas")
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value).strip().lower()
        if len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _enum_str(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _calc_text_similarity(left: str | None, right: str | None) -> float:
    return float(SequenceMatcher(None, (left or "")[:1200], (right or "")[:1200]).ratio())


def _shared_lemmas(left: set[str], right: set[str]) -> list[str]:
    return sorted(left & right)


def _stable_pair_link_id(left_id: int, right_id: int) -> int:
    a, b = sorted((int(left_id), int(right_id)))
    return (a * 1_000_003 + b * 97) % 2_000_000_000


def _extract_post_lemmas(post: Post) -> set[str]:
    cached = _extract_search_lemmas(post.entities)
    if cached:
        return set(cached)
    return set(build_search_lemmas(post.text_normalized or post.text))


def _select_transient_node_ids(
    *,
    post_by_id: dict[int, Post],
    node_sources: dict[int, str],
    max_nodes: int,
) -> tuple[list[int], bool]:
    if len(post_by_id) <= max_nodes:
        return sorted(post_by_id.keys()), False

    ordered = sorted(
        post_by_id.keys(),
        key=lambda post_id: (
            0 if node_sources.get(post_id) == "seed" else 1,
            -(post_by_id[post_id].date.timestamp() if post_by_id[post_id].date else 0.0),
            -post_id,
        ),
    )
    selected = ordered[:max_nodes]
    return sorted(selected), True


def _collect_transient_candidate_pairs(
    *,
    post_ids: list[int],
    post_by_id: dict[int, Post],
    lemma_sets: dict[int, set[str]],
    max_time_distance_hours: int,
    max_candidates_per_node: int,
) -> tuple[list[tuple[int, int]], dict[str, int]]:
    sorted_ids = sorted(post_ids, key=lambda post_id: (post_by_id[post_id].date, post_id))
    window: deque[int] = deque()
    lemma_index: dict[str, set[int]] = {}
    candidate_pairs: list[tuple[int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()

    max_distance = float(max_time_distance_hours) * 3600.0
    stats = {
        "pairs_generated": 0,
        "pairs_deduplicated": 0,
        "pairs_truncated_by_node_limit": 0,
    }

    for right_id in sorted_ids:
        right_post = post_by_id[right_id]
        right_ts = right_post.date.timestamp()

        while window:
            leftmost_id = window[0]
            left_ts = post_by_id[leftmost_id].date.timestamp()
            if right_ts - left_ts <= max_distance:
                break
            stale_id = window.popleft()
            for lemma in lemma_sets.get(stale_id, set()):
                ids = lemma_index.get(lemma)
                if not ids:
                    continue
                ids.discard(stale_id)
                if not ids:
                    lemma_index.pop(lemma, None)

        candidate_ids: set[int] = set()
        for lemma in lemma_sets.get(right_id, set()):
            candidate_ids.update(lemma_index.get(lemma, set()))

        if len(candidate_ids) > max_candidates_per_node:
            candidate_ids = set(
                sorted(candidate_ids, key=lambda post_id: post_by_id[post_id].date, reverse=True)[:max_candidates_per_node]
            )
            stats["pairs_truncated_by_node_limit"] += 1

        for left_id in candidate_ids:
            a, b = sorted((left_id, right_id))
            pair = (a, b)
            if pair in seen_pairs:
                stats["pairs_deduplicated"] += 1
                continue
            seen_pairs.add(pair)
            candidate_pairs.append(pair)

        stats["pairs_generated"] += len(candidate_ids)

        window.append(right_id)
        for lemma in lemma_sets.get(right_id, set()):
            lemma_index.setdefault(lemma, set()).add(right_id)

    return candidate_pairs, stats


async def _refresh_search_lemmas_if_needed(session: AsyncSession, posts: list[Post]) -> None:
    for post in posts:
        existing_entities = post.entities if isinstance(post.entities, dict) else {}
        existing_lemmas = _extract_search_lemmas(existing_entities)
        if existing_lemmas:
            continue
        computed = build_search_lemmas(post.text_normalized or post.text)
        if not computed:
            continue
        merged = dict(existing_entities)
        merged["search_lemmas"] = computed
        await session.execute(
            Post.__table__.update()
            .where(Post.id == post.id)
            .values(entities=merged)
        )


async def search_posts_by_keywords(
    session: AsyncSession,
    payload: KeywordSearchRequest,
) -> KeywordSearchResponse:
    started = time.perf_counter()
    normalized_query = _normalize_query_text(payload.query)
    lemmas = build_search_lemmas(normalized_query)
    if not normalized_query or not lemmas:
        return KeywordSearchResponse(
            query=payload.query,
            normalized_query=normalized_query,
            lemmas=lemmas,
            took_ms=0,
            total=0,
            items=[],
        )

    vector_expr = func.to_tsvector("russian", func.coalesce(Post.text_normalized, Post.text, ""))
    tsquery = func.plainto_tsquery("russian", normalized_query)
    rank_expr = func.ts_rank_cd(vector_expr, tsquery).label("rank")

    stmt = (
        select(Post, Channel, rank_expr)
        .join(Channel, Channel.id == Post.channel_id)
        .where(vector_expr.op("@@")(tsquery))
    )
    conditions = []
    if payload.date_from is not None:
        conditions.append(Post.date >= payload.date_from)
    if payload.date_to is not None:
        conditions.append(Post.date <= payload.date_to)
    if payload.channel_ids:
        conditions.append(Post.channel_id.in_(payload.channel_ids))
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(rank_expr), Post.date.desc()).limit(payload.limit)

    rows = (await session.execute(stmt)).all()
    posts = [row[0] for row in rows]
    await _refresh_search_lemmas_if_needed(session, posts)

    items: list[KeywordSearchItem] = []
    for post, channel, rank in rows:
        cache_lemmas = _extract_search_lemmas(post.entities)
        if cache_lemmas:
            lemma_pool = cache_lemmas
        else:
            lemma_pool = build_search_lemmas(post.text_normalized or post.text)
        cache_set = set(lemma_pool)
        matched = [lemma for lemma in lemmas if lemma in cache_set]
        items.append(
            KeywordSearchItem(
                post_id=post.id,
                channel_id=post.channel_id,
                channel_username=channel.username,
                date=post.date,
                text_preview=_safe_preview(post.text),
                comments_count=post.comments_count,
                views=post.views,
                involvement=post.involvement,
                rank=float(rank or 0.0),
                matched_lemmas=matched,
            )
        )

    took_ms = int((time.perf_counter() - started) * 1000)
    return KeywordSearchResponse(
        query=payload.query,
        normalized_query=normalized_query,
        lemmas=lemmas,
        took_ms=took_ms,
        total=len(items),
        items=items,
    )


async def build_posts_graph(
    session: AsyncSession,
    payload: GraphBuildRequest,
) -> GraphBuildResponse:
    if payload.graph_mode == "transient":
        return await _build_transient_graph(session, payload)
    return await _build_persisted_graph(session, payload)


async def _build_transient_graph(
    session: AsyncSession,
    payload: GraphBuildRequest,
) -> GraphBuildResponse:
    started = time.perf_counter()
    excluded = {int(post_id) for post_id in payload.exclude_post_ids}
    seed_ids = [int(post_id) for post_id in payload.post_ids if int(post_id) not in excluded]
    if not seed_ids:
        return GraphBuildResponse(seed_post_ids=[], excluded_post_ids=sorted(excluded), nodes=[], edges=[], took_ms=0, meta={})

    seed_rows = (
        await session.execute(
            select(Post, Channel)
            .join(Channel, Channel.id == Post.channel_id)
            .where(Post.id.in_(seed_ids))
        )
    ).all()
    if not seed_rows:
        return GraphBuildResponse(seed_post_ids=seed_ids, excluded_post_ids=sorted(excluded), nodes=[], edges=[], took_ms=0, meta={})

    post_by_id: dict[int, Post] = {}
    channel_by_post_id: dict[int, Channel] = {}
    node_sources: dict[int, str] = {}
    for post, channel in seed_rows:
        post_by_id[post.id] = post
        channel_by_post_id[post.id] = channel
        node_sources[post.id] = "seed"

    await _refresh_search_lemmas_if_needed(session, list(post_by_id.values()))
    lemma_sets: dict[int, set[str]] = {post_id: _extract_post_lemmas(post) for post_id, post in post_by_id.items()}

    if payload.include_neighbors:
        seed_lemmas: set[str] = set()
        for values in lemma_sets.values():
            seed_lemmas.update(values)
        lemma_tokens = sorted(seed_lemmas)[:32]
        min_seed_date = min(item.date for item in post_by_id.values())
        max_seed_date = max(item.date for item in post_by_id.values())
        date_from = min_seed_date - timedelta(hours=int(payload.max_time_distance_hours))
        date_to = max_seed_date + timedelta(hours=int(payload.max_time_distance_hours))

        effective_neighbor_limit = int(payload.neighbor_limit) * max(int(payload.neighbor_depth), 1)
        neighbor_stmt = (
            select(Post, Channel)
            .join(Channel, Channel.id == Post.channel_id)
            .where(Post.id.not_in(seed_ids))
            .where(Post.id.not_in(sorted(excluded)) if excluded else True)
            .where(
                and_(
                    Post.date >= date_from,
                    Post.date <= date_to,
                )
            )
            .order_by(Post.date.desc(), Post.id.desc())
            .limit(effective_neighbor_limit)
        )
        if lemma_tokens:
            neighbor_stmt = neighbor_stmt.where(
                func.to_tsvector("russian", func.coalesce(Post.text_normalized, Post.text, "")).op("@@")(
                    func.plainto_tsquery("russian", " ".join(lemma_tokens[:8]))
                )
            )
        neighbor_rows = (await session.execute(neighbor_stmt)).all()
        for post, channel in neighbor_rows:
            post_by_id[post.id] = post
            channel_by_post_id[post.id] = channel
            node_sources[post.id] = "neighbor"
        if neighbor_rows:
            await _refresh_search_lemmas_if_needed(session, [row[0] for row in neighbor_rows])
            for post, _ in neighbor_rows:
                lemma_sets[post.id] = _extract_post_lemmas(post)

    selected_node_ids, nodes_truncated = _select_transient_node_ids(
        post_by_id=post_by_id,
        node_sources=node_sources,
        max_nodes=int(payload.transient_max_nodes),
    )
    post_by_id = {post_id: post_by_id[post_id] for post_id in selected_node_ids}
    channel_by_post_id = {post_id: channel_by_post_id[post_id] for post_id in selected_node_ids if post_id in channel_by_post_id}
    node_sources = {post_id: node_sources[post_id] for post_id in selected_node_ids if post_id in node_sources}
    lemma_sets = {post_id: lemma_sets.get(post_id, set()) for post_id in selected_node_ids}

    nodes: list[GraphNodeOut] = [
        GraphNodeOut(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_username=channel_by_post_id[post.id].username if post.id in channel_by_post_id else None,
            date=post.date,
            text_preview=_safe_preview(post.text),
            comments_count=post.comments_count,
            views=post.views,
            involvement=post.involvement,
            included_by=node_sources.get(post.id, "neighbor"),
        )
        for post in post_by_id.values()
    ]
    nodes.sort(key=lambda item: (item.date, item.post_id))

    post_ids = [node.post_id for node in nodes]
    candidate_pairs, candidate_stats = _collect_transient_candidate_pairs(
        post_ids=post_ids,
        post_by_id=post_by_id,
        lemma_sets=lemma_sets,
        max_time_distance_hours=payload.max_time_distance_hours,
        max_candidates_per_node=int(payload.transient_max_candidates_per_node),
    )

    deadline = started + (int(payload.transient_timeout_ms) / 1000.0)
    edges: list[GraphEdgeOut] = []
    pair_eval_count = 0
    for left_id, right_id in candidate_pairs:
        pair_eval_count += 1
        if len(edges) >= int(payload.transient_max_edges):
            break
        if time.perf_counter() > deadline:
            break
        left_post = post_by_id[left_id]
        left_lemmas = lemma_sets.get(left_id, set())
        right_post = post_by_id[right_id]
        right_lemmas = lemma_sets.get(right_id, set())
        shared = _shared_lemmas(left_lemmas, right_lemmas)
        if len(shared) < payload.min_shared_lemmas:
            continue
        time_distance_hours = abs((right_post.date - left_post.date).total_seconds()) / 3600.0
        if time_distance_hours > float(payload.max_time_distance_hours):
            continue
        text_similarity = _calc_text_similarity(left_post.text_normalized or left_post.text, right_post.text_normalized or right_post.text)
        if text_similarity < float(payload.min_text_similarity):
            continue
        score = min(
            1.0,
            0.45 * min(1.0, len(shared) / max(payload.min_shared_lemmas, 1))
            + 0.35 * text_similarity
            + 0.20 * max(0.0, 1.0 - time_distance_hours / max(float(payload.max_time_distance_hours), 1.0)),
        )
        edges.append(
            GraphEdgeOut(
                link_id=_stable_pair_link_id(left_id, right_id),
                src_post_id=left_id,
                dst_post_id=right_id,
                link_type="related",
                direction="none",
                score=score,
                status="transient",
                edge_source="transient",
                evidence={
                    "shared_lemmas_count": len(shared),
                    "shared_lemmas_sample": shared[:8],
                    "time_distance_hours": round(time_distance_hours, 3),
                    "text_similarity": round(text_similarity, 4),
                    "thresholds": {
                        "min_shared_lemmas": payload.min_shared_lemmas,
                        "max_time_distance_hours": payload.max_time_distance_hours,
                        "min_text_similarity": payload.min_text_similarity,
                    },
                },
            )
        )

    took_ms = int((time.perf_counter() - started) * 1000)
    edge_limit_hit = len(edges) >= int(payload.transient_max_edges)
    timeout_hit = time.perf_counter() > deadline

    return GraphBuildResponse(
        seed_post_ids=seed_ids,
        excluded_post_ids=sorted(excluded),
        nodes=nodes,
        edges=sorted(edges, key=lambda item: (item.score or 0.0, item.link_id), reverse=True),
        took_ms=took_ms,
        meta={
            "graph_mode": "transient",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes_truncated": nodes_truncated,
            "edge_limit_hit": edge_limit_hit,
            "timeout_hit": timeout_hit,
            "candidate_pairs_count": len(candidate_pairs),
            "pair_eval_count": pair_eval_count,
            "candidate_stats": candidate_stats,
            "transient_limits": {
                "max_nodes": int(payload.transient_max_nodes),
                "max_edges": int(payload.transient_max_edges),
                "max_candidates_per_node": int(payload.transient_max_candidates_per_node),
                "timeout_ms": int(payload.transient_timeout_ms),
            },
        },
    )


async def _build_persisted_graph(
    session: AsyncSession,
    payload: GraphBuildRequest,
) -> GraphBuildResponse:
    started = time.perf_counter()
    excluded = {int(post_id) for post_id in payload.exclude_post_ids}
    seed_ids = [int(post_id) for post_id in payload.post_ids if int(post_id) not in excluded]
    if not seed_ids:
        return GraphBuildResponse(seed_post_ids=[], excluded_post_ids=sorted(excluded), nodes=[], edges=[], took_ms=0, meta={})

    node_sources: dict[int, str] = {post_id: "seed" for post_id in seed_ids}
    node_ids: set[int] = set(seed_ids)
    edge_by_id: dict[int, GraphEdgeOut] = {}

    allowed_link_types = {value.strip().lower() for value in payload.allowed_link_types if value.strip()}
    if not payload.include_neighbors:
        stmt = select(PostLink).where(
            and_(
                PostLink.src_post_id.in_(seed_ids),
                PostLink.dst_post_id.in_(seed_ids),
            )
        )
        if allowed_link_types:
            stmt = stmt.where(func.lower(func.cast(PostLink.link_type, String())).in_(allowed_link_types))
        links = (await session.execute(stmt.limit(payload.neighbor_limit))).scalars().all()
        for link in links:
            edge_by_id[link.id] = GraphEdgeOut(
                link_id=link.id,
                src_post_id=int(link.src_post_id),
                dst_post_id=int(link.dst_post_id),
                link_type=_enum_str(link.link_type),
                direction=_enum_str(link.direction),
                score=link.score,
                status=_enum_str(link.status),
                edge_source="persisted",
                evidence=link.evidence_json if isinstance(link.evidence_json, dict) else None,
            )

    frontier = deque(seed_ids)
    depth = 0
    while frontier and payload.include_neighbors and depth < payload.neighbor_depth:
        level_ids: list[int] = []
        while frontier:
            level_ids.append(frontier.popleft())
        if not level_ids:
            break

        stmt = select(PostLink).where(or_(PostLink.src_post_id.in_(level_ids), PostLink.dst_post_id.in_(level_ids)))
        if allowed_link_types:
            stmt = stmt.where(func.lower(func.cast(PostLink.link_type, String())).in_(allowed_link_types))
        links = (await session.execute(stmt.limit(payload.neighbor_limit))).scalars().all()
        for link in links:
            src = int(link.src_post_id)
            dst = int(link.dst_post_id)
            if src in excluded or dst in excluded:
                continue
            edge_by_id[link.id] = GraphEdgeOut(
                link_id=link.id,
                src_post_id=src,
                dst_post_id=dst,
                link_type=_enum_str(link.link_type),
                direction=_enum_str(link.direction),
                score=link.score,
                status=_enum_str(link.status),
                edge_source="persisted",
                evidence=link.evidence_json if isinstance(link.evidence_json, dict) else None,
            )
            for post_id in (src, dst):
                if post_id in node_ids:
                    continue
                node_ids.add(post_id)
                node_sources[post_id] = "neighbor"
                frontier.append(post_id)
        depth += 1

    full_edges_stmt = select(PostLink).where(
        and_(
            PostLink.src_post_id.in_(sorted(node_ids)),
            PostLink.dst_post_id.in_(sorted(node_ids)),
        )
    )
    if allowed_link_types:
        full_edges_stmt = full_edges_stmt.where(func.lower(func.cast(PostLink.link_type, String())).in_(allowed_link_types))
    full_edges_limit = max(payload.neighbor_limit, len(node_ids) * 4)
    full_edges = (await session.execute(full_edges_stmt.limit(full_edges_limit))).scalars().all()
    for link in full_edges:
        src = int(link.src_post_id)
        dst = int(link.dst_post_id)
        if src in excluded or dst in excluded:
            continue
        edge_by_id[link.id] = GraphEdgeOut(
            link_id=link.id,
            src_post_id=src,
            dst_post_id=dst,
            link_type=_enum_str(link.link_type),
            direction=_enum_str(link.direction),
            score=link.score,
            status=_enum_str(link.status),
            edge_source="persisted",
            evidence=link.evidence_json if isinstance(link.evidence_json, dict) else None,
        )

    posts_stmt = (
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id.in_(sorted(node_ids)))
    )
    rows = (await session.execute(posts_stmt)).all()
    node_map: dict[int, GraphNodeOut] = {}
    for post, channel in rows:
        node_map[post.id] = GraphNodeOut(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_username=channel.username,
            date=post.date,
            text_preview=_safe_preview(post.text),
            comments_count=post.comments_count,
            views=post.views,
            involvement=post.involvement,
            included_by=node_sources.get(post.id, "neighbor"),
        )

    took_ms = int((time.perf_counter() - started) * 1000)
    return GraphBuildResponse(
        seed_post_ids=seed_ids,
        excluded_post_ids=sorted(excluded),
        nodes=sorted(node_map.values(), key=lambda item: (item.date, item.post_id)),
        edges=sorted(edge_by_id.values(), key=lambda item: item.link_id),
        took_ms=took_ms,
        meta={
            "graph_mode": "persisted",
            "node_count": len(node_map),
            "edge_count": len(edge_by_id),
        },
    )


def _build_graph_report_prompt(title: str, nodes: list[GraphNodeOut], edges: list[GraphEdgeOut]) -> str:
    lines: list[str] = []
    lines.append(f"Graph: {title}")
    lines.append(f"Nodes: {len(nodes)}")
    lines.append(f"Edges: {len(edges)}")
    lines.append("")
    lines.append("Posts:")
    for node in nodes[:60]:
        lines.append(
            f"- post_id={node.post_id} channel=@{node.channel_username or '-'} "
            f"date={node.date.isoformat()} comments={node.comments_count} views={node.views or 0} "
            f"text={_safe_preview(node.text_preview, 180) or ''}"
        )
    lines.append("")
    lines.append("Links:")
    for edge in edges[:120]:
        lines.append(
            f"- {edge.src_post_id} -> {edge.dst_post_id} "
            f"type={edge.link_type} status={edge.status} score={edge.score}"
        )
    return "\n".join(lines)


async def generate_graph_report(
    session: AsyncSession,
    payload: GraphReportRequest,
    report_project: TgReportProject,
) -> GraphReportResponse:
    graph = await build_posts_graph(
        session,
        GraphBuildRequest(
            post_ids=payload.post_ids,
            exclude_post_ids=payload.exclude_post_ids,
            graph_mode=payload.graph_mode,
            include_neighbors=payload.include_neighbors,
            neighbor_depth=payload.neighbor_depth,
            neighbor_limit=payload.neighbor_limit,
            allowed_link_types=payload.allowed_link_types,
            min_shared_lemmas=payload.min_shared_lemmas,
            max_time_distance_hours=payload.max_time_distance_hours,
            min_text_similarity=payload.min_text_similarity,
            transient_max_nodes=payload.transient_max_nodes,
            transient_max_edges=payload.transient_max_edges,
            transient_max_candidates_per_node=payload.transient_max_candidates_per_node,
            transient_timeout_ms=payload.transient_timeout_ms,
        ),
    )
    if not graph.nodes:
        return GraphReportResponse(
            status="not_found",
            title=payload.title or "Graph Report",
            post_ids=payload.post_ids,
            excluded_post_ids=payload.exclude_post_ids,
            content="No posts found for graph report.",
        )

    title = payload.title or "Graph Report"
    synthetic_post_text = _build_graph_report_prompt(title, graph.nodes, graph.edges)
    comments = [node.text_preview for node in graph.nodes if node.text_preview]
    try:
        content = await report_project.generate_report(
            channel="graph",
            post_id=min(payload.post_ids),
            published_at_iso=graph.nodes[0].date.isoformat(),
            post_text=synthetic_post_text,
            comments=comments,
            thread_comments=[],
            views=sum(int(node.views or 0) for node in graph.nodes),
            config=ReportConfig(min_comments=0, report_word_target=500, report_word_min=250, report_word_max=900),
        )
        status = "ready"
    except Exception as exc:
        status = "failed"
        content = f"STATUS: FAILED\nREASON: {exc!r}"

    return GraphReportResponse(
        status=status,
        title=title,
        post_ids=payload.post_ids,
        excluded_post_ids=payload.exclude_post_ids,
        content=content,
    )
