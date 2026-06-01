from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from schemas.report import EventReportPayload, ProcessReportPayload


PUBLIC_READY_STATUSES = {"ready", "limited"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_status(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return "ready"
    value = str(payload.get("status") or "ready").strip().lower()
    return value or "ready"


def _aggregation_status(payloads: list[dict]) -> str:
    statuses = [_report_status(payload) for payload in payloads]
    if any(status == "limited" for status in statuses):
        return "limited"
    return "ready"


def _aggregation_confidence(*, count: int, limited: bool) -> str:
    if count >= 2 and not limited:
        return "high"
    if count >= 1:
        return "medium"
    return "low"


def _safe_str_list(values: list[Any], *, limit: int = 5) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        out.append(item)
        seen.add(item)
        if len(out) >= limit:
            break
    return out


def _normalize_distribution(payload: dict | None) -> dict[str, float]:
    sentiment = payload.get("sentiment") if isinstance(payload, dict) else {}
    distribution = sentiment.get("distribution") if isinstance(sentiment, dict) else {}
    normalized: dict[str, float] = {}
    for key in ("positive", "negative", "neutral"):
        value = distribution.get(key, 0.0) if isinstance(distribution, dict) else 0.0
        try:
            normalized[key] = max(0.0, float(value))
        except (TypeError, ValueError):
            normalized[key] = 0.0
    total = sum(normalized.values())
    if total <= 0:
        return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
    return {key: round(value / total, 4) for key, value in normalized.items()}


def _dominant_from_distribution(distribution: dict[str, float]) -> str:
    return max(distribution.items(), key=lambda item: item[1])[0]


def _weighted_sentiment(post_reports: list[dict]) -> dict[str, Any]:
    totals = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    weight_total = 0.0
    for payload in post_reports:
        weight = max(1.0, float(payload.get("comment_count") or 0))
        distribution = _normalize_distribution(payload)
        for key in totals:
            totals[key] += distribution[key] * weight
        weight_total += weight
    if weight_total <= 0:
        distribution = {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
    else:
        distribution = {key: round(value / weight_total, 4) for key, value in totals.items()}
    return {
        "dominant": _dominant_from_distribution(distribution),
        "distribution": distribution,
    }


def build_event_report_payload(
    *,
    event_id: int,
    event_title: str | None,
    post_reports: list[dict],
) -> dict:
    ordered_reports = sorted(
        [item for item in post_reports if _report_status(item) in PUBLIC_READY_STATUSES],
        key=lambda item: str(item.get("published_at") or ""),
    )
    sentiment = _weighted_sentiment(ordered_reports)
    status = _aggregation_status(ordered_reports)

    topic_counter: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    anomaly_counter: Counter[str] = Counter()
    dynamics: list[dict] = []
    trend_summaries: list[dict] = []

    for payload in ordered_reports:
        topics = payload.get("topics") if isinstance(payload.get("topics"), list) else []
        for topic in topics:
            if isinstance(topic, dict):
                name = str(topic.get("name") or "").strip()
                if name:
                    topic_counter[name] += 1
        for risk in _safe_str_list(payload.get("risks") or [], limit=3):
            risk_counter[risk] += 1
        for anomaly in _safe_str_list(payload.get("anomalies") or [], limit=3):
            anomaly_counter[anomaly] += 1

        dynamics.append(
            {
                "post_id": int(payload.get("post_id") or 0),
                "role": str(payload.get("event_role") or "context"),
                "sentiment": str((payload.get("sentiment") or {}).get("dominant") or "neutral"),
                "main_topics": [name for name, _ in topic_counter.most_common(2)] or _safe_str_list(
                    [topic.get("name") for topic in topics if isinstance(topic, dict)],
                    limit=2,
                ),
                "summary": str(payload.get("summary") or "").strip(),
            }
        )
        if payload.get("summary"):
            trend_summaries.append(
                {
                    "phase": f"post_{payload.get('post_id')}",
                    "summary": str(payload.get("summary")),
                }
            )

    topic_items = [
        {
            "name": name,
            "share": round(count / max(1, len(ordered_reports)), 4),
        }
        for name, count in topic_counter.most_common(5)
    ]

    summary = (
        f"Событие объединяет {len(ordered_reports)} постов. "
        f"Доминирующая тональность обсуждения: {sentiment['dominant']}. "
        f"Основные темы: {', '.join(name for name, _ in topic_counter.most_common(3)) or 'явно не выделены'}."
    )
    payload = EventReportPayload(
        status=status,
        event_id=event_id,
        event_title=event_title or f"Event {event_id}",
        posts_count=len(ordered_reports),
        source_post_reports=[int(item.get("post_id") or 0) for item in ordered_reports if item.get("post_id") is not None],
        sentiment={
            "dominant": sentiment["dominant"],
            "distribution": sentiment["distribution"],
            "confidence": "high" if len(ordered_reports) >= 2 else "medium",
        },
        cross_post_topics=topic_items,
        post_dynamics=dynamics[:10],
        event_trends=trend_summaries[:10],
        risks=[name for name, _ in risk_counter.most_common(5)],
        anomalies=[name for name, _ in anomaly_counter.most_common(5)],
        summary=summary,
        confidence={
            "overall": _aggregation_confidence(count=len(ordered_reports), limited=status == "limited"),
            "reason": (
                "Сводка собрана по готовым public post_report_v2."
                if status == "ready"
                else "Сводка собрана по public post_report_v2 с ограниченными дочерними выводами."
            ),
        },
        meta={"prompt_version": "event_report_v2", "source_type": "post_reports", "generated_at": _utcnow_iso()},
    )
    return payload.model_dump()


def build_process_report_payload(
    *,
    process_id: int,
    process_title: str | None,
    event_reports: list[dict],
) -> dict:
    ordered_reports = [item for item in event_reports if _report_status(item) in PUBLIC_READY_STATUSES]
    status = _aggregation_status(ordered_reports)
    totals = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    for payload in ordered_reports:
        report_sentiment = payload.get("sentiment") if isinstance(payload.get("sentiment"), dict) else payload.get("overall_sentiment")
        distribution = _normalize_distribution({"sentiment": report_sentiment or {}})
        for key in totals:
            totals[key] += distribution[key]
    count = max(1, len(ordered_reports))
    distribution = {key: round(value / count, 4) for key, value in totals.items()}
    dominant = _dominant_from_distribution(distribution)

    stage_analysis: list[dict] = []
    trend_items: list[dict] = []
    bottlenecks: Counter[str] = Counter()
    risks: Counter[str] = Counter()

    for payload in ordered_reports:
        event_id = int(payload.get("event_id") or 0)
        event_title = str(payload.get("event_title") or f"Event {event_id}")
        topics = payload.get("cross_post_topics") or []
        stage_analysis.append(
            {
                "stage_name": event_title,
                "event_ids": [event_id],
                "dominant_sentiment": str((payload.get("sentiment") or {}).get("dominant") or "neutral"),
                "main_topics": _safe_str_list([topic.get("name") for topic in topics if isinstance(topic, dict)], limit=3),
                "summary": str(payload.get("summary") or "").strip(),
            }
        )
        if payload.get("summary"):
            trend_items.append({"trend": str(payload.get("summary"))})
        for item in _safe_str_list(payload.get("anomalies") or [], limit=3):
            bottlenecks[item] += 1
        for item in _safe_str_list(payload.get("risks") or [], limit=3):
            risks[item] += 1

    summary = (
        f"Процесс объединяет {len(ordered_reports)} событий. "
        f"Преобладающая тональность: {dominant}. "
        f"Ключевой фокус обсуждения смещается между событиями по мере развития процесса."
    )
    payload = ProcessReportPayload(
        status=status,
        process_id=process_id,
        process_title=process_title or f"Process {process_id}",
        events_count=len(ordered_reports),
        source_event_reports=[int(item.get("event_id") or 0) for item in ordered_reports if item.get("event_id") is not None],
        overall_sentiment={
            "dominant": dominant,
            "distribution": distribution,
            "confidence": "high" if len(ordered_reports) >= 2 else "medium",
        },
        stage_analysis=stage_analysis[:10],
        process_trends=trend_items[:10],
        bottlenecks=[name for name, _ in bottlenecks.most_common(5)],
        risks=[name for name, _ in risks.most_common(5)],
        summary=summary,
        confidence={
            "overall": _aggregation_confidence(count=len(ordered_reports), limited=status == "limited"),
            "reason": (
                "Сводка собрана по готовым event_report_v2."
                if status == "ready"
                else "Сводка собрана по event_report_v2 с ограниченными дочерними выводами."
            ),
        },
        meta={"prompt_version": "process_report_v2", "source_type": "event_reports", "generated_at": _utcnow_iso()},
    )
    return payload.model_dump()
