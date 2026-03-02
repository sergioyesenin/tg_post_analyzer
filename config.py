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

    LINKING_PIPELINE_VERSION: str = os.getenv("LINKING_PIPELINE_VERSION", "v2-evidence-first")
    LINKING_TOP_K: int = _env_int("LINKING_TOP_K", 50)
    LINKING_EMBED_ENABLED: bool = os.getenv("LINKING_EMBED_ENABLED", "true").lower() == "true"
    LINKING_EMBED_MODEL: str = os.getenv("LINKING_EMBED_MODEL", "nomic-embed-text")
    LINKING_EMBED_TIMEOUT_SEC: int = _env_int("LINKING_EMBED_TIMEOUT_SEC", 20)
    LINKING_EMBED_MIN_SIM: float = _env_float("LINKING_EMBED_MIN_SIM", 0.45)
    LINKING_CANDIDATE_MIN_EMBED_SIM: float = _env_float("LINKING_CANDIDATE_MIN_EMBED_SIM", 0.9)
    LINKING_PREFILTER_MULTIPLIER: int = _env_int("LINKING_PREFILTER_MULTIPLIER", 6)
    LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN: float = _env_float("LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN", 0.2)
    LINKING_RELATED_TIME_WINDOW_HOURS: int = _env_int("LINKING_RELATED_TIME_WINDOW_HOURS", 168)
    LINKING_MAX_TEXT_CHARS: int = _env_int("LINKING_MAX_TEXT_CHARS", 5000)
    NO_LLM_SAME_EVENT_MIN_SIM: float = _env_float("NO_LLM_SAME_EVENT_MIN_SIM", 0.915)
    NO_LLM_SAME_EVENT_MAX_HOURS: int = _env_int("NO_LLM_SAME_EVENT_MAX_HOURS", 10)
    TITLES_AI_ENABLED: bool = os.getenv("TITLES_AI_ENABLED", "true").lower() == "true"
    TITLES_AI_MAX_INPUT_POSTS: int = _env_int("TITLES_AI_MAX_INPUT_POSTS", 6)
    DISCUSSION_FALLBACK_ID_WINDOW: int = _env_int("DISCUSSION_FALLBACK_ID_WINDOW", 2)
    DISCUSSION_FALLBACK_MAX_SECONDS: int = _env_int("DISCUSSION_FALLBACK_MAX_SECONDS", 10)
    AUTH_JWT_SECRET: str = os.getenv("AUTH_JWT_SECRET", "change-me-in-prod")
    AUTH_JWT_ALG: str = os.getenv("AUTH_JWT_ALG", "HS256")
    AUTH_ACCESS_TTL_MINUTES: int = _env_int("AUTH_ACCESS_TTL_MINUTES", 60)
    AUTH_PROVIDER_MODE: str = os.getenv("AUTH_PROVIDER_MODE", "local")

settings = Settings()
