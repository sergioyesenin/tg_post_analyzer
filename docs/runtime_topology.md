# Runtime Topology

## Canonical runtime roles

### `api`

- Boundary: HTTP-serving process
- Entrypoint: `python scripts/run_api.py`
- Ownership:
  - FastAPI routers under `api/`
  - auth/session endpoints
  - dashboard/reporting/admin/monitor/jobs APIs
  - integrated SPA serving from `frontend/dist`
- Diagnostics:
  - HTTP/API reachability
  - `/api/monitor/health`
  - process manager logs/status
- Heartbeat:
  - no DB-backed runtime heartbeat is expected for API

### `scheduler`

- Boundary: control-plane process
- Entrypoint: `python scripts/run_scheduler.py`
- Ownership:
  - APScheduler lifecycle
  - periodic retention dispatch
  - scheduler-mode retention ownership
- Diagnostics:
  - `/api/monitor/scheduler`
  - `/api/monitor/runtime-topology`
  - runtime heartbeat `runtime.scheduler`
- Heartbeat:
  - expected only when scheduler mode is enabled

### `telegram_pipeline`

- Boundary: Telegram ingestion worker
- Entrypoint: `python scripts/run_telegram_pipeline.py`
- Ownership:
  - channel ingestion
  - comment collection jobs
  - linking jobs
  - retention fallback when scheduler mode is disabled
- Diagnostics:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.telegram_pipeline`
- Heartbeat:
  - expected whenever the ingestion worker process is running

### `ai_pipeline`

- Boundary: AI worker
- Entrypoint: `python scripts/run_ai_pipeline.py`
- Ownership:
  - AI report generation
  - AI batch scheduling/execution
  - report job backlog draining
- Diagnostics:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.ai_pipeline`
- Heartbeat:
  - expected whenever the AI worker process is running

## Ownership rules

- API does not own periodic scheduling loops.
- Scheduler does not serve HTTP traffic or run ingestion/AI workloads.
- Telegram ingestion does not own AI report execution.
- AI worker does not ingest Telegram channels or run APScheduler.
- Shared libraries under `services/` may be imported by multiple runtimes, but process ownership is defined by the entrypoint role above.
