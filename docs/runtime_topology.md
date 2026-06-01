# Runtime topology

## Canonical runtime roles

### `api`

- Boundary: HTTP-serving process
- Entrypoint: `python scripts/run_api.py`
- Responsibility:
  - FastAPI routers from `api/`
  - auth and session endpoints
  - dashboard, reporting, admin, monitor, and jobs API
  - integrated SPA serving from `frontend/dist`
- Diagnostics:
  - HTTP/API availability
  - `/api/monitor/health`
  - process-manager logs and status
- Heartbeat:
  - no DB-backed runtime heartbeat is expected for API

### `scheduler`

- Boundary: control-plane process
- Entrypoint: `python scripts/run_scheduler.py`
- Responsibility:
  - APScheduler lifecycle
  - periodic retention dispatch
  - ownership of scheduler retention mode
- Diagnostics:
  - `/api/monitor/scheduler`
  - `/api/monitor/runtime-topology`
  - runtime heartbeat `runtime.scheduler`
- Heartbeat:
  - required only when scheduler mode is enabled

### `telegram_pipeline`

- Boundary: Telegram ingestion worker
- Entrypoint: `python scripts/run_telegram_pipeline.py`
- Responsibility:
  - channel ingest
  - comment collection jobs
  - linking jobs
  - retention fallback when scheduler mode is disabled
- Diagnostics:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.telegram_pipeline`
- Heartbeat:
  - required while the ingestion worker is running

### `ai_pipeline`

- Boundary: AI worker
- Entrypoint: `python scripts/run_ai_pipeline.py`
- Responsibility:
  - consume queued report jobs
  - execute queued `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, and `BUILD_PROCESS_REPORT`
  - consume `BUILD_POST_REPORT_BATCH` without expanding it into child `BUILD_POST_REPORT` jobs
  - persist report build results and stale-mark downstream reports when applicable
  - keep post-report multi-agent orchestration inside one existing `BUILD_POST_REPORT` job when rollout is enabled
- Diagnostics:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.ai_pipeline`
- Heartbeat:
  - required while the AI worker is running
- Explicit non-responsibility:
  - does not auto-enqueue background report jobs
  - does not fan out batch report jobs into new report jobs
  - does not expose internal multi-agent traces through public API payloads

## Ownership rules

- API does not own periodic scheduling loops.
- Scheduler does not serve HTTP traffic and does not run ingestion or AI workloads.
- Telegram ingestion does not execute AI reports and does not enqueue background report builds.
- AI worker does not ingest Telegram channels, does not run APScheduler, and does not create report jobs without an explicit user or API trigger.
- Shared libraries in `services/` may be imported by multiple runtime roles, but ownership is defined by the role entrypoint.

## Report generation mode

- Background creation of `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, and `BUILD_PROCESS_REPORT` is disabled.
- Existing reports may still become `stale` after ingest, comments refresh, or downstream dependency changes.
- Fresh report jobs should appear only after explicit manual/API-triggered requests.
- This topology does not promise dependency orchestration, automatic rebuild cascades, or readiness-driven background scheduling.
- Default rollout position remains safe-off: `features.multi_agent_mode_enabled=false` and `features.multi_agent_rollout_percent=0`.
- Rollout enablement must happen through existing settings surfaces only, with frontend status-label coverage already shipped for `limited` and `insufficient_data`.
- Public report contracts stay stable while internal multi-agent stages, reruns, and reviewer history remain internal to persisted `report_json.meta.multi_agent`.
