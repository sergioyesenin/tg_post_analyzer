from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import PostLink, PostLinkType, VerificationStatus
from db.session import AsyncSessionLocal

REPLY_KINDS = {"native_reply", "reply_to_post"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill reply links: migrate background(native_reply) to canonical update type."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not persist changes.")
    return parser


async def run_backfill(*, dry_run: bool) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(PostLink).where(
                    and_(
                        PostLink.link_type == PostLinkType.BACKGROUND,
                        PostLink.status == VerificationStatus.VERIFIED,
                    )
                )
            )
        ).scalars().all()

        migrated = 0
        deleted = 0
        for row in rows:
            evidence = row.evidence_json or {}
            kind = str(evidence.get("kind") or "").strip().lower()
            if kind not in REPLY_KINDS:
                continue

            stmt = (
                insert(PostLink)
                .values(
                    src_post_id=row.src_post_id,
                    dst_post_id=row.dst_post_id,
                    link_type=PostLinkType.UPDATE,
                    direction=row.direction,
                    score=row.score,
                    status=row.status,
                    evidence_json=evidence,
                    model_version="reply-link-backfill-v1",
                    pipeline_version=row.pipeline_version,
                    created_at=row.created_at,
                    updated_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    constraint="uq_post_links_src_dst_type",
                    set_={
                        "direction": row.direction,
                        "score": row.score,
                        "status": row.status,
                        "evidence_json": evidence,
                        "model_version": "reply-link-backfill-v1",
                        "pipeline_version": row.pipeline_version,
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
            )
            await session.execute(stmt)
            migrated += 1

            await session.delete(row)
            deleted += 1

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return {
        "migrated_to_update": migrated,
        "deleted_background_reply": deleted,
    }


async def main_async() -> None:
    args = _build_parser().parse_args()
    result = await run_backfill(dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"[{mode}] migrated_to_update={result['migrated_to_update']} deleted_background_reply={result['deleted_background_reply']}")


if __name__ == "__main__":
    asyncio.run(main_async())
