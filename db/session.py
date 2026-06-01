from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from config import settings


_engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}
if not settings.DB_URL.lower().startswith("sqlite"):
    _engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
    )

engine = create_async_engine(settings.DB_URL, **_engine_kwargs)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
