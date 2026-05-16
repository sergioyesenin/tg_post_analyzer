from __future__ import annotations

import hashlib
import inspect
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+", flags=re.UNICODE)
_NUMBER_RE = re.compile(r"\b\d+[\d.,]*\b")

_CACHE: dict[str, tuple[datetime, dict[str, Any]]] = {}
logger = logging.getLogger(__name__)

_TIER1_DOMAINS = {
    "pravo.by",
    "president.gov.by",
    "gov.by",
    "belta.by",
    "tass.ru",
    "government.ru",
    "kremlin.ru",
}
_TIER2_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "rbc.ru",
    "interfax.ru",
    "ria.ru",
    "kommersant.ru",
}
_SOCIAL_DOMAINS = {
    "t.me",
    "telegram.me",
    "x.com",
    "twitter.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "tiktok.com",
    "facebook.com",
    "instagram.com",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _domain(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower().replace("www.", "")


def _tier_for_domain(domain: str) -> str:
    if any(domain == d or domain.endswith(f".{d}") for d in _TIER1_DOMAINS) or ".gov" in domain:
        return "1"
    if any(domain == d or domain.endswith(f".{d}") for d in _TIER2_DOMAINS):
        return "2"
    if any(domain == d or domain.endswith(f".{d}") for d in _SOCIAL_DOMAINS):
        return "3"
    return "2"


def _source_authority_score(tier: str) -> float:
    return {"1": 1.0, "2": 0.75, "3": 0.35}.get(str(tier), 0.6)


def _freshness_score(published_at: str | None, *, category: str) -> float:
    if not published_at:
        return 0.55
    try:
        dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
    except Exception:
        return 0.55
    age_days = max(0.0, (_now() - dt.astimezone(timezone.utc)).total_seconds() / 86400.0)
    if category in {"news", "politics", "economy", "crisis"}:
        if age_days <= 1:
            return 1.0
        if age_days <= 7:
            return 0.8
        if age_days <= 30:
            return 0.55
        return 0.35
    if age_days <= 30:
        return 0.9
    if age_days <= 180:
        return 0.7
    return 0.5


def _semantic_relevance_score(*, query: str, title: str, supports: str) -> float:
    q_terms = {
        t.lower()
        for t in _TOKEN_RE.findall(query)
        if len(t) >= 4 and not str(t).lower().startswith("site")
    }
    q_terms = {t for t in q_terms if t not in {"gov", "pravo", "belta", "tass", "ria", "reuters"}}
    if not q_terms:
        return 0.6
    hay = _normalize_text(f"{title} {supports}")
    hits = sum(1 for term in q_terms if term in hay)
    return max(0.0, min(1.0, hits / max(1, len(q_terms))))


def _content_quality_score(*, title: str, supports: str) -> float:
    t = _normalize_text(title)
    s = _normalize_text(supports)
    if len(t) < 8 or len(s) < 40:
        return 0.2
    if len(s) < 80:
        return 0.45
    if len(s) < 180:
        return 0.7
    return 0.9


def _core_claim_text(supports: str) -> str:
    text = _normalize_text(supports)
    sentence = re.split(r"(?<=[.!?])\s+", text)[0]
    return sentence[:240]


def _build_queries(request: Mapping[str, Any]) -> dict[str, str]:
    event_title = str(request.get("event_title") or "").strip()
    post_text = str(request.get("post_text") or request.get("root_post_text") or "").strip()
    category = str(request.get("category") or "").lower().strip()

    base_tokens = [t for t in _TOKEN_RE.findall(f"{event_title} {post_text}") if len(t) >= 4]
    uniq_tokens: list[str] = []
    seen: set[str] = set()
    for token in base_tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_tokens.append(token)
        if len(uniq_tokens) >= 10:
            break
    token_query = " ".join(uniq_tokens)

    queries = {
        "exact_event_query": (event_title or token_query).strip(),
        "entity_based_query": token_query,
        "official_source_query": f"{token_query} site:gov.by OR site:pravo.by OR site:belta.by".strip(),
        "news_source_query": f"{token_query} site:tass.ru OR site:ria.ru OR site:reuters.com".strip(),
    }
    if category in {"politics", "regulation", "economy", "crisis"}:
        queries["legal_document_query"] = f"{token_query} закон указ постановление site:pravo.by".strip()

    return {k: v for k, v in queries.items() if v}


def _cache_ttl_hours(category: str) -> int:
    c = category.lower().strip()
    if c in {"news", "politics", "economy", "crisis"}:
        return 12
    if c in {"legal", "reference", "regulation"}:
        return 24 * 14
    return 24


def _cache_key(request: Mapping[str, Any], queries: Mapping[str, str]) -> str:
    signature = {
        "kind": str(request.get("kind") or ""),
        "event_id": request.get("event_id"),
        "post_id": request.get("post_id"),
        "category": str(request.get("category") or ""),
        "queries": queries,
    }
    raw = repr(signature).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _extract_facts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for src in sources:
        supports = str(src.get("supports") or "")
        claim = _core_claim_text(supports)
        if not claim:
            continue
        nums = _NUMBER_RE.findall(supports)
        facts.append({
            "claim": claim,
            "numbers": nums,
            "source": src.get("source"),
            "tier": src.get("tier"),
            "confidence": src.get("score", 0.5),
        })
    return facts


def _detect_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    by_claim: dict[str, set[str]] = {}
    for fact in facts:
        claim = str(fact.get("claim") or "")
        claim_key = _NUMBER_RE.sub("#", claim.lower())
        claim_key = re.sub(r"\\s+", " ", claim_key).strip()
        nums = set(str(n) for n in list(fact.get("numbers") or []))
        if not claim_key or not nums:
            continue
        current = by_claim.setdefault(claim_key, set())
        current.update(nums)
    for claim, nums in by_claim.items():
        if len(nums) >= 2:
            conflicts.append(
                {
                    "claim": claim,
                    "values": sorted(nums),
                    "severity": "critical" if len(nums) >= 3 else "moderate",
                }
            )
    if not conflicts:
        all_numbers: set[str] = set()
        for fact in facts:
            all_numbers.update(str(n) for n in list(fact.get("numbers") or []))
        if len(all_numbers) >= 2:
            conflicts.append(
                {
                    "claim": "cross_source_numeric_mismatch",
                    "values": sorted(all_numbers),
                    "severity": "moderate",
                }
            )
    return conflicts


def _quality_gate(*, category: str, sources: list[dict[str, Any]], quality_score: float, conflicts: list[dict[str, Any]]) -> str:
    if not sources:
        return "failed"
    if len(sources) < 2:
        return "insufficient"
    if quality_score < 0.55:
        return "insufficient"
    if category in {"politics", "economy", "crisis", "regulation"}:
        has_tier12 = any(str(s.get("tier") or "") in {"1", "2"} for s in sources)
        if not has_tier12:
            return "insufficient"
    critical_conflict = any(str(c.get("severity") or "") == "critical" for c in conflicts)
    if critical_conflict:
        return "partial"
    return "success"


def normalize_retrieval_sources(raw_sources: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if isinstance(raw_sources, Mapping):
        if isinstance(raw_sources.get("sources"), list):
            raw_sources = raw_sources.get("sources")
        elif isinstance(raw_sources.get("results"), list):
            raw_sources = raw_sources.get("results")
        else:
            raw_sources = []

    if not isinstance(raw_sources, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_sources[:limit]:
        if not isinstance(item, Mapping):
            continue

        title = str(item.get("title") or item.get("name") or "").strip()
        source = str(item.get("source") or item.get("url") or item.get("provider") or "").strip()
        supports = str(item.get("supports") or item.get("snippet") or item.get("summary") or "").strip()
        if not title or not source or not supports or len(supports) < 30:
            continue

        domain = _domain(source)
        tier = str(item.get("tier") or _tier_for_domain(domain)).strip()
        if tier not in {"1", "2", "3"}:
            tier = _tier_for_domain(domain)
        published_at = str(item.get("published_at") or "").strip() or None

        normalized.append(
            {
                "title": title[:240],
                "source": source,
                "tier": tier,
                "supports": supports[:900],
                "relevance": float(item.get("relevance", item.get("score", 0.5)) or 0.5),
                "domain": domain,
                "published_at": published_at,
            }
        )

    return normalized


async def run_retrieval_manager(provider: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    category = str(request.get("category") or ("news" if str(request.get("kind") or "") in {"post", "event"} else "reference")).lower()
    queries = _build_queries(request)
    key = _cache_key(request, queries)
    ttl = timedelta(hours=_cache_ttl_hours(category))
    cached = _CACHE.get(key)
    if cached and (_now() - cached[0]) <= ttl:
        payload = dict(cached[1])
        payload.setdefault("diagnostics", {})["cache"] = "hit"
        return payload

    diagnostics: dict[str, Any] = {"errors": [], "queries": queries, "cache": "miss"}
    raw_results: list[dict[str, Any]] = []

    if provider is None or not queries:
        result = {
            "status": "failed",
            "quality_score": 0.0,
            "sources": [],
            "facts": [],
            "conflicts": [],
            "gaps": ["provider_unavailable" if provider is None else "query_generation_failed"],
            "diagnostics": diagnostics,
            "raw_results": [],
        }
        _CACHE[key] = (_now(), result)
        return result

    for query_name, query in queries.items():
        q_request = dict(request)
        q_request["query"] = query
        q_request["query_name"] = query_name
        try:
            if hasattr(provider, "retrieve"):
                out = provider.retrieve(q_request)
            elif callable(provider):
                out = provider(q_request)
            else:
                out = {"sources": []}
            if inspect.isawaitable(out):
                out = await out
            normalized = normalize_retrieval_sources(out, limit=20)
            for src in normalized:
                src["query_name"] = query_name
            raw_results.extend(normalized)
        except Exception as exc:
            diagnostics["errors"].append(f"{query_name}:{type(exc).__name__}:{exc}")

    # Dedup by normalized title + core claim
    grouped: dict[str, dict[str, Any]] = {}
    for src in raw_results:
        key_group = f"{_normalize_text(str(src.get('title') or ''))}::{_core_claim_text(str(src.get('supports') or ''))}"
        if not key_group.strip(":"):
            continue

        relevance = float(src.get("relevance") or 0.0)
        semantic = _semantic_relevance_score(
            query=str(queries.get(src.get("query_name"), "")),
            title=str(src.get("title") or ""),
            supports=str(src.get("supports") or ""),
        )
        authority = _source_authority_score(str(src.get("tier") or "2"))
        freshness = _freshness_score(src.get("published_at"), category=category)
        content_quality = _content_quality_score(title=str(src.get("title") or ""), supports=str(src.get("supports") or ""))
        uniqueness = 1.0
        score = (semantic * 0.35) + (authority * 0.25) + (freshness * 0.15) + (content_quality * 0.15) + (relevance * 0.10)
        scored = {
            **src,
            "semantic_relevance": round(semantic, 4),
            "source_authority": round(authority, 4),
            "freshness": round(freshness, 4),
            "content_quality": round(content_quality, 4),
            "uniqueness": round(uniqueness, 4),
            "score": round(max(0.0, min(1.0, score)), 4),
        }
        old = grouped.get(key_group)
        if old is None or float(scored["score"]) > float(old.get("score") or 0.0):
            grouped[key_group] = scored

    curated = list(grouped.values())
    removed_reasons: list[str] = []
    before_filter_count = len(curated)

    # Filtering
    after_threshold = [s for s in curated if float(s.get("semantic_relevance") or 0.0) >= 0.5 and float(s.get("score") or 0.0) >= 0.35]
    if len(after_threshold) < len(curated):
        removed_reasons.append("low_relevance")
    curated = after_threshold
    if any(float(s.get("score") or 0.0) >= 0.55 for s in curated):
        after_score_gate = [s for s in curated if float(s.get("score") or 0.0) >= 0.55]
        if len(after_score_gate) < len(curated):
            removed_reasons.append("low_score_gate")
        curated = after_score_gate

    curated.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    if len(curated) > 5:
        removed_reasons.append("top5_cap")
    curated = curated[:5]

    # Prefer tier1/2 over social when too many
    if len(curated) > 3:
        t12 = [s for s in curated if str(s.get("tier") or "") in {"1", "2"}]
        t3 = [s for s in curated if str(s.get("tier") or "") == "3"]
        prioritized = (t12 + t3)[:5]
        if len(prioritized) < len(curated):
            removed_reasons.append("tier_priority")
        curated = prioritized
    if len(curated) > 3:
        removed_reasons.append("top3_cap")
    curated = curated[:3] if len(curated) > 3 else curated
    if before_filter_count != len(curated):
        logger.info(
            "retrieval sources filtered",
            extra={
                "post_id": request.get("post_id"),
                "event_id": request.get("event_id"),
                "before": before_filter_count,
                "after": len(curated),
                "removed_reasons": sorted(set(removed_reasons)) or ["filtered"],
            },
        )

    facts = _extract_facts(curated)
    conflicts = _detect_conflicts(facts)

    quality_score = round(sum(float(s.get("score") or 0.0) for s in curated) / max(1, len(curated)), 4) if curated else 0.0
    status = _quality_gate(category=category, sources=curated, quality_score=quality_score, conflicts=conflicts)

    gaps: list[str] = []
    if len(curated) < 2:
        gaps.append("insufficient_source_count")
    if category in {"politics", "economy", "crisis", "regulation"} and not any(str(s.get("tier") or "") in {"1", "2"} for s in curated):
        gaps.append("missing_tier1_or_tier2")
    if conflicts:
        gaps.append("conflicting_claims_detected")
    if diagnostics["errors"]:
        gaps.append("provider_engine_errors")

    result = {
        "status": status,
        "quality_score": quality_score,
        "sources": curated,
        "facts": facts,
        "conflicts": conflicts,
        "gaps": gaps,
        "diagnostics": diagnostics,
        "raw_results": raw_results,
    }

    _CACHE[key] = (_now(), result)
    return result


async def run_retrieval_provider(provider: Any, request: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = await run_retrieval_manager(provider, request)
    return list(result.get("sources") or [])
