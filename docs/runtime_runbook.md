# Runbook по runtime

## Запуск ролей по отдельности

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

## Диагностика по ролям

API:

- проверить process manager / container status
- запросить `/api/monitor/health`
- убедиться в доступности frontend/API

Scheduler:

- запросить `/api/monitor/scheduler`
- запросить `/api/monitor/runtime-topology`
- проверить `runtime.scheduler`

Telegram ingestion:

- запросить `/api/monitor/pipeline`
- проверить `runtime.telegram_pipeline`
- проверить backlog telegram/comment jobs

AI worker:

- запросить `/api/monitor/pipeline`
- проверить `runtime.ai_pipeline`
- проверить backlog report jobs

## Ожидаемое поведение heartbeat

- `api`: DB-backed heartbeat не используется; диагностика идет через HTTP health и process manager
- `scheduler`: heartbeat обязателен только когда включен scheduler retention mode
- `telegram_pipeline`: heartbeat обязателен, пока работает ingestion worker
- `ai_pipeline`: heartbeat обязателен, пока работает AI worker
