# tg_post_analyzer

## Обзор

`tg_post_analyzer` — это приложение для аналитики Telegram с:

- FastAPI-бэкендом в `api/`
- React SPA в `frontend/`
- PostgreSQL-хранилищем с миграциями через Alembic
- отдельными runtime-entrypoint-ами для API, scheduler, Telegram ingestion и AI-воркера

В репозитории поддерживается один frontend-контур: React-приложение в `frontend/`. Для интегрированного runtime FastAPI раздает собранный SPA из `frontend/dist`.

## Технологический стек

Бэкенд:

- Python
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- APScheduler
- Telethon

Фронтенд:

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- React Hook Form
- Zod
- i18next
- MUI / MUI X DataGrid
- React Flow

Тестирование:

- Pytest
- Vitest
- Testing Library

## Структура проекта

```text
api/                    FastAPI-приложение и роутеры
client/                 Жизненный цикл Telegram-клиента
db/                     SQLAlchemy-модели и database helpers
frontend/               Каноническое React-приложение
schemas/                Backend-схемы запросов и ответов
scripts/                Runtime и служебные entrypoint-ы
services/               Доменные сервисы, runtime, jobs, monitoring и pipeline-логика
tests/                  Быстрые backend-тесты и integration-тесты
docs/                   Runbook-ы и сопутствующая инженерная документация
```

## Статус Legacy И CI

- `frontend/` — единственный канонический frontend-контур.
- Legacy static prototype `web/` удален из репозитория; поддерживается только `frontend/`.
- Минимальный repo-local CI живет в [.github/workflows/ci.yml](/d:/Projects/tg_post_analyzer/.github/workflows/ci.yml) и запускает канонический быстрый regression loop: backend tests и frontend tests.
- Backend integration suite остается отдельным manual/gated слоем и не входит в минимальный CI по умолчанию.

## Архитектурные решения

- `frontend/` — единственная поддерживаемая frontend-кодовая база.
- FastAPI обслуживает собранный SPA из `frontend/dist`.
- API-маршруты живут под `/api/*`, клиентские маршруты обрабатываются SPA-оболочкой.
- Канонический linking bounded context расположен в `api/routers/linking.py`.
- Local auth использует access token только в памяти фронтенда и `HttpOnly` refresh cookie со стороны бэкенда.
- CORS управляется через env и должен быть совместим с cookie-based auth.
- Telegram ingestion использует один shared Telethon client/session на процесс runtime, поэтому ingest по каналам намеренно сериализован.
- Долгие операции вроде добавления канала, генерации отчетов и обновления комментариев выполняются через jobs flow, а не синхронно внутри HTTP-запроса.

## Runtime-топология

Канонические runtime-роли:

- `api`: HTTP API и интегрированная раздача SPA
- `scheduler`: APScheduler control plane
- `telegram_pipeline`: Telegram ingestion и Telegram-backed jobs
- `ai_pipeline`: AI-воркер для генерации отчетов

Канонические entrypoint-ы:

- `python scripts/run_api.py`
- `python scripts/run_scheduler.py`
- `python scripts/run_telegram_pipeline.py`
- `python scripts/run_ai_pipeline.py`

Практические рекомендации для AI pipeline:

- В проде запускать `run_ai_pipeline.py` с `--skip-db-migrations` (миграции прогоняются отдельно), чтобы не блокировать воркер на старте.
- Фиксировать таймауты LLM через `AI_JOB_TIMEOUT_SECONDS` (например, `60` или `120` секунд), чтобы зависшие запросы не держали очередь.
- При диагностике использовать `scripts/check_ai_pipeline_status.py` и при необходимости сбрасывать зависшие AI jobs через `scripts/reset_ai_jobs.py`.

Связанные документы:

- [docs/runtime_topology.md](/d:/Projects/tg_post_analyzer/docs/runtime_topology.md)
- [docs/runtime_runbook.md](/d:/Projects/tg_post_analyzer/docs/runtime_runbook.md)

## Доставка фронтенда

Разработка:

- запускать Vite в `frontend/`
- Vite проксирует `/api` на бэкенд
- proxy target берется из `VITE_API_PROXY_TARGET` или `VITE_API_BASE_URL`, по умолчанию это `http://localhost:8000`

Интегрированный runtime:

- собрать фронтенд в `frontend/dist`
- запустить `python scripts/run_api.py`
- FastAPI раздает `/` и SPA-маршруты из собранных ассетов

Если `frontend/dist` отсутствует, бэкенд все равно обслуживает `/api/*`, но `/` возвращает ошибку о том, что frontend build не найден.

## Модель маршрутизации

Публичный маршрут:

- `/login`

