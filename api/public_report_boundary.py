from __future__ import annotations

from copy import deepcopy

from schemas.linking import LinkedReportOut
from schemas.report import ReportOut


def sanitize_public_report_json(report_json: dict | None) -> dict | None:
    if not isinstance(report_json, dict):
        return report_json

    sanitized = deepcopy(report_json)
    meta = sanitized.get("meta")
    if not isinstance(meta, dict):
        return sanitized

    meta = dict(meta)
    meta.pop("multi_agent", None)
    if meta:
        sanitized["meta"] = meta
    else:
        sanitized.pop("meta", None)
    return sanitized


def to_public_report_out(report) -> ReportOut:
    return ReportOut.model_validate(
        {
            "id": report.id,
            "post_id": report.post_id,
            "status": report.status,
            "content": report.content,
            "report_json": sanitize_public_report_json(report.report_json),
            "created_at": report.created_at,
        }
    )


def to_public_linked_report_out(report) -> LinkedReportOut:
    return LinkedReportOut(
        id=report.id,
        status=report.report_json.get("status", "ready") if isinstance(report.report_json, dict) else "ready",
        version=report.version,
        report_text=report.report_text,
        report_json=sanitize_public_report_json(report.report_json),
        created_at=report.created_at,
    )
