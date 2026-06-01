from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from deps import get_session, require_roles
from schemas.keyword_graph import (
    GraphBuildRequest,
    GraphBuildResponse,
    GraphReportRequest,
    GraphReportResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
)
from services.auth import AuthUser, write_audit_log
from services.keyword_graph import build_posts_graph, search_posts_by_keywords
from services.settings_store import get_setting

router = APIRouter()


def _in_rollout(user_id: int, percent: int) -> bool:
    if percent >= 100:
        return True
    if percent <= 0:
        return False
    return (user_id % 100) < percent


async def _ensure_feature_enabled(session: AsyncSession, user_id: int) -> None:
    features = await get_setting(session, "features")
    if not bool(features.get("keyword_graph_api_enabled", False)):
        raise HTTPException(status_code=404, detail="Feature disabled")
    percent = int(features.get("keyword_graph_rollout_percent", 0))
    if not _in_rollout(user_id, percent):
        raise HTTPException(status_code=404, detail="Feature rollout gate")


@router.post("/search/posts", response_model=KeywordSearchResponse)
async def search_posts(
    payload: KeywordSearchRequest,
    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_feature_enabled(session, current_user.id)
    result = await search_posts_by_keywords(session, payload)
    await write_audit_log(
        session,
        action="keyword_graph.search_posts",
        actor_user_id=current_user.id,
        target_type="keyword_graph",
        details={
            "query": payload.query,
            "limit": payload.limit,
            "date_from": payload.date_from.isoformat() if payload.date_from else None,
            "date_to": payload.date_to.isoformat() if payload.date_to else None,
            "total": result.total,
            "took_ms": result.took_ms,
        },
    )
    await session.commit()
    return result


@router.post("/graph/build", response_model=GraphBuildResponse)
async def build_graph(
    payload: GraphBuildRequest,
    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_feature_enabled(session, current_user.id)
    result = await build_posts_graph(session, payload)
    await write_audit_log(
        session,
        action="keyword_graph.build_graph",
        actor_user_id=current_user.id,
        target_type="keyword_graph",
        details={
            "seed_count": len(payload.post_ids),
            "excluded_count": len(payload.exclude_post_ids),
            "graph_mode": payload.graph_mode,
            "nodes": len(result.nodes),
            "edges": len(result.edges),
            "took_ms": result.took_ms,
            "meta": result.meta,
        },
    )
    await session.commit()
    return result


#@router.post("/graph/report", response_model=GraphReportResponse)
#async def report_graph(
#    payload: GraphReportRequest,
#    current_user: AuthUser = Depends(require_roles("admin", "analyst")),
#    session: AsyncSession = Depends(get_session),
#):
#    await _ensure_feature_enabled(session, current_user.id)
#    result = await generate_graph_report(session, payload, report_project=get_report_project())
#    await write_audit_log(
#        session,
#        action="keyword_graph.report_graph",
#        actor_user_id=current_user.id,
#        target_type="keyword_graph",
#        details={
#            "status": result.status,
#            "seed_count": len(payload.post_ids),
#            "excluded_count": len(payload.exclude_post_ids),
#            "graph_mode": payload.graph_mode,
#        },
#    )
#    await session.commit()
#    return result
