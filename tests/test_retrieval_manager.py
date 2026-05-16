from __future__ import annotations

import asyncio

from services.reporting_v2 import retrieval as retrieval_module


def test_query_builder_generates_multiple_queries() -> None:
    retrieval_module._CACHE.clear()
    queries = retrieval_module._build_queries(
        {
            "event_title": "president signed decree on fines",
            "post_text": "new fines become effective on june 1",
            "category": "politics",
        }
    )
    assert "exact_event_query" in queries
    assert "entity_based_query" in queries
    assert "official_source_query" in queries
    assert "news_source_query" in queries
    assert "legal_document_query" in queries


def test_retrieval_filters_low_relevance_sources() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, _request):
            return {
                "sources": [
                    {"title": "ok", "source": "https://belta.by/a", "supports": "x" * 120, "relevance": 0.95, "tier": "1"},
                    {"title": "bad", "source": "https://foo.bar/b", "supports": "x" * 120, "relevance": 0.2, "tier": "2"},
                ]
            }

    result = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), {"event_title": "a", "post_text": "b"}))
    assert all(float(item["semantic_relevance"]) >= 0.5 for item in result["sources"])


def test_retrieval_deduplicates_social_reposts() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, _request):
            return {
                "sources": [
                    {"title": "news", "source": "https://t.me/x1", "supports": "same claim fine 100 rubles.", "relevance": 0.8, "tier": "3"},
                    {"title": "news", "source": "https://vk.com/x2", "supports": "same claim fine 100 rubles.", "relevance": 0.7, "tier": "3"},
                ]
            }

    result = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), {"event_title": "fine", "post_text": "fine"}))
    assert len(result["sources"]) <= 1


def test_retrieval_prefers_tier1_over_social_sources() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, _request):
            return {
                "sources": [
                    {"title": "gov release", "source": "https://pravo.by/doc", "supports": "decree enters into force tomorrow." * 4, "relevance": 0.8},
                    {"title": "repost", "source": "https://t.me/some", "supports": "decree enters into force tomorrow." * 4, "relevance": 0.95},
                ]
            }

    result = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), {"event_title": "decree", "post_text": "enters force"}))
    assert any(src["tier"] in {"1", "2"} for src in result["sources"])


def test_retrieval_quality_gate_success() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, request):
            q = str(request.get("query_name") or "")
            if q == "official_source_query":
                return {
                    "sources": [
                        {
                            "title": "Official release",
                            "source": "https://pravo.by/a",
                            "supports": "Official text states a 100-ruble fine starts June 1 and includes legal appeal details." * 2,
                            "relevance": 0.9,
                        }
                    ]
                }
            return {
                "sources": [
                    {
                        "title": "Media report",
                        "source": "https://reuters.com/a",
                        "supports": "News report confirms a 100-ruble fine starts June 1 with agency commentary." * 2,
                        "relevance": 0.85,
                    }
                ]
            }

    result = asyncio.run(
        retrieval_module.run_retrieval_manager(
            _Provider(),
            {"event_title": "fine starts june", "post_text": "policy update", "category": "politics"},
        )
    )
    assert result["status"] == "success"


def test_retrieval_quality_gate_insufficient_when_only_social_sources() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, _request):
            return {
                "sources": [
                    {"title": "post", "source": "https://t.me/a", "supports": "fine 100 rubles starts june 1." * 4, "relevance": 0.9},
                    {"title": "post2", "source": "https://vk.com/b", "supports": "fine 100 rubles starts june 1." * 4, "relevance": 0.9},
                ]
            }

    result = asyncio.run(
        retrieval_module.run_retrieval_manager(
            _Provider(),
            {"event_title": "fine", "post_text": "starts force", "category": "politics"},
        )
    )
    assert result["status"] in {"insufficient", "partial"}


def test_retrieval_detects_conflicting_numbers() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, request):
            q = str(request.get("query_name") or "")
            if q == "official_source_query":
                return {
                    "sources": [
                        {
                            "title": "A",
                            "source": "https://pravo.by/a",
                            "supports": "Official document says the fine equals 100 rubles and starts in June.",
                            "relevance": 0.9,
                        }
                    ]
                }
            return {
                "sources": [
                    {
                        "title": "B",
                        "source": "https://reuters.com/b",
                        "supports": "Media report says the fine equals 200 rubles and starts in summer.",
                        "relevance": 0.9,
                    }
                ]
            }

    result = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), {"event_title": "fine", "post_text": "rubles"}))
    assert result["conflicts"]


def test_retrieval_cache_reuses_recent_results() -> None:
    retrieval_module._CACHE.clear()
    calls = {"n": 0}

    class _Provider:
        async def retrieve(self, _request):
            calls["n"] += 1
            return {"sources": [{"title": "A", "source": "https://pravo.by/a", "supports": "fine 100 rubles." * 4, "relevance": 0.9}]}

    req = {"event_title": "fine", "post_text": "rubles", "category": "politics"}
    _ = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), req))
    _ = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), req))
    assert calls["n"] >= 1
    assert calls["n"] < 6


def test_searx_engine_errors_do_not_crash_pipeline() -> None:
    retrieval_module._CACHE.clear()

    class _Provider:
        async def retrieve(self, request):
            if request.get("query_name") == "official_source_query":
                raise RuntimeError("engine_429")
            return {"sources": [{"title": "A", "source": "https://reuters.com/a", "supports": "event context confirmed." * 4, "relevance": 0.8}]}

    result = asyncio.run(retrieval_module.run_retrieval_manager(_Provider(), {"event_title": "event", "post_text": "confirmed"}))
    assert isinstance(result, dict)
    assert "status" in result
    assert "diagnostics" in result
