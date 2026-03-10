from dataclasses import dataclass

from config import settings

DEFAULT_TELEGRAM_SESSION_NAME = "tg_analytics.session"
DEFAULT_TG_FLOOD_SLEEP_THRESHOLD = 5


@dataclass(frozen=True)
class TelegramClientSettings:
    session: str
    api_id: int
    api_hash: str
    flood_sleep_threshold: int


def load_client_settings() -> TelegramClientSettings:
    # Keep threshold low so FloodWait is surfaced to job-level backoff logic
    # instead of long implicit sleeps inside Telethon.
    threshold = int(getattr(settings, "TG_FLOOD_SLEEP_THRESHOLD", DEFAULT_TG_FLOOD_SLEEP_THRESHOLD))
    threshold = max(0, min(threshold, 5))
    return TelegramClientSettings(
        session=getattr(settings, "TG_SESSION_NAME", DEFAULT_TELEGRAM_SESSION_NAME),
        api_id=settings.TG_API_ID,
        api_hash=settings.TG_API_HASH,
        flood_sleep_threshold=threshold,
    )


def resolve_session_name(
    *,
    base_session: str,
    session_suffix: str = "",
    unique_session_per_run: bool = False,
    pid: int | None = None,
) -> str:
    session_name = (base_session or DEFAULT_TELEGRAM_SESSION_NAME).strip() or DEFAULT_TELEGRAM_SESSION_NAME
    suffix = session_suffix.strip()
    if suffix:
        session_name = f"{session_name}_{suffix}"
    if unique_session_per_run:
        resolved_pid = pid if pid is not None else 0
        session_name = f"{session_name}_{resolved_pid}"
    return session_name
