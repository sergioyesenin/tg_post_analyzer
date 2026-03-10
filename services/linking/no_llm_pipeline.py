from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import LinkDirection, Post, PostLink, PostLinkType, VerificationStatus
from schemas.linking import LinkRunResponse
from services.linking.candidates import Candidate, retrieve_candidates


@dataclass(slots=True)
class NoLlmLinkingPipeline:
    same_event_min_sim: float = settings.NO_LLM_SAME_EVENT_MIN_SIM
    same_event_max_hours: int = settings.NO_LLM_SAME_EVENT_MAX_HOURS
    same_event_min_entity_overlap: float = settings.LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN

    @classmethod
    def build_default(cls) -> "NoLlmLinkingPipeline":
        return cls()

    async def _commit_reply_update_link(self, session: AsyncSession, post: Post) -> int:
        if not post.parent_post_id:
            return 0

        # Canonical domain semantics: native Telegram reply relation is UPDATE.
        stmt = (
            insert(PostLink)
            .values(
                src_post_id=post.id,
                dst_post_id=post.parent_post_id,
                link_type=PostLinkType.UPDATE,
                direction=LinkDirection.SRC_TO_DST,
                score=1.0,
                status=VerificationStatus.VERIFIED,
                evidence_json={
                    "source": "telegram",
                    "kind": "reply_to_post",
                    "parent_post_id": post.parent_post_id,
                    "rationale": "Native Telegram reply relation.",
                },
                model_version="no-llm-reply-v1",
                pipeline_version=f"{settings.LINKING_PIPELINE_VERSION}-no-llm",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                constraint="uq_post_links_src_dst_type",
                set_={
                    "direction": LinkDirection.SRC_TO_DST,
                    "score": 1.0,
                    "status": VerificationStatus.VERIFIED,
                    "evidence_json": {
                        "source": "telegram",
                        "kind": "reply_to_post",
                        "parent_post_id": post.parent_post_id,
                    },
                    "model_version": "no-llm-reply-v1",
                    "pipeline_version": f"{settings.LINKING_PIPELINE_VERSION}-no-llm",
                    "updated_at": datetime.utcnow(),
                },
            )
        )
        await session.execute(stmt)
        return 1

    async def _commit_same_event_link(
        self,
        session: AsyncSession,
        *,
        src_post: Post,
        candidate: Candidate,
    ) -> int:
        # For same_event we keep a canonical order to avoid mirrored duplicate edges.
        left_id, right_id = sorted((src_post.id, candidate.post.id))

        score = max(0.0, min(1.0, candidate.embedding_similarity))
        stmt = (
            insert(PostLink)
            .values(
                src_post_id=left_id,
                dst_post_id=right_id,
                link_type=PostLinkType.SAME_EVENT,
                direction=LinkDirection.NONE,
                score=score,
                status=VerificationStatus.VERIFIED,
                evidence_json={
                    "source": "no-llm",
                    "kind": "cross_channel_embedding_match",
                    "embedding_similarity": candidate.embedding_similarity,
                    "entity_overlap": candidate.entity_overlap,
                    "time_proximity": candidate.time_proximity,
                    "time_distance_hours": candidate.time_distance_hours,
                    "anchors": {
                        "shared_entities": [],
                        "shared_places": [],
                        "shared_dates": [],
                        "shared_numbers": [],
                        "shared_tickers": [],
                    },
                    "rationale": "Cross-channel similarity and temporal proximity passed thresholds.",
                },
                model_version="no-llm-sim-v1",
                pipeline_version=f"{settings.LINKING_PIPELINE_VERSION}-no-llm",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                constraint="uq_post_links_src_dst_type",
                set_={
                    "direction": LinkDirection.NONE,
                    "score": score,
                    "status": VerificationStatus.VERIFIED,
                    "evidence_json": {
                        "source": "no-llm",
                        "kind": "cross_channel_embedding_match",
                        "embedding_similarity": candidate.embedding_similarity,
                        "entity_overlap": candidate.entity_overlap,
                        "time_proximity": candidate.time_proximity,
                        "time_distance_hours": candidate.time_distance_hours,
                    },
                    "model_version": "no-llm-sim-v1",
                    "pipeline_version": f"{settings.LINKING_PIPELINE_VERSION}-no-llm",
                    "updated_at": datetime.utcnow(),
                },
            )
        )
        await session.execute(stmt)
        return 1

    def _is_same_event_candidate(self, post: Post, candidate: Candidate) -> bool:
        if candidate.post.channel_id == post.channel_id:
            return False
        if candidate.time_distance_hours > float(self.same_event_max_hours):
            return False
        if candidate.embedding_similarity < self.same_event_min_sim:
            return False
        if candidate.entity_overlap < self.same_event_min_entity_overlap:
            return False
        return True

    async def run_for_post(self, session: AsyncSession, post: Post) -> LinkRunResponse:
        links_verified = await self._commit_reply_update_link(session, post)
        _, candidates = await retrieve_candidates(session, post=post)

        links_rejected = 0
        candidates_checked = 0
        for candidate in candidates:
            candidates_checked += 1
            if self._is_same_event_candidate(post, candidate):
                links_verified += await self._commit_same_event_link(
                    session,
                    src_post=post,
                    candidate=candidate,
                )
            else:
                links_rejected += 1

        return LinkRunResponse(
            post_id=post.id,
            links_verified=links_verified,
            links_proposed=0,
            links_rejected=links_rejected,
            candidates_checked=candidates_checked,
            verify_checked=0,
            critic_checked=0,
            queued_for_review=0,
        )
