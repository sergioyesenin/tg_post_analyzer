from __future__ import annotations

import copy
import logging
import re
from collections.abc import Iterable
from typing import Any

from services.llm.openai_client import OpenAIAdapterConfig, OpenAIClientAdapter

logger = logging.getLogger(__name__)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ENGLISH_PHRASE_RE = re.compile(r"\b([A-Za-z][A-Za-z'-]{1,})\s+([A-Za-z][A-Za-z'-]{1,})\b")
_ENGLISH_ALLOWLIST = {
    "api",
    "ui",
    "ux",
    "url",
    "llm",
    "kpi",
    "telegram",
    "openai",
    "youtube",
    "tiktok",
}


class ReportLanguageNormalizationError(RuntimeError):
    def __init__(self, paths: list[tuple[str | int, ...]]) -> None:
        self.paths = paths
        formatted = ", ".join(".".join(str(part) for part in path) for path in paths)
        super().__init__(f"public_fields_not_russian_after_normalization: {formatted}")


def _has_non_allowed_english_phrase(value: str) -> bool:
    for m in _ENGLISH_PHRASE_RE.finditer(value):
        w1 = str(m.group(1) or "").lower()
        w2 = str(m.group(2) or "").lower()
        if w1 in _ENGLISH_ALLOWLIST and w2 in _ENGLISH_ALLOWLIST:
            continue
        return True
    return False


