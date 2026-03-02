from telethon import TelegramClient

from client.config import load_client_settings

client_settings = load_client_settings()
client = TelegramClient(
    session=client_settings.session,
    api_id=client_settings.api_id,
    api_hash=client_settings.api_hash,
    flood_sleep_threshold=client_settings.flood_sleep_threshold,
)
