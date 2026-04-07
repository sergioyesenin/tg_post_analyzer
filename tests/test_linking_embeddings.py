from __future__ import annotations

from services.linking.embeddings import EmbeddingProvider


def test_embedding_provider_uses_report_llm_base_url(monkeypatch):
    monkeypatch.setattr("services.linking.embeddings.settings.REPORT_LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    monkeypatch.setattr("services.linking.embeddings.settings.LINKING_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setattr("services.linking.embeddings.settings.LINKING_EMBED_TIMEOUT_SEC", 20)
    monkeypatch.setattr("services.linking.embeddings.settings.LINKING_EMBED_ENABLED", True)

    provider = EmbeddingProvider()

    assert provider._base_url == "http://host.docker.internal:11434"
