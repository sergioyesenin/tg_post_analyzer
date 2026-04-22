from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from config import settings

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIAdapterConfig:
    model: str
    fallback_models: tuple[str, ...]
    routing_enabled: bool
    base_url: str | None
    api_key: str | None
    timeout_sec: float
    max_retries: int
    local_fallback_enabled: bool
    local_model: str
    local_base_url: str | None
    local_api_key: str | None

    @classmethod
    def from_settings(cls) -> "OpenAIAdapterConfig":
        fallback_models = tuple(
            model.strip()
            for model in (settings.REPORT_V2_OPENAI_FALLBACK_MODELS or [])
            if isinstance(model, str) and model.strip()
        )
        return cls(
            model=settings.REPORT_V2_OPENAI_MODEL,
            fallback_models=fallback_models,
            routing_enabled=bool(settings.REPORT_V2_OPENAI_ROUTING_ENABLED),
            base_url=settings.REPORT_V2_OPENAI_BASE_URL,
            api_key=settings.REPORT_V2_OPENAI_API_KEY,
            timeout_sec=float(settings.REPORT_V2_OPENAI_TIMEOUT_SEC),
            max_retries=int(settings.REPORT_V2_OPENAI_MAX_RETRIES),
            local_fallback_enabled=bool(settings.REPORT_V2_LOCAL_FALLBACK_ENABLED),
            local_model=str(settings.REPORT_V2_LOCAL_MODEL or "llama3.1:8b-instruct-q4_K_M"),
            local_base_url=settings.REPORT_V2_LOCAL_BASE_URL,
            local_api_key=settings.REPORT_V2_LOCAL_API_KEY,
        )


@dataclass(frozen=True)
class OpenAIChatCompletionTrace:
    content: str
    provider: str
    model: str
    latency_ms: int | None
    fallback_used: bool
    fallback_reason: str | None
    executed: bool
    success: bool
    attempt_index: int


class OpenAIClientAdapter:
    def __init__(
        self,
        config: OpenAIAdapterConfig,
        *,
        client: Any | None = None,
        local_client: Any | None = None,
    ) -> None:
        self.config = config
        if client is not None:
            self.client = client
        else:
            self.client = self._build_client(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout_sec,
                max_retries=config.max_retries,
            )

        self.local_client = local_client
        if self.local_client is None and config.local_fallback_enabled and config.local_base_url and config.local_model:
            self.local_client = self._build_client(
                api_key=(config.local_api_key or "local-fallback-key"),
                base_url=config.local_base_url,
                timeout=config.timeout_sec,
                max_retries=config.max_retries,
            )

    @staticmethod
    def _build_client(*, api_key: str | None, base_url: str | None, timeout: float, max_retries: int) -> Any:
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is required for OpenAIClientAdapter")
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    def _build_primary_models(self, requested_model: str | None) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for candidate in [requested_model, self.config.model, *list(self.config.fallback_models)]:
            if not isinstance(candidate, str):
                continue
            name = candidate.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        return ordered

    def _provider_for_client(self, *, client_kind: str) -> str:
        base_url = str(self.config.base_url or "").lower()
        if client_kind == "local":
            return "openai_compatible_local"
        if "openrouter" in base_url:
            return "openrouter"
        return "openai_compatible"

    async def _create_once(
        self,
        *,
        client: Any,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, Any] | None,
        routed_models: list[str] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if routed_models:
            kwargs["extra_body"] = {"models": routed_models}
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text")
                    if isinstance(value, str):
                        text_parts.append(value)
            return "".join(text_parts)
        return ""

    async def create_chat_completion_with_trace(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
    ) -> OpenAIChatCompletionTrace:
        primary_models = self._build_primary_models(model)
        primary_errors: list[str] = []
        requested_model = model or self.config.model
        attempt_index = 0

        if self.config.routing_enabled and len(primary_models) > 1:
            started = time.perf_counter()
            try:
                logger.warning("LLM routing request activated models=%s", primary_models)
                content = await self._create_once(
                    client=self.client,
                    model=primary_models[0],
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                    routed_models=primary_models,
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return OpenAIChatCompletionTrace(
                    content=content,
                    provider=self._provider_for_client(client_kind="primary"),
                    model=primary_models[0],
                    latency_ms=max(0, elapsed_ms),
                    fallback_used=False,
                    fallback_reason=None,
                    executed=True,
                    success=True,
                    attempt_index=attempt_index,
                )
            except Exception as exc:
                primary_errors.append(f"routing:{type(exc).__name__}:{exc}")
                logger.warning("LLM routing request failed err=%r", exc)
                attempt_index += 1

        for model_name in primary_models:
            started = time.perf_counter()
            try:
                if model_name != requested_model:
                    logger.warning("LLM model fallback activated model=%s", model_name)
                content = await self._create_once(
                    client=self.client,
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                fallback_used = model_name != requested_model
                return OpenAIChatCompletionTrace(
                    content=content,
                    provider=self._provider_for_client(client_kind="primary"),
                    model=model_name,
                    latency_ms=max(0, elapsed_ms),
                    fallback_used=fallback_used,
                    fallback_reason="model_fallback" if fallback_used else None,
                    executed=True,
                    success=True,
                    attempt_index=attempt_index,
                )
            except Exception as exc:
                primary_errors.append(f"{model_name}:{type(exc).__name__}:{exc}")
                logger.warning("LLM model failed model=%s err=%r", model_name, exc)
                attempt_index += 1

        if self.local_client is not None and self.config.local_fallback_enabled:
            started = time.perf_counter()
            try:
                logger.warning(
                    "LLM local fallback activated local_model=%s local_base_url=%s",
                    self.config.local_model,
                    self.config.local_base_url,
                )
                content = await self._create_once(
                    client=self.local_client,
                    model=self.config.local_model,
                    messages=messages,
                    temperature=temperature,
                    response_format=response_format,
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return OpenAIChatCompletionTrace(
                    content=content,
                    provider=self._provider_for_client(client_kind="local"),
                    model=self.config.local_model,
                    latency_ms=max(0, elapsed_ms),
                    fallback_used=True,
                    fallback_reason="local_fallback",
                    executed=True,
                    success=True,
                    attempt_index=attempt_index,
                )
            except Exception as exc:
                primary_errors.append(f"local:{self.config.local_model}:{type(exc).__name__}:{exc}")
                logger.warning("LLM local fallback failed model=%s err=%r", self.config.local_model, exc)
                attempt_index += 1

        summary = " | ".join(primary_errors) if primary_errors else "no_models_configured"
        raise RuntimeError(f"All LLM fallbacks failed: {summary}")

    async def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        trace = await self.create_chat_completion_with_trace(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=response_format,
        )
        return trace.content
