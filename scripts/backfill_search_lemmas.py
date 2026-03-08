from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from db.models import Post
from db.session import AsyncSessionLocal
from services.keyword_graph import build_search_lemmas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill posts.entities.search_lemmas for keyword search.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--commit-every", type=int, default=100)
    parser.add_argument("--start-post-id", type=int, default=0)
    parser.add_argument("--max-posts", type=int, default=None)
    return parser.parse_args()


async def run_backfill(*, batch_size: int, commit_every: int, start_post_id: int, max_posts: int | None) -> None:
    processed = 0
    updated = 0
    last_id = start_post_id
    since_commit = 0

    async with AsyncSessionLocal() as session:
        while True:
            rows = (
                await session.execute(
                    select(Post)
                    .where(Post.id > last_id)
                    .order_by(Post.id.asc())
                    .limit(batch_size)
                )
            ).scalars().all()
            if not rows:
                break

            for post in rows:
                if max_posts is not None and processed >= max_posts:
                    if since_commit:
                        await session.commit()
                    print(f"[DONE] processed={processed} updated={updated}")
                    return

                processed += 1
                last_id = post.id

                entities = post.entities if isinstance(post.entities, dict) else {}
                existing = entities.get("search_lemmas")
                if isinstance(existing, list) and existing:
                    continue

                lemmas = build_search_lemmas(post.text_normalized or post.text or "")
                if not lemmas:
                    continue

                merged = dict(entities)
                merged["search_lemmas"] = lemmas
                await session.execute(
                    Post.__table__.update()
                    .where(Post.id == post.id)
                    .values(entities=merged)
                )
                updated += 1
                since_commit += 1

                if since_commit >= commit_every:
                    await session.commit()
                    print(f"[PROGRESS] processed={processed} updated={updated} last_id={last_id}")
                    since_commit = 0

        if since_commit:
            await session.commit()

    print(f"[DONE] processed={processed} updated={updated}")


async def _main() -> None:
    args = parse_args()
    await run_backfill(
        batch_size=args.batch_size,
        commit_every=args.commit_every,
        start_post_id=args.start_post_id,
        max_posts=args.max_posts,
    )


if __name__ == "__main__":
    asyncio.run(_main())
