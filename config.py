from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    TG_API_ID: int = int(os.getenv("TG_API_ID"))
    TG_API_HASH: str = os.getenv("TG_API_HASH")
    TG_SESSION_NAME: str = os.getenv("TG_SESSION_NAME", "tg_session")
    DB_URL: str = os.getenv("DB_URL")
    tz: str = os.getenv("APP_TZ", "Europe/Minsk")

settings = Settings()