Защищенные SPA-маршруты:

- `/dashboard/posts`
- `/dashboard/events`
- `/dashboard/processes`
- `/posts/:postId`
- `/events/:eventId`
- `/processes/:processId`
- `/reports/:reportType`
- `/settings`
- `/channels`
- `/users`
- `/monitor`
- `/jobs`
- `/keyword-graph`

Правила маршрутизации:

- `/` редиректит на `/dashboard/posts`
- гость редиректится на `/login`
- аутентифицированный пользователь при заходе на `/login` редиректится в рабочую область
- запрещенные защищенные маршруты показывают экран forbidden, а не молчаливый redirect

Связанный документ:

- [docs/frontend_route_map.md](/d:/Projects/tg_post_analyzer/docs/frontend_route_map.md)

## API-модель

Основные группы API:

- `/api/auth/*`
- `/api/settings/*`
- `/api/channels/*`
- `/api/posts/*`
- `/api/dashboard/*`
- `/api/reports/*`
- `/api/monitor/*`
- `/api/jobs/*`
- `/api/keyword/*`

Канонические linking-маршруты:

- `GET /api/events`
- `GET /api/events/{id}`
- `GET /api/processes/{process_id}`
- `GET /api/posts/{post_id}/links`
- `POST /api/linking/run`
- `POST /api/events/rebuild`
- `POST /api/processes/rebuild`

Legacy-алиасы `/api/links/*` существуют только как deprecated compatibility bridge.

## Модель auth / session

- `POST /api/auth/login` возвращает access token и выставляет refresh cookie
- `POST /api/auth/refresh` ротирует refresh cookie и возвращает новый access token
- `POST /api/auth/logout` отзывает refresh session и очищает cookie
- `GET /api/auth/me` инициализирует frontend session state
- фронтенд хранит access token только в памяти
- refresh token хранится только в `HttpOnly` cookie

## Модель RBAC

Доступ к маршрутам:

- `admin`: полный доступ, включая admin-модули, monitor, jobs и keyword graph
- `analyst`: dashboard, detail, reports, keyword graph и read-only доступ к settings
- `viewer`: только чтение dashboard/detail/report surfaces

Ограничения по действиям:

- `reports.generate`: admin, analyst
- `comments.refresh`: admin, analyst
- `settings.update`: только admin
- `channels.manage`: только admin
- `users.manage`: только admin
- `jobs.retry`: только admin

## Модель асинхронных jobs

Общий async flow:

1. вызвать mutation endpoint
2. получить `job_id`
3. опрашивать статус job через `/api/jobs/*`
4. получить результат или дождаться terminal state
5. обновить затронутые UI-запросы

Подтвержденные async-поверхности включают генерацию и обновление отчетов, refresh комментариев и добавление канала.

## CORS и runtime-настройки

- CORS origins задаются через `CORS_ALLOWED_ORIGINS`
- credentialed cross-origin auth управляется через `CORS_ALLOW_CREDENTIALS`
- `dev`, `local` и `test` по умолчанию используют localhost-friendly origins
- вне dev-сред origins должны задаваться явно
- wildcard CORS нельзя использовать вместе с credentials

Ключевые auth- и runtime-настройки описаны в [.env.example](/d:/Projects/tg_post_analyzer/.env.example).

## Стратегия тестирования

В репозитории используются три слоя:

- `tests/`: быстрые backend-тесты с изолированными фикстурами и точечными fake-объектами
- `tests/integration/`: реальные PostgreSQL integration-тесты против `TEST_DATABASE_URL` с примененными Alembic-миграциями
- `frontend/src/test/`: Vitest-покрытие маршрутизации, auth, фильтров и поведения экранов

Integration-тесты запускаются только при явном `--run-integration`.

Запуск быстрых backend-тестов:

```bash
venv\Scripts\python -m pytest -q tests
```

Для этого fast-suite достаточно установленных Python-зависимостей из `requirements.txt`; отдельная test database не требуется.

Подготовка integration DB:

```bash
docker compose up -d postgres
set TEST_DATABASE_URL=postgresql+asyncpg://tg_analytics_app:replace-with-strong-password@localhost:5432/tg_analytics_test
venv\Scripts\python scripts/test_bootstrap_backend.py
```

Запуск backend integration-тестов:

```bash
venv\Scripts\python -m pytest -q tests/integration --run-integration
```

Запуск frontend-тестов:

```bash
cd frontend
npm install
npm test
```

Для frontend suite нужны только зависимости из `frontend/package.json`; отдельные backend secrets или локальная PostgreSQL для этих тестов не требуются.

Канонический локальный engineering flow:

