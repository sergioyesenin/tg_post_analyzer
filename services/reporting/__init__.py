from __future__ import annotations

import logging
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Event, EventReport, Process, ProcessEvent, ProcessReport
from services.jobs import JobType
from services.report_aggregation import build_process_report_payload
from services.reporting_v2 import build_event_report_v2_impl


from services.reporting.mapping import (
    _is_payload_dependency_ready,
    _localize_public_section_labels,
    _trim_sentence,
    report_status_from_payload,
)

from services.reporting.constants import (
    REPORT_STATUS_DEFERRED,
    REPORT_STATUS_DRAFT,
    REPORT_STATUS_READY,
    REPORT_STATUS_STALE,
)

from services.reporting.payload import _aggregate_child_coverage



from services.reporting.post_reports import (
    _build_dependency,
)

logger = logging.getLogger(__name__)



def _render_event_or_process_text(payload: dict) -> str:
    summary = _localize_public_section_labels(str(payload.get("summary") or ""))
    return _trim_sentence(summary, fallback="Недостаточно данных для итогового описания.")


async def _load_latest_event_report_snapshots_for_process(session: AsyncSession, *, process_id: int) -> list[tuple[int, str | None, dict | None, str]]:
    event_rows = (
        await session.execute(
            select(ProcessEvent.event_id, Event.title)
            .join(Event, Event.id == ProcessEvent.event_id)
            .where(ProcessEvent.process_id == process_id)
            .order_by(ProcessEvent.created_at.asc(), ProcessEvent.event_id.asc())
        )
    ).all()
    rows = (
        await session.execute(
            select(
                EventReport.event_id,
                EventReport.report_json,
                EventReport.version,
                EventReport.id,
            )
            .where(
                EventReport.event_id.in_(
                    select(ProcessEvent.event_id).where(ProcessEvent.process_id == process_id)
                )
            )
            .order_by(EventReport.event_id.asc(), EventReport.version.desc(), EventReport.id.desc())
        )
    ).all()
    latest_by_event_id: dict[int, dict | None] = {}
    for event_id, report_json, _version, _report_id in rows:
        latest_by_event_id.setdefault(int(event_id), report_json if isinstance(report_json, dict) else None)

    snapshots: list[tuple[int, str | None, dict | None, str]] = []
    for event_id, event_title in event_rows:
        payload = latest_by_event_id.get(int(event_id))
        snapshots.append(
            (
                int(event_id),
                event_title,
                dict(payload) if isinstance(payload, dict) else None,
                report_status_from_payload(payload, fallback=""),
            )
        )
    return snapshots


async def _load_latest_event_report_payloads_for_process(session: AsyncSession, *, process_id: int) -> list[dict]:
    payloads: list[dict] = []
    for event_id, event_title, payload, _status in await _load_latest_event_report_snapshots_for_process(session, process_id=process_id):
        if not _is_payload_dependency_ready(payload):
            continue
        selected_payload = dict(payload or {})
        selected_payload.setdefault("event_id", int(event_id))
        selected_payload.setdefault("event_title", event_title)
        payloads.append(selected_payload)
    return payloads

async def _process_report_readiness(session: AsyncSession, *, process_id: int) -> dict:
    snapshots = await _load_latest_event_report_snapshots_for_process(session, process_id=process_id)
    total_events = len(snapshots)
    if total_events == 0:
        return {
            "ready": True,
            "reason": "no_events",
            "total_events": 0,
            "ready_event_reports": 0,
            "required_ready_event_reports": 0,
        }
    ready_event_reports = 0
    blocked_events = 0
    dependencies: list[dict] = []
    for event_id, _event_title, payload, status in snapshots:
        if _is_payload_dependency_ready(payload):
            ready_event_reports += 1
        elif status in {"", REPORT_STATUS_STALE}:
            dependencies.append(
                _build_dependency(
                    JobType.BUILD_EVENT_REPORT,
                    entity_id=int(event_id),
                    reason="waiting_event_reports",
                )
            )
        else:
            blocked_events += 1
    required_ready = max(1, math.ceil(total_events * 0.7))
    ready = ready_event_reports >= required_ready
    return {
        "ready": ready,
        "reason": "ready" if ready else ("blocked_event_reports" if blocked_events > 0 and not dependencies else "waiting_event_reports"),
        "total_events": total_events,
        "ready_event_reports": ready_event_reports,
        "required_ready_event_reports": required_ready,
        "blocked_event_reports": blocked_events,
        "dependencies": dependencies,
    }


async def build_process_report_draft(
    session: AsyncSession,
    *,
    process_id: int,
) -> dict:
    process = await session.get(Process, process_id)
    if process is None:
        return {"status": "not_found", "process_id": process_id}

    readiness = await _process_report_readiness(session, process_id=process_id)
    if not readiness.get("ready"):
        return {
            "status": REPORT_STATUS_DEFERRED,
            "process_id": process_id,
            "reason": readiness.get("reason"),
            "readiness": readiness,
            "dependencies": list(readiness.get("dependencies") or []),
        }

    event_payloads = await _load_latest_event_report_payloads_for_process(session, process_id=process_id)
    if not event_payloads:
        payload = {
            "type": "process_report_v2",
            "status": REPORT_STATUS_DRAFT,
            "process_id": process_id,
            "process_title": process.title,
            "events_count": int(readiness.get("total_events") or 0),
            "source_event_reports": [],
            "summary": "Р”Р»СЏ РїСЂРѕС†РµСЃСЃР° РїРѕРєР° РЅРµС‚ РіРѕС‚РѕРІС‹С… РѕС‚С‡РµС‚РѕРІ РїРѕ СЃРѕР±С‹С‚РёСЏРј РёР»Рё РїРѕСЃС‚Р°Рј.",
            "meta": {"prompt_version": "process_report_v2", "source_type": "event_reports", "readiness": readiness},
        }
        status = REPORT_STATUS_DRAFT
    else:
        payload = build_process_report_payload(
            process_id=process_id,
            process_title=process.title,
            event_reports=event_payloads,
        )
        status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    coverage, stance = _aggregate_child_coverage(event_payloads)
    payload["reactions_coverage"] = coverage
    payload["audience_stance"] = stance
    payload["meta"] = {
        **dict(payload.get("meta") or {}),
        "coverage_factor": coverage.get("factor"),
    }

    last_version = (
        await session.execute(
            select(ProcessReport.version)
            .where(ProcessReport.process_id == process_id)
            .order_by(ProcessReport.version.desc(), ProcessReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = ProcessReport(
        process_id=process_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "process_id": process_id, "report_id": report.id}

