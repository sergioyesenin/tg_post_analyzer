from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.postgresql import JSONB

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import settings
from db.models import Post, PostFeature
from db.session import AsyncSessionLocal
from services.linking.embeddings import EmbeddingProvider


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill embeddings into post_features.embedding.vector")
    parser.add_argument("--batch-size", type=int, default=25, help="Posts per DB batch")
    parser.add_argument("--max-posts", type=int, default=500, help="Max posts to process in this run")
    parser.add_argument("--channel-id", type=int, default=None, help="Optional channel_id filter")
    parser.add_argument("--hours-back", type=int, default=None, help="Optional time window from now")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(asctime)s | %(levelname)-7s | %(message)s")


async def _load_batch(*, batch_size: int, channel_id: int | None, date_from: datetime | None) -> list[Post]:
    async with AsyncSessionLocal() as session:
        conditions = []
        if channel_id is not None:
            conditions.append(Post.channel_id == channel_id)
        if date_from is not None:
            conditions.append(Post.date >= date_from)

        stmt = (
            select(Post)
            .outerjoin(PostFeature, PostFeature.post_id == Post.id)
            .where(
                and_(
                    *conditions,
                    or_(
                        PostFeature.post_id.is_(None),
                        PostFeature.embedding.is_(None),
                        func.jsonb_typeof(cast(PostFeature.embedding, JSONB)["vector"]).is_(None),
                    ),
                )
            )
            .order_by(Post.date.desc(), Post.id.desc())
            .limit(batch_size)
        )
        return list((await session.execute(stmt)).scalars().all())


async def _upsert_embedding(post: Post, vector: list[float]) -> None:
    payload = {
        "model": settings.LINKING_EMBED_MODEL,
        "vector": vector,
    }
    async with AsyncSessionLocal() as session:
        stmt = (
            insert(PostFeature)
            .values(
                post_id=post.id,
                text_normalized=(post.text or "")[: settings.LINKING_MAX_TEXT_CHARS].lower(),
                embedding=payload,
                analyzer_version="embedding-backfill-v1",
            )
            .on_conflict_do_update(
                index_elements=[PostFeature.post_id],
                set_={
                    "text_normalized": (post.text or "")[: settings.LINKING_MAX_TEXT_CHARS].lower(),
                    "embedding": payload,
                    "analyzer_version": "embedding-backfill-v1",
                },
            )
        )
        await session.execute(stmt)
        await session.commit()


async def run_backfill(args: argparse.Namespace) -> None:
    provider = EmbeddingProvider()
    if not provider.enabled:
        logging.error("Embedding provider is disabled by config. Set LINKING_EMBED_ENABLED=true.")
        return

    date_from = None
    if args.hours_back is not None:
        date_from = datetime.now(timezone.utc) - timedelta(hours=args.hours_back)

    done = 0
    failures = 0
    started = datetime.now(timezone.utc)
    logging.info(
        "Embedding backfill started | model=%s | max_posts=%s | batch_size=%s",
        settings.LINKING_EMBED_MODEL,
        args.max_posts,
        args.batch_size,
    )
    while done < args.max_posts:
        batch = await _load_batch(
            batch_size=min(args.batch_size, args.max_posts - done),
            channel_id=args.channel_id,
            date_from=date_from,
        )
        if not batch:
            break

        for post in batch:
            text = (post.text or "").strip()
            if not text:
                done += 1
                continue
            vector = await provider.embed_text(text)
            if not vector:
                failures += 1
                done += 1
                continue
            await _upsert_embedding(post, vector)
            done += 1
            if done % 10 == 0:
                logging.info("Progress: processed=%s failures=%s", done, failures)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logging.info("Embedding backfill finished | processed=%s failures=%s elapsed=%.1fs", done, failures, elapsed)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _configure_logging(args.log_level)
    asyncio.run(run_backfill(args))


if __name__ == "__main__":
    main()
