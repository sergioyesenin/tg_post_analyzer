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
web/                    Устаревший legacy UI-артефакт; FastAPI его не обслуживает
```

## Архитектурные решения

- `frontend/` — единственная поддерживаемая frontend-кодовая база.
- FastAPI обслуживает собранный SPA из `frontend/dist` и не делает fallback на `web/`.
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
