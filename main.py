from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from agents.reporter import TgReportProject
from client import client
from config import settings
from db.models import Channel, Comment
from db.session import AsyncSessionLocal
from services.ingest import upsert_report
from services.ingestion_core import IngestionCore, IngestionOptions, day_bounds_utc
from services.linker import link_post_to_graph, upsert_post_link
from services.TGqueries import update_post_comments

LINK_REPLY_TO = "REPLY_TO"
MIN_REPLIES_TODAY = 20

report_project = TgReportProject(
    llm_model="ollama/llama3:8b-instruct-q4_K_M",
)


async def _get_active_channels() -> list[Channel]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Channel).where(Channel.is_active.is_(True)))
        return list(res.scalars().all())


async def _load_post_comments_text(session, post_id: int) -> list[str]:
    rows = await session.execute(
        select(Comment.text).where(Comment.post_id == post_id).order_by(Comment.date.asc(), Comment.id.asc())
    )
    return [text or "" for (text,) in rows.all()]


async def _on_post_saved(session, post, ctx) -> None:
    if isinstance(ctx.parent_post_id, int):
        await upsert_post_link(
            session,
            src_post_id=post.id,
            dst_post_id=ctx.parent_post_id,
            link_type=LINK_REPLY_TO,
            confidence=1.0,
            evidence={
                "source": "telegram",
                "kind": "native_reply",
                "parent_tg_message_id": ctx.parent_tg_message_id,
            },
            model_version="telegram-native-v1",
        )

    comments_result = await update_post_comments(session, post.id, tg_client=client)
    views = getattr(ctx.message, "views", None)
    if comments_result.get("status") == "ok":
        comments = await _load_post_comments_text(session, post.id)
        report_text = await report_project.generate_report(
            channel=f"@{ctx.channel.username}",
            post_id=post.id,
            published_at_iso=ctx.message.date.isoformat(),
            post_text=ctx.message.message or "",
            comments=comments,
            views=views,
        )
        await upsert_report(
            session,
            post_id=post.id,
            status="ready",
            content=report_text,
        )
    else:
        await upsert_report(
            session,
            post_id=post.id,
            status="pending",
            content="",
        )

    try:
        await link_post_to_graph(session, post=post)
    except Exception as link_err:
        print(f"[{ctx.channel.username}] linker warning for post_id={post.id}: {link_err!r}")

    print(
        f"Saved post: channel=@{ctx.channel.username} tg_msg_id={ctx.message.id} "
        f"db_post_id={post.id} comments_status={comments_result.get('status')}"
    )


async def run_today_ingestion() -> None:
    channels = await _get_active_channels()
    if not channels:
        print("No active channels in DB. Add one via: python -m scripts.add_channel @username")
        return

    await client.start()
    try:
        start_utc, end_utc = day_bounds_utc(settings.tz)
        core = IngestionCore(
            tg_client=client,
            session_factory=AsyncSessionLocal,
        )
        options = IngestionOptions(
            since_utc=start_utc,
            until_utc=end_utc,
            min_replies=MIN_REPLIES_TODAY,
            max_posts=10_000,
            sleep_every=50,
            sleep_base_sec=0.4,
            sleep_jitter_sec=0.6,
            stop_on_existing_post=False,
        )

        for channel in channels:
            print(f"Parsing today for @{channel.username}...")
            result = await core.ingest_channel(
                channel=channel,
                options=options,
                on_post_saved=_on_post_saved,
            )
            print(
                f"Channel done @{channel.username}: processed={result.processed_posts} "
                f"stopped_reason={result.stopped_reason}"
            )
    finally:
        if client.is_connected():
            await client.disconnect()

    print(f"Done at {datetime.now(timezone.utc).isoformat()}.")


async def main() -> None:
    await run_today_ingestion()


if __name__ == "__main__":
    asyncio.run(main())
