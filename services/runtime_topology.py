from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuntimeRole:
    role: str
    runtime_name: str | None
    process_boundary: str
    entrypoint: str
    ownership: str
    heartbeat_source: str
    diagnostics: str


API_RUNTIME = RuntimeRole(
    role="api",
    runtime_name=None,
    process_boundary="http-serving",
    entrypoint="python scripts/run_api.py",
    ownership="FastAPI routers, auth/session endpoints, dashboard/reporting APIs, integrated SPA serving.",
    heartbeat_source="http-health",
    diagnostics="Diagnose through /api/monitor/*, process manager status, and HTTP health/API reachability.",
)

SCHEDULER_RUNTIME = RuntimeRole(
    role="scheduler",
    runtime_name="scheduler",
    process_boundary="control-plane",
    entrypoint="python scripts/run_scheduler.py",
    ownership="APScheduler control plane and periodic retention dispatch ownership.",
    heartbeat_source="runtime.scheduler",
    diagnostics="Diagnose through runtime heartbeat, scheduler snapshot, and retention enqueue timestamps.",
)

TELEGRAM_PIPELINE_RUNTIME = RuntimeRole(
    role="telegram_pipeline",
    runtime_name="telegram_pipeline",
    process_boundary="telegram-ingestion",
    entrypoint="python scripts/run_telegram_pipeline.py",
    ownership="Telegram ingestion, comment collection, linking jobs, and retention fallback when scheduler is disabled.",
    heartbeat_source="runtime.telegram_pipeline",
    diagnostics="Diagnose through runtime heartbeat, pipeline backlog metrics, and Telegram job health.",
)

AI_PIPELINE_RUNTIME = RuntimeRole(
    role="ai_pipeline",
    runtime_name="ai_pipeline",
    process_boundary="ai-worker",
    entrypoint="python scripts/run_ai_pipeline.py",
    ownership="AI report generation, batch report scheduling, and AI job execution.",
    heartbeat_source="runtime.ai_pipeline",
    diagnostics="Diagnose through runtime heartbeat, AI job backlog, and report generation outcomes.",
)

CANONICAL_RUNTIME_ROLES = (
    API_RUNTIME,
    SCHEDULER_RUNTIME,
    TELEGRAM_PIPELINE_RUNTIME,
    AI_PIPELINE_RUNTIME,
)


def runtime_topology_snapshot() -> list[dict]:
    return [asdict(role) for role in CANONICAL_RUNTIME_ROLES]
