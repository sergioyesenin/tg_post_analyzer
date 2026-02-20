from __future__ import annotations

import argparse
import asyncio
import itertools
from dataclasses import dataclass

from sqlalchemy import select

from db.models import Post
from db.session import AsyncSessionLocal
from services.linker import (
    calibrate_ai_confidence,
    extract_entities,
    get_anchor_set,
    jaccard_similarity,
    normalize_text,
    tokenize,
)
from services.linker_ai import AiLinkClassifier


@dataclass
class PairCase:
    label: str
    post_a: Post
    post_b: Post
    text_j: float
    entities_j: float
    shared_anchor_count: int


def _pair_metrics(a: Post, b: Post) -> tuple[float, float, int]:
    a_norm = normalize_text(a.text or "")
    b_norm = normalize_text(b.text or "")
    a_tokens = tokenize(a_norm)
    b_tokens = tokenize(b_norm)
    text_j = jaccard_similarity(a_tokens, b_tokens)

    a_anchors = get_anchor_set(extract_entities(a.text or ""))
    b_anchors = get_anchor_set(extract_entities(b.text or ""))
    entities_j = jaccard_similarity(a_anchors, b_anchors)
    shared_anchor_count = len(a_anchors & b_anchors)
    return text_j, entities_j, shared_anchor_count


def _hours_diff(a: Post, b: Post) -> float:
    return abs((a.date - b.date).total_seconds()) / 3600.0


def build_cases(posts: list[Post], limit_per_group: int) -> list[PairCase]:
    obvious: list[PairCase] = []
    ambiguous: list[PairCase] = []
    unrelated: list[PairCase] = []

    for a, b in itertools.combinations(posts, 2):
        text_j, entities_j, shared = _pair_metrics(a, b)
        hours = _hours_diff(a, b)

        if (
            len(obvious) < limit_per_group
            and a.channel_id == b.channel_id
            and hours <= 48
            and (shared >= 2 or text_j >= 0.33)
        ):
            obvious.append(PairCase("obvious", a, b, text_j, entities_j, shared))
            continue

        if (
            len(ambiguous) < limit_per_group
            and hours <= 72
            and text_j >= 0.2
            and shared == 0
        ): 
            ambiguous.append(PairCase("ambiguous", a, b, text_j, entities_j, shared))
            continue

        if (
            len(unrelated) < limit_per_group
            and text_j <= 0.05
            and entities_j == 0.0
            and shared == 0
            and abs((a.date - b.date).days) >= 1
        ):
            unrelated.append(PairCase("unrelated", a, b, text_j, entities_j, shared))

        if (
            len(obvious) >= limit_per_group
            and len(ambiguous) >= limit_per_group
            and len(unrelated) >= limit_per_group
        ):
            break

    return obvious + ambiguous + unrelated


async def run_eval(*, sample_posts: int, per_group: int) -> None:
    async with AsyncSessionLocal() as session:
        posts = (
            await session.execute(
                select(Post)
                .where(Post.text.is_not(None))
                .order_by(Post.date.desc(), Post.id.desc())
                .limit(sample_posts)
            )
        ).scalars().all()

    if len(posts) < 2:
        print("Not enough posts for pair testing.")
        return

    cases = build_cases(posts, per_group)
    if not cases:
        print("Could not build test pairs from current sample.")
        return

    ai = AiLinkClassifier()
    print(f"Testing {len(cases)} pairs from {len(posts)} sampled posts")
    print("-" * 90)

    for idx, case in enumerate(cases, start=1):
        decision = await ai.classify_pair(
            post_a_text=case.post_a.text or "",
            post_b_text=case.post_b.text or "",
            post_a_channel_id=case.post_a.channel_id,
            post_b_channel_id=case.post_b.channel_id,
            post_a_date=case.post_a.date,
            post_b_date=case.post_b.date,
            text_jaccard=case.text_j,
            entities_jaccard=case.entities_j,
            hash_equal=False,
            shared_anchor_count=case.shared_anchor_count,
        )
        final_conf = calibrate_ai_confidence(
            model_confidence=decision.confidence,
            link_type=decision.link_type,
            text_score=case.text_j,
            entities_score=case.entities_j,
            shared_anchor_count=case.shared_anchor_count,
            reason=decision.reason,
            shared_facts=decision.shared_facts,
            hash_equal=False,
        )

        print(
            f"[{idx:02d}] group={case.label} "
            f"pair=({case.post_a.id},{case.post_b.id}) "
            f"text_j={case.text_j:.3f} entities_j={case.entities_j:.3f} anchors={case.shared_anchor_count}"
        )
        print(
            f"     model: related={decision.is_related} type={decision.link_type} conf={decision.confidence:.3f} "
            f"| final_conf={final_conf:.3f}"
        )
        print(f"     reason: {decision.reason}")
        if decision.shared_facts:
            print(f"     facts: {decision.shared_facts[:3]}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate AI linker on sampled post pairs (obvious/ambiguous/unrelated).",
    )
    parser.add_argument("--sample-posts", type=int, default=100, help="How many recent posts to sample from DB.")
    parser.add_argument("--per-group", type=int, default=1, help="How many pairs per group.")
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    await run_eval(sample_posts=args.sample_posts, per_group=args.per_group)


if __name__ == "__main__":
    asyncio.run(_main())
