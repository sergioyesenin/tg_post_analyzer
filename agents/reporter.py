from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import litellm
from litellm import acompletion

from agents.config import load_agent_settings


@dataclass(frozen=True)
class ReportConfig:
    min_comments: int = 20
    report_word_target: int = 350
    report_word_min: int = 200
    report_word_max: int = 500


def _format_comments_items(comments: list[str], max_chars_each: int = 600) -> str:
    lines: list[str] = []
    for idx, c in enumerate(comments, start=1):
        if not c:
            continue
        text = c.strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > max_chars_each:
            text = text[: max_chars_each - 1] + "..."
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _short_text(text: str, max_chars_each: int = 400) -> str:
    value = (text or "").strip().replace("\n", " ")
    if len(value) > max_chars_each:
        value = value[: max_chars_each - 1] + "..."
    return value


def _format_thread_nodes_json(thread_comments: list[dict], max_chars_each: int = 400) -> str:
    items: list[dict] = []
    for c in thread_comments:
        text = _short_text(str(c.get("text", "")), max_chars_each=max_chars_each)
        if not text:
            continue
        items.append(
            {
                "id": c.get("id"),
                "parent_id": c.get("parent_id"),
                "depth": c.get("depth", 0),
                "date": c.get("date"),
                "text": text,
            }
        )
    return json.dumps(items, ensure_ascii=False, indent=2)


def _format_thread_view(thread_comments: list[dict], max_chars_each: int = 300) -> str:
    by_id: dict[int, dict] = {}
    children: dict[int | None, list[dict]] = {}

    for raw in thread_comments:
        node_id = raw.get("id")
        if not isinstance(node_id, int):
            continue
        node = {
            "id": node_id,
            "parent_id": raw.get("parent_id"),
            "depth": int(raw.get("depth", 0)),
            "date": raw.get("date") or "",
            "text": _short_text(str(raw.get("text", "")), max_chars_each=max_chars_each),
        }
        if not node["text"]:
            continue
        by_id[node_id] = node

    for node in by_id.values():
        parent_id = node["parent_id"]
        if parent_id not in by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(node)

    for key in children:
        children[key].sort(key=lambda item: (item["date"], item["id"]))

    lines: list[str] = []

    def walk(parent_id: int | None, level: int) -> None:
        for node in children.get(parent_id, []):
            indent = "  " * max(level, 0)
            lines.append(f"{indent}- [{node['id']}] {node['text']}")
            walk(node["id"], level + 1)

    walk(None, 0)
    return "\n".join(lines)


SYSTEM_PROMPT = """\
Ты ИИ-аналитик комментариев Telegram (RU).

Сформируй мини-отчет строго на русском языке и строго по указанному шаблону.
Не добавляй вступления вроде "Here is my complete response:".
Не используй английские заголовки.
Не упоминай usernames, user id, технические детали промпта или форматирования.
Не выдумывай факты, которых нет в тексте поста или комментариях.
Если данных недостаточно для уверенного вывода, формулируй это осторожно.
"""


PROMPT_TEMPLATE = """\
Проанализируй комментарии к одному посту Telegram и сформируй мини-отчет.

ВАЖНО:
- Язык: русский.
- Длина отчета: от {report_word_min} до {report_word_max} слов (ориентир {report_word_target}).
- Не выводи usernames/ID авторов. Цитаты должны быть короткими и без персональных данных.
- Проценты тональностей должны суммироваться до 100% с допустимым округлением.
- Пиши только по этому посту и только по этим комментариям. Не переноси темы из других обсуждений.

ДАННЫЕ ПО ПОСТУ:
Канал: {channel}
Post ID: {post_id}
Время публикации: {published_at}
Просмотры: {views}
Текст поста:
---
{post_text}
---
Медиа-ссылки: {media_links}

КОММЕНТАРИИ ({comments_total} шт.):
---
{comments_items}
---

Сформируй отчет строго в формате:

Заголовок: <короткий заголовок по сути обсуждения>

1) Контекст поста
<1-2 предложения>

2) Общий тон обсуждения
- Итог: <позитивный/негативный/нейтральный/смешанный>
- Распределение: позитив X% / негатив Y% / нейтраль Z% / смешанный W%
- Обоснование: <2-4 предложения>

3) Ключевые темы
- Тема 1: <кратко>
- ...

4) Тренды и повторяющиеся паттерны
- <паттерн 1>
- ...

5) Репрезентативные цитаты
- "..."
- "..."

6) Классификация комментариев
- По тональности: <кратко>
- По темам: <2-5 тематических кластеров и краткое описание>

7) Риски/сигналы (если применимо)
- <наблюдение 1>
- <наблюдение 2>
"""