def is_probably_russian(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    cyr = len(_CYRILLIC_RE.findall(value))
    lat = len(_LATIN_RE.findall(value))
    if cyr == 0 and lat == 0:
        return True
    if cyr == 0 and lat > 0:
        letter_count = len(re.findall(r"[A-Za-zА-Яа-яЁё]", value))
        if letter_count <= 4:
            return True
    if cyr >= lat and not _has_non_allowed_english_phrase(value):
        return True
    return False


def _iter_field_value_pairs(payload: dict[str, Any]) -> Iterable[tuple[tuple[str | int, ...], str]]:
    def value_by_path(path: tuple[str | int, ...]) -> str | None:
        cur: Any = payload
        for key in path:
            if isinstance(key, int):
                if not isinstance(cur, list) or key >= len(cur):
                    return None
                cur = cur[key]
            else:
                if not isinstance(cur, dict) or key not in cur:
                    return None
                cur = cur[key]
        return cur if isinstance(cur, str) else None

    static_paths: list[tuple[str | int, ...]] = [
        ("title",),
        ("summary",),
        ("confidence", "reason"),
        ("audience_stance", "reason"),
        ("meta", "multi_agent", "steps", "synthesis", "report_text"),
        ("meta", "multi_agent", "steps", "synthesis", "confidence_reason"),
        ("meta", "multi_agent", "steps", "context", "llm_context", "event_summary"),
        ("meta", "multi_agent", "steps", "context", "llm_context", "article_focus"),
    ]
    for path in static_paths:
        text = value_by_path(path)
        if isinstance(text, str) and text.strip():
            yield path, text

    for idx, item in enumerate(payload.get("topics") or []):
        if isinstance(item, dict) and isinstance(item.get("name"), str) and str(item["name"]).strip():
            yield ("topics", idx, "name"), str(item["name"])

    for idx, item in enumerate(payload.get("clusters") or []):
        if isinstance(item, dict):
            name = item.get("name")
            summary = item.get("summary")
            if isinstance(name, str) and name.strip():
                yield ("clusters", idx, "name"), name
            if isinstance(summary, str) and summary.strip():
                yield ("clusters", idx, "summary"), summary

    for idx, item in enumerate(payload.get("time_trends") or []):
        if isinstance(item, dict) and isinstance(item.get("summary"), str) and str(item["summary"]).strip():
            yield ("time_trends", idx, "summary"), str(item["summary"])

    for idx, item in enumerate(payload.get("risks") or []):
        if isinstance(item, str) and item.strip():
            yield ("risks", idx), item

    for idx, item in enumerate(payload.get("anomalies") or []):
        if isinstance(item, str) and item.strip():
            yield ("anomalies", idx), item

    po = ((((payload.get("meta") or {}).get("multi_agent") or {}).get("steps") or {}).get("public_opinion") or {})
    for idx, item in enumerate(po.get("main_topics") or []):
        if isinstance(item, str) and item.strip():
            yield ("meta", "multi_agent", "steps", "public_opinion", "main_topics", idx), item

    for idx, item in enumerate(po.get("dominant_reactions") or []):
        if isinstance(item, dict) and isinstance(item.get("text"), str) and str(item["text"]).strip():
            yield ("meta", "multi_agent", "steps", "public_opinion", "dominant_reactions", idx, "text"), str(item["text"])

    llm_po = po.get("llm_public_opinion") if isinstance(po.get("llm_public_opinion"), dict) else {}
    for idx, item in enumerate(llm_po.get("main_topics") or []):
        if isinstance(item, str) and item.strip():
            yield ("meta", "multi_agent", "steps", "public_opinion", "llm_public_opinion", "main_topics", idx), item

    for idx, item in enumerate(llm_po.get("dominant_reactions") or []):
        if isinstance(item, dict) and isinstance(item.get("text"), str) and str(item["text"]).strip():
            yield (
                "meta",
                "multi_agent",
                "steps",
                "public_opinion",
                "llm_public_opinion",
                "dominant_reactions",
                idx,
                "text",
            ), str(item["text"])

    expert = ((((payload.get("meta") or {}).get("multi_agent") or {}).get("steps") or {}).get("expert") or {})
    for section in ("background", "interpretations", "consequences"):
        for idx, item in enumerate(expert.get(section) or []):
            if isinstance(item, dict) and isinstance(item.get("text"), str) and str(item["text"]).strip():
                yield ("meta", "multi_agent", "steps", "expert", section, idx, "text"), str(item["text"])


def iter_public_text_fields(payload: dict) -> Iterable[tuple[tuple[str | int, ...], str]]:
    if not isinstance(payload, dict):
        return []
    return _iter_field_value_pairs(payload)


def _set_value_by_path(payload: dict[str, Any], path: tuple[str | int, ...], value: str) -> None:
    cur: Any = payload
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = value


async def translate_text_to_ru(text: str) -> str:
    prompt = (
        "Переведи текст на русский язык.\n\n"
        "Требования:\n"
        "- сохрани смысл без добавления новых фактов;\n"
        "- не меняй числа, даты, имена, названия организаций, названия платформ, URL;\n"
        "- не добавляй пояснений;\n"
        "- не используй английские заголовки вроде Context, Public reaction, Interpretation, Consequences, Outlook;\n"
        "- верни только перевод."
    )
    cfg = OpenAIAdapterConfig.from_settings()
    adapter = OpenAIClientAdapter(cfg)
    content = await adapter.create_chat_completion(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
    )
    return str(content or "").strip()


async def normalize_report_language(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    normalized = copy.deepcopy(payload)
    translated_paths: list[str] = []
    for path, text in list(iter_public_text_fields(normalized)):
        if is_probably_russian(text):
            continue
        translated = await translate_text_to_ru(text)
        if not translated:
            logger.warning("Language normalization returned empty translation for path=%s", ".".join(str(p) for p in path))
            continue
        _set_value_by_path(normalized, path, translated)
        translated_paths.append(".".join(str(p) for p in path))

    if translated_paths:
        logger.warning(
            "report language normalized",
            extra={
                "fields": translated_paths,
                "source_lang": "en_or_mixed",
                "target_lang": "ru",
            },
        )

    unresolved: list[tuple[str | int, ...]] = []
    for path, text in list(iter_public_text_fields(normalized)):
        if not is_probably_russian(text):
            unresolved.append(path)
    if unresolved:
        raise ReportLanguageNormalizationError(unresolved)
    return normalized
