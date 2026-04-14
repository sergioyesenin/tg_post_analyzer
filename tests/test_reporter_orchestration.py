from __future__ import annotations

import asyncio

from agents import reporter


def _valid_response_json() -> str:
    return (
        '{"type":"post_report_v2","status":"ready","title":"t","summary":"s",'
        '"sentiment":{"dominant":"neutral","distribution":{"positive":0.1,"negative":0.2,"neutral":0.7}},'
        '"topics":[],"clusters":[],"time_trends":[],"risks":[],"anomalies":[],"representative_quotes":[],'
        '"confidence":{"overall":"high","reason":"ok"}}'
    )


def _strong_thread_comments() -> list[dict]:
    return [
        {"id": 1, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:10+00:00", "text": "Поддерживаю реформы и считаю решение полезным."},
        {"id": 2, "parent_id": 1, "depth": 1, "date": "2026-03-31T10:00:20+00:00", "text": "Важно, что в посте есть конкретика по бюджету."},
        {"id": 3, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:30+00:00", "text": "Хорошо, что автор объяснил последствия для регионов."},
        {"id": 4, "parent_id": 3, "depth": 1, "date": "2026-03-31T10:00:40+00:00", "text": "Согласен, особенно по срокам и приоритетам."},
        {"id": 5, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:50+00:00", "text": "Нужен контроль исполнения, но направление выглядит здраво."},
        {"id": 6, "parent_id": 5, "depth": 1, "date": "2026-03-31T10:01:00+00:00", "text": "Да, тема бюджета и реформ здесь раскрыта лучше обычного."},
    ]


def _strong_comments() -> list[str]:
    return [item["text"] for item in _strong_thread_comments()]


def _compliant_signal_summary() -> dict:
    return {
        "comment_count": 6,
        "views": 120,
        "top_keywords": [{"term": "реформа"}, {"term": "бюджет"}, {"term": "регион"}],
        "named_entities": {"persons": [], "organizations": ["Минфин"], "locations": ["регион"]},
        "representative_samples": [{"text": item["text"]} for item in _strong_thread_comments()[:5]],
        "article_sufficiency": "sufficient",
        "comment_sufficiency": "sufficient",
        "sufficiency": "sufficient",
        "discussion_state": "stable",
        "weak_signal": False,
        "public_opinion_strength": "strong",
        "evidence_candidates": [{"id": 1, "text": "Поддерживаю реформы и считаю решение полезным.", "score": 3}],
        "nlp_backend": {
            "sentiment_diagnostics": {
                "backend": "test",
                "model": None,
                "configured": False,
                "transformers_available": False,
            }
        },
        "sentiment_hint": {
            "dominant_hint": "positive",
            "distribution_hint": {"positive": 0.6, "negative": 0.1, "neutral": 0.3},
            "confidence": "medium",
            "backend": "test",
        },
    }


def test_generate_post_report_payload_records_sequential_stage_execution_and_budget(monkeypatch):
    async def _fake_acompletion(**kwargs):
        assert kwargs["timeout"] == 50
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {"message": type("_Msg", (), {"content": _valid_response_json()})()},
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    monkeypatch.setattr(reporter, "build_post_signal_summary", lambda **kwargs: _compliant_signal_summary())
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=55,
            published_at_iso="2026-03-31T10:00:00+00:00",
            post_text="Подробный пост про реформы бюджета и региональные последствия.",
            comments=_strong_comments(),
            thread_comments=_strong_thread_comments(),
            views=88,
            config=reporter.ReportConfig(min_comments=0),
            job_timeout_seconds=60,
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "ready"
    assert multi_agent["orchestration"]["sequence"] == ["context", "routing", "expert", "public_opinion", "synthesis"]
    assert multi_agent["orchestration"]["requested_rerun_stage"] is None
    assert multi_agent["orchestration"]["timeout_budget"]["job_timeout_seconds"] == 60
    assert multi_agent["orchestration"]["timeout_budget"]["synthesis_timeout_seconds"] == 50
    assert multi_agent["review_iterations"] == 1
    assert multi_agent["stages"]["reviewer"]["decision"] == "accept"
    for stage_name in reporter.POST_REPORT_STAGE_SEQUENCE:
        assert multi_agent["stages"][stage_name]["status"] == "completed"
        assert multi_agent["stages"][stage_name]["run_count"] == 1


def test_generate_post_report_payload_reviewer_requests_single_rerun_and_caps_iterations(monkeypatch):
    async def _fake_acompletion(**kwargs):
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {"message": type("_Msg", (), {"content": _valid_response_json()})()},
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=56,
            published_at_iso="2026-03-31T10:00:00+00:00",
            post_text="Тестовый пост",
            comments=["Комментарий один", "Комментарий два"],
            thread_comments=[
                {"id": 1, "parent_id": None, "depth": 0, "date": "2026-03-31T10:00:10+00:00", "text": "Комментарий один"},
                {"id": 2, "parent_id": 1, "depth": 1, "date": "2026-03-31T10:00:20+00:00", "text": "Комментарий два"},
            ],
            views=88,
            config=reporter.ReportConfig(min_comments=0),
            rerun_stage="expert",
        )
    )

    multi_agent = payload["meta"]["multi_agent"]
    assert payload["status"] == "insufficient_data"
    assert multi_agent["orchestration"]["requested_rerun_stage"] == "expert"
    assert multi_agent["orchestration"]["executed_rerun_stage"] == "synthesis"
    assert multi_agent["review_iterations"] == 2
    assert multi_agent["stages"]["context"]["run_count"] == 1
    assert multi_agent["stages"]["routing"]["run_count"] == 1
    assert multi_agent["stages"]["expert"]["run_count"] == 2
    assert multi_agent["stages"]["public_opinion"]["run_count"] == 2
    assert multi_agent["stages"]["synthesis"]["run_count"] == 3
    assert multi_agent["stages"]["expert"]["rerun_requested"] is True
    assert multi_agent["stages"]["reviewer"]["history"][0]["decision"] == "rerun"
    assert multi_agent["stages"]["reviewer"]["history"][1]["decision"] == "downgrade"


def test_generate_post_report_payload_returns_failed_fallback_with_stage_trace_when_synthesis_fails(monkeypatch):
    async def _fake_acompletion(**kwargs):
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {"message": type("_Msg", (), {"content": "not valid json"})()},
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    monkeypatch.setattr(reporter, "build_post_signal_summary", lambda **kwargs: _compliant_signal_summary())
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=57,
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

    assert payload["status"] == "failed"
    assert payload["meta"]["multi_agent"]["stages"]["context"]["run_count"] == 1
    assert payload["meta"]["multi_agent"]["stages"]["synthesis"]["status"] == "failed"
    assert payload["meta"]["multi_agent"]["orchestration"]["sequence"] == ["context", "routing", "expert", "public_opinion", "synthesis"]


def test_generate_post_report_payload_reviewer_accepts_compliant_synthesis(monkeypatch):
    async def _fake_acompletion(**kwargs):
        return type(
            "_Resp",
            (),
            {
                "choices": [
                    type(
                        "_Choice",
                        (),
                        {"message": type("_Msg", (), {"content": _valid_response_json()})()},
                    )()
                ]
            },
        )()

    monkeypatch.setattr(reporter, "acompletion", _fake_acompletion)
    monkeypatch.setattr(reporter, "build_post_signal_summary", lambda **kwargs: _compliant_signal_summary())
    project = reporter.TgReportProject(llm_model="test-model", llm_base_url="http://localhost", llm_api_key="x")

    payload = asyncio.run(
        project.generate_post_report_payload(
            channel="@demo",
            post_id=58,
            published_at_iso="2026-03-31T10:00:00+00:00",
            post_text="Подробный пост про реформы бюджета и региональные последствия.",
            comments=_strong_comments(),
            thread_comments=_strong_thread_comments(),
            views=120,
            config=reporter.ReportConfig(min_comments=0),
        )
    )

    assert payload["status"] == "ready"
    assert payload["meta"]["multi_agent"]["review_iterations"] == 1
    assert payload["meta"]["multi_agent"]["stages"]["reviewer"]["decision"] == "accept"
    assert payload["meta"]["multi_agent"]["final_status"] == "ready"
