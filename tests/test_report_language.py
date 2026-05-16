from __future__ import annotations

import asyncio

from services import report_language
from services import reporting


def _payload_base() -> dict:
    return {
        "type": "post_report_v2",
        "status": "ready",
        "post_id": 1,
        "title": "Report title",
        "summary": "In Belarus, authorities announced new measures.",
        "comment_count": 0,
        "sentiment": {"dominant": "neutral", "distribution": {"positive": 0.0, "negative": 0.0, "neutral": 1.0}},
        "topics": [],
        "clusters": [],
        "time_trends": [],
        "risks": [],
        "anomalies": [],
        "representative_quotes": ["Зачем?????"],
        "post_reactions": {"total_count": 0, "distinct_count": 0, "top_reactions": []},
        "comment_reactions": {"total_count": 0, "distinct_count": 0, "top_reactions": []},
        "reactions_coverage": {"is_complete": False, "factor": 0.0, "comments_scanned": 0, "comments_with_visible_reactions": 0, "expected_comments": 0},
        "audience_stance": {"label": "unclear", "confidence": "low", "reason": None},
        "confidence": {"overall": "medium", "reason": "Model output seems plausible."},
        "meta": {
            "multi_agent": {
                "steps": {
                    "synthesis": {
                        "report_text": "Context: main trend and implications.",
                        "confidence_reason": "Evidence is consistent across comments.",
                    },
                    "context": {"llm_context": {"event_summary": "Event summary", "article_focus": "Public reaction"}},
                    "public_opinion": {"main_topics": [], "dominant_reactions": []},
                    "expert": {"background": [], "interpretations": [], "consequences": []},
                },
                "retrieval": {"sources": [{"source": "https://belta.by/news"}]},
            }
        },
    }


def test_normalize_translates_english_summary(monkeypatch) -> None:
    payload = _payload_base()

    async def _fake_translate(text: str) -> str:
        return "В Беларуси власти объявили о новых мерах." if text.startswith("In Belarus") else "Переведенный фрагмент."

    monkeypatch.setattr(report_language, "translate_text_to_ru", _fake_translate)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert normalized["summary"] == "В Беларуси власти объявили о новых мерах."


def test_normalize_does_not_translate_quotes(monkeypatch) -> None:
    payload = _payload_base()

    async def _fake_translate(text: str) -> str:
        return "Переведенный фрагмент."

    monkeypatch.setattr(report_language, "translate_text_to_ru", _fake_translate)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert normalized["representative_quotes"] == ["Зачем?????"]


def test_normalize_does_not_translate_urls_or_enums(monkeypatch) -> None:
    payload = _payload_base()

    async def _fake_translate(text: str) -> str:
        return "Резюме"

    monkeypatch.setattr(report_language, "translate_text_to_ru", _fake_translate)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert normalized["status"] == "ready"
    assert normalized["meta"]["multi_agent"]["retrieval"]["sources"][0]["source"] == "https://belta.by/news"


def test_normalize_translates_multi_agent_synthesis_report_text(monkeypatch) -> None:
    payload = _payload_base()

    async def _fake_translate(text: str) -> str:
        if text.startswith("Context:"):
            return "Контекст: основной тренд и последствия."
        return "Переведенный фрагмент."

    monkeypatch.setattr(report_language, "translate_text_to_ru", _fake_translate)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert normalized["meta"]["multi_agent"]["steps"]["synthesis"]["report_text"] == "Контекст: основной тренд и последствия."


def test_normalize_is_idempotent_for_russian_report(monkeypatch) -> None:
    payload = _payload_base()
    payload["title"] = "Заголовок отчета"
    payload["summary"] = "В Беларуси объявлены новые меры."
    payload["confidence"]["reason"] = "Данные согласованы."
    payload["meta"]["multi_agent"]["steps"]["synthesis"]["report_text"] = "Основной тренд и последствия."
    payload["meta"]["multi_agent"]["steps"]["synthesis"]["confidence_reason"] = "Сигналы согласованы."
    payload["meta"]["multi_agent"]["steps"]["context"]["llm_context"]["event_summary"] = "Сводка события."
    payload["meta"]["multi_agent"]["steps"]["context"]["llm_context"]["article_focus"] = "Фокус публикации."

    async def _should_not_call(_text: str) -> str:
        raise AssertionError("translate_text_to_ru should not be called for Russian payload")

    monkeypatch.setattr(report_language, "translate_text_to_ru", _should_not_call)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert normalized["summary"] == "В Беларуси объявлены новые меры."


def test_normalize_translates_mixed_language_synthesis_phrase(monkeypatch) -> None:
    payload = _payload_base()
    payload["meta"]["multi_agent"]["steps"]["synthesis"]["report_text"] = (
        "В отчете отмечены administrative barriers, which discourage longer-term stays."
    )

    async def _fake_translate(text: str) -> str:
        if "administrative barriers" in text:
            return "В отчете отмечены административные барьеры, которые препятствуют более длительному пребыванию."
        return "Переведенный фрагмент."

    monkeypatch.setattr(report_language, "translate_text_to_ru", _fake_translate)
    normalized = asyncio.run(report_language.normalize_report_language(payload))
    assert "administrative barriers" not in normalized["meta"]["multi_agent"]["steps"]["synthesis"]["report_text"]


def test_rendered_report_contains_no_english_section_titles() -> None:
    payload = {
        "status": "ready",
        "meta": {
            "multi_agent": {
                "steps": {
                    "synthesis": {
                        "report_text": (
                            "Context: локальный фон. "
                            "Public reaction: реакция аудитории. "
                            "Interpretation: вывод. "
                            "Consequences: последствия. "
                            "Outlook: прогноз."
                        )
                    }
                }
            }
        },
    }

    summary = reporting._build_public_post_summary(payload)
    assert "Context:" not in summary
    assert "Public reaction:" not in summary
    assert "Interpretation:" not in summary
    assert "Consequences:" not in summary
    assert "Outlook:" not in summary
    assert "Контекст:" in summary
    assert "Общественная реакция:" in summary
    assert "Интерпретация:" in summary
    assert "Последствия:" in summary
    assert "Возможное развитие:" in summary


def test_renderer_keeps_enum_values_unchanged() -> None:
    payload = {
        "status": "ready",
        "audience_stance": {"label": "mixed", "confidence": "medium"},
        "meta": {"multi_agent": {"steps": {"synthesis": {"report_text": "Context: сигнал."}}}},
    }
    mapped = reporting.map_internal_post_report_to_public_payload(payload)
    assert mapped is not None
    assert mapped["status"] == "ready"
    assert mapped["audience_stance"]["label"] == "mixed"


def test_fallback_report_is_russian() -> None:
    assert reporting._build_public_post_summary({"status": "insufficient_data", "meta": {}}) == "Недостаточно данных."
    assert reporting._build_public_post_summary({"status": "limited", "meta": {}}) == "Доказательная база ограничена."
    assert reporting._build_public_post_summary({"status": "failed", "meta": {}}) == "Не удалось сформировать отчет."
