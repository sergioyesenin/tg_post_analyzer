from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ModelEntry:
    name: str                    # полное имя модели, передаваемое в API (например, "llama-3.3-70b-versatile")
    provider: str                # идентификатор провайдера: "groq", "openrouter", "google", "github"
    base_url: str                # API endpoint
    api_key: str                 # ключ (может быть None для некоторых)
    max_tokens_per_day: int      # дневной лимит токенов (0 = без ограничений)
    max_requests_per_minute: int # лимит запросов в минуту (0 = без)
    token_usage_today: int = 0
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    last_reset_day: int = field(default_factory=lambda: time.localtime().tm_yday)

    def reset_if_needed(self):
        today = time.localtime().tm_yday
        if today != self.last_reset_day:
            self.token_usage_today = 0
            self.request_timestamps.clear()
            self.last_reset_day = today

    def can_use(self, estimated_tokens: int = 0) -> bool:
        self.reset_if_needed()
        if self.max_tokens_per_day > 0 and self.token_usage_today + estimated_tokens > self.max_tokens_per_day:
            return False
        if self.max_requests_per_minute > 0:
            now = time.time()
            # убираем запросы старше минуты
            while self.request_timestamps and now - self.request_timestamps[0] > 60:
                self.request_timestamps.popleft()
            if len(self.request_timestamps) >= self.max_requests_per_minute:
                return False
        return True

    def record_usage(self, tokens_used: int):
        self.reset_if_needed()
        self.token_usage_today += tokens_used
        self.request_timestamps.append(time.time())


class ModelRouter:
    """
    Маршрутизатор запросов к LLM, поддерживающий несколько моделей/провайдеров.
    При ошибке 429 автоматически переключается на следующую доступную модель.
    """
    def __init__(self, models: List[ModelEntry], default_estimated_tokens: int = 1500):
        self.models = models
        self.default_estimated_tokens = default_estimated_tokens
        self._current_index = 0

    def get_next_available_model(self, estimated_tokens: int = 0) -> Optional[ModelEntry]:
        """Возвращает первую модель, которая может принять запрос (по лимитам)."""
        for _ in range(len(self.models)):
            idx = self._current_index % len(self.models)
            model = self.models[idx]
            if model.can_use(estimated_tokens):
                self._current_index = (idx + 1) % len(self.models)  # следующий раз начнём со следующей
                return model
            self._current_index += 1
        return None

    async def execute_with_fallback(
        self,
        client_factory,
        estimated_tokens: int,
        **kwargs,
    ) -> Tuple[Any, ModelEntry]:
        """Выполняет запрос к LLM, перебирая модели при ошибках 429."""
        tried_models = set()
        while len(tried_models) < len(self.models):
            model = self.get_next_available_model(estimated_tokens)
            if not model:
                break
            if model.name in tried_models:
                continue
            tried_models.add(model.name)

            try:
                client = client_factory(model)
                # Используем стандартный метод OpenAI
                response = await client.chat.completions.create(
                    model=model.name,
                    **kwargs,
                )
                # Извлечение количества токенов
                total_tokens = estimated_tokens  # fallback
                if hasattr(response, 'usage') and response.usage:
                    total_tokens = getattr(response.usage, 'total_tokens', estimated_tokens)
                model.record_usage(total_tokens)
                return response, model
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "rate limit" in error_msg or "tokens per day" in error_msg:
                    logger.warning(
                        "Model %s hit rate limit: %s. Switching to next model.",
                        model.name, e
                    )
                    continue
                else:
                    logger.error("Model %s failed with error: %s", model.name, e)
                    continue
        raise RuntimeError("All models exhausted or unavailable")