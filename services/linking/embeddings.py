from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


def _normalize_ollama_base(base_url: str) -> str:
    value = (base_url or "").rstrip("/")
    if value.endswith("/v1"):
        return value[:-3]
    return value


class EmbeddingProvider:
    def __init__(self) -> None:
        self._base_url = _normalize_ollama_base(settings.LINKER_LLM_BASE_URL)
        self._model = settings.LINKING_EMBED_MODEL
        self._timeout = float(settings.LINKING_EMBED_TIMEOUT_SEC)
        self._enabled = settings.LINKING_EMBED_ENABLED
        self._warned = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def embed_text(self, text: str) -> list[float] | None:
        if not self._enabled:
            return None
        payload = {
            "model": self._model,
            "prompt": (text or "")[: settings.LINKING_MAX_TEXT_CHARS],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/embeddings", json=payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
        except Exception as exc:
            if not self._warned:
                logger.warning("Embedding provider unavailable, fallback to lexical retrieval: %r", exc)
                self._warned = True
            self._enabled = False
            return None

        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            return None
        try:
            return [float(x) for x in emb]
        except Exception:
            return None
