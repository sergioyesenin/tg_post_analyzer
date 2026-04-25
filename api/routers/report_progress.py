from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uvicorn.protocols.utils import ClientDisconnected

from db.models import Job, User
from deps import get_session
from services.auth import decode_access_token
from services.jobs import JOB_STATUS_DONE, JOB_STATUS_FAILED, JOB_STATUS_PENDING, JOB_STATUS_RUNNING, get_job_result

router = APIRouter()

REPORT_JOB_TYPES = {
    "build_post_report": "post",
    "build_event_report": "event",
    "build_process_report": "process",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_current_user(session: AsyncSession, *, access_token: str | None) -> User | None:
    if not access_token:
        return None
    try:
        payload = decode_access_token(access_token)
        subject = payload.get("sub")
        user_id = int(subject)
    except Exception:
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def _extract_entity(job: Job) -> tuple[str | None, int | None]:
    entity_type = REPORT_JOB_TYPES.get(str(job.type))
    payload = dict(job.payload_json or {})
    if entity_type == "post":
        return entity_type, _safe_int(payload.get("post_id"))
    if entity_type == "event":
        return entity_type, _safe_int(payload.get("event_id"))
    if entity_type == "process":
        return entity_type, _safe_int(payload.get("process_id"))
    return None, None


def _safe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_request_id(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "undefined", "null", "none"}:
        return None
    return _safe_int(value)


async def _resolve_report_job(
    session: AsyncSession,
    *,
    request_id: int | None,
    expected_entity_type: str | None,
    expected_entity_id: int | None,
    current_user_id: int,
) -> Job | None:
    if request_id is not None:
        return await session.get(Job, request_id, populate_existing=True)

    if expected_entity_type is None or expected_entity_id is None:
        return None

    report_job_type = next((job_type for job_type, entity in REPORT_JOB_TYPES.items() if entity == expected_entity_type), None)
    if report_job_type is None:
        return None

    stmt = (
        select(Job)
        .where(Job.type == report_job_type)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(100)
    )
    candidates = (await session.execute(stmt)).scalars().all()
    for candidate in candidates:
        payload = dict(candidate.payload_json or {})
        if _safe_int(payload.get("requested_by_user_id")) != current_user_id:
            continue
        entity_type, entity_id = _extract_entity(candidate)
        if entity_type == expected_entity_type and entity_id == expected_entity_id:
            return candidate
    return None


def _job_is_blocked(*, job: Job, result: dict) -> bool:
    markers = [
        str(result.get("status") or ""),
        str(result.get("reason") or ""),
        str(result.get("error") or ""),
        str(job.last_error or ""),
    ]
    return any("blocked" in marker.lower() for marker in markers if marker)


def _job_timestamp(job: Job) -> str:
    value = job.updated_at or job.created_at or _utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _build_progress_event(job: Job) -> dict | None:
    entity_type, entity_id = _extract_entity(job)
    if entity_type is None or entity_id is None:
        return None

    result = dict(get_job_result(job) or {})
    payload = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "request_id": int(job.id),
        "timestamp": _job_timestamp(job),
    }

    if job.status in {JOB_STATUS_PENDING, JOB_STATUS_RUNNING}:
        return {
            **payload,
            "type": "report_build_started",
            "status": "building_report",
            "message": "Report is building.",
        }

    if job.status == JOB_STATUS_DONE:
        completed = {
            **payload,
            "type": "report_build_completed",
            "status": "completed",
        }
        report_id = _safe_int(result.get("report_id"))
        location = result.get("location")
        if report_id is not None or isinstance(location, str):
            completed["result"] = {}
            if report_id is not None:
                completed["result"]["report_id"] = report_id
            if isinstance(location, str) and location.strip():
                completed["result"]["location"] = location
        return completed

    if job.status == JOB_STATUS_FAILED:
        error_code = str(result.get("reason") or "build_failed")
        error_message = (
            str(result.get("message") or "")
            or str(result.get("error") or "")
            or str(job.last_error or "")
            or "Report build failed."
        )
        if _job_is_blocked(job=job, result=result):
            return {
                **payload,
                "type": "report_build_blocked",
                "status": "blocked",
                "message": error_message,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
            }
        return {
            **payload,
            "type": "report_build_failed",
            "status": "failed",
            "message": error_message,
            "error": {
                "code": error_code,
                "message": error_message,
            },
        }

    return None


def _event_fingerprint(event: dict) -> tuple[object, ...]:
    result = event.get("result") if isinstance(event.get("result"), dict) else {}
    error = event.get("error") if isinstance(event.get("error"), dict) else {}
    return (
        event.get("type"),
        event.get("status"),
        event.get("request_id"),
        event.get("timestamp"),
        result.get("report_id"),
        result.get("location"),
        error.get("code"),
        error.get("message"),
    )


async def _release_session(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        # Session may already be closed/invalid; best effort to release resources.
        return


async def _safe_close_websocket(websocket: WebSocket, *, code: int = 1000, reason: str = "") -> None:
    if websocket.application_state is not WebSocketState.CONNECTED:
        return
    try:
        await websocket.close(code=code, reason=reason)
    except (RuntimeError, WebSocketDisconnect, ClientDisconnected):
        return


@router.websocket("/ws")
async def report_progress_websocket(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
):
    access_token = websocket.query_params.get("access_token")
    request_id = _normalize_request_id(websocket.query_params.get("request_id"))
    expected_entity_type = websocket.query_params.get("entity_type")
    expected_entity_id = _safe_int(websocket.query_params.get("entity_id"))

    current_user = await _resolve_current_user(session, access_token=access_token)
    if current_user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    if request_id is None and (expected_entity_type is None or expected_entity_id is None):
        await websocket.close(code=4400, reason="request_id or entity binding is required")
        return

    job = await _resolve_report_job(
        session,
        request_id=request_id,
        expected_entity_type=expected_entity_type,
        expected_entity_id=expected_entity_id,
        current_user_id=int(current_user.id),
    )
    if job is None or str(job.type) not in REPORT_JOB_TYPES:
        await websocket.close(code=4404, reason="Report request not found")
        return
    request_id = int(job.id)

    payload = dict(job.payload_json or {})
    if _safe_int(payload.get("requested_by_user_id")) != int(current_user.id):
        await websocket.close(code=4403, reason="Forbidden")
        return

    entity_type, entity_id = _extract_entity(job)
    if entity_type is None or entity_id is None:
        await websocket.close(code=4404, reason="Entity binding not found")
        return
    if expected_entity_type and expected_entity_type != entity_type:
        await websocket.close(code=4404, reason="Entity type mismatch")
        return
    if expected_entity_id is not None and expected_entity_id != entity_id:
        await websocket.close(code=4404, reason="Entity id mismatch")
        return

    # Release DB connection before entering long-lived websocket loop.
    await _release_session(session)
    await websocket.accept()
    last_fingerprint: tuple[object, ...] | None = None

    try:
        while True:
            try:
                job = await session.get(Job, request_id, populate_existing=True)
            finally:
                # Do not keep transaction open between websocket polls.
                await _release_session(session)
            if job is None:
                await _safe_close_websocket(websocket, code=4404, reason="Report request not found")
                return

            event = _build_progress_event(job)
            if event is not None:
                fingerprint = _event_fingerprint(event)
                if fingerprint != last_fingerprint:
                    await websocket.send_json(event)
                    last_fingerprint = fingerprint
                if event["status"] in {"completed", "failed", "blocked"}:
                    return

            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, ClientDisconnected):
        return
    finally:
        await _safe_close_websocket(websocket)
