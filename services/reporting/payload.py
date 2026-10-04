"""Payload enrichment для публичного post_report_v2.

Здесь только чистые преобразования payload-словарей и подмешивание
данных, уже загруженных в Post и comment_rows. Никаких обращений
к БД и к внешним сервисам.
"""
from __future__ import annotations

from typing import Any

from db.models import Post
from services.reporting.mapping import (
    _canonicalize_multi_agent_trace,
    _clean_list_text,
    _share_to_percent,
)


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_reaction_items(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    items: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        reaction_obj = item.get("reaction")
        label = None
        if isinstance(reaction_obj, dict):
            label = _clean_list_text(reaction_obj.get("emoticon") or reaction_obj.get("title") or reaction_obj.get("_"))
        if not label:
            label = _clean_list_text(item.get("reaction_type"))
        if not label:
            continue
        items.append({"label": label, "count": _safe_int(item.get("count"))})
    return items


def _summarize_reaction_items(items: list[dict], *, limit: int = 5) -> dict:
    total_count = sum(_safe_int(item.get("count")) for item in items)
    ordered = sorted(items, key=lambda item: (-_safe_int(item.get("count")), str(item.get("label") or "")))
    return {
        "total_count": total_count,
        "distinct_count": len([item for item in ordered if _safe_int(item.get("count")) > 0]),
        "top_reactions": [
            {
                "label": str(item.get("label") or ""),
                "count": _safe_int(item.get("count")),
                "share": round((_safe_int(item.get("count")) / total_count), 4) if total_count > 0 else 0.0,
            }
            for item in ordered[:limit]
        ],
    }


def _post_reactions_enrichment(*, post: Post, comment_rows: list[tuple]) -> dict:
    post_payload = post.reactions_json if isinstance(post.reactions_json, dict) else {}
    comment_meta = post_payload.get("comment_reactions") if isinstance(post_payload, dict) else {}
    post_reactions = _summarize_reaction_items(
        _extract_reaction_items(post_payload.get("post_reactions") if isinstance(post_payload, dict) else None)
    )
    comment_reactions = _summarize_reaction_items(
        [
            item
            for _tg_message_id, _parent_tg_message_id, _thread_root_tg_message_id, _depth, _date, _text, reactions_json in comment_rows
            for item in _extract_reaction_items(reactions_json if isinstance(reactions_json, dict) else None)
        ]
    )
    expected_comments = max(
        _safe_int(post.comments_count),
        len(comment_rows),
        _safe_int(comment_meta.get("comments_scanned") if isinstance(comment_meta, dict) else 0),
    )
    comments_scanned = _safe_int(comment_meta.get("comments_scanned") if isinstance(comment_meta, dict) else 0)
    is_complete = bool(post_payload.get("is_complete")) if isinstance(post_payload, dict) else False
    comment_status = str(comment_meta.get("status") or "") if isinstance(comment_meta, dict) else ""
    factor = 1.0 if is_complete else 0.0
    if expected_comments > 0 and comments_scanned > 0:
        factor = max(factor, min(1.0, comments_scanned / expected_comments))
    if comment_status == "no_reactions":
        factor = 1.0
    elif comment_status == "partial":
        factor = min(factor, 0.7) if factor > 0 else 0.5
    elif comment_status == "unavailable":
        factor = min(factor, 0.35) if factor > 0 else 0.2
    return {
        "post_reactions": post_reactions,
        "comment_reactions": comment_reactions,
        "reactions_coverage": {
            "source": post_payload.get("source") if isinstance(post_payload, dict) else None,
            "collected_at": post_payload.get("collected_at") if isinstance(post_payload, dict) else None,
            "is_complete": is_complete,
            "factor": round(max(0.0, min(1.0, factor)), 4),
            "comment_status": comment_status or None,
            "comments_scanned": comments_scanned,
            "comments_with_visible_reactions": _safe_int(comment_meta.get("comments_with_visible_reactions") if isinstance(comment_meta, dict) else 0),
            "expected_comments": expected_comments,
        },
    }


def _build_audience_stance(payload: dict) -> dict:
    sentiment = payload.get("sentiment") or payload.get("overall_sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    positive = _safe_float(distribution.get("positive"))
    negative = _safe_float(distribution.get("negative"))
    neutral = _safe_float(distribution.get("neutral"))

    positive_reaction_count = 0
    critical_reaction_count = 0
    ambiguous_reaction_count = 0
    positive_reaction_labels = {"👍", "❤", "❤️", "🔥", "👏", "🙏", "😃", "👌", "💯"}
    critical_reaction_labels = {"👎", "🤬", "😡", "💩", "🤮", "😢", "😭"}
    ambiguous_reaction_labels = {"🤣", "😂", "😆", "😹"}

    for source_payload in (payload.get("post_reactions") or {}, payload.get("comment_reactions") or {}):
        for item in list(source_payload.get("top_reactions") or []):
            label = str(item.get("label") or "")
            count = _safe_int(item.get("count"))
            if label in positive_reaction_labels:
                positive_reaction_count += count
            elif label in critical_reaction_labels:
                critical_reaction_count += count
            elif label in ambiguous_reaction_labels:
                ambiguous_reaction_count += count

    multi_agent = _canonicalize_multi_agent_trace(payload)
    public_opinion = (((multi_agent.get("steps") or {}).get("public_opinion") or {}) if isinstance(multi_agent, dict) else {})
    discussion_state = str(public_opinion.get("discussion_state") or "").strip().lower()
    data_status = str(public_opinion.get("data_status") or "").strip().lower()
    comment_count = _safe_int(payload.get("comment_count"))

    dominant_reactions = public_opinion.get("dominant_reactions")
    dominant_texts: list[str] = []
    if isinstance(dominant_reactions, list):
        for item in dominant_reactions:
            if isinstance(item, dict):
                text = _clean_list_text(item.get("text"))
            elif isinstance(item, str):
                text = _clean_list_text(item)
            else:
                text = None
            if text:
                dominant_texts.append(text.lower())

    critical_markers = ("скеп", "сарказ", "недовер", "крит", "насмеш", "сомнен", "опасен", "штраф", "налог")
    supportive_markers = ("поддерж", "одобр", "довер", "соглас")
    semantic_critical = any(any(marker in text for marker in critical_markers) for text in dominant_texts)
    semantic_supportive = any(any(marker in text for marker in supportive_markers) for text in dominant_texts)

    if max(positive, negative) < 0.2 and neutral >= 0.6:
        label = "neutral"
    elif abs(positive - negative) <= 0.15 and positive >= 0.2 and negative >= 0.2:
        label = "mixed"
    elif positive > negative:
        label = "supportive"
    elif negative > positive:
        label = "critical"
    else:
        label = "unclear"

    if positive_reaction_count > critical_reaction_count * 1.5 and positive_reaction_count >= 3:
        label = "supportive"
    elif critical_reaction_count > positive_reaction_count * 1.5 and critical_reaction_count >= 3:
        label = "critical"

    comments_semantically_strong = comment_count >= 5 and data_status not in {"weak_signal", "insufficient"}
    if semantic_critical or discussion_state in {"conflicted", "noisy"}:
        if label == "supportive":
            label = "mixed" if positive_reaction_count > 0 else "critical"
        if comments_semantically_strong:
            label = "critical" if critical_reaction_count >= positive_reaction_count else "mixed"

    if ambiguous_reaction_count > 0 and positive_reaction_count == 0 and critical_reaction_count == 0 and not semantic_supportive:
        label = "mixed" if comments_semantically_strong else "unclear"

    if positive_reaction_count > 0 and semantic_critical:
        label = "mixed" if positive_reaction_count >= critical_reaction_count else "critical"

    if semantic_supportive and not semantic_critical and positive_reaction_count > 0:
        label = "supportive"

    coverage_factor = _safe_float((payload.get("reactions_coverage") or {}).get("factor"))
    confidence = "high" if coverage_factor >= 0.85 else "medium" if coverage_factor >= 0.45 else "low"
    if semantic_critical and positive_reaction_count > 0:
        confidence = "medium"
    if comments_semantically_strong and label in {"mixed", "critical"} and confidence == "low":
        confidence = "medium"

    return {
        "label": label,
        "confidence": confidence,
        "reason": (
            f"Тональность: позитив {_share_to_percent(positive)}, негатив {_share_to_percent(negative)}, нейтрально {_share_to_percent(neutral)}. "
            f"Reactions: positive={positive_reaction_count}, critical={critical_reaction_count}, ambiguous_laugh={ambiguous_reaction_count}. "
            f"Public opinion: discussion_state={discussion_state or 'unknown'}, semantic_critical={semantic_critical}."
        ),
    }


def _enrich_post_report_payload(*, payload: dict, post: Post, comment_rows: list[tuple]) -> dict:
    enriched = dict(payload)
    reactions = _post_reactions_enrichment(post=post, comment_rows=comment_rows)
    enriched["post_reactions"] = reactions["post_reactions"]
    enriched["comment_reactions"] = reactions["comment_reactions"]
    enriched["reactions_coverage"] = reactions["reactions_coverage"]
    enriched["audience_stance"] = _build_audience_stance(enriched)
    meta = dict(enriched.get("meta") or {})
    meta["coverage_factor"] = reactions["reactions_coverage"]["factor"]
    enriched["meta"] = meta
    return enriched


def _aggregate_child_coverage(payloads: list[dict]) -> tuple[dict, dict]:
    if not payloads:
        return (
            {
                "source": "child_reports",
                "collected_at": None,
                "is_complete": False,
                "factor": 0.0,
                "comment_status": None,
                "comments_scanned": 0,
                "comments_with_visible_reactions": 0,
                "expected_comments": 0,
            },
            {
                "label": "unclear",
                "confidence": "low",
                "reason": "Недостаточно дочерних отчетов для оценки позиции аудитории.",
            },
        )
    factor = round(sum(_safe_float((item.get("reactions_coverage") or {}).get("factor")) for item in payloads) / len(payloads), 4)
    stance_counts = {"supportive": 0, "critical": 0, "mixed": 0, "neutral": 0, "unclear": 0}
    for item in payloads:
        stance_counts[str((item.get("audience_stance") or {}).get("label") or "unclear")] += 1
    label = max(stance_counts.items(), key=lambda pair: pair[1])[0]
    confidence = "high" if factor >= 0.85 else "medium" if factor >= 0.45 else "low"
    return (
        {
            "source": "child_reports",
            "collected_at": None,
            "is_complete": factor >= 0.99,
            "factor": factor,
            "comment_status": "aggregated",
            "comments_scanned": 0,
            "comments_with_visible_reactions": 0,
            "expected_comments": 0,
        },
        {
            "label": label,
            "confidence": confidence,
            "reason": f"Агрегация по дочерним отчетам: supportive={stance_counts['supportive']}, critical={stance_counts['critical']}, mixed={stance_counts['mixed']}, neutral={stance_counts['neutral']}.",
        },
    )