from __future__ import annotations

import os
import string
from urllib.parse import urlsplit
import warnings
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()


class Settings:
    _JWT_MIN_SECRET_LENGTH = 32
    _JWT_FORBIDDEN_SECRETS = frozenset({"change-me-in-prod"})
    _NON_PROD_ENVS = frozenset({"dev", "local", "test"})
    _INSECURE_PASSWORDS = frozenset({"postgres", "password", "changeme", "change-me-in-prod"})

    def __init__(self) -> None:
        errors: list[str] = []

        self.TG_API_ID = self._env_int("TG_API_ID", default=None, required=True, errors=errors)
        self.TG_API_HASH = self._env_str("TG_API_HASH", required=True, errors=errors)
        self.TG_SESSION_NAME = self._env_str("TG_SESSION_NAME", default="tg_analytics.session", errors=errors)
        self.TG_FLOOD_SLEEP_THRESHOLD = self._env_int("TG_FLOOD_SLEEP_THRESHOLD", default=5, errors=errors)
        self.DB_URL = self._env_str("DB_URL", alias="DATABASE_URL", required=True, errors=errors)
        self.APP_ENV = self._env_str("APP_ENV", default="dev", errors=errors) or "dev"
        self._validate_non_dev_db_credentials(self.DB_URL, self.APP_ENV, errors)
        self.tz = self._env_str("APP_TZ", alias="TZ", default="Europe/Minsk", errors=errors)
        self._validate_timezone(self.tz, errors)

        self.LINKER_LLM_MODEL = self._env_str("LINKER_LLM_MODEL", default="ollama/llama3:8b-instruct-q4_K_M", errors=errors)
        self.LINKER_LLM_BASE_URL = self._env_str("LINKER_LLM_BASE_URL", default="http://localhost:11434", errors=errors)
        self.LINKER_LLM_API_KEY = self._env_str("LINKER_LLM_API_KEY", default=None, errors=errors)

        self.LINKING_PIPELINE_VERSION = self._env_str("LINKING_PIPELINE_VERSION", default="v2-evidence-first", errors=errors)
        self.LINKING_TOP_K = self._env_int("LINKING_TOP_K", default=50, errors=errors)
        self.LINKING_EMBED_ENABLED = self._env_bool("LINKING_EMBED_ENABLED", default=True, errors=errors)
        self.LINKING_EMBED_MODEL = self._env_str("LINKING_EMBED_MODEL", default="nomic-embed-text", errors=errors)
        self.LINKING_EMBED_TIMEOUT_SEC = self._env_int("LINKING_EMBED_TIMEOUT_SEC", default=20, errors=errors)
        self.LINKING_EMBED_MIN_SIM = self._env_float("LINKING_EMBED_MIN_SIM", default=0.45, errors=errors)
        self.LINKING_CANDIDATE_MIN_EMBED_SIM = self._env_float("LINKING_CANDIDATE_MIN_EMBED_SIM", default=0.9, errors=errors)
        self.LINKING_PREFILTER_MULTIPLIER = self._env_int("LINKING_PREFILTER_MULTIPLIER", default=6, errors=errors)
        self.LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN = self._env_float("LINKING_SAME_EVENT_ENTITY_OVERLAP_MIN", default=0.2, errors=errors)
        self.LINKING_RELATED_TIME_WINDOW_HOURS = self._env_int("LINKING_RELATED_TIME_WINDOW_HOURS", default=168, errors=errors)
        self.LINKING_MAX_TEXT_CHARS = self._env_int("LINKING_MAX_TEXT_CHARS", default=5000, errors=errors)
        self.NO_LLM_SAME_EVENT_MIN_SIM = self._env_float("NO_LLM_SAME_EVENT_MIN_SIM", default=0.915, errors=errors)
        self.NO_LLM_SAME_EVENT_MAX_HOURS = self._env_int("NO_LLM_SAME_EVENT_MAX_HOURS", default=10, errors=errors)
        self.TITLES_AI_ENABLED = self._env_bool("TITLES_AI_ENABLED", default=True, errors=errors)
        self.TITLES_AI_MAX_INPUT_POSTS = self._env_int("TITLES_AI_MAX_INPUT_POSTS", default=6, errors=errors)
        self.DISCUSSION_FALLBACK_ID_WINDOW = self._env_int("DISCUSSION_FALLBACK_ID_WINDOW", default=1, errors=errors)
        self.DISCUSSION_FALLBACK_MAX_SECONDS = self._env_int("DISCUSSION_FALLBACK_MAX_SECONDS", default=10, errors=errors)
        self.COMMENTS_SLEEP_EVERY = self._env_int("COMMENTS_SLEEP_EVERY", default=10, errors=errors)
        self.COMMENTS_SLEEP_BASE_SEC = self._env_float("COMMENTS_SLEEP_BASE_SEC", default=0.6, errors=errors)
        self.COMMENTS_SLEEP_JITTER_SEC = self._env_float("COMMENTS_SLEEP_JITTER_SEC", default=0.4, errors=errors)
        self.AUTH_JWT_SECRET = self._env_str("AUTH_JWT_SECRET", required=True, errors=errors)
        self._validate_jwt_secret(self.AUTH_JWT_SECRET, errors)
        self.AUTH_JWT_ALG = self._env_str("AUTH_JWT_ALG", default="HS256", errors=errors)
        self.AUTH_ACCESS_TTL_MINUTES = self._env_int("AUTH_ACCESS_TTL_MINUTES", default=60, errors=errors)
        self.AUTH_REFRESH_TTL_DAYS = self._env_int("AUTH_REFRESH_TTL_DAYS", default=30, errors=errors)
        self.AUTH_PROVIDER_MODE = self._env_str("AUTH_PROVIDER_MODE", default="local", errors=errors)

        if errors:
            ordered = "\n".join(f"- {item}" for item in sorted(errors))
            raise RuntimeError(f"Invalid environment configuration:\n{ordered}")

    @staticmethod
    def _read_env(name: str, *, alias: str | None = None) -> tuple[str | None, str | None]:
        value = os.getenv(name)
        if value is not None and value != "":
            return value, name
        if alias:
            alias_value = os.getenv(alias)
            if alias_value is not None and alias_value != "":
                warnings.warn(
                    f"Environment variable '{alias}' is deprecated; use '{name}' instead.",
                    UserWarning,
                    stacklevel=3,
                )
                return alias_value, alias
        return None, None

    @classmethod
    def _env_str(
        cls,
        name: str,
        *,
        alias: str | None = None,
        default: str | None = None,
        required: bool = False,
        errors: list[str],
    ) -> str | None:
        value, _ = cls._read_env(name, alias=alias)
        if value is None:
            if required:
                errors.append(f"Missing required env var: {name}")
            return default
        return value

    @classmethod
    def _env_int(
        cls,
        name: str,
        *,
        alias: str | None = None,
        default: int | None,
        required: bool = False,
        errors: list[str],
    ) -> int | None:
        value = cls._env_str(name, alias=alias, default=None, required=required, errors=errors)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            errors.append(f"Invalid integer env var: {name}='{value}'")
            return default

    @classmethod
    def _env_float(
        cls,
        name: str,
        *,
        alias: str | None = None,
        default: float,
        errors: list[str],
    ) -> float:
        value = cls._env_str(name, alias=alias, default=None, errors=errors)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            errors.append(f"Invalid float env var: {name}='{value}'")
            return default

    @classmethod
    def _env_bool(
        cls,
        name: str,
        *,
        alias: str | None = None,
        default: bool,
        errors: list[str],
    ) -> bool:
        value = cls._env_str(name, alias=alias, default=None, errors=errors)
        if value is None:
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        errors.append(f"Invalid boolean env var: {name}='{value}'")
        return default

    @staticmethod
    def _validate_timezone(tz_name: str | None, errors: list[str]) -> None:
        if tz_name is None:
            errors.append("Missing timezone value for APP_TZ")
            return
        try:
            ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            errors.append(f"Invalid timezone env var: APP_TZ='{tz_name}'")

    @classmethod
    def _validate_jwt_secret(cls, secret: str | None, errors: list[str]) -> None:
        if secret is None:
            return

        normalized = secret.strip()
        if not normalized:
            errors.append("Invalid AUTH_JWT_SECRET: value must not be empty")
            return
        if normalized in cls._JWT_FORBIDDEN_SECRETS:
            errors.append("Invalid AUTH_JWT_SECRET: insecure placeholder value is not allowed")
            return
        if len(normalized) < cls._JWT_MIN_SECRET_LENGTH:
            errors.append(
                f"Invalid AUTH_JWT_SECRET: value must be at least {cls._JWT_MIN_SECRET_LENGTH} characters"
            )
            return

        classes = 0
        if any(ch.islower() for ch in normalized):
            classes += 1
        if any(ch.isupper() for ch in normalized):
            classes += 1
        if any(ch.isdigit() for ch in normalized):
            classes += 1
        if any(ch in string.punctuation for ch in normalized):
            classes += 1
        if classes < 3:
            errors.append(
                "Invalid AUTH_JWT_SECRET: value must include at least 3 character classes "
                "(lowercase, uppercase, digits, symbols)"
            )

    @classmethod
    def _validate_non_dev_db_credentials(cls, db_url: str | None, app_env: str, errors: list[str]) -> None:
        env_normalized = app_env.strip().lower()
        if env_normalized in cls._NON_PROD_ENVS:
            return
        if db_url is None:
            return

        try:
            parsed = urlsplit(db_url)
        except Exception:
            return

        username = (parsed.username or "").strip().lower()
        password = (parsed.password or "").strip().lower()
        if username == "postgres" and password in cls._INSECURE_PASSWORDS:
            errors.append(
                "Insecure DB credentials are not allowed outside dev/local/test; "
                "set non-default DB_URL credentials"
            )

settings = Settings()
