from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class AgentSettings:
    llm_model: str = "ollama/llama3:8b-instruct-q4_K_M"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str | None = None


def load_agent_settings() -> AgentSettings:
    return AgentSettings(
        llm_model=settings.LINKER_LLM_MODEL,
        llm_base_url=settings.LINKER_LLM_BASE_URL,
        llm_api_key=settings.LINKER_LLM_API_KEY,
    )
