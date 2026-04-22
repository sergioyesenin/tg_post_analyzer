from __future__ import annotations

import asyncio

from services.llm import openai_client
from services.llm.openai_client import OpenAIAdapterConfig, OpenAIClientAdapter


def test_openai_adapter_config_from_settings(monkeypatch) -> None:
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_MODEL", "gpt-test")
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_FALLBACK_MODELS", ["m1", "m2"])
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_ROUTING_ENABLED", False)
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_BASE_URL", "https://llm.example/v1")
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_API_KEY", "secret")
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_TIMEOUT_SEC", 33.0)
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_OPENAI_MAX_RETRIES", 4)
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_LOCAL_FALLBACK_ENABLED", True)
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_LOCAL_MODEL", "llama-local")
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_LOCAL_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr("services.llm.openai_client.settings.REPORT_V2_LOCAL_API_KEY", "local-secret")

    cfg = OpenAIAdapterConfig.from_settings()

    assert cfg == OpenAIAdapterConfig(
        model="gpt-test",
        fallback_models=("m1", "m2"),
        routing_enabled=False,
        base_url="https://llm.example/v1",
        api_key="secret",
        timeout_sec=33.0,
        max_retries=4,
        local_fallback_enabled=True,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key="local-secret",
    )


def test_openai_adapter_initializes_sdk_client_with_expected_params(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = object()

    monkeypatch.setattr(openai_client, "AsyncOpenAI", _FakeAsyncOpenAI)

    cfg = OpenAIAdapterConfig(
        model="gpt-test",
        fallback_models=(),
        routing_enabled=False,
        base_url="https://llm.example/v1",
        api_key="secret",
        timeout_sec=21.5,
        max_retries=5,
        local_fallback_enabled=False,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg)

    assert adapter.client is not None
    assert captured == {
        "api_key": "secret",
        "base_url": "https://llm.example/v1",
        "timeout": 21.5,
        "max_retries": 5,
    }


def test_openai_adapter_create_chat_completion_returns_message_content() -> None:
    class _FakeCompletions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "gpt-test"
            assert kwargs["messages"][0]["role"] == "system"
            return type(
                "_Resp",
                (),
                {
                    "choices": [
                        type(
                            "_Choice",
                            (),
                            {"message": type("_Msg", (), {"content": "{\"ok\":true}"})()},
                        )()
                    ]
                },
            )()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    cfg = OpenAIAdapterConfig(
        model="gpt-test",
        fallback_models=(),
        routing_enabled=False,
        base_url=None,
        api_key=None,
        timeout_sec=30,
        max_retries=2,
        local_fallback_enabled=False,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg, client=_FakeClient())

    result = asyncio.run(
        adapter.create_chat_completion(
            messages=[{"role": "system", "content": "you are helpful"}],
            response_format={"type": "json_object"},
        )
    )

    assert result == "{\"ok\":true}"


def test_openai_adapter_fallbacks_to_next_model_on_failure() -> None:
    attempts: list[str] = []

    class _FakeCompletions:
        async def create(self, **kwargs):
            model = kwargs["model"]
            attempts.append(model)
            if model == "broken-model":
                raise RuntimeError("primary failed")
            return type(
                "_Resp",
                (),
                {
                    "choices": [
                        type("_Choice", (), {"message": type("_Msg", (), {"content": "ok-from-fallback"})()})()
                    ]
                },
            )()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    cfg = OpenAIAdapterConfig(
        model="broken-model",
        fallback_models=("backup-model",),
        routing_enabled=False,
        base_url=None,
        api_key=None,
        timeout_sec=30,
        max_retries=2,
        local_fallback_enabled=False,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg, client=_FakeClient())

    result = asyncio.run(adapter.create_chat_completion(messages=[{"role": "system", "content": "x"}]))
    assert result == "ok-from-fallback"
    assert attempts == ["broken-model", "backup-model"]


def test_openai_adapter_uses_local_fallback_when_primary_models_fail() -> None:
    class _FailCompletions:
        async def create(self, **kwargs):
            raise RuntimeError(f"upstream fail {kwargs['model']}")

    class _PrimaryChat:
        completions = _FailCompletions()

    class _PrimaryClient:
        chat = _PrimaryChat()

    class _LocalCompletions:
        async def create(self, **kwargs):
            return type(
                "_Resp",
                (),
                {
                    "choices": [
                        type("_Choice", (), {"message": type("_Msg", (), {"content": "ok-local"})()})()
                    ]
                },
            )()

    class _LocalChat:
        completions = _LocalCompletions()

    class _LocalClient:
        chat = _LocalChat()

    cfg = OpenAIAdapterConfig(
        model="broken-1",
        fallback_models=("broken-2",),
        routing_enabled=False,
        base_url=None,
        api_key=None,
        timeout_sec=30,
        max_retries=2,
        local_fallback_enabled=True,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg, client=_PrimaryClient(), local_client=_LocalClient())

    result = asyncio.run(adapter.create_chat_completion(messages=[{"role": "system", "content": "x"}]))
    assert result == "ok-local"


def test_openai_adapter_initializes_local_fallback_client_without_explicit_local_api_key(monkeypatch) -> None:
    captured_calls: list[dict[str, object]] = []

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured_calls.append(dict(kwargs))
            self.chat = object()

    monkeypatch.setattr(openai_client, "AsyncOpenAI", _FakeAsyncOpenAI)

    cfg = OpenAIAdapterConfig(
        model="primary",
        fallback_models=(),
        routing_enabled=False,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-real",
        timeout_sec=12.0,
        max_retries=2,
        local_fallback_enabled=True,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg)

    assert adapter.client is not None
    assert adapter.local_client is not None
    assert len(captured_calls) == 2
    assert captured_calls[1]["api_key"] == "local-fallback-key"


def test_openai_adapter_routes_models_via_extra_body_when_enabled() -> None:
    captured: dict[str, object] = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return type(
                "_Resp",
                (),
                {
                    "choices": [
                        type("_Choice", (), {"message": type("_Msg", (), {"content": "ok-routed"})()})()
                    ]
                },
            )()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    cfg = OpenAIAdapterConfig(
        model="qwen/qwen3-coder:free",
        fallback_models=("openai/gpt-oss-120b:free", "openai/gpt-oss-20b:free"),
        routing_enabled=True,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-real",
        timeout_sec=12.0,
        max_retries=2,
        local_fallback_enabled=False,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg, client=_FakeClient())
    result = asyncio.run(adapter.create_chat_completion(messages=[{"role": "user", "content": "x"}]))

    assert result == "ok-routed"
    assert captured["model"] == "qwen/qwen3-coder:free"
    assert captured["extra_body"] == {
        "models": [
            "qwen/qwen3-coder:free",
            "openai/gpt-oss-120b:free",
            "openai/gpt-oss-20b:free",
        ]
    }


def test_openai_adapter_returns_trace_metadata() -> None:
    class _FakeCompletions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "qwen/qwen3-coder:free"
            return type(
                "_Resp",
                (),
                {
                    "choices": [
                        type("_Choice", (), {"message": type("_Msg", (), {"content": "{\"ok\":true}"})()})()
                    ]
                },
            )()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    cfg = OpenAIAdapterConfig(
        model="qwen/qwen3-coder:free",
        fallback_models=(),
        routing_enabled=False,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-real",
        timeout_sec=12.0,
        max_retries=2,
        local_fallback_enabled=False,
        local_model="llama-local",
        local_base_url="http://localhost:11434/v1",
        local_api_key=None,
    )
    adapter = OpenAIClientAdapter(cfg, client=_FakeClient())
    trace = asyncio.run(adapter.create_chat_completion_with_trace(messages=[{"role": "user", "content": "x"}]))

    assert trace.content == "{\"ok\":true}"
    assert trace.provider == "openrouter"
    assert trace.model == "qwen/qwen3-coder:free"
    assert trace.executed is True
    assert trace.success is True
