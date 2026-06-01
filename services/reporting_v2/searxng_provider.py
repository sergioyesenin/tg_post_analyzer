from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura


_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_]+", flags=re.UNICODE)


class SearxngRetrievalProvider:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 8.0,
        max_results: int = 6,
        fetch_pages: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.fetch_pages = fetch_pages

    async def retrieve(self, request: dict[str, Any]) -> dict[str, Any]:
        query = self._build_query(request)
        if not query:
            return {"sources": []}

        search_results = await self._search(query)
        if not search_results:
            return {"sources": []}

        sources: list[dict[str, Any]] = []

        for item in search_results[: self.max_results]:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()

            if not title or not url:
                continue

            supports = snippet

            if self.fetch_pages:
                extracted = await self._fetch_and_extract(url)
                if extracted:
                    supports = self._select_supporting_excerpt(
                        text=extracted,
                        query=query,
                        fallback=snippet,
                    )

            if not supports:
                continue

            relevance = self._score_result(title=title, snippet=supports, query=query)
            if relevance < 0.3:
                continue

            sources.append(
                {
                    "title": title[:240],
                    "source": url,
                    "tier": self._tier_for_url(url),
                    "supports": supports[:700],
                    "relevance": relevance,
                }
            )

        return {"sources": sources}

    def _build_query(self, request: dict[str, Any]) -> str:
        explicit_query = str(request.get("query") or "").strip()
        if explicit_query:
            return explicit_query
        text = " ".join(
            [
                str(request.get("event_title") or ""),
                str(request.get("post_text") or ""),
                str(request.get("root_post_text") or ""),
            ]
        )

        tokens = [token for token in _TOKEN_RE.findall(text) if len(token) >= 4]
        if not tokens:
            return ""

        # Берем первые значимые токены из события. Для новостных постов это обычно дает хороший поисковый запрос.
        query_tokens: list[str] = []
        seen: set[str] = set()

        for token in tokens:
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            query_tokens.append(token)
            if len(query_tokens) >= 12:
                break

        return " ".join(query_tokens)

    async def _search(self, query: str) -> list[dict[str, Any]]:
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "language": "ru",
            "safesearch": 0,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results")
        return results if isinstance(results, list) else []

    async def _fetch_and_extract(self, url: str) -> str:
        # Trafilatura синхронная; выносим в thread, чтобы не блокировать event loop.
        return await asyncio.to_thread(self._fetch_and_extract_sync, url)

    def _fetch_and_extract_sync(self, url: str) -> str:
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return ""

            extracted = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            return " ".join((extracted or "").split())
        except Exception:
            return ""

    def _select_supporting_excerpt(self, *, text: str, query: str, fallback: str) -> str:
        text = " ".join(text.split())
        if not text:
            return fallback

        query_terms = {token.lower() for token in _TOKEN_RE.findall(query) if len(token) >= 4}
        sentences = re.split(r"(?<=[.!?])\s+", text)

        best_sentence = ""
        best_score = 0

        for sentence in sentences[:80]:
            sentence_norm = sentence.lower()
            score = sum(1 for term in query_terms if term in sentence_norm)
            if score > best_score:
                best_score = score
                best_sentence = sentence

        if best_sentence:
            return best_sentence.strip()

        return text[:700] or fallback

    def _score_result(self, *, title: str, snippet: str, query: str) -> float:
        haystack = f"{title} {snippet}".lower()
        terms = {token.lower() for token in _TOKEN_RE.findall(query) if len(token) >= 4}
        if not terms:
            return 0.5

        hits = sum(1 for term in terms if term in haystack)
        score = hits / max(1, len(terms))
        return max(0.15, min(1.0, score))

    def _tier_for_url(self, url: str) -> str:
        host = urlparse(url).netloc.lower()

        # Tier 1: официальные источники / правовые порталы / госорганы.
        tier1_markers = (
            ".gov",
            "government",
            "pravo.by",
            "president.gov.by",
            "sovrep.gov.by",
            "house.gov.by",
            "belta.by",
        )
        if any(marker in host for marker in tier1_markers):
            return "1"

        # Tier 2: СМИ, агрегаторы, организации.
        return "2"
