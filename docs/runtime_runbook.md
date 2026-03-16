# Runtime Runbook

## Start roles independently

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

## Diagnose by role

API:

- check process manager / container status
- query `/api/monitor/health`
- verify frontend/API reachability

Scheduler:

- query `/api/monitor/scheduler`
- query `/api/monitor/runtime-topology`
- inspect `runtime.scheduler`

Telegram ingestion:

- query `/api/monitor/pipeline`
- inspect `runtime.telegram_pipeline`
- inspect telegram/comment job backlog

AI worker:

- query `/api/monitor/pipeline`
- inspect `runtime.ai_pipeline`
- inspect report job backlog

## Expected heartbeat behavior

- `api`: no DB-backed heartbeat; diagnose through HTTP health/process manager
- `scheduler`: heartbeat required only when scheduler retention mode is enabled
- `telegram_pipeline`: heartbeat required while ingestion worker is running
- `ai_pipeline`: heartbeat required while AI worker is running
