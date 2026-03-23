from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from math import sqrt

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Post, PostFact
from services.linking.entity_dictionaries import ENTITY_NOISE_WORDS, ORG_HINTS, PLACE_HINTS
from services.linking.embeddings import EmbeddingProvider

try:
    from natasha import Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter

    _NATASHA_AVAILABLE = True
except Exception:
    _NATASHA_AVAILABLE = False

ENTITY_RE = re.compile(r"[A-Z\u0410-\u042F][a-z\u0430-\u044f0-9_-]{2,}", re.UNICODE)
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")
HASHTAG_RE = re.compile(r"#([A-Za-z\u0410-\u042F\u0430-\u044f0-9_]{2,})", re.UNICODE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
CASHTAG_RE = re.compile(r"\$[A-Za-z\u0410-\u042F\u0430-\u044f0-9_]{1,16}", re.UNICODE)
WORD_RE = re.compile(r"[A-Za-z\u0410-\u042F\u0430-\u044F]{2,}", re.UNICODE)
CTA_LINE_RE = re.compile(
    r"(?im)^\s*(подписывайтесь|подпишись|подписаться|наш\s+канал|наш\s+чат|видео\s+от\s+подписчика|источник)\b.*$"
)
CTA_TAIL_RE = re.compile(
    r"(?is)[\n\r]+(?:подписывайтесь|подпишись|подписаться)\b.*$"
)

_segmenter = None
_morph_vocab = None
_morph_tagger = None
_ner_tagger = None
_natasha_init_failed = False

LINKING_ANALYZER_VERSION = getattr(
    settings,
    "LINKING_ANALYZER_VERSION",
    "linking-retrieval-v3-ner-ru",
)


@dataclass(slots=True)
class Candidate:
    post: Post
    facts: PostFact
    embedding_similarity: float
    entity_overlap: float
    time_proximity: float
    time_distance_hours: float


def _safe_text(text: str | None) -> str:
    return (text or "")[: settings.LINKING_MAX_TEXT_CHARS]


def _cleanup_for_entity_extraction(text: str) -> str:
    text = URL_RE.sub(" ", text)
    text = CASHTAG_RE.sub(" ", text)
    text = re.sub(r"#[A-Za-z\u0410-\u042F\u0430-\u044f0-9_]+", " ", text)
    text = CTA_LINE_RE.sub(" ", text)
    text = CTA_TAIL_RE.sub(" ", text)
    return text


def _get_natasha_components():
    global _segmenter, _morph_vocab, _morph_tagger, _ner_tagger, _natasha_init_failed
    if not _NATASHA_AVAILABLE:
        return None
    if _natasha_init_failed:
        return None
    if _segmenter is not None:
        return _segmenter, _morph_vocab, _morph_tagger, _ner_tagger

    try:
        emb = NewsEmbedding()
        _segmenter = Segmenter()
        _morph_vocab = MorphVocab()
        _morph_tagger = NewsMorphTagger(emb)
        _ner_tagger = NewsNERTagger(emb)
    except Exception:
        _natasha_init_failed = True
        return None
    return _segmenter, _morph_vocab, _morph_tagger, _ner_tagger


def _normalize_entity_value(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip(" \t\r\n.,:;!?\"'`[](){}<>«»"))


def _is_entity_noise(value: str) -> bool:
    words = [w.lower() for w in WORD_RE.findall(value)]
    if not words:
        return True
    if len(words) == 1 and words[0] in ENTITY_NOISE_WORDS:
        return True
    if all(w in ENTITY_NOISE_WORDS for w in words):
        return True
    return False


def _add_entity(target: set[str], value: str, *, lowercase: bool = False) -> None:
    normalized = _normalize_entity_value(value)
    if not normalized or _is_entity_noise(normalized):
        return
    target.add(normalized.lower() if lowercase else normalized)


def _extract_entities_with_natasha(text: str) -> tuple[list[str], list[str], list[str]]:
    components = _get_natasha_components()
    if components is None:
        return [], [], []
    segmenter, morph_vocab, morph_tagger, ner_tagger = components

    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    doc.tag_ner(ner_tagger)

    persons: set[str] = set()
    organizations: set[str] = set()
    locations: set[str] = set()
    for span in doc.spans:
        if span.type not in {"PER", "ORG", "LOC"}:
            continue
        try:
            span.normalize(morph_vocab)
            value = (span.normal or span.text or "").strip()
        except Exception:
            value = (span.text or "").strip()
        if not value:
            continue
        if span.type == "PER":
            _add_entity(persons, value)
        elif span.type == "ORG":
            _add_entity(organizations, value)
        elif span.type == "LOC":
            _add_entity(locations, value, lowercase=True)
    return sorted(persons), sorted(organizations), sorted(locations)


def _extract_entities_with_fallback(cleaned: str) -> tuple[list[str], list[str], list[str]]:
    entity_candidates = sorted(set(e.strip() for e in ENTITY_RE.findall(cleaned)))
    lowered_tokens = [tok for tok in WORD_RE.findall(cleaned.lower())]
    locations: set[str] = {tok for tok in lowered_tokens if tok in PLACE_HINTS}
    organizations: set[str] = set()
    for candidate in entity_candidates:
        lc = candidate.lower()
        if lc in ORG_HINTS or any(h in lc for h in ORG_HINTS):
            _add_entity(organizations, candidate)
            continue
        if lc in PLACE_HINTS:
            _add_entity(locations, lc, lowercase=True)
    return [], sorted(organizations), sorted(locations)


def _extract_fact_payload(text: str | None) -> tuple[dict, dict, dict, dict]:
    raw = _safe_text(text)
    cleaned = _cleanup_for_entity_extraction(raw)

    numbers = sorted(set(n for n in NUMBER_RE.findall(raw)))
    dates = sorted(set(d for d in DATE_RE.findall(raw)))
    topics = sorted(set(t.lower() for t in HASHTAG_RE.findall(raw)))

    nat_persons, nat_organizations, nat_locations = _extract_entities_with_natasha(cleaned)
    fb_persons, fb_organizations, fb_locations = _extract_entities_with_fallback(cleaned)

    persons_list = sorted(set([*nat_persons, *fb_persons]))
    organizations_list = sorted(set([*nat_organizations, *fb_organizations]))
    locations = sorted(set([*nat_locations, *fb_locations]))
    generic_entities = sorted(set([*persons_list, *organizations_list, *locations]))

    entities_json = {
        "persons": persons_list,
        "organizations": organizations_list,
        "locations": locations,
        "entities": generic_entities,
    }
    topics_json = {"topic_tags": topics}
    key_numbers_json = {"numbers": numbers}
    fingerprint_json = {
        "entity_keys": generic_entities[:12],
        "topic_keys": topics[:8],
        "date_keys": dates[:6],
    }
    return entities_json, topics_json, key_numbers_json, fingerprint_json


def _extract_embedding_vector(post: Post | None) -> list[float] | None:
    if post is None or not isinstance(post.embedding, dict):
        return None
    vec = post.embedding.get("vector")
    if not isinstance(vec, list) or not vec:
        return None
    try:
        return [float(x) for x in vec]
    except Exception:
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def _extract_entity_set(facts: PostFact) -> set[str]:
    if not isinstance(facts.entities_json, dict):
        return set()
    entities = facts.entities_json.get("entities", [])
    persons = facts.entities_json.get("persons", [])
    organizations = facts.entities_json.get("organizations", [])
    locations = facts.entities_json.get("locations", [])
    legacy_places = facts.entities_json.get("places", [])
    values = [*entities, *persons, *organizations, *locations, *legacy_places]
    return {str(v).lower() for v in values if str(v).strip()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _time_proximity(distance_hours: float, window_hours: int) -> float:
    if distance_hours <= 0:
        return 1.0
    if distance_hours >= window_hours:
        return 0.0
    return 1.0 - (distance_hours / float(window_hours))


async def upsert_post_facts(session: AsyncSession, post: Post) -> PostFact:
    entities_json, topics_json, key_numbers_json, fingerprint_json = _extract_fact_payload(post.text)

    stmt = (
        insert(PostFact)
        .values(
            post_id=post.id,
            entities_json=entities_json,
            topics_json=topics_json,
            key_numbers_json=key_numbers_json,
            fingerprint_json=fingerprint_json,
            embedding_ref=None,
        )
        .on_conflict_do_update(
            index_elements=[PostFact.post_id],
            set_={
                "entities_json": entities_json,
                "topics_json": topics_json,
                "key_numbers_json": key_numbers_json,
                "fingerprint_json": fingerprint_json,
            },
        )
    )
    await session.execute(stmt)

    normalized = _safe_text(post.text).lower()
    if (
        post.text_normalized != normalized
        or post.entities != entities_json
        or post.analyzer_version != LINKING_ANALYZER_VERSION
    ):
        await session.execute(
            Post.__table__.update()
            .where(Post.id == post.id)
            .values(
                text_normalized=normalized,
                entities=entities_json,
                analyzer_version=LINKING_ANALYZER_VERSION,
            )
        )

    facts = await session.get(PostFact, post.id)
    if facts is None:
        raise RuntimeError("PostFact upsert failed")
    return facts


async def _ensure_post_metadata(session: AsyncSession, post: Post) -> Post:
    normalized = _safe_text(post.text).lower()
    if post.text_normalized == normalized and post.analyzer_version == LINKING_ANALYZER_VERSION:
        return post

    await session.execute(
        Post.__table__.update()
        .where(Post.id == post.id)
        .values(
            text_normalized=normalized,
            analyzer_version=LINKING_ANALYZER_VERSION,
        )
    )
    refreshed = await session.get(Post, post.id)
    if refreshed is None:
        raise RuntimeError("Post metadata upsert failed")
    return refreshed


async def _ensure_embedding(
    session: AsyncSession,
    *,
    post: Post,
    provider: EmbeddingProvider,
) -> list[float] | None:
    refreshed = await _ensure_post_metadata(session, post)
    vector = _extract_embedding_vector(refreshed)
    if vector is not None:
        return vector

    vector = await provider.embed_text(post.text or "")
    if vector is None:
        return None

    payload = {
        "model": settings.LINKING_EMBED_MODEL,
        "vector": vector,
    }
    await session.execute(
        Post.__table__.update()
        .where(Post.id == post.id)
        .values(
            text_normalized=_safe_text(post.text).lower(),
            embedding=payload,
            analyzer_version=LINKING_ANALYZER_VERSION,
        )
    )
    return vector


async def prepare_post_features(
    session: AsyncSession,
    *,
    post: Post,
    provider: EmbeddingProvider | None = None,
) -> tuple[Post, PostFact, list[float] | None]:
    """
    Write-phase preparation for the source post only.
    Safe to call before read-only retrieval.
    """
    provider = provider or EmbeddingProvider()

    facts = await upsert_post_facts(session, post)
    refreshed = await session.get(Post, post.id)
    if refreshed is None:
        raise RuntimeError("Post refresh failed after facts upsert")

    vector = _extract_embedding_vector(refreshed)
    if vector is None:
        vector = await _ensure_embedding(session, post=refreshed, provider=provider)
        refreshed = await session.get(Post, post.id)
        if refreshed is None:
            raise RuntimeError("Post refresh failed after embedding update")

    return refreshed, facts, vector


async def get_or_prepare_post_features(
    session: AsyncSession,
    *,
    post: Post,
    provider: EmbeddingProvider | None = None,
) -> tuple[Post, PostFact, list[float] | None]:
    """
    Source-post helper: reuse stored features when possible, otherwise prepare them.
    """
    existing_facts = await session.get(PostFact, post.id)
    existing_vector = _extract_embedding_vector(post)
    normalized = _safe_text(post.text).lower()
    metadata_ready = (
        post.text_normalized == normalized
        and post.analyzer_version == LINKING_ANALYZER_VERSION
    )

    if existing_facts is not None and metadata_ready:
        return post, existing_facts, existing_vector

    return await prepare_post_features(session, post=post, provider=provider)


async def retrieve_candidates(
    session: AsyncSession,
    *,
    post: Post,
    top_k: int | None = None,
    src_facts: PostFact | None = None,
    src_vector: list[float] | None = None,
) -> tuple[PostFact, list[Candidate]]:
    """
    Read-only retrieval.
    Does not update candidate posts and does not call embedding provider.
    """
    top_k = top_k or settings.LINKING_TOP_K
    prefilter_limit = max(top_k * settings.LINKING_PREFILTER_MULTIPLIER, top_k)

    if src_facts is None:
        src_facts = await session.get(PostFact, post.id)
        if src_facts is None:
            raise RuntimeError(f"Source PostFact missing for post_id={post.id}")

    if src_vector is None:
        src_vector = _extract_embedding_vector(post)

    src_entities = _extract_entity_set(src_facts)

    window = timedelta(hours=settings.LINKING_RELATED_TIME_WINDOW_HOURS)
    from_dt = post.date - window
    to_dt = post.date + window

    stmt = (
        select(Post, PostFact)
        .join(PostFact, PostFact.post_id == Post.id)
        .where(
            and_(
                Post.id != post.id,
                Post.date >= from_dt,
                Post.date <= to_dt,
            )
        )
        .order_by(Post.id.asc())
        .limit(prefilter_limit)
    )
    rows = (await session.execute(stmt)).all()

    scored: list[Candidate] = []
    for candidate_post, candidate_facts in rows:
        entity_overlap = _jaccard(src_entities, _extract_entity_set(candidate_facts))
        distance_h = abs((candidate_post.date - post.date).total_seconds()) / 3600.0
        time_prox = _time_proximity(distance_h, settings.LINKING_RELATED_TIME_WINDOW_HOURS)

        cand_vector = _extract_embedding_vector(candidate_post)
        if src_vector is not None and cand_vector is not None:
            embedding_similarity = _cosine_similarity(src_vector, cand_vector)
        else:
            embedding_similarity = entity_overlap

        if embedding_similarity <= settings.LINKING_CANDIDATE_MIN_EMBED_SIM:
            continue
        if (
            embedding_similarity < settings.LINKING_EMBED_MIN_SIM
            and entity_overlap < settings.LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN
        ):
            continue

        scored.append(
            Candidate(
                post=candidate_post,
                facts=candidate_facts,
                embedding_similarity=embedding_similarity,
                entity_overlap=entity_overlap,
                time_proximity=time_prox,
                time_distance_hours=distance_h,
            )
        )

    scored.sort(
        key=lambda c: (c.embedding_similarity, c.entity_overlap, c.time_proximity),
        reverse=True,
    )
    return src_facts, scored[:top_k]