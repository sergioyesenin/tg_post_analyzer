from dataclasses import dataclass

from config import settings


@dataclass(frozen=True)
class TelegramClientSettings:
    session: str
    api_id: int
    api_hash: str
    flood_sleep_threshold: int


def load_client_settings() -> TelegramClientSettings:
    # Keep threshold low so FloodWait is surfaced to job-level backoff logic
    # instead of long implicit sleeps inside Telethon.
    threshold = int(getattr(settings, "TG_FLOOD_SLEEP_THRESHOLD", 180))
    threshold = max(0, min(threshold, 5))
    return TelegramClientSettings(
        session=settings.TG_SESSION_NAME,
        api_id=settings.TG_API_ID,
        api_hash=settings.TG_API_HASH,
        flood_sleep_threshold=threshold,
    )
