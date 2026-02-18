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
from services.ingest import upsert_post, upsert_comment, set_post_comments_count, upsert_report
from client import client
from agent.reporter import TgReportProject

report_project = TgReportProject(
    llm_model="ollama/llama3:8b-instruct-q4_K_M",
)

POSTS_SLEEP_EVERY = 50
COMMENTS_SLEEP_EVERY = 50

def day_bounds_utc(tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)# + timedelta(days= -1)
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc

async def polite_sleep(base: float, jitter: float) -> None:
    """Небольшой сон с джиттером, чтобы запросы не шли ровно 'по линейке'."""
    await asyncio.sleep(base + random.random() * jitter)




async def parse_channel_today(channel: Channel) -> None:
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

    await get_posts(channel, entity)

async def get_posts(channel: Channel, entity):
    start_utc, end_utc = day_bounds_utc(settings.tz)
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
                            comments = await get_comments(channel, session, entity, msg.id, post.id)

                            report_text = await report_project.generate_report(
                                channel=f"@{channel.username}",
                                post_id=post.id,
                                published_at_iso=msg.date.isoformat(),
                                post_text=msg.message or "",
                                comments=comments,
                                views=getattr(msg, "views", None),
                            )

                            await upsert_report(
                                session,
                                post_id=post.id,
                                status="ready",
                                content=report_text,
                            )
                            print("REPORT:\n", report_text)



                            print(f"Saved post: channel=@{channel.username} tg_msg_id={msg.id} db_post_id={post.id}")


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
async def get_comments(channel: Channel, session, entity, message_id, post_id):
    try:
        discussion = await client(GetDiscussionMessageRequest(peer=entity, msg_id=message_id))
    except MsgIdInvalidError:
        # У этого поста нет валидной ветки обсуждения
        pass
    except FloodWaitError as e:
        print(f"[{channel.username}] FloodWait {e.seconds}s on GetDiscussionMessage, stopping channel")
        await client.disconnect()
        return
    except RPCError as e:
        print(e)
        # нет комментариев / нет linked chat / нет доступа
        pass
    except Exception as e:
        print(e)
        pass

    # discussion.chats[0] — discussion group/supergroup
    if not discussion.chats or not discussion.messages:
        pass

    discussion_chat = discussion.chats[0]
    discussion_root = discussion.messages[0]  # сообщение в группе, связанное с постом

    k = 0
    comments = []
    comments_saved_today = 0
    try:
        async for c in client.iter_messages(discussion_chat, reply_to=discussion_root.id):
            k += 1
            comments.append(c.message)
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
        pass
    
    await set_post_comments_count(
            session,
            post_id=post_id,
            comments_count=comments_saved_today,
        )
    return comments

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