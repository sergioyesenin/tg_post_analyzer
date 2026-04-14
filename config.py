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
    _DEV_CORS_ORIGINS = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )

    def __init__(self) -> None:
        errors: list[str] = []

        self.TG_API_ID = self._env_int("TG_API_ID", default=None, required=True, errors=errors)
        self.TG_API_HASH = self._env_str("TG_API_HASH", required=True, errors=errors)
        self.TG_SESSION_NAME = self._env_str("TG_SESSION_NAME", default="tg_analytics.session", errors=errors)
        self.TG_FLOOD_SLEEP_THRESHOLD = self._env_int("TG_FLOOD_SLEEP_THRESHOLD", default=5, errors=errors)
        self.DB_URL = self._env_str("DB_URL", alias="DATABASE_URL", required=True, errors=errors)
        self.APP_ENV = self._env_str("APP_ENV", default="dev", errors=errors) or "dev"
        self.IS_NON_PROD = self.APP_ENV.strip().lower() in self._NON_PROD_ENVS
        self._validate_non_dev_db_credentials(self.DB_URL, self.APP_ENV, errors)
        self.tz = self._env_str("APP_TZ", alias="TZ", default="Europe/Minsk", errors=errors)
        self._validate_timezone(self.tz, errors)

        self.REPORT_LLM_MODEL = self._env_str(
            "REPORT_LLM_MODEL",
            alias="LINKER_LLM_MODEL",
            default="ollama/llama3:8b-instruct-q4_K_M",
            errors=errors,
        )
        self.REPORT_LLM_BASE_URL = self._env_str(
            "REPORT_LLM_BASE_URL",
            alias="LINKER_LLM_BASE_URL",
            default="http://localhost:11434",
            errors=errors,
        )
        self.REPORT_LLM_API_KEY = self._env_str(
            "REPORT_LLM_API_KEY",
            alias="LINKER_LLM_API_KEY",
            default=None,
            errors=errors,
        )

        self.RETRIEVAL_POLICY_ENABLED = self._env_bool("RETRIEVAL_POLICY_ENABLED", default=False, errors=errors)
        self.RETRIEVAL_ROLLOUT_PERCENT = self._env_int("RETRIEVAL_ROLLOUT_PERCENT", default=0, errors=errors)
        self.RETRIEVAL_PROVIDER_ENABLED = self._env_bool("RETRIEVAL_PROVIDER_ENABLED", default=False, errors=errors)
        self.RETRIEVAL_PROVIDER_NAME = self._env_str("RETRIEVAL_PROVIDER_NAME", default="none", errors=errors)

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
        self.COMMENTS_RECONCILIATION_ENABLED = self._env_bool("COMMENTS_RECONCILIATION_ENABLED", default=False, errors=errors)
        self.COMMENTS_REACTIONS_REFRESH_TTL_SECONDS = self._env_int(
            "COMMENTS_REACTIONS_REFRESH_TTL_SECONDS",
            default=900,
            errors=errors,
        )
        self.COMMENTS_REACTIONS_TOP_N = self._env_int("COMMENTS_REACTIONS_TOP_N", default=10, errors=errors)
        self.COMMENTS_LONG_COMMENT_THRESHOLD = self._env_int(
            "COMMENTS_LONG_COMMENT_THRESHOLD",
            default=100,
            errors=errors,
        )
        self.AUTH_JWT_SECRET = self._env_str("AUTH_JWT_SECRET", required=True, errors=errors)
        self._validate_jwt_secret(self.AUTH_JWT_SECRET, errors)
        self.AUTH_JWT_ALG = self._env_str("AUTH_JWT_ALG", default="HS256", errors=errors)
        self.AUTH_ACCESS_TTL_MINUTES = self._env_int("AUTH_ACCESS_TTL_MINUTES", default=60, errors=errors)
        self.AUTH_REFRESH_TTL_DAYS = self._env_int("AUTH_REFRESH_TTL_DAYS", default=30, errors=errors)
        self.AUTH_PROVIDER_MODE = self._env_str("AUTH_PROVIDER_MODE", default="local", errors=errors)
        self.AUTH_REFRESH_COOKIE_NAME = self._env_str("AUTH_REFRESH_COOKIE_NAME", default="tgpa_refresh", errors=errors)
        self.AUTH_REFRESH_COOKIE_SECURE = self._env_bool("AUTH_REFRESH_COOKIE_SECURE", default=False, errors=errors)
        self.AUTH_REFRESH_COOKIE_SAMESITE = self._env_str("AUTH_REFRESH_COOKIE_SAMESITE", default="lax", errors=errors)
        self.AUTH_REFRESH_COOKIE_DOMAIN = self._env_str("AUTH_REFRESH_COOKIE_DOMAIN", default=None, errors=errors)
        self.AUTH_REFRESH_COOKIE_PATH = self._env_str("AUTH_REFRESH_COOKIE_PATH", default="/api/auth", errors=errors)
        self.AUTH_TRUST_PROXY_HEADERS = self._env_bool("AUTH_TRUST_PROXY_HEADERS", default=False, errors=errors)
        self.AUTH_RATE_LIMIT_WINDOW_SECONDS = self._env_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", default=300, errors=errors)
        self.AUTH_LOGIN_MAX_ATTEMPTS = self._env_int("AUTH_LOGIN_MAX_ATTEMPTS", default=10, errors=errors)
        self.AUTH_REFRESH_MAX_ATTEMPTS = self._env_int("AUTH_REFRESH_MAX_ATTEMPTS", default=20, errors=errors)
        self._validate_auth_cookie_policy(errors)
        self._validate_auth_rate_limits(errors)
        self.CORS_ALLOWED_ORIGINS = self._env_csv(
            "CORS_ALLOWED_ORIGINS",
            default=self._default_cors_origins(self.APP_ENV),
            errors=errors,
        )
        self.CORS_ALLOW_CREDENTIALS = self._env_bool(
            "CORS_ALLOW_CREDENTIALS",
            default=True,
            errors=errors,
        )
        self._validate_cors_settings(errors)

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

    @classmethod
    def _env_csv(
        cls,
        name: str,
        *,
        alias: str | None = None,
        default: tuple[str, ...] | list[str] | None,
        errors: list[str],
    ) -> list[str]:
        value = cls._env_str(name, alias=alias, default=None, errors=errors)
        if value is None:
            return list(default or [])
        return [item.strip() for item in value.split(",") if item.strip()]

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

    def _validate_auth_cookie_policy(self, errors: list[str]) -> None:
        samesite = (self.AUTH_REFRESH_COOKIE_SAMESITE or "").strip().lower()
        cookie_name = (self.AUTH_REFRESH_COOKIE_NAME or "").strip()
        cookie_path = (self.AUTH_REFRESH_COOKIE_PATH or "").strip()
        cookie_domain = (self.AUTH_REFRESH_COOKIE_DOMAIN or "").strip().lower()

        if not cookie_name:
            errors.append("Invalid AUTH_REFRESH_COOKIE_NAME: value must not be empty")
        if not cookie_path.startswith("/"):
            errors.append("Invalid AUTH_REFRESH_COOKIE_PATH: value must start with '/'")
        if samesite not in {"lax", "strict", "none"}:
            errors.append(
                "Invalid AUTH_REFRESH_COOKIE_SAMESITE: value must be one of lax, strict, none"
            )
        if samesite == "none" and not self.AUTH_REFRESH_COOKIE_SECURE:
            errors.append(
                "Invalid auth cookie policy: AUTH_REFRESH_COOKIE_SAMESITE=none requires AUTH_REFRESH_COOKIE_SECURE=true"
            )
        if not self.IS_NON_PROD and not self.AUTH_REFRESH_COOKIE_SECURE:
            errors.append(
                "Invalid auth cookie policy outside dev/local/test: AUTH_REFRESH_COOKIE_SECURE must be true"
            )
        if not self.IS_NON_PROD and cookie_domain in {"localhost", "127.0.0.1", "::1"}:
            errors.append(
                "Invalid auth cookie policy outside dev/local/test: "
                "AUTH_REFRESH_COOKIE_DOMAIN cannot point to localhost"
            )

    def _validate_auth_rate_limits(self, errors: list[str]) -> None:
        if self.AUTH_RATE_LIMIT_WINDOW_SECONDS is None or self.AUTH_RATE_LIMIT_WINDOW_SECONDS < 30:
            errors.append("Invalid AUTH_RATE_LIMIT_WINDOW_SECONDS: value must be >= 30")
        if self.AUTH_LOGIN_MAX_ATTEMPTS is None or self.AUTH_LOGIN_MAX_ATTEMPTS < 1:
            errors.append("Invalid AUTH_LOGIN_MAX_ATTEMPTS: value must be >= 1")
        if self.AUTH_REFRESH_MAX_ATTEMPTS is None or self.AUTH_REFRESH_MAX_ATTEMPTS < 1:
            errors.append("Invalid AUTH_REFRESH_MAX_ATTEMPTS: value must be >= 1")

    @classmethod
    def _default_cors_origins(cls, app_env: str | None) -> tuple[str, ...]:
        env_normalized = (app_env or "dev").strip().lower()
        if env_normalized in cls._NON_PROD_ENVS:
            return cls._DEV_CORS_ORIGINS
        return ()

    def _validate_cors_settings(self, errors: list[str]) -> None:
        origins = list(self.CORS_ALLOWED_ORIGINS or [])
        if self.CORS_ALLOW_CREDENTIALS and "*" in origins:
            errors.append("Invalid CORS configuration: wildcard origins cannot be used with credentials")

        env_normalized = self.APP_ENV.strip().lower()
        if env_normalized not in self._NON_PROD_ENVS and not origins:
            errors.append(
                "Invalid CORS configuration: CORS_ALLOWED_ORIGINS must be set outside dev/local/test"
            )

settings = Settings()
