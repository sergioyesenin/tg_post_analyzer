from __future__ import annotations

import copy
import json
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
    def __init__(self, paths: list[tuple[str | int, ...]] | list[str]) -> None:
        # Поддержка как кортежей (старый формат) так и строковых путей (новый формат)
        self.paths = paths
        formatted = ", ".join(
            ".".join(str(part) for part in path) if isinstance(path, tuple) else path
            for path in paths
        )
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


def _set_value_by_path(payload: dict[str, Any], path: tuple[str | int, ...], value: str) -> None:
    cur: Any = payload
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = value


def _iter_field_value_pairs(payload: dict[str, Any]) -> Iterable[tuple[tuple[str | int, ...], str]]:
    """Генератор всех публичных текстовых полей в виде (путь-кортеж, текст)."""
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
    """Публичный итератор по полям, подлежащим переводу."""
    if not isinstance(payload, dict):
        return []
    return _iter_field_value_pairs(payload)


async def _collect_path_text_map(payload: dict[str, Any]) -> dict[str, str]:
    """Собирает все непереведённые публичные текстовые поля в карту {строковый_путь: текст}."""
    result = {}
    for path_tuple, text in iter_public_text_fields(payload):
        if not is_probably_russian(text):
            path_str = ".".join(str(part) for part in path_tuple)
            result[path_str] = text
    return result


def _apply_translated_map(payload: dict[str, Any], translation_map: dict[str, str]) -> None:
    """Применяет переводы из translation_map к payload, изменяя его in-place."""
    for path_str, translated_text in translation_map.items():
        parts = []
        for part in path_str.split("."):
            if part.isdigit():
                parts.append(int(part))
            else:
                parts.append(part)
        path_tuple = tuple(parts)
        _set_value_by_path(payload, path_tuple, translated_text)


async def _translate_text_batch(texts_map: dict[str, str]) -> dict[str, str]:
    """
    Переводит значения всех полей в texts_map на русский язык за один LLM запрос.
    Возвращает словарь с теми же ключами и переведёнными значениями.
    """
    if not texts_map:
        return {}

    input_json = json.dumps(texts_map, ensure_ascii=False, indent=2)

    prompt = (
        "Ты — переводчик на русский язык. Получи JSON объект, где ключи — это идентификаторы полей, а значения — тексты на английском или смешанном языке.\n"
        "Задача: перевести каждое значение на русский язык, сохранив ключи без изменений.\n"
        "Правила:\n"
        "- Сохраняй смысл, не добавляй новых фактов.\n"
        "- Не меняй числа, даты, имена собственные, названия организаций, названия платформ, URL.\n"
        "- Не используй английские заголовки вроде Context, Public reaction, Interpretation, Consequences, Outlook.\n"
        "- Верни ТОЛЬКО JSON объект с теми же ключами и переведёнными значениями.\n"
        "Входной JSON:\n"
        f"{input_json}\n"
        "Переведённый JSON:"
    )

    cfg = OpenAIAdapterConfig.from_settings()
    
    # === ДОБАВЛЕННЫЙ БЛОК ДЛЯ ЗАГРУЗКИ РОУТЕРА ===
    router = None
    if cfg.routing_enabled:
        import os
        from pathlib import Path
        from services.llm.model_router import ModelEntry, ModelRouter
        
        file_path = os.getenv("REPORT_V2_ROUTER_MODELS_FILE")
        if not file_path:
            file_path = "services/llm/router_models.json"
        
        path = Path(file_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models = []
                for item in data:
                    models.append(ModelEntry(
                        name=item["name"],
                        provider=item["provider"],
                        base_url=item["base_url"],
                        api_key=item.get("api_key"),
                        max_tokens_per_day=item.get("max_tokens_per_day", 0),
                        max_requests_per_minute=item.get("max_requests_per_minute", 0),
                    ))
                if models:
                    router = ModelRouter(models)
                    logger.info(f"Translation ModelRouter loaded with {len(models)} models from {path}")
                else:
                    logger.warning("Translation router file contains no models")
            except Exception as e:
                logger.exception(f"Failed to load translation router from {path}: {e}")
        else:
            logger.warning(f"Translation router file not found: {path}")
    # ========================================

    adapter = OpenAIClientAdapter(cfg, router=router)

    try:
        content = await adapter.create_chat_completion(
            messages=[
                {"role": "system", "content": "Ты — полезный переводчик, возвращающий только JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
    except Exception as e:
        logger.exception("Translation batch request failed: %s", e)
        raise ReportLanguageNormalizationError(["translation_request_failed"]) from e

    if not content:
        raise ReportLanguageNormalizationError(["empty_translation_response"])

    try:
        translated_map = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse translation response as JSON: %s", content[:500])
        raise ReportLanguageNormalizationError([f"invalid_json_response: {e}"]) from e

    if not isinstance(translated_map, dict):
        raise ReportLanguageNormalizationError(["response_not_dict"])

    # Дополняем пропущенные ключи исходными текстами (fallback)
    missing_keys = set(texts_map.keys()) - set(translated_map.keys())
    if missing_keys:
        logger.warning("Translation response missing keys: %s", missing_keys)
        for key in missing_keys:
            translated_map[key] = texts_map[key]

    return translated_map


async def normalize_report_language(payload: dict, llm_adapter: OpenAIClientAdapter | None = None) -> dict:
    """
    Нормализует язык отчёта: переводит все публичные текстовые поля на русский язык.
    Выполняет один LLM запрос для всех полей.
    """
    if not isinstance(payload, dict):
        return payload

    # 1. Собираем все поля, требующие перевода
    texts_to_translate = await _collect_path_text_map(payload)
    if not texts_to_translate:
        return payload

    # 2. Пакетный перевод
    translated_map = await _translate_text_batch(texts_to_translate)

    # 3. Создаём глубокую копию и применяем переводы
    normalized = copy.deepcopy(payload)
    _apply_translated_map(normalized, translated_map)

    # 4. Финальная проверка: все ли поля стали русскими
    unresolved_paths: list[str] = []
    for path_tuple, text in iter_public_text_fields(normalized):
        if not is_probably_russian(text):
            path_str = ".".join(str(p) for p in path_tuple)
            unresolved_paths.append(path_str)
    if unresolved_paths:
        raise ReportLanguageNormalizationError(unresolved_paths)

    return normalized