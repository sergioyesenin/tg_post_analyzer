"""Генерация post-report'ов.

Здесь единственная точка входа для post-report job'ов:
build_post_report() — вызывается из services.ai_runtime.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Channel, Comment, Job, Post
from schemas.report import PostReportPayload
from services.ingest import upsert_report
from services.jobs import JobType
from services.report_language import (
    ReportLanguageNormalizationError,
    iter_public_text_fields,
    normalize_report_language,
)
from services.reporting.constants import (
    DEFAULT_MIN_COMMENTS,
    REPORT_GENERATION_FAILED_CONTENT,
    REPORT_STATUS_DEFERRED,
    REPORT_STATUS_FAILED,
    REPORT_STATUS_LIMITED,
    REPORT_STATUS_READY,
)
from services.reporting.mapping import (
    _stringify_path,
    _value_by_path,
    map_internal_post_report_to_public_payload,
    report_status_from_payload,
    _build_public_post_summary,
)
from services.reporting.multi_agent import (
    _build_retrieval_provider,
    _is_multi_agent_shadow_mode_enabled,
    _load_reporting_feature_flags,
    should_use_multi_agent_v2,
    validate_report_contract,
)
from services.reporting.payload import (
    _enrich_post_report_payload,
)
from services.reporting.staleness import (
    _build_post_report_input_signature,
    _load_post_refresh_attempt_info,
)
from services.reporting_v2 import generate_post_report_payload_v2


logger = logging.getLogger(__name__)


def _build_dependency(job_type: str, *, entity_id: int, reason: str) -> dict:
    entity_key = {
        JobType.REFRESH_COMMENTS: "post_id",
        JobType.BUILD_POST_REPORT: "post_id",
        JobType.BUILD_EVENT_REPORT: "event_id",
        JobType.BUILD_PROCESS_REPORT: "process_id",
    }.get(job_type)
    if entity_key is None:
        raise ValueError(f"Unsupported dependency job type: {job_type}")
    return {
        "job_type": job_type,
        entity_key: int(entity_id),
        "reason": reason,
    }

async def _post_report_readiness(session: AsyncSession, *, post: Post) -> dict:
    if not (post.text or "").strip():
        return {
            "ready": False,
            "reason": "missing_post_text",
            "dependencies": [],
            "terminal": True,
        }

    refresh_attempt = await _load_post_refresh_attempt_info(session, post_id=int(post.id))
    if refresh_attempt is None:
        return {
            "ready": False,
            "reason": "waiting_refresh_post_data",
            "dependencies": [
                _build_dependency(
                    JobType.REFRESH_COMMENTS,
                    entity_id=int(post.id),
                    reason="waiting_refresh_post_data",
                )
            ],
            "terminal": False,
        }

    return {
        "ready": True,
        "reason": "ready",
        "dependencies": [],
        "terminal": False,
        "refresh_attempt": refresh_attempt,
    }




def _render_post_report_text(payload: dict) -> str:
    return _build_public_post_summary(payload)



async def build_post_report(
    session: AsyncSession,
    *,
    post_id: int,
    job_timeout_seconds: int | None = None
) -> dict:
    post_result = await session.execute(
        select(Post, Channel)
        .join(Channel, Channel.id == Post.channel_id)
        .where(Post.id == post_id)
    )
    row = post_result.first()
    if row is None:
        return {"status": "not_found", "post_id": post_id}

    post, channel = row
    readiness = await _post_report_readiness(session, post=post)
    if not readiness.get("ready"):
        status = REPORT_STATUS_FAILED if readiness.get("terminal") else REPORT_STATUS_DEFERRED
        return {
            "status": status,
            "post_id": post.id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    comments_result = await session.execute(
        select(
            Comment.tg_message_id,
            Comment.parent_tg_message_id,
            Comment.thread_root_tg_message_id,
            Comment.depth,
            Comment.date,
            Comment.text,
            Comment.reactions_json,
        )
        .where(Comment.post_id == post.id)
        .order_by(Comment.date.asc(), Comment.id.asc())
    )
    comment_rows = comments_result.all()
    input_signature = _build_post_report_input_signature(post=post, comment_rows=comment_rows)

    comments: list[str] = []
    thread_comments: list[dict] = []
    for tg_message_id, parent_tg_message_id, thread_root_tg_message_id, depth, date, text, reactions_json in comment_rows:
        if not text or not text.strip():
            continue
        comments.append(text)
        normalized_parent_id = parent_tg_message_id
        if thread_root_tg_message_id is not None and parent_tg_message_id == thread_root_tg_message_id:
            normalized_parent_id = None
        thread_comments.append(
            {
                "id": tg_message_id,
                "parent_id": normalized_parent_id,
                "depth": depth,
                "date": date.isoformat() if date is not None else None,
                "text": text,
            }
        )

    channel_label = f"@{channel.username}" if channel.username else f"channel:{channel.id}"
    status = REPORT_STATUS_READY
    report_json: dict | None = None
    shadow_compare: dict[str, Any] | None = None
    try:
        features = await _load_reporting_feature_flags(session)
        use_multi_agent_v2 = should_use_multi_agent_v2(post_id=int(post.id), features=features)
        shadow_mode_enabled = _is_multi_agent_shadow_mode_enabled(features=features)
        logger.info(
            "build_post_report path decision post_id=%s use_multi_agent_v2=%s shadow_mode_enabled=%s",
            post.id,
            use_multi_agent_v2,
            shadow_mode_enabled,
        )
        retrieval_provider = _build_retrieval_provider(features)

        report_json = await generate_post_report_payload_v2(
        channel=channel_label,
        post_id=post.id,
        published_at_iso=post.date.isoformat(),
        post_text=post.text or "",
        comments=comments,
        thread_comments=thread_comments,
        views=post.views,
        job_timeout_seconds=job_timeout_seconds,
        effective_features=features,
        retrieval_provider=retrieval_provider,
        )
        logger.info(
            "build_post_report selected path post_id=%s",
            post.id
        )
        report_json = map_internal_post_report_to_public_payload(report_json)
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)

        report_json = _enrich_post_report_payload(payload=report_json, post=post, comment_rows=comment_rows)
        report_json.setdefault("post_id", post.id)
        report_json.setdefault("published_at", post.date.isoformat())
        report_json["meta"] = {
            **dict(report_json.get("meta") or {}),
            "input_signature": input_signature,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "refresh_attempt": readiness.get("refresh_attempt"),
        }
        report_json = PostReportPayload.model_validate(report_json).model_dump(mode="python")
        pre_normalization_payload = dict(report_json)
        pre_normalization_status = str(report_json.get("status") or "")
        try:
            report_json = await normalize_report_language(report_json)
            translated_fields: list[str] = []
            for path, _text in list(iter_public_text_fields(report_json)):
                before_text = _value_by_path(pre_normalization_payload, path)
                after_text = _value_by_path(report_json, path)
                if isinstance(before_text, str) and isinstance(after_text, str) and before_text != after_text:
                    translated_fields.append(_stringify_path(path))
            if translated_fields:
                logger.warning(
                    "report language normalized",
                    extra={
                        "post_id": post.id,
                        "fields": translated_fields,
                        "source_lang": "en_or_mixed",
                        "target_lang": "ru",
                    },
                )
        except ReportLanguageNormalizationError as language_exc:
            logger.warning("Post report language normalization was partial post_id=%s err=%s", post.id, language_exc)
            report_json["status"] = REPORT_STATUS_LIMITED
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "language_normalization": {
                    "status": "partial",
                    "error": str(language_exc),
                },
            }
            logger.warning(
                "report status downgraded",
                extra={
                    "post_id": post.id,
                    "from_status": pre_normalization_status or "unknown",
                    "to_status": str(report_json.get("status") or REPORT_STATUS_LIMITED),
                    "issues": ["language_normalization_partial"],
                },
            )
        except Exception as language_exc:
            logger.warning("Post report language normalization failed post_id=%s err=%s", post.id, language_exc)
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "language_normalization": {
                    "status": "failed",
                    "error": f"{type(language_exc).__name__}: {language_exc}",
                },
            }
        contract_result = validate_report_contract(report_json)
        if contract_result.issues:
            logger.warning(
                "report validation issues detected",
                extra={
                    "post_id": post.id,
                    "critical": contract_result.critical,
                    "issues": contract_result.issues,
                },
            )
            report_json["meta"] = {
                **dict(report_json.get("meta") or {}),
                "validation": {
                    "ok": contract_result.ok,
                    "critical": contract_result.critical,
                    "issues": contract_result.issues,
                },
            }
        if contract_result.critical:
            previous_status = str(report_json.get("status") or "")
            report_json["status"] = REPORT_STATUS_LIMITED
            confidence_payload = dict(report_json.get("confidence") or {})
            confidence_payload["overall"] = "low" if any(item.get("code") in {"C1", "C3", "C5", "C9"} for item in contract_result.issues) else "medium"
            confidence_payload["reason"] = "contract_validator_downgrade"
            report_json["confidence"] = confidence_payload
            logger.warning(
                "report status downgraded",
                extra={
                    "post_id": post.id,
                    "from_status": previous_status or "unknown",
                    "to_status": REPORT_STATUS_LIMITED,
                    "issues": [str(item.get("reason") or item.get("code") or "validation_issue") for item in contract_result.issues],
                },
            )
        report_json = PostReportPayload.model_validate(report_json).model_dump(mode="python")
        status = report_status_from_payload(report_json, fallback=REPORT_STATUS_READY)
        if status != str(report_json.get("status") or ""):
            logger.info(
                "report final status resolved",
                extra={
                    "post_id": post.id,
                    "payload_status": str(report_json.get("status") or ""),
                    "resolved_status": status,
                    "reason": "report_status_from_payload",
                },
            )
        if status == REPORT_STATUS_FAILED:
            content = REPORT_GENERATION_FAILED_CONTENT
            technical_error = str((report_json.get("meta") or {}).get("validation_error") or "invalid_model_output")
        else:
            content = _render_post_report_text(report_json)
            technical_error = None
    except Exception as exc:
        status = REPORT_STATUS_FAILED
        content = REPORT_GENERATION_FAILED_CONTENT
        technical_error = f"{type(exc).__name__}: {exc}"

    report = await upsert_report(
        session,
        post_id=post.id,
        status=status,
        content=content,
        report_json=report_json,
    )
    result = {"status": status, "post_id": post.id, "report_id": report.id}
    if technical_error is not None:
        result["technical_error"] = technical_error
    if shadow_compare is not None:
        result["shadow_compare"] = shadow_compare
    return result