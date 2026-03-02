from __future__ import annotations

import asyncio
import inspect
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select

from db.models import PostFeature
from db.session import AsyncSessionLocal

# pymorphy2 compatibility for Python 3.12+
if not hasattr(inspect, "getargspec"):
    from collections import namedtuple

    ArgSpec = namedtuple("ArgSpec", "args varargs keywords defaults")

    def getargspec(func):
        spec = inspect.getfullargspec(func)
        return ArgSpec(spec.args, spec.varargs, spec.varkw, spec.defaults)

    inspect.getargspec = getargspec

import pymorphy2

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass
class RowAudit:
    post_id: int
    created_at: str | None
    entities_count: int
    strict_precision: float | None
    lemma_precision: float | None
    unmatched_strict_entities: list[str]
    text_sample: str


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def build_morph() -> pymorphy2.MorphAnalyzer:
    return pymorphy2.MorphAnalyzer()


def lemma_token(tok: str, morph: pymorphy2.MorphAnalyzer) -> str:
    if tok.isascii():
        return tok
    try:
        return morph.parse(tok)[0].normal_form
    except Exception:
        return tok


def lemmas(text: str, morph: pymorphy2.MorphAnalyzer) -> list[str]:
    return [lemma_token(t, morph) for t in tokenize(text)]


def ent_lemmas(ent: str, morph: pymorphy2.MorphAnalyzer) -> list[str]:
    return [lemma_token(t, morph) for t in tokenize(ent)]


def seq_in_seq(needle: list[str], hay: list[str]) -> bool:
    if not needle or not hay or len(needle) > len(hay):
        return False
    n = len(needle)
    for i in range(len(hay) - n + 1):
        if hay[i : i + n] == needle:
            return True
    return False


def strict_match(ent: str, text: str) -> bool:
    e = (ent or "").strip().lower()
    if len(e) <= 2:
        return False
    p = r"(?<![\\w])" + re.escape(e) + r"(?![\\w])"
    return re.search(p, (text or "").lower()) is not None


def flatten_entities(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    keys = ["entities", "persons", "organizations", "locations", "places", "tickers", "entity_keys"]
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        values = payload.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            s = str(value).strip()
            if not s:
                continue
            sl = s.lower()
            if sl in seen:
                continue
            seen.add(sl)
            out.append(s)
    return out


async def run_audit(limit: int = 30) -> dict[str, Any]:
    morph = build_morph()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(PostFeature).order_by(desc(PostFeature.created_at)).limit(limit)
            )
        ).scalars().all()

    strict_total = strict_hit = 0
    lemma_total = lemma_hit = 0
    rows_without_entities = 0
    audits: list[RowAudit] = []

    for row in rows:
        text = (row.text_normalized or "").strip()
        text_lemmas = lemmas(text, morph)
        entities = flatten_entities(row.entities)

        if not entities:
            rows_without_entities += 1

        s_hit = l_hit = 0
        strict_unmatched: list[str] = []

        for ent in entities:
            strict_total += 1
            lemma_total += 1

            s_ok = strict_match(ent, text)
            l_ok = seq_in_seq(ent_lemmas(ent, morph), text_lemmas)

            if s_ok:
                s_hit += 1
                strict_hit += 1
            else:
                strict_unmatched.append(ent)

            if l_ok:
                l_hit += 1
                lemma_hit += 1

        count = len(entities)
        audits.append(
            RowAudit(
                post_id=row.post_id,
                created_at=row.created_at.isoformat() if row.created_at else None,
                entities_count=count,
                strict_precision=round(s_hit / count, 3) if count else None,
                lemma_precision=round(l_hit / count, 3) if count else None,
                unmatched_strict_entities=strict_unmatched,
                text_sample=text[:180].replace("\n", " "),
            )
        )

    return {
        "summary": {
            "rows": len(rows),
            "rows_without_entities": rows_without_entities,
            "saved_entities_total": lemma_total,
            "strict_match_rate": round(strict_hit / strict_total, 4) if strict_total else None,
            "lemma_match_rate": round(lemma_hit / lemma_total, 4) if lemma_total else None,
        },
        "rows": [a.__dict__ for a in audits],
    }


if __name__ == "__main__":
    report = asyncio.run(run_audit(limit=30))
    print(json.dumps(report, ensure_ascii=False, indent=2))