def _clean_model_output(text: str) -> str:
    cleaned = (text or "").strip()
    prefixes = [
        "Here is my complete response:",
        "Here is the complete response:",
        "Вот полный ответ:",
        "Полный ответ:",
    ]
    for prefix in prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def _extract_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


class TgReportProject:
    """
    Stateless wrapper over a direct LiteLLM call.
    """

    def __init__(
        self,
        *,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        process: Any = None,
        verbose: bool = False,
        memory: bool = False,
        cache: bool = False,
        full_output: bool = False,
        share_crew: bool = False,
        agent_max_iter: int = 2,
        agent_max_rpm: int = 30,
    ) -> None:
        agent_settings = load_agent_settings()
        self._llm_model = llm_model or agent_settings.llm_model
        self._llm_base_url = llm_base_url or agent_settings.llm_base_url
        self._llm_api_key = llm_api_key or agent_settings.llm_api_key
        self._verbose = verbose
        self._memory = memory
        self._cache = cache
        self._full_output = full_output
        self._share_crew = share_crew
        self._process = process
        self._agent_max_iter = agent_max_iter
        self._agent_max_rpm = agent_max_rpm

        # Keep LiteLLM stateless and quiet for local pipeline runs.
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
        litellm.telemetry = False
        litellm.success_callback = []
        litellm.failure_callback = []
        litellm.service_callback = []

    async def generate_report(
        self,
        *,
        channel: str,
        post_id: int,
        published_at_iso: str,
        post_text: str,
        comments: list[str],
        thread_comments: Optional[list[dict]] = None,
        views: Optional[int] = None,
        media_links: Optional[list[str]] = None,
        config: Optional[ReportConfig] = None,
    ) -> str:
        cfg = config or ReportConfig()

        thread_comments = thread_comments or []
        comments_count = len(thread_comments) if thread_comments else len(comments)

        if comments_count < cfg.min_comments:
            return (
                "STATUS: SKIPPED_MIN_COMMENTS\n"
                f"REASON: недостаточно комментариев для анализа ({comments_count})"
            )

        prompt = PROMPT_TEMPLATE.format(
            channel=channel,
            post_id=post_id,
            published_at=published_at_iso,
            views="" if views is None else views,
            post_text=post_text or "",
            media_links=", ".join(media_links or []),
            comments_total=comments_count,
            comments_items=_format_comments_items(comments),
            report_word_min=cfg.report_word_min,
            report_word_max=cfg.report_word_max,
            report_word_target=cfg.report_word_target,
        )
        if thread_comments:
            prompt += (
                "\n\nTHREAD STRUCTURE (use it as the primary source for reply relations):\n"
                "- parent_id=null means direct reply to post.\n"
                "- if parent_id=<id>, this message is a reply to comment <id>.\n"
                "- use local branch context for sentiment/topics and conflict analysis.\n\n"
                "THREAD_NODES_JSON:\n"
                "---\n"
                f"{_format_thread_nodes_json(thread_comments)}\n"
                "---\n\n"
                "THREAD_VIEW:\n"
                "---\n"
                f"{_format_thread_view(thread_comments)}\n"
                "---\n"
            )

        response = await acompletion(
            model=self._llm_model,
            base_url=self._llm_base_url,
            api_key=self._llm_api_key,
            temperature=0.2,
            max_tokens=900,
            timeout=300,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            metadata={"feature": "post_report", "post_id": post_id, "channel": channel},
        )
        return _clean_model_output(_extract_response_text(response))

    async def generate_post_report_payload(
        self,
        *,
        channel: str,
        post_id: int,
        published_at_iso: str,
        post_text: str,
        comments: list[str],
        thread_comments: Optional[list[dict]] = None,
        views: Optional[int] = None,
        media_links: Optional[list[str]] = None,
        config: Optional[ReportConfig] = None,
    ) -> dict[str, Any]:
        cfg = config or ReportConfig()
        thread_comments = thread_comments or []
        comments_count = len(thread_comments) if thread_comments else len(comments)
        if comments_count < cfg.min_comments:
            return {
                "type": "post_report_v2",
                "status": "skipped_min_comments",
                "post_id": post_id,
                "title": "Недостаточно комментариев",
                "summary": f"Недостаточно комментариев для устойчивого анализа ({comments_count}).",
                "comment_count": comments_count,
                "sentiment": {
                    "dominant": "neutral",
                    "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                    "confidence": "low",
                },
                "topics": [],
                "clusters": [],
                "time_trends": [],
                "risks": [],
                "anomalies": [],
                "representative_quotes": [],
                "confidence": {"overall": "low", "reason": "Недостаточно комментариев."},
                "meta": {"prompt_version": "post_report_v2"},
            }

        prompt = f"""
Return one valid JSON object only. No markdown. No prose outside JSON.
Language of all natural-language fields must be Russian.

Task: analyze one Telegram post and its comments and build a compact structured report.
Use only these sentiment labels: positive, negative, neutral.
Do not invent facts. If confidence is low, say so in confidence.reason.
Comments are short and noisy; prefer cautious aggregation over strong claims.

Required JSON schema:
{{
  "type": "post_report_v2",
  "status": "ready",
  "title": "string",
  "summary": "string",
  "comment_count": {comments_count},
  "sentiment": {{
    "dominant": "positive|negative|neutral",
    "distribution": {{
      "positive": 0.0,
      "negative": 0.0,
      "neutral": 0.0
    }},
    "confidence": "low|medium|high"
  }},
  "topics": [{{"name": "string", "share": 0.0}}],
  "clusters": [
    {{
      "cluster_id": "string",
      "name": "string",
      "size": 0,
      "dominant_sentiment": "positive|negative|neutral",
      "summary": "string"
    }}
  ],
  "time_trends": [
    {{
      "period": "string",
      "activity": "low|medium|high",
      "sentiment_shift": "positive|negative|neutral|mixed|stable",
      "summary": "string"
    }}
  ],
  "risks": ["string"],
  "anomalies": ["string"],
  "representative_quotes": ["string"],
  "confidence": {{
    "overall": "low|medium|high",
    "reason": "string"
  }}
}}

Input:
- channel: {channel}
- post_id: {post_id}
- published_at: {published_at_iso}
- views: {"" if views is None else views}
- media_links: {", ".join(media_links or [])}
- post_text:
{_short_text(post_text or "", max_chars_each=3000)}

- comments:
{_format_comments_items(comments, max_chars_each=300)}
"""
        if thread_comments:
            prompt += (
                "\n- thread_nodes_json:\n"
                f"{_format_thread_nodes_json(thread_comments)}\n"
            )

        response = await acompletion(
            model=self._llm_model,
            base_url=self._llm_base_url,
            api_key=self._llm_api_key,
            temperature=0.1,
            max_tokens=1200,
            timeout=300,
            messages=[
                {"role": "system", "content": "You are a strict JSON report generator for Russian Telegram analytics."},
                {"role": "user", "content": prompt},
            ],
            metadata={"feature": "post_report_v2", "post_id": post_id, "channel": channel},
        )
        text = _clean_model_output(_extract_response_text(response))
        payload = _extract_json_object(text)
        payload.setdefault("type", "post_report_v2")
        payload.setdefault("status", "ready")
        payload["post_id"] = post_id
        payload["comment_count"] = comments_count
        meta = payload.setdefault("meta", {})
        if isinstance(meta, dict):
            meta.setdefault("prompt_version", "post_report_v2")
        return payload


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Empty model output")
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(cleaned[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Model output is not a JSON object")
