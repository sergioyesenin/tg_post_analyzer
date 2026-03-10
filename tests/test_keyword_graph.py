import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
os.environ.setdefault("TG_API_ID", "12345")
os.environ.setdefault("TG_API_HASH", "hash")
os.environ.setdefault("DB_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tg_analytics")
os.environ.setdefault("APP_TZ", "UTC")
os.environ.setdefault("AUTH_JWT_SECRET", "A_strong_test_secret_value_2026!XYZ")

from services.keyword_graph import (
    _collect_transient_candidate_pairs,
    _select_transient_node_ids,
    build_search_lemmas,
)
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


def test_graph_build_has_transient_limits_defaults():
    payload = GraphBuildRequest(post_ids=[1, 2, 3])
    assert payload.transient_max_nodes == 300
    assert payload.transient_max_edges == 1200
    assert payload.transient_max_candidates_per_node == 120
    assert payload.transient_timeout_ms == 2500


def test_select_transient_node_ids_enforces_max_nodes_with_seed_priority():
    now = datetime.now(timezone.utc)
    post_by_id = {
        1: SimpleNamespace(id=1, date=now - timedelta(hours=1)),
        2: SimpleNamespace(id=2, date=now - timedelta(hours=2)),
        3: SimpleNamespace(id=3, date=now - timedelta(hours=3)),
        4: SimpleNamespace(id=4, date=now - timedelta(hours=4)),
    }
    node_sources = {
        1: "seed",
        2: "seed",
        3: "neighbor",
        4: "neighbor",
    }

    selected_ids, truncated = _select_transient_node_ids(
        post_by_id=post_by_id,
        node_sources=node_sources,
        max_nodes=2,
    )

    assert truncated is True
    assert selected_ids == [1, 2]


def test_collect_transient_candidate_pairs_avoids_full_pairwise_on_sparse_lemmas():
    now = datetime.now(timezone.utc)
    post_by_id = {
        idx: SimpleNamespace(id=idx, date=now + timedelta(minutes=idx))
        for idx in range(1, 51)
    }
    lemma_sets = {idx: {f"token_{idx}"} for idx in range(1, 51)}
    post_ids = list(post_by_id.keys())

    pairs, stats = _collect_transient_candidate_pairs(
        post_ids=post_ids,
        post_by_id=post_by_id,
        lemma_sets=lemma_sets,
        max_time_distance_hours=48,
        max_candidates_per_node=100,
    )

    assert pairs == []
    assert stats["pairs_generated"] == 0
    assert len(pairs) < (len(post_ids) * (len(post_ids) - 1)) // 2
