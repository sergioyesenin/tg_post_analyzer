from __future__ import annotations

import inspect
from typing import Any, Mapping


def normalize_retrieval_sources(raw_sources: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    """Normalize provider output into RetrievalSourceEvidence-compatible dicts.

    Accepted provider shapes:
    - list[dict]
    - {"sources": list[dict]}
    - {"results": list[dict]}
    """
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
        tier = str(item.get("tier") or "2").strip()

        try:
            relevance = float(item.get("relevance", item.get("score", 0.5)))
        except (TypeError, ValueError):
            relevance = 0.5

        relevance = max(0.0, min(1.0, relevance))

        if tier not in {"1", "2", "3"}:
            tier = "2"

        if not title or not source or not supports:
            continue

        normalized.append(
            {
                "title": title,
                "source": source,
                "tier": tier,
                "supports": supports,
                "relevance": relevance,
            }
        )

    return normalized


async def run_retrieval_provider(provider: Any, request: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Call an injected retrieval provider and normalize its evidence.

    The provider may be:
    - an async/sync callable accepting request dict;
    - an object with async/sync .retrieve(request).
    """
    if provider is None:
        return []

    if hasattr(provider, "retrieve"):
        result = provider.retrieve(dict(request))
    elif callable(provider):
        result = provider(dict(request))
    else:
        return []

    if inspect.isawaitable(result):
        result = await result

    return normalize_retrieval_sources(result)