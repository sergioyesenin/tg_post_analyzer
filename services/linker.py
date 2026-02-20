from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Event, EventPost, Post, PostFeature, PostLink
from services.linker_ai import AiLinkClassifier

LINK_DUPLICATE = "DUPLICATE"
LINK_NEAR_DUPLICATE = "NEAR_DUPLICATE"
LINK_SAME_EVENT = "SAME_EVENT"
LINK_UNRELATED = "UNRELATED"

TOKEN_RE = re.compile(r"[a-zA-Z\u0400-\u04FF0-9_]{3,}", re.UNICODE)
HASHTAG_RE = re.compile(r"#([a-zA-Z\u0400-\u04FF0-9_]+)", re.UNICODE)
MENTION_RE = re.compile(r"@([a-zA-Z0-9_]+)")
URL_RE = re.compile(r"https?://\S+")
GENERIC_REASON_RE = re.compile(
    r"(both posts|оба поста|similar topics|похожие темы|same city|один город|unusual events|необычные события)",
    re.IGNORECASE,
)

# Compact stopword set for early lexical noise filtering in candidate stage.
STOPWORDS = {
    "это", "как", "что", "где", "когда", "после", "сейчас", "сегодня", "вчера", "теперь",
    "пока", "уже", "очень", "просто", "только", "также", "другой", "свои", "снова", "были",
    "который", "которая", "которые", "через", "подписывайтесь", "подписывайся", "минске",
    "минск", "видео", "фото", "новости", "post", "posts", "this", "that", "with", "from",
    "about", "after", "today", "yesterday", "there", "their", "have", "has", "been",
}


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text).strip().lower()
    return compact


def tokenize(text: str) -> set[str]:
    return {
        t
        for t in TOKEN_RE.findall(text)
        if t not in STOPWORDS and not t.isdigit()
    }


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 0.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def extract_entities(text: str) -> dict:
    normalized = normalize_text(text)
    keywords = sorted(tokenize(normalized))[:15]
    return {
        "hashtags": sorted(set(HASHTAG_RE.findall(text))),
        "mentions": sorted(set(MENTION_RE.findall(text))),
        "urls": sorted(set(URL_RE.findall(text))),
        "keywords": keywords,
    }


def get_anchor_set(entities: dict | None) -> set[str]:
    payload = entities or {}
    anchors: set[str] = set()
    for key in ("hashtags", "mentions", "urls", "keywords"):
        values = payload.get(key, [])
        if isinstance(values, list):
            anchors.update(str(v).strip().lower() for v in values if str(v).strip())
    return anchors


def calibrate_ai_confidence(
    *,
    model_confidence: float,
    link_type: str,
    text_score: float,
    entities_score: float,
    shared_anchor_count: int,
    reason: str,
    shared_facts: list[str],
    hash_equal: bool,
) -> float:
    final_conf = max(0.0, min(1.0, model_confidence))

    if not hash_equal and shared_anchor_count == 0:
        final_conf -= 0.24
    if text_score < 0.2:
        final_conf -= 0.15
    if entities_score < 0.08:
        final_conf -= 0.1
    if GENERIC_REASON_RE.search(reason or ""):
        final_conf -= 0.2
    if len(shared_facts) < 2 and not hash_equal:
        final_conf -= 0.15

    if link_type in {"CAUSE_EFFECT", "REFUTES", "UPDATE"} and shared_anchor_count < 1 and text_score < 0.35:
        final_conf -= 0.2
    if link_type == LINK_SAME_EVENT and shared_anchor_count == 0:
        final_conf = min(final_conf, 0.74)

    return max(0.0, min(1.0, final_conf))


def is_candidate_for_ai(*, text_score: float, entities_score: float, shared_anchor_count: int, hash_equal: bool) -> bool:
    if hash_equal:
        return True
    if shared_anchor_count >= settings.LINKER_MIN_SHARED_ANCHORS:
        return True
    if text_score >= settings.LINKER_MIN_TEXT_JACCARD and entities_score >= settings.LINKER_MIN_ENTITIES_JACCARD:
        return True
    return False


