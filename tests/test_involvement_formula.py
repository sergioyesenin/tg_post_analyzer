from __future__ import annotations

import math

from services.involvement import (
    LONG_COMMENT_MIN_LENGTH,
    compute_involvement,
    compute_long_comments_ratio,
    count_long_comments,
    extract_total_reactions_count,
    is_long_comment_text,
    normalize_non_negative_int,
    normalize_non_negative_number,
)


def test_compute_involvement_happy_path_matches_manual_formula():
    payload = {
        "post_reactions": {
            "results": [
                {"reaction": "like", "count": 10},
                {"reaction": "fire", "count": 5},
            ]
        }
    }

    expected = ((15 + 3 * 20) / 1000) * (1 + 0.2 * (4 / 20)) * math.log(1 + 20 / 5)

    result = compute_involvement(
        views=1000,
        comments_count=20,
        commenters=5,
        long_comments=4,
        reactions_payload=payload,
    )

    assert result == expected


def test_compute_involvement_returns_zero_when_views_is_zero():
    result = compute_involvement(
        views=0,
        comments_count=10,
        commenters=3,
        long_comments=2,
        reactions_payload={"post_reactions": {"results": [{"count": 7}]}},
    )

    assert result == 0.0


def test_compute_involvement_returns_zero_when_comments_count_is_zero():
    result = compute_involvement(
        views=100,
        comments_count=0,
        commenters=3,
        long_comments=2,
        reactions_payload={"post_reactions": {"results": [{"count": 7}]}},
    )

    assert result == 0.0


def test_compute_involvement_returns_zero_when_commenters_is_zero():
    result = compute_involvement(
        views=100,
        comments_count=10,
        commenters=0,
        long_comments=2,
        reactions_payload={"post_reactions": {"results": [{"count": 7}]}},
    )

    assert result == 0.0


def test_extract_total_reactions_count_handles_malformed_and_null_payloads():
    assert extract_total_reactions_count(None) == 0
    assert extract_total_reactions_count({}) == 0
    assert extract_total_reactions_count({"post_reactions": None}) == 0
    assert extract_total_reactions_count({"post_reactions": {"results": None}}) == 0
    assert extract_total_reactions_count({"post_reactions": {"results": ["bad", {"count": None}, {"count": "x"}]}}) == 0
    assert extract_total_reactions_count({"post_reactions": {"results": [{"count": 3}, {"count": "4"}]}}) == 7


def test_long_comment_threshold_behavior_is_deterministic():
    exact = "x" * LONG_COMMENT_MIN_LENGTH
    short = "x" * (LONG_COMMENT_MIN_LENGTH - 1)

    assert is_long_comment_text(exact)
    assert not is_long_comment_text(short)
    assert count_long_comments([short, exact, exact + " more"]) == 2


def test_normalization_clamps_negative_values_to_zero():
    assert normalize_non_negative_number(-1) == 0.0
    assert normalize_non_negative_number(float("-inf")) == 0.0
    assert normalize_non_negative_number("bad") == 0.0
    assert normalize_non_negative_int(-4) == 0
    assert extract_total_reactions_count({"post_reactions": {"results": [{"count": -3}, {"count": 2}]}}) == 2

    result = compute_involvement(
        views=-100,
        comments_count=5,
        commenters=2,
        long_comments=-9,
        reactions_payload={"post_reactions": {"results": [{"count": -5}]}},
    )

    assert result == 0.0


def test_compute_long_comments_ratio_clamps_values_above_one():
    assert compute_long_comments_ratio(9, 3) == 1.0
    assert compute_long_comments_ratio(3, 3) == 1.0
    assert compute_long_comments_ratio(1, 4) == 0.25


def test_empty_or_whitespace_comments_are_not_long_comments():
    assert not is_long_comment_text("")
    assert not is_long_comment_text("   \n\t  ")
    assert count_long_comments(["", "   \n\t  ", None]) == 0
