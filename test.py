import asyncio
from telethon import events
from telethon.tl.functions.channels import LeaveChannelRequest, JoinChannelRequest
from sqlalchemy import select
from datetime import datetime

from client import client
from db.session import AsyncSessionLocal
from db.models import Channel


async def get_channels():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Channel).where(Channel.username == "example567"))
        return list(res.scalars().all())


async def main():
    await client.start()

    channels = await get_channels()
    usernames = [f"@{ch.username}" for ch in channels]

    for c in usernames:
        try:
            await client(JoinChannelRequest(c))
            print(f"leaved channel {c}")
        except Exception as e:
            print("Leave skipped:", c, e)

    print(usernames)
    print(datetime.now())

    @client.on(events.NewMessage(chats=usernames))
    async def get_posts(event):
        print("new message!")
        print(event.text)

    print("Listener started. Press Ctrl+C to stop.")
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("Stopped by user")


if __name__ == "__main__":
    asyncio.run(main())
