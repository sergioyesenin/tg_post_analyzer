from dotenv import load_dotenv
import os

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


class Settings:
    TG_API_ID: int = _env_int("TG_API_ID", 0)
    TG_API_HASH: str = os.getenv("TG_API_HASH", "")
    TG_SESSION_NAME: str = os.getenv("TG_SESSION_NAME", "tg_session")
    DB_URL: str = os.getenv("DB_URL", "")
    tz: str = os.getenv("APP_TZ", "Europe/Minsk")

    LINKER_LLM_MODEL: str = os.getenv("LINKER_LLM_MODEL", "ollama/llama3:8b-instruct-q4_K_M")
    LINKER_LLM_BASE_URL: str = os.getenv("LINKER_LLM_BASE_URL", "http://localhost:11434")
    LINKER_LLM_API_KEY: str | None = os.getenv("LINKER_LLM_API_KEY")

    LINKER_AI_ENABLED: bool = os.getenv("LINKER_AI_ENABLED", "true").lower() == "true"
    LINKER_AI_MAX_CANDIDATES: int = _env_int("LINKER_AI_MAX_CANDIDATES", 30)
    LINKER_AI_MIN_CONFIDENCE: float = _env_float("LINKER_AI_MIN_CONFIDENCE", 0.72)
    LINKER_MIN_TEXT_JACCARD: float = _env_float("LINKER_MIN_TEXT_JACCARD", 0.12)
    LINKER_MIN_ENTITIES_JACCARD: float = _env_float("LINKER_MIN_ENTITIES_JACCARD", 0.08)
    LINKER_MIN_SHARED_ANCHORS: int = _env_int("LINKER_MIN_SHARED_ANCHORS", 1)
    LINKER_LOOKBACK_DAYS: int = _env_int("LINKER_LOOKBACK_DAYS", 7)
    LINKER_CANDIDATE_LIMIT: int = _env_int("LINKER_CANDIDATE_LIMIT", 500)
    DISCUSSION_FALLBACK_ID_WINDOW: int = _env_int("DISCUSSION_FALLBACK_ID_WINDOW", 2)
    DISCUSSION_FALLBACK_MAX_SECONDS: int = _env_int("DISCUSSION_FALLBACK_MAX_SECONDS", 10)

settings = Settings()
