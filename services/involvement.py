from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping


LONG_COMMENT_MIN_LENGTH = 100


def normalize_non_negative_number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(normalized) or normalized <= 0:
        return 0.0
    return normalized


def normalize_non_negative_int(value: Any) -> int:
    return max(0, int(normalize_non_negative_number(value)))


def build_commenter_key(author_id: Any, author_username: Any) -> str | None:
    author_id_value = normalize_non_negative_int(author_id)
    if author_id_value > 0:
        return f"id:{author_id_value}"
    if isinstance(author_username, str):
        normalized_username = author_username.strip().lower()
        if normalized_username:
            return f"u:{normalized_username}"
    return None


def extract_total_reactions_count(reactions_payload: Any) -> int:
    if not isinstance(reactions_payload, dict):
        return 0

    post_reactions = reactions_payload.get("post_reactions")
    if not isinstance(post_reactions, dict):
        return 0

    total = 0
    for item in post_reactions.get("results", []) or []:
        if not isinstance(item, dict):
            continue
        total += normalize_non_negative_int(item.get("count"))
    return total


def is_long_comment_text(text: Any, *, min_length: int = LONG_COMMENT_MIN_LENGTH) -> bool:
    if not isinstance(text, str):
        return False
    collapsed = " ".join(text.split())
    if not collapsed:
        return False
    return len(collapsed) >= max(1, int(min_length))


def count_long_comments(comment_texts: list[Any] | tuple[Any, ...] | None, *, min_length: int = LONG_COMMENT_MIN_LENGTH) -> int:
    if not comment_texts:
        return 0
    return sum(1 for text in comment_texts if is_long_comment_text(text, min_length=min_length))


def count_unique_commenters(comment_rows: Iterable[tuple[Any, Any] | Mapping[str, Any]]) -> int:
    commenters: set[str] = set()
    for row in comment_rows:
        if isinstance(row, Mapping):
            commenter_key = build_commenter_key(row.get("author_id"), row.get("author_username"))
        else:
            author_id, author_username = row
            commenter_key = build_commenter_key(author_id, author_username)
        if commenter_key is not None:
            commenters.add(commenter_key)
    return len(commenters)


def compute_comment_metrics(
    comment_rows: Iterable[tuple[Any, Any, Any] | Mapping[str, Any]],
    *,
    min_length: int = LONG_COMMENT_MIN_LENGTH,
) -> tuple[int, int]:
    normalized_rows: list[tuple[Any, Any, Any]] = []
    for row in comment_rows:
        if isinstance(row, Mapping):
            normalized_rows.append((row.get("author_id"), row.get("author_username"), row.get("text")))
        else:
            author_id, author_username, text = row
            normalized_rows.append((author_id, author_username, text))
    commenters = count_unique_commenters((author_id, author_username) for author_id, author_username, _text in normalized_rows)
    long_comments = count_long_comments([text for _author_id, _author_username, text in normalized_rows], min_length=min_length)
    return commenters, long_comments


def compute_comment_metrics_by_post_id(
    comment_rows: Iterable[tuple[Any, Any, Any, Any] | Mapping[str, Any]],
    *,
    min_length: int = LONG_COMMENT_MIN_LENGTH,
) -> dict[int, tuple[int, int]]:
    grouped_rows: dict[int, list[tuple[Any, Any, Any]]] = defaultdict(list)
    for row in comment_rows:
        if isinstance(row, Mapping):
            post_id = normalize_non_negative_int(row.get("post_id"))
            author_id = row.get("author_id")
            author_username = row.get("author_username")
            text = row.get("text")
        else:
            post_id, author_id, author_username, text = row
            post_id = normalize_non_negative_int(post_id)
        if post_id <= 0:
            continue
        grouped_rows[post_id].append((author_id, author_username, text))

    return {
        post_id: compute_comment_metrics(rows, min_length=min_length)
        for post_id, rows in grouped_rows.items()
    }


def compute_long_comments_ratio(long_comments: Any, comments_count: Any) -> float:
    comments = normalize_non_negative_number(comments_count)
    if comments <= 0:
        return 0.0
    ratio = normalize_non_negative_number(long_comments) / comments
    return min(1.0, max(0.0, ratio))


def compute_involvement(
    *,
    views: Any,
    comments_count: Any,
    commenters: Any,
    long_comments: Any,
    reactions_payload: Any,
) -> float:
    views_value = normalize_non_negative_number(views)
    comments_value = normalize_non_negative_number(comments_count)
    commenters_value = normalize_non_negative_number(commenters)

    if views_value <= 0 or comments_value <= 0 or commenters_value <= 0:
        return 0.0

    reactions_value = float(extract_total_reactions_count(reactions_payload))
    long_comments_ratio = compute_long_comments_ratio(long_comments, comments_value)

    return (
        ((reactions_value + 3.0 * comments_value) / views_value)
        * (1.0 + 0.2 * long_comments_ratio)
        * math.log(1.0 + (comments_value / commenters_value))
    )
