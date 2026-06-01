from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import Comment, Post
from db.session import AsyncSessionLocal
from services.involvement import compute_comment_metrics_by_post_id, compute_involvement


logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill commenters, long_comments, and involvement for historical posts.")
    parser.add_argument("--batch-size", type=int, default=100, help="Posts per DB batch")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of posts to process")
    parser.add_argument("--min-post-id", type=int, default=None, help="Optional inclusive lower bound for Post.id")
    parser.add_argument("--max-post-id", type=int, default=None, help="Optional inclusive upper bound for Post.id")
    parser.add_argument("--dry-run", action="store_true", help="Compute and log results without persisting changes")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


def _build_posts_stmt(
    *,
    batch_size: int,
    last_seen_post_id: int,
    min_post_id: int | None,
    max_post_id: int | None,
    remaining: int | None,
) -> Select[tuple[Post]]:
    stmt = select(Post).where(Post.id > last_seen_post_id)
    if min_post_id is not None:
        stmt = stmt.where(Post.id >= min_post_id)
    if max_post_id is not None:
        stmt = stmt.where(Post.id <= max_post_id)
    stmt = stmt.order_by(Post.id.asc())
    effective_batch_size = batch_size if remaining is None else min(batch_size, remaining)
    return stmt.limit(max(1, effective_batch_size))


async def _load_post_batch(
    session: AsyncSession,
    *,
    batch_size: int,
    last_seen_post_id: int,
    min_post_id: int | None,
    max_post_id: int | None,
    remaining: int | None,
) -> list[Post]:
    stmt = _build_posts_stmt(
        batch_size=batch_size,
        last_seen_post_id=last_seen_post_id,
        min_post_id=min_post_id,
        max_post_id=max_post_id,
        remaining=remaining,
    )
    return list((await session.execute(stmt)).scalars().all())


async def _load_comment_metrics_for_posts(session: AsyncSession, post_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not post_ids:
        return {}
    rows = (
        await session.execute(
            select(Comment.post_id, Comment.author_id, Comment.author_username, Comment.text).where(Comment.post_id.in_(post_ids))
        )
    ).all()
    return compute_comment_metrics_by_post_id(rows)


async def _persist_post_metrics(
    session: AsyncSession,
    *,
    post_id: int,
    commenters: int,
    long_comments: int,
    involvement: float,
) -> None:
    await session.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(
            commenters=commenters,
            long_comments=long_comments,
            involvement=involvement,
        )
    )


async def backfill_involvement_metrics(
    *,
    session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession] = AsyncSessionLocal,
    batch_size: int = 100,
    dry_run: bool = False,
    min_post_id: int | None = None,
    max_post_id: int | None = None,
    limit: int | None = None,
) -> dict[str, int | bool | float | None]:
    effective_batch_size = max(1, int(batch_size))
    remaining = None if limit is None else max(0, int(limit))
    processed = 0
    updated = 0
    last_seen_post_id = 0 if min_post_id is None else max(0, int(min_post_id) - 1)

    while remaining is None or remaining > 0:
        async with session_factory() as session:
            posts = await _load_post_batch(
                session,
                batch_size=effective_batch_size,
                last_seen_post_id=last_seen_post_id,
                min_post_id=min_post_id,
                max_post_id=max_post_id,
                remaining=remaining,
            )
            if not posts:
                break

            post_ids = [int(post.id) for post in posts]
            comment_metrics_by_post_id = await _load_comment_metrics_for_posts(session, post_ids)

            for post in posts:
                commenters, long_comments = comment_metrics_by_post_id.get(int(post.id), (0, 0))
                involvement = compute_involvement(
                    views=post.views,
                    comments_count=post.comments_count,
                    commenters=commenters,
                    long_comments=long_comments,
                    reactions_payload=post.reactions_json,
                )

                if dry_run:
                    logger.info(
                        "Dry-run post_id=%s commenters=%s long_comments=%s involvement=%.6f",
                        post.id,
                        commenters,
                        long_comments,
                        involvement,
                    )
                else:
                    await _persist_post_metrics(
                        session,
                        post_id=int(post.id),
                        commenters=commenters,
                        long_comments=long_comments,
                        involvement=involvement,
                    )
                    updated += 1

                processed += 1
                if remaining is not None:
                    remaining -= 1
                last_seen_post_id = int(post.id)

            if not dry_run:
                await session.commit()

    logger.info(
        "Involvement backfill finished | processed=%s updated=%s dry_run=%s min_post_id=%s max_post_id=%s limit=%s",
        processed,
        updated,
        dry_run,
        min_post_id,
        max_post_id,
        limit,
    )
    return {
        "processed": processed,
        "updated": updated,
        "dry_run": dry_run,
        "batch_size": effective_batch_size,
        "min_post_id": min_post_id,
        "max_post_id": max_post_id,
        "limit": limit,
    }


async def run_backfill(args: argparse.Namespace) -> dict[str, int | bool | float | None]:
    return await backfill_involvement_metrics(
        batch_size=args.batch_size,
        dry_run=bool(args.dry_run),
        min_post_id=args.min_post_id,
        max_post_id=args.max_post_id,
        limit=args.limit,
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)
    asyncio.run(run_backfill(args))


if __name__ == "__main__":
    main()
