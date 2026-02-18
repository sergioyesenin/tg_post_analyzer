# scripts/parse_today.py
from __future__ import annotations

import asyncio
import random

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telethon.errors import RPCError, FloodWaitError
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import PeerChannel, PeerUser
from telethon.errors.rpcerrorlist import MsgIdInvalidError


from sqlalchemy import select

from config import settings
from db.session import AsyncSessionLocal
from db.models import Channel
from services.ingest import upsert_post, upsert_comment, set_post_comments_count
from client import client

POSTS_SLEEP_EVERY = 50
COMMENTS_SLEEP_EVERY = 50

def day_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc

async def polite_sleep(base: float, jitter: float) -> None:
    """Небольшой сон с джиттером, чтобы запросы не шли ровно 'по линейке'."""
    await asyncio.sleep(base + random.random() * jitter)

async def parse_channel_today(channel: Channel) -> None:
    start_utc, end_utc = day_bounds_utc(settings.tz)

    await client.start()

    # telethon peer by channel username (быстро), fallback — по id в username формата id_<num>
    # Мы храним username без "@", в модели это "mychannel"
    username = channel.username
    peer = None
    if username.startswith("id_") and username[3:].isdigit():
        peer = PeerChannel(int(username[3:]))
    else:
        peer = f"@{username}"

    try:
        entity = await client.get_entity(peer)
    except FloodWaitError as e:
        print(f"[{channel.username}] FloodWait {FloodWaitError.seconds}s on get_entity, skipping channel")
        await client.disconnect()
        return
    except Exception as e:
        print(f"Не удалось найти канал с названием: {channel.username}")
    

    posts_today: list[tuple[int, int]] = []  # (post_db_id, tg_message_id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            i = 0
            try:
                async for msg in client.iter_messages(entity):

                    i += 1

                    if msg.date is None:
                        continue

                    # msg.date обычно timezone-aware UTC
                    if msg.date < start_utc:
                        break
                    if not (start_utc <= msg.date < end_utc):
                        continue

                    text = msg.message  # None or str
                    views = getattr(msg, "views", None)

                    # replies / comments count
                    replies_obj = getattr(msg, "replies", None)
                    replies_count = getattr(replies_obj, "replies", 0) if replies_obj else 0


                    if replies_count >= 20:
                        try:
                            post = await upsert_post(
                                session,
                                channel_id=channel.id,
                                tg_message_id=msg.id,
                                date=msg.date,
                                text=msg.message,
                                views=getattr(msg, "views", None),
                                comments_count=int(replies_count or 0),
                            )

                            print(f"Saved post: channel=@{channel.username} tg_msg_id={msg.id} db_post_id={post.id}")

                            posts_today.append((post.id, msg.id))

                        except Exception as e:
                            print(
                                f"[{channel.username}] error saving post "
                                f"tg_msg_id={msg.id}: {e!r}"
                            )
                            continue
                    


                if i == POSTS_SLEEP_EVERY:
                    i = 0
                    await polite_sleep(0.4, 0.6)

            except FloodWaitError as e:

                print(f"[{channel.username}] FloodWait {e.seconds}s during iter_messages, stopping channel")
                await client.disconnect()
                return
            # 1) посты за сегодня
          

            # 2) комментарии к постам
            j = 0
            for post_id, tg_post_id in posts_today:

                j += 1 
                comments_saved_today = 0

                try:
                    discussion = await client(GetDiscussionMessageRequest(peer=entity, msg_id=tg_post_id))
                except MsgIdInvalidError:
                    # У этого поста нет валидной ветки обсуждения
                    continue
                except FloodWaitError as e:
                    print(f"[{channel.username}] FloodWait {e.seconds}s on GetDiscussionMessage, stopping channel")
                    await client.disconnect()
                    return
                except RPCError as e:
                    print(e)
                    # нет комментариев / нет linked chat / нет доступа
                    continue
                except Exception as e:
                    print(e)
                    continue

                # discussion.chats[0] — discussion group/supergroup
                if not discussion.chats or not discussion.messages:
                    continue

                discussion_chat = discussion.chats[0]
                discussion_root = discussion.messages[0]  # сообщение в группе, связанное с постом

                if j == POSTS_SLEEP_EVERY:
                    j = 0
                    polite_sleep(0.4, 0.6)


                k = 0
                try:
                    async for c in client.iter_messages(discussion_chat, reply_to=discussion_root.id):
                        k += 1
                        if c.date is None:
                            continue
                        # author_id
                        author_id = None
                        from_id = getattr(c, "from_id", None)
                        if isinstance(from_id, PeerUser):
                            author_id = from_id.user_id

                        author_username = None
                        try:
                            sender = await c.get_sender()
                            author_username = getattr(sender, "username", None)
                        except Exception:
                            pass

                        await upsert_comment(
                            session,
                            channel_id=channel.id,
                            post_id=post_id,
                            tg_message_id=c.id,
                            date=c.date,
                            author_id=author_id,
                            author_username=author_username,
                            text=c.message,
                        )
                        comments_saved_today += 1

                        if k == COMMENTS_SLEEP_EVERY:
                            k = 0
                            await polite_sleep(0.4, 0.6)

                    # обновляем comments_count на “кол-во комментов за сегодня”
                    
                except FloodWaitError as e:
                    print(f"[{channel.username}] FloodWait {e.seconds}s during comments iter, stopping channel")
                    await client.disconnect()
                    return
                except MsgIdInvalidError:
                    # Telegram говорит: "reply_to невалиден" — значит ветки комментариев нет/недоступна
                    continue
                
                await set_post_comments_count(
                        session,
                        post_id=post_id,
                        comments_count=comments_saved_today,
                    )

                

    await client.disconnect()


async def main() -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Channel).where(Channel.is_active.is_(True)))
        channels = list(res.scalars().all())

    if not channels:
        print("No active channels in DB. Add one via: python -m scripts.add_channel @username")
        return

    for ch in channels:
        print(f"Parsing today for @{ch.username}...")
        await parse_channel_today(ch)

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
