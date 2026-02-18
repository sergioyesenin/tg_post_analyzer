from telethon import TelegramClient
from config import settings

client = TelegramClient(
    session=settings.TG_SESSION_NAME,
    api_id=settings.TG_API_ID,
    api_hash=settings.TG_API_HASH,
    flood_sleep_threshold=int(getattr(settings, "tg_flood_sleep_threshold", 60))
)