1. `venv\Scripts\python -m pytest -q tests`
2. `cd frontend && npm test`
3. `venv\Scripts\python -m pytest -q tests/integration --run-integration`
4. `cd frontend && npm run build`
5. `python scripts/run_api.py`

Минимальный repo-local CI автоматизирует только шаги `1` и `2`. Integration suite (`3`) остается gated/manual, потому что требует отдельный `TEST_DATABASE_URL` и bootstrap test database.

Канонические verification-команды:

- Backend fast regression: `venv\Scripts\python -m pytest -q tests`
- Backend integration regression: `venv\Scripts\python -m pytest -q tests/integration --run-integration`
- Frontend regression: `cd frontend && npm test`
- Frontend type/build verification: `cd frontend && npm run build`

Отдельного canonical backend lint/typecheck command в репозитории сейчас нет. Для frontend роль легкого type/build verification выполняет `npm run build`.

Связанный документ:

- [docs/test_runbook.md](/d:/Projects/tg_post_analyzer/docs/test_runbook.md)

## Быстрый старт

Backend API:

```bash
copy .env.example .env
alembic upgrade head
python scripts/run_api.py --reload
```

Разработка фронтенда:

```bash
cd frontend
npm install
npm run dev
```

Интегрированная раздача фронтенда:

```bash
cd frontend
npm install
npm run build
cd ..
python scripts/run_api.py
```

## Docker Compose

The repository now includes a production-style Docker setup with separate services for:

- `postgres`
- `migrate`
- `api`
- `scheduler`
- `telegram_pipeline`
- `ai_pipeline`

All app services share one common image: `tg_post_analyzer:latest`.
They still run as separate containers, but Docker Desktop should now show a single project image instead of one image per role.

Recommended startup flow:

```bash
copy .env.example .env
docker compose up --build
```

Because `docker-compose.override.yml` is included, the local Docker run already overrides:

- container DB host to `postgres`
- URL-encoded database password for asyncpg DSN
- `REPORT_LLM_BASE_URL` to `http://host.docker.internal:11434`
- Telethon session path to `/app/runtime/tg_analytics.session`

After startup:

- API and integrated frontend are available at `http://localhost:8000`
- PostgreSQL is exposed on `localhost:5432`

Important Docker-specific notes:

- Inside containers, `localhost` does not point to your host machine.
- `telegram_pipeline` stores the Telethon session in the named volume `tg_session` using `/app/runtime/tg_analytics.session`.
- `ai_pipeline` defaults `REPORT_LLM_BASE_URL` to `http://host.docker.internal:11434`; override it with `DOCKER_REPORT_LLM_BASE_URL` if your LLM endpoint lives elsewhere.
- If you want environment-specific overrides, keep them in `docker-compose.override.yml` or switch to `DOCKER_*` variables in `.env`.

Example Docker overrides for `.env`:

```env
DOCKER_DB_URL=postgresql+asyncpg://tg_analytics_app:replace-with-url-encoded-password@postgres:5432/tg_analytics
DOCKER_TEST_DATABASE_URL=postgresql+asyncpg://tg_analytics_app:replace-with-url-encoded-password@postgres:5432/tg_analytics_test
DOCKER_REPORT_LLM_BASE_URL=http://host.docker.internal:11434
DOCKER_TG_SESSION_NAME=/app/runtime/tg_analytics.session
```

Useful commands:

```bash
docker compose logs -f api
docker compose logs -f telegram_pipeline
docker compose logs -f ai_pipeline
docker compose down
docker compose down -v
```

Note: the Docker migration service uses `alembic upgrade heads` because the current repository state may contain multiple Alembic heads.

## Скрипты и legacy surface

Чтобы developer loop оставался понятным, `scripts/` стоит читать так:

- Канонические runtime entrypoint-ы:
  - `scripts/run_api.py`
  - `scripts/run_scheduler.py`
  - `scripts/run_telegram_pipeline.py`
  - `scripts/run_ai_pipeline.py`
- Канонические test/support entrypoint-ы:
  - `scripts/test_bootstrap_backend.py` для подготовки integration DB
- Manual ops-only / diagnostic scripts:
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
- Manual exploratory / smoke scripts, не являющиеся canonical test loop:
  - `scripts/test_pipeline_run.py`
  - `scripts/test_parse_last_post_per_channel.py`
  - `scripts/run_keyword_search_tests.py`
  - `scripts/run_keyword_graph_build_tests.py`
  - `scripts/test_db.py`

Compatibility / legacy surface, intentionally retained:

- `main.py` — deprecated compatibility entrypoint; использовать вместо него `python scripts/run_telegram_pipeline.py`
- `/api/links/*` в `api/routers/links.py` — deprecated compatibility bridge к canonical linking routes
