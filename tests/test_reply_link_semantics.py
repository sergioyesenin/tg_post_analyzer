from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from db.models import PostLinkType
from services.linker import _normalize_link_type, upsert_post_link
from services.linking.no_llm_pipeline import NoLlmLinkingPipeline


class _CaptureSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement


def test_reply_mapping_is_canonical_update():
    assert _normalize_link_type("reply_to") == PostLinkType.UPDATE
    assert _normalize_link_type("native_reply") == PostLinkType.UPDATE
    assert _normalize_link_type("background") == PostLinkType.BACKGROUND


def test_upsert_post_link_maps_reply_to_update():
    session = _CaptureSession()
    asyncio.run(
        upsert_post_link(
            session,
            src_post_id=10,
            dst_post_id=20,
            link_type="reply_to",
            confidence=1.0,
            evidence={"kind": "native_reply"},
        )
    )
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert compiled.params["link_type"] == PostLinkType.UPDATE


def test_no_llm_pipeline_reply_link_type_is_update():
    pipeline = NoLlmLinkingPipeline.build_default()
    session = _CaptureSession()
    post = SimpleNamespace(id=100, parent_post_id=50)
    asyncio.run(pipeline._commit_reply_update_link(session, post))  # noqa: SLF001
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert compiled.params["link_type"] == PostLinkType.UPDATE
