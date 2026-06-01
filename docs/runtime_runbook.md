# Runtime runbook

## Role startup

API:

```bash
python scripts/run_api.py --host 127.0.0.1 --port 8000
```

Scheduler:

```bash
python scripts/run_scheduler.py
```

Telegram ingestion worker:

```bash
python scripts/run_telegram_pipeline.py --daemon
```

AI worker:

```bash
python scripts/run_ai_pipeline.py --daemon
```

## Role diagnostics

API:

- check process manager or container status
- query `/api/monitor/health`
- verify frontend and API availability

Scheduler:

- query `/api/monitor/scheduler`
- query `/api/monitor/runtime-topology`
- verify `runtime.scheduler`

Telegram ingestion:

- query `/api/monitor/pipeline`
- verify `runtime.telegram_pipeline`
- verify backlog of telegram and comment jobs

AI worker:

- query `/api/monitor/pipeline`
- verify `runtime.ai_pipeline`
- verify backlog of report jobs
- expect passive-consumer behavior only
- `BUILD_POST_REPORT` still executes as one existing AI job, but internally runs sequential stages `Context -> Routing -> Expert -> Public Opinion -> Synthesis`.
- Internal stage rerun is allowed only inside the same job execution; the worker must not fan out into child jobs or extra queue types.
- Reviewer loop is bounded inside the same job: at most 2 review iterations, no child jobs, no public exposure of review history.

## Report operating mode

- Automatic background enqueue for `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, and `BUILD_PROCESS_REPORT` is disabled.
- Telegram ingest, comment refresh, and AI runtime flows may still mark existing reports as `stale`.
- New report jobs must appear only after an explicit user or API request.
- AI worker must not expand `BUILD_POST_REPORT_BATCH` into child `BUILD_POST_REPORT` jobs.
- If `jobs` contains new `BUILD_*_REPORT` rows without a matching API-triggered request, treat that as a runtime regression.
- `features.multi_agent_mode_enabled=false` and `features.multi_agent_rollout_percent=0` are the safe defaults; multi-agent rollout stays opt-in until explicitly enabled.
- Internal multi-agent traces may be persisted under `report_json.meta.multi_agent`, but public APIs must strip that subtree before returning report payloads.
- Public consumers that must not receive `meta.multi_agent`: `GET /api/reports/post/{id}`, `GET /api/events/{id}`, and `GET /api/processes/{id}`.
- Internal multi-agent stage outputs must be mapped back into the existing public `post_report_v2` contract before persistence-dependent consumers read them.
- Public post `summary` stays factual, while `limited` and `insufficient_data` remain explicit public statuses; downstream event/process aggregation may consume `ready` and `limited`, but must not treat `insufficient_data` as a ready dependency.

## Rollout checklist

1. Verify defaults through `/api/settings/effective`: `features.multi_agent_mode_enabled=false`, `features.multi_agent_rollout_percent=0`.
2. Enable rollout in stages through existing settings surfaces only:
   - first `multi_agent_mode_enabled=true` with `multi_agent_rollout_percent=0` to verify config propagation only
   - then a small rollout percentage such as `5` or `10`
   - expand only after backend and frontend regressions stay green and public API payloads remain stable
3. During rollout, check:
   - `/api/monitor/pipeline` for healthy `runtime.ai_pipeline`
   - post reports for public `ready` / `limited` / `insufficient_data` semantics
   - `GET /api/reports/post/{id}`, `GET /api/events/{id}`, `GET /api/processes/{id}` never returning `meta.multi_agent`
4. If outputs degrade:
   - first set `multi_agent_rollout_percent=0`
   - if needed also set `multi_agent_mode_enabled=false`
   - keep existing job model; do not introduce manual child-job retries

## Failure semantics

- `limited`: report is schema-valid and public, but conclusions are intentionally constrained; downstream event/process aggregation may still consume it.
- `insufficient_data`: report is schema-valid but must not count as a ready dependency for downstream aggregation.
- reviewer exhaustion or unresolved epistemic issues must not leave the final public status as `ready`.
- invalid model output still falls back to existing failed-report behavior and does not change WebSocket event names or job lifecycle semantics.

## Expected heartbeat behavior

- `api`: no DB-backed heartbeat is expected; use HTTP health plus process-manager checks
- `scheduler`: heartbeat is required only when scheduler retention mode is enabled
- `telegram_pipeline`: heartbeat is required while the ingestion worker is running
- `ai_pipeline`: heartbeat is required while the AI worker is running
