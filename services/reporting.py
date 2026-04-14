from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.reporter import ReportConfig, TgReportProject
from db.models import Channel, Comment, Event, EventPost, EventReport, Job, Post, Process, ProcessEvent, ProcessReport, Report
from services.jobs import JOB_STATUS_DONE, JobType
from services.ingest import upsert_report
from services.report_aggregation import build_event_report_payload, build_process_report_payload


SKIPPED_MIN_COMMENTS_PREFIX = "STATUS: SKIPPED_MIN_COMMENTS"
REPORT_GENERATION_FAILED_CONTENT = "STATUS: FAILED\nREASON: report_generation_failed"
REPORT_STATUS_DRAFT = "draft"
REPORT_STATUS_READY = "ready"
REPORT_STATUS_LIMITED = "limited"
REPORT_STATUS_INSUFFICIENT_DATA = "insufficient_data"
REPORT_STATUS_FAILED = "failed"
REPORT_STATUS_DEFERRED = "deferred_waiting_dependencies"
REPORT_STATUS_STALE = "stale"
POST_REPORT_REBUILD_PRIORITY = 40
AGGREGATABLE_REPORT_STATUSES = {REPORT_STATUS_READY, REPORT_STATUS_LIMITED}


def _build_dependency(job_type: str, *, entity_id: int, reason: str) -> dict:
    entity_key = {
        JobType.REFRESH_COMMENTS: "post_id",
        JobType.BUILD_POST_REPORT: "post_id",
        JobType.BUILD_EVENT_REPORT: "event_id",
        JobType.BUILD_PROCESS_REPORT: "process_id",
    }.get(job_type)
    if entity_key is None:
        raise ValueError(f"Unsupported dependency job type: {job_type}")
    return {
        "job_type": job_type,
        entity_key: int(entity_id),
        "reason": reason,
    }


def _is_payload_dependency_ready(payload: dict | None) -> bool:
    status = report_status_from_payload(payload, fallback="")
    return status in AGGREGATABLE_REPORT_STATUSES


def _serialize_report_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_public_confidence(payload: dict) -> dict:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    confidence = dict(payload.get("confidence") or {})
    current_overall = str(confidence.get("overall") or "medium").strip().lower()
    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        confidence["overall"] = "low"
        confidence["reason"] = (
            "Недостаточно данных для надежного итогового вывода по обсуждению."
        )
    elif status == REPORT_STATUS_LIMITED:
        confidence["overall"] = "medium" if current_overall == "high" else (current_overall or "medium")
        confidence["reason"] = (
            "Выводы ограничены доступным объемом и устойчивостью сигналов обсуждения."
        )
    else:
        confidence["overall"] = current_overall if current_overall in {"low", "medium", "high"} else "medium"
    return confidence


def _normalize_public_topics(payload: dict) -> list[dict]:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        return []

    topics = payload.get("topics")
    if not isinstance(topics, list):
        return []

    normalized: list[dict] = []
    seen: set[str] = set()
    for item in topics:
        if isinstance(item, dict):
            name = _clean_list_text(item.get("name"))
            share = item.get("share")
        elif isinstance(item, str):
            name = _clean_list_text(item)
            share = None
        else:
            continue
        if not name or name in seen:
            continue
        next_item = {"name": name}
        try:
            if share is not None:
                next_item["share"] = max(0.0, min(1.0, float(share)))
        except (TypeError, ValueError):
            pass
        normalized.append(next_item)
        seen.add(name)
        if len(normalized) >= 5:
            break
    return normalized


def _build_public_post_summary(payload: dict) -> str:
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    comment_count = int(payload.get("comment_count") or 0)
    dominant = _sentiment_label_ru((payload.get("sentiment") or {}).get("dominant"))
    topic_names = [item["name"] for item in _normalize_public_topics(payload)[:3] if isinstance(item, dict) and item.get("name")]
    topics_text = ", ".join(topic_names) if topic_names else "явные темы не выделены"

    if status == REPORT_STATUS_INSUFFICIENT_DATA:
        return (
            f"Недостаточно данных для надежного вывода: проанализировано {comment_count} комментариев; "
            f"уверенные темы не выделены."
        )
    if status == REPORT_STATUS_LIMITED:
        return (
            f"Анализ ограничен: проанализировано {comment_count} комментариев; "
            f"преобладает {dominant} тон; основные темы: {topics_text}."
        )
    return (
        f"Проанализировано {comment_count} комментариев; "
        f"преобладает {dominant} тон; основные темы: {topics_text}."
    )


def map_internal_post_report_to_public_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload

    public_payload = dict(payload)
    public_payload["status"] = report_status_from_payload(public_payload, fallback=REPORT_STATUS_READY)
    public_payload["topics"] = _normalize_public_topics(public_payload)
    public_payload["confidence"] = _normalize_public_confidence(public_payload)
    public_payload["summary"] = _build_public_post_summary(public_payload)
    return public_payload


def _sentiment_label_ru(value: str | None) -> str:
    mapping = {
        "positive": "позитивный",
        "negative": "негативный",
        "neutral": "нейтральный",
        "mixed": "смешанный",
        "stable": "стабильный",
    }
    normalized = str(value or "").strip().lower()
    return mapping.get(normalized, normalized or "нейтральный")


def _share_to_percent(value: object) -> str:
    try:
        return f"{round(float(value or 0.0) * 100, 1):g}%"
    except (TypeError, ValueError):
        return "0%"


def _clean_list_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text or None