def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    latin = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04FF")
    if cyr > latin:
        return "ru"
    if latin > cyr:
        return "en"
    return "unknown"


def content_hash(text_normalized: str) -> str:
    return hashlib.sha256(text_normalized.encode("utf-8")).hexdigest()


async def build_post_features(
    session: AsyncSession,
    *,
    post: Post,
    analyzer_version: str = "v1-rule-based",
) -> PostFeature:
    normalized = normalize_text(post.text)
    entities = extract_entities(post.text or "")
    lang = detect_language(normalized)
    hash_value = content_hash(normalized) if normalized else None
    tokens = sorted(tokenize(normalized))

    stmt = (
        insert(PostFeature)
        .values(
            post_id=post.id,
            text_normalized=normalized,
            content_hash=hash_value,
            embedding={"tokens": tokens},
            entities=entities,
            lang=lang,
            topic=None,
            analyzer_version=analyzer_version,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            index_elements=[PostFeature.post_id],
            set_={
                "text_normalized": normalized,
                "content_hash": hash_value,
                "embedding": {"tokens": tokens},
                "entities": entities,
                "lang": lang,
                "analyzer_version": analyzer_version,
                "updated_at": datetime.utcnow(),
            },
        )
        .returning(PostFeature.post_id)
    )
    res = await session.execute(stmt)
    post_id = res.scalar_one()
    feature = await session.get(PostFeature, post_id)
    assert feature is not None
    return feature


async def upsert_post_link(
    session: AsyncSession,
    *,
    src_post_id: int,
    dst_post_id: int,
    link_type: str,
    confidence: float,
    evidence: dict,
    model_version: str = "v1-rule-based",
) -> None:
    if src_post_id == dst_post_id:
        return
    stmt = (
        insert(PostLink)
        .values(
            src_post_id=src_post_id,
            dst_post_id=dst_post_id,
            link_type=link_type,
            confidence=confidence,
            evidence=evidence,
            model_version=model_version,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_post_links_src_dst_type",
            set_={
                "confidence": confidence,
                "evidence": evidence,
                "model_version": model_version,
            },
        )
    )
    await session.execute(stmt)


