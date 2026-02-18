import asyncio
from sqlalchemy import select

from db.session import AsyncSessionLocal
from db.models import Channel

async def main():
    async with AsyncSessionLocal() as session:
        # вставим канал, если его нет
        username = "example_channel"
        res = await session.execute(select(Channel).where(Channel.username == username))
        channel = res.scalar_one_or_none()
        if not channel:
            channel = Channel(username=username, title="Example", category="test")
            session.add(channel)
            await session.commit()

        res2 = await session.execute(select(Channel))
        all_channels = res2.scalars().all()
        print("channels:", [(c.id, c.username) for c in all_channels])

asyncio.run(main())