def _collect_topic_names(items: object, *, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        name = None
        if isinstance(item, dict):
            name = _clean_list_text(item.get("name"))
        elif isinstance(item, str):
            name = _clean_list_text(item)
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _collect_text_items(items: object, *, limit: int = 5) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = _clean_list_text(item.get("summary") or item.get("trend") or item.get("name"))
        else:
            text = _clean_list_text(item)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _trim_sentence(text: str | None, *, fallback: str) -> str:
    value = _clean_list_text(text)
    if not value:
        return fallback
    return value if value[-1] in ".!?" else f"{value}."


def _build_emotional_background(payload: dict, *, sentiment_key: str = "sentiment") -> list[str]:
    sentiment = payload.get(sentiment_key) or {}
    distribution = sentiment.get("distribution") or {}
    dominant = _sentiment_label_ru(sentiment.get("dominant"))
    lines = [
        (
            f"В целом преобладает {dominant} тон. "
            f"Распределение реакций: позитив {_share_to_percent(distribution.get('positive'))} / "
            f"негатив {_share_to_percent(distribution.get('negative'))} / "
            f"нейтрально {_share_to_percent(distribution.get('neutral'))}."
        )
    ]
    summary = _clean_list_text(payload.get("summary"))
    if summary:
        lines.append(_trim_sentence(summary, fallback=""))
    confidence_reason = _clean_list_text((payload.get("confidence") or {}).get("reason"))
    if confidence_reason:
        lines.append(_trim_sentence(confidence_reason, fallback=""))
    risks = _collect_text_items(payload.get("risks"), limit=2)
    if risks:
        lines.append(f"В обсуждении также заметны спорные сигналы: {'; '.join(risks)}.")
    return [line for line in lines if line]


def _render_legacy_report_text(
    payload: dict,
    *,
    title: str,
    intro_label: str,
    intro_fallback: str,
    topics: list[str],
    patterns: list[str],
    examples: list[str],
    conclusion_fallback: str,
    sentiment_key: str = "sentiment",
) -> str:
    heading = _clean_list_text(title) or "Заголовок: Отчет"
    intro = _trim_sentence(payload.get("summary"), fallback=intro_fallback)
    emotional_background = _build_emotional_background(payload, sentiment_key=sentiment_key)
    if not topics:
        topics = ["Явно выраженные тематические линии в данных не выделяются."]
    if not patterns:
        patterns = ["Повторяющиеся паттерны выражены слабо, дискуссия выглядит относительно ровной."]
    if not examples:
        examples = ["Характерные тезисы в исходных данных выражены недостаточно явно для надежной выборки."]

    risks = _collect_text_items(payload.get("risks"), limit=3)
    anomalies = _collect_text_items(payload.get("anomalies"), limit=3)
    conclusion_parts: list[str] = []
    summary = _clean_list_text(payload.get("summary"))
    if summary:
        conclusion_parts.append(summary.rstrip("."))
    if risks:
        conclusion_parts.append(f"Среди заметных рисков и спорных моментов: {'; '.join(risks)}")
    if anomalies:
        conclusion_parts.append(f"Дополнительные сигналы: {'; '.join(anomalies)}")
    conclusion = ". ".join(part for part in conclusion_parts if part).strip()
    if conclusion:
        conclusion = conclusion if conclusion.endswith(".") else f"{conclusion}."
    else:
        conclusion = conclusion_fallback

    lines = [
        f"Краткий анализ комментариев к {intro_label}",
        "",
        heading,
        "",
        "Общий эмоциональный фон",
        *emotional_background,
        "2. Основные направления мысли",
        *[f"- {item}" for item in topics[:5]],
        "3. Противоречия и спорные моменты",
        *[f"- {item}" for item in patterns[:5]],
        "4. Примеры характерных тезисов (для ориентира)",
        *[f"- {item}" for item in examples[:5]],
        "Итог",
        conclusion,
        "",
        "8) Reactions и позиция аудитории",
        _format_reactions_summary_line("Post reactions", payload.get("post_reactions") or {}),
        _format_reactions_summary_line("Comment reactions", payload.get("comment_reactions") or {}),
        _format_reactions_coverage_line(payload),
        f"- Audience stance: {(payload.get('audience_stance') or {}).get('label') or 'unclear'} ({(payload.get('audience_stance') or {}).get('confidence') or 'low'}).",
        f"- Обоснование stance: {_trim_sentence((payload.get('audience_stance') or {}).get('reason'), fallback='Позиция аудитории определена по сочетанию тональности комментариев и reactions coverage.')}",
    ]
    return "\n".join(lines).strip()


def _signature_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _build_post_report_input_signature(
    *,
    post: Post,
    comment_rows: list[tuple],
) -> str:
    payload = {
        "post": {
            "id": int(post.id),
            "date": _signature_timestamp(post.date),
            "text": post.text or "",
            "views": int(post.views) if post.views is not None else None,
            "comments_count": int(post.comments_count or 0),
            "reactions_json": post.reactions_json if isinstance(post.reactions_json, dict) else None,
        },
        "comments": [
            {
                "tg_message_id": int(tg_message_id),
                "parent_tg_message_id": int(parent_tg_message_id) if parent_tg_message_id is not None else None,
                "thread_root_tg_message_id": int(thread_root_tg_message_id) if thread_root_tg_message_id is not None else None,
                "depth": int(depth or 0),
                "date": _signature_timestamp(date),
                "text": text or "",
                "reactions_json": reactions_json if isinstance(reactions_json, dict) else None,
            }
            for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, reactions_json in comment_rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _load_post_comment_rows_for_signature(session: AsyncSession, *, post_id: int) -> list[tuple]:
    return (
        await session.execute(
            select(
                Comment.tg_message_id,
                Comment.parent_tg_message_id,
                Comment.thread_root_tg_message_id,
                Comment.depth,
                Comment.date,
                Comment.text,
                Comment.reactions_json,
            )
            .where(Comment.post_id == post_id)
            .order_by(Comment.date.asc(), Comment.id.asc())
        )
    ).all()


async def compute_post_report_input_signature(
    session: AsyncSession,
    *,
    post_id: int,
    post: Post | None = None,
) -> str | None:
    post_row = post or await session.get(Post, post_id)
    if post_row is None:
        return None
    comment_rows = await _load_post_comment_rows_for_signature(session, post_id=post_row.id)
    return _build_post_report_input_signature(post=post_row, comment_rows=comment_rows)


async def _load_post_refresh_attempt_info(session: AsyncSession, *, post_id: int) -> dict | None:
    row = (
        await session.execute(
            select(Job.type, Job.updated_at)
            .where(Job.type.in_((JobType.COLLECT_COMMENTS, JobType.REFRESH_COMMENTS)))
            .where(Job.status == JOB_STATUS_DONE)
            .where(Job.payload_json["post_id"].astext == str(post_id))
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    job_type, updated_at = row
    return {
        "source": str(job_type),
        "collected_at": updated_at.isoformat() if updated_at is not None else None,
        "is_complete": False,
    }


async def _post_report_readiness(session: AsyncSession, *, post: Post) -> dict:
    if not (post.text or "").strip():
        return {
            "ready": False,
            "reason": "missing_post_text",
            "dependencies": [],
            "terminal": True,
        }

    refresh_attempt = await _load_post_refresh_attempt_info(session, post_id=int(post.id))
    if refresh_attempt is None:
        return {
            "ready": False,
            "reason": "waiting_refresh_post_data",
            "dependencies": [
                _build_dependency(
                    JobType.REFRESH_COMMENTS,
                    entity_id=int(post.id),
                    reason="waiting_refresh_post_data",
                )
            ],
            "terminal": False,
        }

    return {
        "ready": True,
        "reason": "ready",
        "dependencies": [],
        "terminal": False,
        "refresh_attempt": refresh_attempt,
    }


def _obsolete_render_post_report_text_v1(payload: dict) -> str:
    lines = [
        f"Заголовок: {payload.get('title') or 'Отчет по посту'}",
        "",
        f"Краткое резюме: {payload.get('summary') or 'Нет данных.'}",
    ]
    sentiment = payload.get("sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    lines.extend(
        [
            "",
            "Тональность:",
            f"- Доминирующая: {sentiment.get('dominant') or 'neutral'}",
            (
                f"- Распределение: позитив {distribution.get('positive', 0)} / "
                f"негатив {distribution.get('negative', 0)} / "
                f"нейтрально {distribution.get('neutral', 0)}"
            ),
        ]
    )
    topics = [item.get("name") for item in payload.get("topics") or [] if isinstance(item, dict) and item.get("name")]
    if topics:
        lines.extend(["", "Темы:", *[f"- {topic}" for topic in topics[:5]]])
    risks = [item for item in payload.get("risks") or [] if isinstance(item, str) and item.strip()]
    if risks:
        lines.extend(["", "Риски:", *[f"- {item}" for item in risks[:5]]])
    return "\n".join(lines).strip()


def _obsolete_render_event_or_process_text_v1(payload: dict) -> str:
    title = payload.get("event_title") or payload.get("process_title") or payload.get("title") or "Отчет"
    lines = [
        f"Заголовок: {title}",
        "",
        f"Краткое резюме: {payload.get('summary') or 'Нет данных.'}",
    ]
    sentiment = payload.get("sentiment") or payload.get("overall_sentiment") or {}
    if isinstance(sentiment, dict):
        lines.extend(
            [
                "",
                "Тональность:",
                f"- Доминирующая: {sentiment.get('dominant') or 'neutral'}",
            ]
        )
    risks = [item for item in payload.get("risks") or [] if isinstance(item, str) and item.strip()]
    if risks:
        lines.extend(["", "Риски:", *[f"- {item}" for item in risks[:5]]])
    return "\n".join(lines).strip()


def _obsolete_render_post_report_text_v2(payload: dict) -> str:
    topics = _collect_topic_names(payload.get("topics"), limit=5)
    patterns = _collect_text_items(payload.get("time_trends"), limit=3)
    for item in payload.get("clusters") or []:
        if not isinstance(item, dict):
            continue
        name = _clean_list_text(item.get("name"))
        summary = _clean_list_text(item.get("summary"))
        pattern = f"{name}: {summary}" if name and summary else name or summary
        if pattern and pattern not in patterns:
            patterns.append(pattern)
        if len(patterns) >= 5:
            break
    patterns.extend(item for item in _collect_text_items(payload.get("risks"), limit=2) if item not in patterns)

    examples = _collect_text_items(payload.get("representative_quotes"), limit=5)
    if not examples:
        examples = topics[:3]

    return _render_legacy_report_text(
        payload,
        title=payload.get("title") or "Заголовок: Отчет по посту",
        intro_label="посту",
        intro_fallback="Комментарии отражают реакцию аудитории на публикацию и связанные с ней смыслы.",
        topics=topics,
        patterns=patterns,
        examples=examples,
        conclusion_fallback="Обсуждение в целом остается содержательным, с преобладанием основных тем и ограниченным числом спорных сигналов.",
    )


def _render_event_or_process_text(payload: dict) -> str:
    is_process = "process_id" in payload or "process_title" in payload
    title = payload.get("process_title") if is_process else payload.get("event_title")
    title = title or payload.get("title") or "Отчет"

    topics = _collect_topic_names(payload.get("cross_post_topics"), limit=5)
    source_items = payload.get("stage_analysis") if is_process else payload.get("post_dynamics")
    for item in source_items or []:
        if not isinstance(item, dict):
            continue
        name = _clean_list_text(item.get("stage_name") or item.get("role"))
        summary = _clean_list_text(item.get("summary"))
        topic = f"{name}: {summary}" if name and summary else summary or name
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) >= 5:
            break

    patterns = _collect_text_items(payload.get("event_trends") or payload.get("process_trends"), limit=5)
    patterns.extend(item for item in _collect_text_items(payload.get("risks"), limit=3) if item not in patterns)
    patterns.extend(item for item in _collect_text_items(payload.get("bottlenecks"), limit=2) if item not in patterns)

    examples = _collect_text_items(payload.get("risks"), limit=2)
    examples.extend(item for item in _collect_text_items(payload.get("anomalies"), limit=3) if item not in examples)
    if not examples:
        examples = topics[:3]

    return _render_legacy_report_text(
        payload,
        title=f"Заголовок: {title}",
        intro_label="обсуждению",
        intro_fallback="Сводный отчет фиксирует общую динамику обсуждения и ключевые смысловые линии.",
        topics=topics,
        patterns=patterns,
        examples=examples,
        conclusion_fallback="Сводное обсуждение сохраняет общую логическую связность и позволяет увидеть основные тенденции без резких перекосов.",
        sentiment_key="overall_sentiment" if is_process else "sentiment",
    )


def _post_report_tone_label(payload: dict) -> str:
    sentiment = payload.get("sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    positive = float(distribution.get("positive", 0.0) or 0.0)
    negative = float(distribution.get("negative", 0.0) or 0.0)
    neutral = float(distribution.get("neutral", 0.0) or 0.0)
    dominant = str(sentiment.get("dominant") or "neutral").strip().lower()
    if abs(positive - negative) <= 0.15 and positive >= 0.2 and negative >= 0.2:
        return "смешанный"
    if dominant == "positive":
        return "позитивный"
    if dominant == "negative":
        return "негативный"
    if dominant == "neutral" and positive >= 0.25 and negative >= 0.15:
        return "смешанный"
    if neutral >= 0.6:
        return "нейтральный"
    return _sentiment_label_ru(dominant)


def _build_post_tone_reasoning(payload: dict) -> str:
    parts: list[str] = []
    summary = _clean_list_text(payload.get("summary"))
    if summary:
        parts.append(summary)
    confidence_reason = _clean_list_text((payload.get("confidence") or {}).get("reason"))
    if confidence_reason and confidence_reason not in parts:
        parts.append(confidence_reason)
    risks = _collect_text_items(payload.get("risks"), limit=2)
    if risks:
        parts.append(f"Отдельно заметны спорные реакции: {'; '.join(risks)}.")
    if not parts:
        parts.append("Вывод основан на распределении тональностей, тематических кластерах и репрезентативных комментариях.")
    return " ".join(part if part.endswith((".", "!", "?")) else f"{part}." for part in parts[:3])


def _build_post_sentiment_classification(payload: dict) -> str:
    sentiment = payload.get("sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    parts = [
        f"позитивные комментарии составляют {_share_to_percent(distribution.get('positive'))} и в основном выражают поддержку или одобрение",
        f"негативные занимают {_share_to_percent(distribution.get('negative'))} и чаще связаны с критикой, сомнениями или возражениями",
        f"нейтральные составляют {_share_to_percent(distribution.get('neutral'))} и обычно содержат уточнения, наблюдения или спокойные оценки",
    ]
    return " ; ".join(parts) + "."


def _build_post_thematic_classification(payload: dict) -> str:
    cluster_parts: list[str] = []
    for item in payload.get("clusters") or []:
        if not isinstance(item, dict):
            continue
        name = _clean_list_text(item.get("name"))
        summary = _clean_list_text(item.get("summary"))
        if name and summary:
            cluster_parts.append(f"{name} — {summary}")
        elif name:
            cluster_parts.append(name)
        if len(cluster_parts) >= 4:
            break
    if cluster_parts:
        return "; ".join(cluster_parts) + "."
    topics = _collect_topic_names(payload.get("topics"), limit=4)
    if topics:
        return "Основные тематические кластеры: " + "; ".join(topics) + "."
    return "Тематическая классификация выражена слабо: заметны только отдельные смысловые линии без устойчивых кластеров."


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
    for source_payload in (payload.get("post_reactions") or {}, payload.get("comment_reactions") or {}):
        for item in list(source_payload.get("top_reactions") or []):
            label = str(item.get("label") or "")
            count = _safe_int(item.get("count"))
            if label in {"👍", "❤", "❤️", "🔥", "👏", "🙏", "😁", "👌", "💯"}:
                positive_reaction_count += count
            elif label in {"👎", "🤬", "😡", "💩", "🤮", "😢", "😭"}:
                critical_reaction_count += count
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
    coverage_factor = _safe_float((payload.get("reactions_coverage") or {}).get("factor"))
    confidence = "high" if coverage_factor >= 0.85 else "medium" if coverage_factor >= 0.45 else "low"
    return {
        "label": label,
        "confidence": confidence,
        "reason": (
            f"Тональность: позитив {_share_to_percent(positive)}, негатив {_share_to_percent(negative)}, нейтрально {_share_to_percent(neutral)}. "
            f"Поддерживающих reactions: {positive_reaction_count}, критических: {critical_reaction_count}."
        ),
    }


def _format_reactions_summary_line(title: str, summary: dict) -> str:
    top = list(summary.get("top_reactions") or [])
    if not top:
        return f"- {title}: выраженных reactions нет."
    return f"- {title}: " + ", ".join(f"{item.get('label')} {_safe_int(item.get('count'))}" for item in top[:5]) + "."


def _format_reactions_coverage_line(payload: dict) -> str:
    coverage = payload.get("reactions_coverage") or {}
    return (
        f"- Покрытие reactions: {_share_to_percent(coverage.get('factor'))}; "
        f"comment reactions status={coverage.get('comment_status') or 'unknown'}; "
        f"scanned={_safe_int(coverage.get('comments_scanned'))}/{_safe_int(coverage.get('expected_comments'))}."
    )


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


def _render_post_report_text(payload: dict) -> str:
    title = _clean_list_text(payload.get("title")) or "Заголовок: Отчет по посту"
    if not title.lower().startswith("заголовок:"):
        title = f"Заголовок: {title}"

    sentiment = payload.get("sentiment") or {}
    distribution = sentiment.get("distribution") or {}
    topics = _collect_topic_names(payload.get("topics"), limit=5)
    if not topics:
        topics = ["Явно выраженные темы в комментариях не выделяются."]

    patterns = _collect_text_items(payload.get("time_trends"), limit=3)
    for item in payload.get("clusters") or []:
        if not isinstance(item, dict):
            continue
        summary = _clean_list_text(item.get("summary"))
        if summary and summary not in patterns:
            patterns.append(summary)
        if len(patterns) >= 5:
            break
    if not patterns:
        patterns = ["Повторяющиеся паттерны выражены умеренно и в основном совпадают с ключевыми темами обсуждения."]

    quotes = _collect_text_items(payload.get("representative_quotes"), limit=5)
    if not quotes:
        quotes = ["Репрезентативные цитаты не выделены, поэтому выводы основаны на агрегированных сигналах."]

    risks = _collect_text_items(payload.get("risks"), limit=5)
    if not risks:
        risks = ["Сильные риск-сигналы в комментариях не выявлены."]

    lines = [
        title,
        "",
        "1) Контекст поста",
        _trim_sentence(
            payload.get("summary"),
            fallback="Отчет суммирует реакцию аудитории на публикацию и показывает, какие темы и оценки доминируют в комментариях.",
        ),
        (
            "Анализ опирается на комментарии к одному посту и включает общий тон, "
            "процентное соотношение настроений, тематические линии, паттерны обсуждения и репрезентативные цитаты."
        ),
        "",
        "2) Общий тон обсуждения",
        f"- Итог: {_post_report_tone_label(payload)}",
        (
            f"- Распределение: позитив {_share_to_percent(distribution.get('positive'))} / "
            f"негатив {_share_to_percent(distribution.get('negative'))} / "
            f"нейтрально {_share_to_percent(distribution.get('neutral'))}"
        ),
        f"- Обоснование: {_build_post_tone_reasoning(payload)}",
        "",
        "3) Ключевые темы",
        *[f"- Тема {idx}: {topic}" for idx, topic in enumerate(topics[:5], start=1)],
        "",
        "4) Тренды и повторяющиеся паттерны",
        *[f"- {item}" for item in patterns[:5]],
        "",
        "5) Репрезентативные цитаты",
        *[f'- "{item}"' for item in quotes[:5]],
        "",
        "6) Классификация комментариев",
        f"- По тональности: {_build_post_sentiment_classification(payload)}",
        f"- По темам: {_build_post_thematic_classification(payload)}",
        "",
        "7) Риски/сигналы",
        *[f"- {item}" for item in risks[:5]],
        "",
        "8) Reactions и позиция аудитории",
        _format_reactions_summary_line("Post reactions", payload.get("post_reactions") or {}),
        _format_reactions_summary_line("Comment reactions", payload.get("comment_reactions") or {}),
        _format_reactions_coverage_line(payload),
        f"- Audience stance: {(payload.get('audience_stance') or {}).get('label') or 'unclear'} ({(payload.get('audience_stance') or {}).get('confidence') or 'low'}).",
        f"- Обоснование stance: {_trim_sentence((payload.get('audience_stance') or {}).get('reason'), fallback='Позиция аудитории определена по сочетанию тональности комментариев и reactions coverage.')}",
    ]
    return "\n".join(lines).strip()


def report_status_from_payload(payload: dict | None, *, fallback: str = REPORT_STATUS_READY) -> str:
    if not isinstance(payload, dict):
        return fallback
    status = payload.get("status")
    if isinstance(status, str) and status:
        return status
    payload_type = payload.get("type")
    if payload_type in {"event_report_draft_v1", "process_report_draft_v1"}:
        return REPORT_STATUS_DRAFT
    return fallback


def mark_report_payload_stale(
    payload: dict | None,
    *,
    dependency_type: str,
    dependency_id: int,
) -> dict:
    next_payload = dict(payload or {})
    previous_status = report_status_from_payload(next_payload, fallback=REPORT_STATUS_READY)
    meta = dict(next_payload.get("meta") or {})
    next_payload["status"] = REPORT_STATUS_STALE
    next_payload["meta"] = {
        **meta,
        "stale": True,
        "stale_dependency_type": dependency_type,
        "stale_dependency_id": int(dependency_id),
        "stale_marked_at": meta.get("stale_marked_at") or datetime.now(timezone.utc).isoformat(),
        "previous_status": meta.get("previous_status") or previous_status,
    }
    return next_payload


async def _mark_related_event_reports_stale_for_post(session: AsyncSession, *, post_id: int) -> tuple[int, list[int]]:
    rows = (
        await session.execute(
            select(EventReport)
            .where(
                EventReport.id.in_(
                    select(EventReport.id)
                    .join(EventPost, EventPost.event_id == EventReport.event_id)
                    .where(EventPost.post_id == post_id)
                    .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
                    .distinct(EventReport.event_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    event_ids: list[int] = []
    for report in rows:
        event_ids.append(int(report.event_id))
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="post_report",
            dependency_id=post_id,
        )
        marked += 1
    if marked:
        await session.flush()
    return marked, event_ids


async def _mark_related_process_reports_stale_for_events(session: AsyncSession, *, event_ids: list[int]) -> int:
    if not event_ids:
        return 0
    rows = (
        await session.execute(
            select(ProcessReport)
            .where(
                ProcessReport.id.in_(
                    select(ProcessReport.id)
                    .join(ProcessEvent, ProcessEvent.process_id == ProcessReport.process_id)
                    .where(ProcessEvent.event_id.in_(event_ids))
                    .order_by(ProcessReport.process_id.asc(), ProcessReport.version.desc(), ProcessReport.id.desc())
                    .distinct(ProcessReport.process_id)
                )
            )
        )
    ).scalars().all()
    marked = 0
    for report in rows:
        payload = report.report_json if isinstance(report.report_json, dict) else {}
        if payload.get("status") == REPORT_STATUS_STALE:
            continue
        report.report_json = mark_report_payload_stale(
            payload,
            dependency_type="event_report",
            dependency_id=int(event_ids[0]),
        )
        marked += 1
    if marked:
        await session.flush()
    return marked


async def sync_post_report_staleness(
    session: AsyncSession,
    *,
    post_id: int,
    source: str,
    dependency_type: str = "post_inputs",
    dependency_id: int | None = None,
) -> dict:
    post = await session.get(Post, post_id)
    if post is None:
        return {"status": "not_found", "post_id": post_id}

    report = (
        await session.execute(select(Report).where(Report.post_id == post_id))
    ).scalar_one_or_none()
    min_comments = ReportConfig().min_comments
    if report is None and int(post.comments_count or 0) < min_comments:
        return {
            "status": "ignored_below_min_comments",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    current_signature = await compute_post_report_input_signature(session, post_id=post_id, post=post)
    if current_signature is None:
        return {"status": "not_found", "post_id": post_id}

    report_payload = report.report_json if report is not None and isinstance(report.report_json, dict) else {}
    report_meta = dict(report_payload.get("meta") or {})
    stored_signature = report_meta.get("current_input_signature") or report_meta.get("input_signature")
    if stored_signature == current_signature:
        return {
            "status": "unchanged",
            "post_id": post_id,
            "changed": False,
            "stale_marked": False,
            "enqueued": False,
        }

    stale_marked = False
    event_reports_marked = 0
    process_reports_marked = 0
    if report is not None and isinstance(report.report_json, dict):
        next_payload = mark_report_payload_stale(
            report.report_json,
            dependency_type=dependency_type,
            dependency_id=dependency_id if dependency_id is not None else post_id,
        )
        next_meta = dict(next_payload.get("meta") or {})
        next_meta["previous_input_signature"] = report_meta.get("input_signature")
        next_meta["current_input_signature"] = current_signature
        next_payload["meta"] = next_meta
        report.report_json = next_payload
        stale_marked = True
        event_reports_marked, event_ids = await _mark_related_event_reports_stale_for_post(session, post_id=post_id)
        process_reports_marked = await _mark_related_process_reports_stale_for_events(session, event_ids=event_ids)

    return {
        "status": "stale_marked" if stale_marked else "changed",
        "post_id": post_id,
        "changed": True,
        "stale_marked": stale_marked,
        "event_reports_marked_stale": event_reports_marked,
        "process_reports_marked_stale": process_reports_marked,
        "enqueued": False,
        "job_id": None,
        "input_signature": current_signature,
        "source": source,
    }


async def build_post_report(
    session: AsyncSession,
    *,
    post_id: int,
    report_project: TgReportProject,
    report_config: ReportConfig | None = None,
    job_timeout_seconds: int | None = None,
    rerun_stage: str | None = None,
) -> dict:
    post_result = await session.execute(
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = post_result.first()
    if row is None:
        return {"status": "not_found", "post_id": post_id}

    post, channel = row
    readiness = await _post_report_readiness(session, post=post)
    if not readiness.get("ready"):
        status = REPORT_STATUS_FAILED if readiness.get("terminal") else REPORT_STATUS_DEFERRED
        return {
            "status": status,
            "post_id": post.id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    comments_result = await session.execute(
        select(
            Comment.tg_message_id,
            Comment.parent_tg_message_id,
            Comment.thread_root_tg_message_id,
            Comment.depth,
            Comment.date,
            Comment.text,
            Comment.reactions_json,
        )
        .where(Comment.post_id == post.id)
        .order_by(Comment.date.asc(), Comment.id.asc())
    )
    comment_rows = comments_result.all()
    input_signature = _build_post_report_input_signature(post=post, comment_rows=comment_rows)

    comments: list[str] = []
    thread_comments: list[dict] = []
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, _reactions_json in comment_rows:
        if not text or not text.strip():
            continue
        comments.append(text)
        normalized_parent_id = parent_tg_message_id
        if thread_root_tg_message_id is not None and parent_tg_message_id == thread_root_tg_message_id:
            normalized_parent_id = None
        thread_comments.append(
            {
                "id": tg_message_id,
                "parent_id": normalized_parent_id,
                "depth": depth,
                "date": date.isoformat() if date is not None else None,
                "text": text,
            }
        )

    channel_label = f"@{channel.username}" if channel.username else f"channel:{channel.id}"
    status = REPORT_STATUS_READY
    report_json: dict | None = None
    try:
        report_json = await report_project.generate_post_report_payload(
            channel=channel_label,
            post_id=post.id,
            published_at_iso=post.date.isoformat(),
            post_text=post.text or "",
            comments=comments,
            thread_comments=thread_comments,
            views=post.views,
            config=report_config,
            job_timeout_seconds=job_timeout_seconds,
            rerun_stage=rerun_stage,
        )
        report_json = map_internal_post_report_to_public_payload(report_json)
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)
        report_json = _enrich_post_report_payload(payload=report_json, post=post, comment_rows=comment_rows)
        report_json.setdefault("post_id", post.id)
        report_json.setdefault("published_at", post.date.isoformat())
        report_json["meta"] = {
            **dict(report_json.get("meta") or {}),
            "input_signature": input_signature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refresh_attempt": readiness.get("refresh_attempt"),
        }
        if status == REPORT_STATUS_FAILED:
            content = REPORT_GENERATION_FAILED_CONTENT
            technical_error = str((report_json.get("meta") or {}).get("validation_error") or "invalid_model_output")
        else:
            content = _render_post_report_text(report_json)
            technical_error = None
    except Exception as exc:
        status = REPORT_STATUS_FAILED
        content = REPORT_GENERATION_FAILED_CONTENT
        technical_error = f"{type(exc).__name__}: {exc}"

    if isinstance(report_json, dict) and report_json.get("status") == "skipped_min_comments":
        return {
            "status": "skipped_min_comments",
            "post_id": post.id,
            "report_id": None,
        }

    report = await upsert_report(
        session,
        post_id=post.id,
        status=status,
        content=content,
        report_json=report_json,
    )
    result = {"status": status, "post_id": post.id, "report_id": report.id}
    if technical_error is not None:
        result["technical_error"] = technical_error
    return result


async def _load_post_report_payloads_for_event(session: AsyncSession, *, event_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(Report.report_json, Report.post_id, EventPost.role, Post.date)
            .join(EventPost, EventPost.post_id == Report.post_id)
            .join(Post, Post.id == Report.post_id)
            .where(EventPost.event_id == event_id)
            .where(Report.report_json.is_not(None))
            .order_by(Post.date.asc(), Report.id.asc())
        )
    ).all()
    payloads: list[dict] = []
    for report_json, post_id, role, post_date in rows:
        if not isinstance(report_json, dict):
            continue
        if not _is_payload_dependency_ready(report_json):
            continue
        payload = dict(report_json)
        payload.setdefault("post_id", int(post_id))
        payload["event_role"] = role
        payload.setdefault("published_at", post_date.isoformat() if post_date is not None else None)
        payloads.append(payload)
    return payloads


async def _event_report_readiness(session: AsyncSession, *, event_id: int) -> dict:
    min_comments = ReportConfig().min_comments
    rows = (
        await session.execute(
            select(EventPost.post_id, EventPost.role, Post.comments_count, Post.text, Report.report_json)
            .join(Post, Post.id == EventPost.post_id)
            .outerjoin(Report, Report.post_id == EventPost.post_id)
            .where(EventPost.event_id == event_id)
            .order_by(EventPost.created_at.asc(), EventPost.post_id.asc())
        )
    ).all()
    total_posts = len(rows)
    if total_posts == 0:
        return {
            "ready": True,
            "reason": "no_posts",
            "total_posts": 0,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "root_ready": True,
        }

    eligible_posts = 0
    ready_post_reports = 0
    root_ready = False
    dependencies: list[dict] = []
    blocked_posts = 0
    for post_id, role, comments_count, post_text, report_json in rows:
        eligible = int(comments_count or 0) >= min_comments
        has_text = bool(str(post_text or "").strip())
        has_report = _is_payload_dependency_ready(report_json if isinstance(report_json, dict) else None)
        status = report_status_from_payload(report_json if isinstance(report_json, dict) else None, fallback="")
        if eligible:
            eligible_posts += 1
            if has_report:
                ready_post_reports += 1
            elif has_text and status in {"", REPORT_STATUS_STALE}:
                dependencies.append(
                    _build_dependency(
                        JobType.BUILD_POST_REPORT,
                        entity_id=int(post_id),
                        reason="waiting_post_reports",
                    )
                )
            else:
                blocked_posts += 1
        if role == "root":
            root_ready = has_report or not eligible

    if eligible_posts == 0:
        return {
            "ready": True,
            "reason": "no_eligible_posts",
            "total_posts": total_posts,
            "eligible_posts": 0,
            "ready_post_reports": 0,
            "required_ready_post_reports": 0,
            "root_ready": True,
        }

    required_ready = max(1, math.ceil(eligible_posts * 0.7))
    ready = root_ready and ready_post_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else ("blocked_post_reports" if blocked_posts > 0 and not dependencies else "waiting_post_reports"),
        "total_posts": total_posts,
        "eligible_posts": eligible_posts,
        "ready_post_reports": ready_post_reports,
        "required_ready_post_reports": required_ready,
        "root_ready": root_ready,
        "blocked_post_reports": blocked_posts,
        "dependencies": dependencies,
    }


async def build_event_report_draft(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict:
    event = await session.get(Event, event_id)
    if event is None:
        return {"status": "not_found", "event_id": event_id}

    readiness = await _event_report_readiness(session, event_id=event_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "event_id": event_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    post_payloads = await _load_post_report_payloads_for_event(session, event_id=event_id)
    if not post_payloads:
        payload = {
            "type": "event_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "event_id": event_id,
            "event_title": event.title,
            "posts_count": int(readiness.get("total_posts") or 0),
            "source_post_reports": [],
            "summary": "Для события пока нет готовых отчетов по постам.",
            "meta": {"prompt_version": "event_report_v2", "source_type": "post_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_event_report_payload(
            event_id=event_id,
            event_title=event.title,
            post_reports=post_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    coverage, stance = _aggregate_child_coverage(post_payloads)
    payload["reactions_coverage"] = coverage
    payload["audience_stance"] = stance
    payload["meta"] = {
        **dict(payload.get("meta") or {}),
        "coverage_factor": coverage.get("factor"),
    }

    last_version = (
        await session.execute(
            select(EventReport.version)
            .where(EventReport.event_id == event_id)
            .order_by(EventReport.version.desc(), EventReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = EventReport(
        event_id=event_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "event_id": event_id, "report_id": report.id}


async def _load_latest_event_report_snapshots_for_process(session: AsyncSession, *, process_id: int) -> list[tuple[int, str | None, dict | None, str]]:
    event_rows = (
        await session.execute(
            select(ProcessEvent.event_id, Event.title)
            .join(Event, Event.id == ProcessEvent.event_id)
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()
    rows = (
        await session.execute(
            select(
                EventReport.event_id,
                EventReport.report_json,
                EventReport.version,
                EventReport.id,
            )
            .where(
                EventReport.event_id.in_(
                    select(ProcessEvent.event_id).where(ProcessEvent.process_id == process_id)
                )
            )
            .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
        )
    ).all()
    latest_by_event_id: dict[int, dict | None] = {}
    for event_id, report_json, _version, _report_id in rows:
        latest_by_event_id.setdefault(int(event_id), report_json if isinstance(report_json, dict) else None)

    snapshots: list[tuple[int, str | None, dict | None, str]] = []
    for event_id, event_title in event_rows:
        payload = latest_by_event_id.get(int(event_id))
        snapshots.append(
            (
                int(event_id),
                event_title,
                dict(payload) if isinstance(payload, dict) else None,
                report_status_from_payload(payload, fallback=""),
            )
        )
    return snapshots


async def _load_latest_event_report_payloads_for_process(session: AsyncSession, *, process_id: int) -> list[dict]:
    payloads: list[dict] = []
    for event_id, event_title, payload, _status in await _load_latest_event_report_snapshots_for_process(session, process_id=process_id):
        if not _is_payload_dependency_ready(payload):
            continue
        selected_payload = dict(payload or {})
        selected_payload.setdefault("event_id", int(event_id))
        selected_payload.setdefault("event_title", event_title)
        payloads.append(selected_payload)
    return payloads


async def _resolve_process_event_payloads(session: AsyncSession, *, process_id: int) -> tuple[list[dict], int]:
    payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    event_ids = [
        int(row[0])
        for row in (
            await session.execute(
                select(ProcessEvent.event_id)
                .where(ProcessEvent.process_id == process_id)
                .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
            )
        ).all()
    ]
    return payloads, len(event_ids)


async def _process_report_readiness(session: AsyncSession, *, process_id: int) -> dict:
    snapshots = await _load_latest_event_report_snapshots_for_process(session, process_id=process_id)
    total_events = len(snapshots)
    if total_events == 0:
        return {
            "ready": True,
            "reason": "no_events",
            "total_events": 0,
            "ready_event_reports": 0,
            "required_ready_event_reports": 0,
        }
    ready_event_reports = 0
    blocked_events = 0
    dependencies: list[dict] = []
    for event_id, _event_title, payload, status in snapshots:
        if _is_payload_dependency_ready(payload):
            ready_event_reports += 1
        elif status in {"", REPORT_STATUS_STALE}:
            dependencies.append(
                _build_dependency(
                    JobType.BUILD_EVENT_REPORT,
                    entity_id=int(event_id),
                    reason="waiting_event_reports",
                )
            )
        else:
            blocked_events += 1
    required_ready = max(1, math.ceil(total_events * 0.7))
    ready = ready_event_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else ("blocked_event_reports" if blocked_events > 0 and not dependencies else "waiting_event_reports"),
        "total_events": total_events,
        "ready_event_reports": ready_event_reports,
        "required_ready_event_reports": required_ready,
        "blocked_event_reports": blocked_events,
        "dependencies": dependencies,
    }


async def build_process_report_draft(
    session: AsyncSession,
    *,
    process_id: int,
) -> dict:
    process = await session.get(Process, process_id)
    if process is None:
        return {"status": "not_found", "process_id": process_id}

    readiness = await _process_report_readiness(session, process_id=process_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "process_id": process_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    event_payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    if not event_payloads:
        payload = {
            "type": "process_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "process_id": process_id,
            "process_title": process.title,
            "events_count": int(readiness.get("total_events") or 0),
            "source_event_reports": [],
            "summary": "Для процесса пока нет готовых отчетов по событиям или постам.",
            "meta": {"prompt_version": "process_report_v2", "source_type": "event_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_process_report_payload(
            process_id=process_id,
            process_title=process.title,
            event_reports=event_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    coverage, stance = _aggregate_child_coverage(event_payloads)
    payload["reactions_coverage"] = coverage
    payload["audience_stance"] = stance
    payload["meta"] = {
        **dict(payload.get("meta") or {}),
        "coverage_factor": coverage.get("factor"),
    }

    last_version = (
        await session.execute(
            select(ProcessReport.version)
            .where(ProcessReport.process_id == process_id)
            .order_by(ProcessReport.version.desc(), ProcessReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = ProcessReport(
        process_id=process_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "process_id": process_id, "report_id": report.id}
