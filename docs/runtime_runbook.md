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

## Report operating mode

- Automatic background enqueue for `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, and `BUILD_PROCESS_REPORT` is disabled.
- Telegram ingest, comment refresh, and AI runtime flows may still mark existing reports as `stale`.
- New report jobs must appear only after an explicit user or API request.
- AI worker must not expand `BUILD_POST_REPORT_BATCH` into child `BUILD_POST_REPORT` jobs.
- If `jobs` contains new `BUILD_*_REPORT` rows without a matching API-triggered request, treat that as a runtime regression.

## Expected heartbeat behavior

- `api`: no DB-backed heartbeat is expected; use HTTP health plus process-manager checks
- `scheduler`: heartbeat is required only when scheduler retention mode is enabled
- `telegram_pipeline`: heartbeat is required while the ingestion worker is running
- `ai_pipeline`: heartbeat is required while the AI worker is running
