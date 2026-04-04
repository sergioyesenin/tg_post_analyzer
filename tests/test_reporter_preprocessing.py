from __future__ import annotations

import asyncio

from agents import reporter


def test_build_post_signal_summary_returns_aggregates_and_samples():
    signal_summary = reporter.build_post_signal_summary(
        post_text="Это пост про бюджет и реформы",
        comments=[],
        thread_comments=[
            {"id": 1, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:00+00:00", "text": "Хорошо, поддерживаю реформы!"},
            {"id": 2, "parent_id": 1, "depth": 1, "date": "2026-03-31T10:01:00+00:00", "text": "Это бред, опять ложь?"},
            {"id": 3, "parent_id": 2, "depth": 2, "date": "2026-03-31T10:02:00+00:00", "text": "Смотрите https://example.com детали"},
        ],
        views=120,
    )

    assert signal_summary["comment_count"] == 3
    assert signal_summary["views"] == 120
    assert signal_summary["thread_shape"] == {
        "root_comments": 1,
        "replies_level_1": 1,
        "replies_deeper": 1,
    }
    assert signal_summary["top_keywords"]
    assert signal_summary["representative_samples"]
    assert len(signal_summary["representative_samples"]) <= 8
    assert "named_entities" in signal_summary
    assert "nlp_backend" in signal_summary
    assert "post_keyword_overlap" in signal_summary
    assert signal_summary["sentiment_hint"]["dominant_hint"] in {"positive", "negative", "neutral"}
    assert signal_summary["sentiment_hint"]["backend"] in {"transformers", "fallback_neutral"}
    assert signal_summary["nlp_backend"]["lemmatizer"] in {"natasha", "regex_fallback"}


def test_generate_post_report_payload_uses_preprocessed_signal_summary(monkeypatch):
    captured = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {
                            "message": type(
                                "_Msg",
                                (),
                                {
                                    "content": (
                                        '{"type":"post_report_v2","status":"ready","title":"t","summary":"s",'
                                        '"sentiment":{"dominant":"neutral","distribution":{"positive":0.1,"negative":0.2,"neutral":0.7}}}'
                                    )
                                },
                            )()
                        },
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=42,
            published_at_iso="2026-03-31T10:00:00+00:00",
            post_text="Пост про реформы и бюджет",
            comments=[
                "Первый сырой комментарий с длинным текстом",
                "Второй сырой комментарий",
            ],
            thread_comments=[
                {"id": 1, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:10+00:00", "text": "Первый сырой комментарий с длинным текстом"},
                {"id": 2, "parent_id": 1, "depth": 1, "date": "2026-03-31T10:00:20+00:00", "text": "Второй сырой комментарий"},
            ],
            views=88,
            config=reporter.ReportConfig(min_comments=0),
        )
    )

    prompt = captured["messages"][1]["content"]
    assert "post_signal_summary" in prompt
    assert "representative_samples" in prompt
    assert '"comment_count": 2' in prompt
    assert '"named_entities"' in prompt
    assert '"nlp_backend"' in prompt
    assert payload["comment_count"] == 2
    assert payload["meta"]["input_mode"] == "preprocessed_signals_v1"
    assert payload["meta"]["input_summary"]["sample_count"] >= 1


def test_generate_post_report_payload_retries_and_returns_valid_failed_fallback(monkeypatch):
    calls = {"count": 0}

    async def _fake_acompletion(**kwargs):
        calls["count"] += 1
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {
                            "message": type(
                                "_Msg",
                                (),
                                {
                                    "content": "not valid json at all",
                                },
                            )()
                        },
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=77,
            published_at_iso="2026-03-31T10:00:00+00:00",
            post_text="Тестовый пост",
            comments=["Комментарий один", "Комментарий два"],
            thread_comments=[
                {"id": 1, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:10+00:00", "text": "Комментарий один"},
                {"id": 2, "parent_id": 1, "depth": 1, "date": "2026-03-31T10:00:20+00:00", "text": "Комментарий два"},
            ],
            views=42,
            config=reporter.ReportConfig(min_comments=0),
        )
    )

    assert calls["count"] == reporter.POST_REPORT_MAX_RETRIES
    assert payload["status"] == "failed"
    assert payload["type"] == "post_report_v2"
    assert payload["post_id"] == 77
    assert payload["meta"]["fallback_reason"] == "invalid_model_output"
    assert payload["anomalies"] == ["model_output_invalid"]
