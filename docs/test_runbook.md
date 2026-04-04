# Тестовый runbook

## Уровни тестов

- `tests/`: быстрые backend-тесты на изолированных модулях, router contracts и точечном `monkeypatch`/fake-session подходе
- `tests/integration/`: реальные PostgreSQL integration-тесты против `TEST_DATABASE_URL` после применения Alembic-миграций
- `frontend/src/test/`: frontend Vitest-покрытие маршрутов, URL filters, guards и UI-поведения

## Быстрый backend-набор

Запуск основного backend-набора:

```bash
venv\Scripts\python -m pytest -q tests
```

Этот набор должен оставаться быстрым и в основном изолированным. Для него не требуется отдельная PostgreSQL test database.
В CI для него дополнительно подставляются только минимальные test-friendly env vars: `APP_ENV`, `TG_API_ID`, `TG_API_HASH`, `AUTH_JWT_SECRET`, `AUTH_PROVIDER_MODE`, `DB_URL`.

## Подготовка backend integration DB

Канонический локальный setup использует PostgreSQL-контейнер из репозитория:

```bash
docker compose up -d postgres
```

Задайте `TEST_DATABASE_URL` на отдельную test database на том же сервере, например:

```bash
set TEST_DATABASE_URL=postgresql+asyncpg://tg_analytics_app:replace-with-strong-password@localhost:5432/tg_analytics_test
```

Подготовьте integration database и примените миграции:

```bash
venv\Scripts\python scripts/test_bootstrap_backend.py
```

Bootstrap-скрипт:

- гарантирует существование базы из `TEST_DATABASE_URL`
- запускает `alembic upgrade head` для этой базы

## Backend integration-набор

Запуск integration-тестов:

```bash
venv\Scripts\python -m pytest -q tests/integration --run-integration
```

Integration-тесты пропускаются, если не передан `--run-integration`. Это сохраняет default suite быстрым и защищает от случайного запуска на отсутствующей или общей базе.

## Frontend-набор

```bash
cd frontend
npm install
npm test
```

Для frontend suite достаточно `npm install`/`npm ci` в `frontend/`; отдельные backend secrets и PostgreSQL не нужны.

## Рекомендуемый локальный workflow

1. Запустить быстрый backend suite.
2. Запустить frontend suite.
3. Запустить backend integration suite для изменений, затрагивающих DB contracts, migrations, auth, jobs или API wiring.
4. Если менялся интегрированный runtime/UI delivery, собрать frontend: `cd frontend && npm run build`.
5. Проверить интегрированный API runtime через `python scripts/run_api.py`.

## Канонический build/test путь

- Backend test entrypoint: `venv\Scripts\python -m pytest -q tests`
- Backend integration entrypoint: `venv\Scripts\python -m pytest -q tests/integration --run-integration`
- Frontend test entrypoint: `cd frontend && npm test`
- Frontend build entrypoint: `cd frontend && npm run build`
- Integrated local runtime entrypoint: `python scripts/run_api.py`
- Separate canonical backend lint/typecheck command is not defined in this repository today.
- Frontend `npm run build` currently serves as the practical type/build verification step because it runs `tsc -b` and `vite build`.

## Legacy и CI

- `frontend/` — единственный поддерживаемый frontend.
- Legacy static prototype `web/` удален; канонический build/runtime path проходит только через `frontend/`.
- Минимальный repo-local CI workflow живет в [.github/workflows/ci.yml](/d:/Projects/tg_post_analyzer/.github/workflows/ci.yml).
- В минимальный CI сейчас входят:
  - `python -m pytest -q tests`
  - `cd frontend && npm test`
- CI не запускает backend integration suite и не выполняет frontend build в минимальном pipeline по умолчанию.
- Backend integration suite остается manual/gated:
  - требует `TEST_DATABASE_URL`
  - требует подготовку test database через `scripts/test_bootstrap_backend.py`
  - не запускается в минимальном CI по умолчанию

## Скрипты по ролям

- Canonical runtime entrypoints:
  - `scripts/run_api.py`
  - `scripts/run_scheduler.py`
  - `scripts/run_telegram_pipeline.py`
  - `scripts/run_ai_pipeline.py`
- Canonical test-support entrypoint:
  - `scripts/test_bootstrap_backend.py`
- Manual ops / diagnostic scripts:
  - `scripts/check_ai_pipeline_status.py`
  - `scripts/check_ready_jobs.py`
  - `scripts/reset_ai_jobs.py`
  - `scripts/create_admin.py`
  - `scripts/add_channel.py`
- Manual maintenance / backfill scripts:
  - `scripts/backfill_embeddings.py`
  - `scripts/backfill_links.py`
  - `scripts/backfill_reply_links.py`
  - `scripts/backfill_search_lemmas.py`
- Manual exploratory / smoke scripts outside canonical regression loop:
  - `scripts/test_pipeline_run.py`
  - `scripts/test_parse_last_post_per_channel.py`
  - `scripts/run_keyword_search_tests.py`
  - `scripts/run_keyword_graph_build_tests.py`
  - `scripts/test_db.py`
- Legacy / compatibility surface intentionally retained:
  - `main.py`
  - deprecated `/api/links/*` bridge in `api/routers/links.py`