async def ensure_event_for_posts(
    session: AsyncSession,
    *,
    source_post: Post,
    related_post_ids: list[int],
    confidence: float,
) -> int:
    if not related_post_ids:
        related_post_ids = [source_post.id]

    existing_event_stmt = (
        select(EventPost.event_id)
        .where(EventPost.post_id.in_(related_post_ids))
        .limit(1)
    )
    existing_event_id = (await session.execute(existing_event_stmt)).scalar_one_or_none()
    if existing_event_id is None:
        event = Event(
            title=None,
            status="open",
            first_seen_at=source_post.date,
            last_seen_at=source_post.date,
            confidence=confidence,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(event)
        await session.flush()
        existing_event_id = event.id

    for post_id in set(related_post_ids + [source_post.id]):
        stmt = (
            insert(EventPost)
            .values(
                event_id=existing_event_id,
                post_id=post_id,
                role="context",
                confidence=confidence,
                linked_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                index_elements=[EventPost.event_id, EventPost.post_id],
                set_={
                    "confidence": confidence,
                    "linked_at": datetime.utcnow(),
                },
            )
        )
        await session.execute(stmt)

    existing_event = await session.get(Event, existing_event_id)
    if existing_event is not None:
        min_date = source_post.date
        max_date = source_post.date
        if existing_event.first_seen_at is not None:
            min_date = min(min_date, existing_event.first_seen_at)
        if existing_event.last_seen_at is not None:
            max_date = max(max_date, existing_event.last_seen_at)
        existing_event.first_seen_at = min_date
        existing_event.last_seen_at = max_date
        existing_event.confidence = max(existing_event.confidence or 0.0, confidence)
        existing_event.updated_at = datetime.utcnow()
    return existing_event_id


async def link_post_to_graph(
    session: AsyncSession,
    *,
    post: Post,
    linker_version: str = "v1-rule-based",
    lookback_days: int | None = None,
    candidate_limit: int | None = None,
) -> dict:
    lookback_days = lookback_days if lookback_days is not None else settings.LINKER_LOOKBACK_DAYS
    candidate_limit = candidate_limit if candidate_limit is not None else settings.LINKER_CANDIDATE_LIMIT

    feature = await build_post_features(session, post=post, analyzer_version=linker_version)
    source_tokens = tokenize(feature.text_normalized or "")
    source_anchors = get_anchor_set(feature.entities)

    since = post.date - timedelta(days=lookback_days)
    until = post.date + timedelta(days=lookback_days)

    # Backfill features for recent posts so candidate search is not empty
    # when post_features was introduced after posts already existed.
    missing_features_stmt = (
        select(Post)
        .outerjoin(PostFeature, PostFeature.post_id == Post.id)
        .where(
            and_(
                Post.id != post.id,
                Post.date >= since,
                Post.date <= until,
                PostFeature.post_id.is_(None),
            )
        )
        .order_by(Post.date.desc())
        .limit(candidate_limit)
    )
    missing_feature_posts = (await session.execute(missing_features_stmt)).scalars().all()
    for missing_post in missing_feature_posts:
        await build_post_features(
            session,
            post=missing_post,
            analyzer_version=linker_version,
        )

    candidates_stmt = (
        select(Post, PostFeature)
        .join(PostFeature, PostFeature.post_id == Post.id)
        .where(
            and_(
                Post.id != post.id,
                Post.date >= since,
                Post.date <= until,
                or_(PostFeature.content_hash.is_not(None), PostFeature.text_normalized.is_not(None)),
            )
        )
        .order_by(Post.date.desc())
        .limit(candidate_limit)
    )
    candidate_rows = (await session.execute(candidates_stmt)).all()

    links_created = 0
    same_event_posts: list[int] = []
    ai_checked = 0
    ai_links_created = 0
    ai_errors = 0

    ai_classifier = AiLinkClassifier() if settings.LINKER_AI_ENABLED else None

    scored_candidates: list[tuple[Post, PostFeature, float, float, bool, int]] = []

    for candidate_post, candidate_feature in candidate_rows:
        candidate_tokens = tokenize(candidate_feature.text_normalized or "")
        text_score = jaccard_similarity(source_tokens, candidate_tokens)
        candidate_anchors = get_anchor_set(candidate_feature.entities)
        entities_score = jaccard_similarity(source_anchors, candidate_anchors)
        hash_equal = bool(feature.content_hash and feature.content_hash == candidate_feature.content_hash)
        shared_anchor_count = len(source_anchors & candidate_anchors)

        scored_candidates.append((candidate_post, candidate_feature, text_score, entities_score, hash_equal, shared_anchor_count))

        link_type: str | None = None
        confidence = 0.0
        if hash_equal:
            link_type = LINK_DUPLICATE
            confidence = 0.99
        elif text_score >= 0.82:
            link_type = LINK_NEAR_DUPLICATE
            confidence = min(0.95, 0.75 + text_score * 0.2)
        elif (
            text_score >= 0.55
            and entities_score >= max(0.2, settings.LINKER_MIN_ENTITIES_JACCARD)
            and shared_anchor_count >= settings.LINKER_MIN_SHARED_ANCHORS
        ):
            link_type = LINK_SAME_EVENT
            confidence = min(0.9, 0.5 + text_score * 0.3 + entities_score * 0.2)

        if link_type is None:
            continue

        evidence = {
            "source": "rules",
            "text_jaccard": round(text_score, 4),
            "entities_jaccard": round(entities_score, 4),
            "shared_anchor_count": shared_anchor_count,
            "hash_equal": hash_equal,
        }
        await upsert_post_link(
            session,
            src_post_id=post.id,
            dst_post_id=candidate_post.id,
            link_type=link_type,
            confidence=confidence,
            evidence=evidence,
            model_version=linker_version,
        )
        links_created += 1

        if link_type in {LINK_DUPLICATE, LINK_NEAR_DUPLICATE, LINK_SAME_EVENT}:
            same_event_posts.append(candidate_post.id)

    if ai_classifier is not None and settings.LINKER_AI_MAX_CANDIDATES > 0:
        scored_candidates.sort(
            key=lambda row: (
                row[2],  # text score
                row[3],  # entities score
                row[5],  # shared anchors
                1.0 if row[4] else 0.0,  # hash equal
                1.0 if row[0].channel_id == post.channel_id else 0.0,
            ),
            reverse=True,
        )
        shortlisted = [
            row
            for row in scored_candidates
            if is_candidate_for_ai(
                text_score=row[2],
                entities_score=row[3],
                shared_anchor_count=row[5],
                hash_equal=row[4],
            )
        ][: settings.LINKER_AI_MAX_CANDIDATES]
        for candidate_post, _, text_score, entities_score, hash_equal, shared_anchor_count in shortlisted:
            ai_checked += 1
            try:
                decision = await ai_classifier.classify_pair(
                    post_a_text=post.text or "",
                    post_b_text=candidate_post.text or "",
                    post_a_channel_id=post.channel_id,
                    post_b_channel_id=candidate_post.channel_id,
                    post_a_date=post.date,
                    post_b_date=candidate_post.date,
                    text_jaccard=text_score,
                    entities_jaccard=entities_score,
                    hash_equal=hash_equal,
                    shared_anchor_count=shared_anchor_count,
                )
            except Exception:
                ai_errors += 1
                continue

            if (not decision.is_related) or decision.link_type == LINK_UNRELATED:
                continue
            final_confidence = calibrate_ai_confidence(
                model_confidence=decision.confidence,
                link_type=decision.link_type,
                text_score=text_score,
                entities_score=entities_score,
                shared_anchor_count=shared_anchor_count,
                reason=decision.reason,
                shared_facts=decision.shared_facts,
                hash_equal=hash_equal,
            )
            if final_confidence < settings.LINKER_AI_MIN_CONFIDENCE:
                continue

            evidence = {
                "source": "ai",
                "ai_reason": decision.reason,
                "shared_facts": decision.shared_facts,
                "text_jaccard": round(text_score, 4),
                "entities_jaccard": round(entities_score, 4),
                "shared_anchor_count": shared_anchor_count,
                "hash_equal": hash_equal,
                "model_confidence": round(decision.confidence, 4),
                "final_confidence": round(final_confidence, 4),
            }
            await upsert_post_link(
                session,
                src_post_id=post.id,
                dst_post_id=candidate_post.id,
                link_type=decision.link_type,
                confidence=final_confidence,
                evidence=evidence,
                model_version="v3-ai-linker-calibrated",
            )
            ai_links_created += 1
            links_created += 1
            if decision.link_type in {
                LINK_DUPLICATE,
                LINK_NEAR_DUPLICATE,
                LINK_SAME_EVENT,
                "UPDATE",
                "REFUTES",
                "CITES_SOURCE",
                "CAUSE_EFFECT",
                "TRANSLATION",
            }:
                same_event_posts.append(candidate_post.id)

    event_id: int | None = None
    if same_event_posts:
        event_id = await ensure_event_for_posts(
            session,
            source_post=post,
            related_post_ids=same_event_posts,
            confidence=0.75,
        )

    return {
        "post_id": post.id,
        "links_created": links_created,
        "ai_links_created": ai_links_created,
        "ai_checked": ai_checked,
        "ai_errors": ai_errors,
        "event_id": event_id,
        "candidates_checked": len(candidate_rows),
    }
