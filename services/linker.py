from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import LinkDirection, Post, PostLink, PostLinkType, VerificationStatus
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline


def _normalize_link_type(value: str) -> PostLinkType:
    normalized = (value or "").strip().lower()
    mapping = {
        "duplicate": "related",
        "near_duplicate": "related",
        "same_event": "same_event",
        "update": "update",
        "refutes": "contradiction",
        "contradiction": "contradiction",
        "cause_effect": "cause",
        "cause": "cause",
        "consequence": "consequence",
        "cites_source": "background",
        "translation": "related",
        "background": "background",
        # Canonical domain semantics: Telegram native reply relation is an UPDATE link.
        "reply_to": "update",
        "reply": "update",
        "native_reply": "update",
        "related": "related",
        "unrelated": "unrelated",
    }
    resolved = mapping.get(normalized, "related")
    return PostLinkType(resolved)


async def upsert_post_link(
    session: AsyncSession,
    *,
    src_post_id: int,
    dst_post_id: int,
    link_type: str,
    confidence: float,
    evidence: dict,
    model_version: str = "legacy-adapter-v1",
) -> None:
    if src_post_id == dst_post_id:
        return
    stmt = (
        insert(PostLink)
        .values(
            src_post_id=src_post_id,
            dst_post_id=dst_post_id,
            link_type=_normalize_link_type(link_type),
            direction=LinkDirection.NONE,
            score=max(0.0, min(1.0, float(confidence))),
            status=VerificationStatus.VERIFIED,
            evidence_json=evidence,
            model_version=model_version,
            pipeline_version=settings.LINKING_PIPELINE_VERSION,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_post_links_src_dst_type",
            set_={
                "score": max(0.0, min(1.0, float(confidence))),
                "status": VerificationStatus.VERIFIED,
                "evidence_json": evidence,
                "model_version": model_version,
                "pipeline_version": settings.LINKING_PIPELINE_VERSION,
                "updated_at": datetime.utcnow(),
            },
        )
    )
    await session.execute(stmt)


async def link_post_to_graph(
    session: AsyncSession,
    *,
    post: Post,
    linker_version: str = "legacy-adapter-v1",
    lookback_days: int | None = None,
    candidate_limit: int | None = None,
) -> dict:
    pipeline = NoLlmLinkingPipeline.build_default()
    result = await pipeline.run_for_post(session, post)
    return {
        "post_id": result.post_id,
        "links_created": result.links_verified + result.links_proposed + result.queued_for_review,
        "ai_links_created": result.links_verified,
        "ai_checked": result.verify_checked,
        "ai_errors": 0,
        "event_id": None,
        "candidates_checked": result.candidates_checked,
    }
