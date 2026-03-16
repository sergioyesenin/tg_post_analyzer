# Runtime-топология

## Канонические runtime-роли

### `api`

- Граница: HTTP-serving process
- Entrypoint: `python scripts/run_api.py`
- Зона ответственности:
  - FastAPI-роутеры из `api/`
  - auth/session endpoints
  - dashboard/reporting/admin/monitor/jobs API
  - интегрированная раздача SPA из `frontend/dist`
- Диагностика:
  - доступность HTTP/API
  - `/api/monitor/health`
  - логи и статус process manager
- Heartbeat:
  - для API не ожидается DB-backed runtime heartbeat

### `scheduler`

- Граница: control-plane process
- Entrypoint: `python scripts/run_scheduler.py`
- Зона ответственности:
  - жизненный цикл APScheduler
  - периодический retention dispatch
  - владение retention-режимом scheduler-а
- Диагностика:
  - `/api/monitor/scheduler`
  - `/api/monitor/runtime-topology`
  - runtime heartbeat `runtime.scheduler`
- Heartbeat:
  - обязателен только когда включен scheduler mode

### `telegram_pipeline`

- Граница: Telegram ingestion worker
- Entrypoint: `python scripts/run_telegram_pipeline.py`
- Зона ответственности:
  - ingest каналов
  - jobs на сбор комментариев
  - linking jobs
  - retention fallback, когда scheduler mode выключен
- Диагностика:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.telegram_pipeline`
- Heartbeat:
  - обязателен, пока запущен ingestion worker

### `ai_pipeline`

- Граница: AI worker
- Entrypoint: `python scripts/run_ai_pipeline.py`
- Зона ответственности:
  - AI-генерация отчетов
  - AI batch scheduling/execution
  - обработка очереди report jobs
- Диагностика:
  - `/api/monitor/pipeline`
  - `/api/monitor/health`
  - runtime heartbeat `runtime.ai_pipeline`
- Heartbeat:
  - обязателен, пока запущен AI worker

## Правила владения

- API не владеет периодическими scheduling loop-ами.
- Scheduler не обслуживает HTTP-трафик и не запускает ingestion/AI workload.
- Telegram ingestion не выполняет AI report execution.
- AI worker не ingests Telegram channels и не запускает APScheduler.
- Общие библиотеки из `services/` могут импортироваться разными runtime-ролями, но ownership определяется ролью entrypoint-а.
