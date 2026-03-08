import os

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("TG_API_ID", "12345")
os.environ.setdefault("TG_API_HASH", "hash")
os.environ.setdefault("DB_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics")
os.environ.setdefault("APP_TZ", "UTC")
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret")

from services.keyword_graph import build_search_lemmas
from schemas.keyword_graph import GraphBuildRequest


def test_build_search_lemmas_deduplicates_and_filters_short_tokens():
    out = build_search_lemmas("alpha alpha beta")
    assert "alpha" in out
    assert "beta" in out
    assert len(out) == len(set(out))


def test_build_search_lemmas_handles_empty_text():
    assert build_search_lemmas("") == []


def test_graph_build_defaults_to_transient_mode():
    payload = GraphBuildRequest(post_ids=[1, 2, 3])
    assert payload.graph_mode == "transient"
