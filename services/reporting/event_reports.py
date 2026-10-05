from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EventReport
from services.reporting.constants import REPORT_STATUS_READY
from services.reporting.mapping import report_status_from_payload
from services.reporting.payload import _render_event_or_process_text
from services.reporting_v2 import build_event_report_v2_impl

async def build_event_report_draft(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict:
    payload = await build_event_report_v2_impl(session=session, event_id=event_id)
    if payload.get("status") == "not_found":
        return {"status": "not_found", "event_id": event_id}
    status = report_status_from_payload(payload, fallback=REPORT_STATUS_READY)
    payload = dict(payload or {})
    payload["status"] = status

    last_version = (
        await session.execute(
            select(EventReport.version)
            .where(EventReport.event_id == event_id)
            .order_by(EventReport.version.desc(), EventReport.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = int(last_version or 0) + 1
    report = EventReport(
        event_id=event_id,
        report_text=_render_event_or_process_text(payload),
        report_json=payload,
        version=next_version,
    )
    session.add(report)
    await session.flush()
    return {"status": status, "event_id": event_id, "report_id": report.id}