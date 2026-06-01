from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings
import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from db.models import Post
from db.session import AsyncSessionLocal
from services.linker import link_post_to_graph


@dataclass
class BackfillStats:
    processed: int = 0
    errors: int = 0
    links_created: int = 0
    candidates_checked: int = 0
    ai_checked: int = 0
    ai_links_created: int = 0
    ai_errors: int = 0


async def run_backfill(
    *,
    batch_size: int,
    commit_every: int,
    start_post_id: int = 0,
    max_posts: int | None = None,
) -> BackfillStats:
    stats = BackfillStats()
    last_seen_id = start_post_id
    pending_since_commit = 0

    async with AsyncSessionLocal() as session:
        while True:
            stmt = (
                select(Post)
                .where(Post.id > last_seen_id)
                .order_by(Post.id.asc())
                .limit(batch_size)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                break

            for post in rows:
                if max_posts is not None and stats.processed >= max_posts:
                    if pending_since_commit > 0:
                        await session.commit()
                    return stats

                last_seen_id = post.id
                try:
                    result = await link_post_to_graph(session, post=post)
                    stats.processed += 1
                    stats.links_created += int(result.get("links_created", 0))
                    stats.candidates_checked += int(result.get("candidates_checked", 0))
                    stats.ai_checked += int(result.get("ai_checked", 0))
                    stats.ai_links_created += int(result.get("ai_links_created", 0))
                    stats.ai_errors += int(result.get("ai_errors", 0))
                    pending_since_commit += 1
                except Exception as exc:
                    stats.errors += 1
                    await session.rollback()
                    pending_since_commit = 0
                    print(f"[ERROR] post_id={post.id}: {exc!r}")
                    continue

                if pending_since_commit >= commit_every:
                    await session.commit()
                    pending_since_commit = 0
                    print(
                        "[PROGRESS] "
                        f"processed={stats.processed} "
                        f"links_created={stats.links_created} "
                        f"ai_links_created={stats.ai_links_created}"
                    )

        if pending_since_commit > 0:
            await session.commit()

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill post metadata/post_links for all posts using linker + AI classifier.",
    )
    parser.add_argument("--batch-size", type=int, default=100, help="How many posts to fetch per DB batch.")
    parser.add_argument("--commit-every", type=int, default=20, help="Commit every N processed posts.")
    parser.add_argument("--start-post-id", type=int, default=0, help="Process posts with id > start-post-id.")
    parser.add_argument("--max-posts", type=int, default=None, help="Optional limit for number of posts to process.")
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()

    print(
        "[CONFIG] "
        f"PIPELINE={settings.LINKING_PIPELINE_VERSION} "
        f"TOP_K={settings.LINKING_TOP_K} "
        f"EMBED_MODEL={settings.LINKING_EMBED_MODEL}"
    )

    stats = await run_backfill(
        batch_size=args.batch_size,
        commit_every=args.commit_every,
        start_post_id=args.start_post_id,
        max_posts=args.max_posts,
    )

    print(
        "[DONE] "
        f"processed={stats.processed} "
        f"errors={stats.errors} "
        f"links_created={stats.links_created} "
        f"candidates_checked={stats.candidates_checked} "
        f"ai_checked={stats.ai_checked} "
        f"ai_links_created={stats.ai_links_created} "
        f"ai_errors={stats.ai_errors}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
