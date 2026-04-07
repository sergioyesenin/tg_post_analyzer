## 1. Краткое резюме backend’а
Это async Python backend на FastAPI + SQLAlchemy + PostgreSQL, но фактически это не только HTTP API, а набор рантаймов: API, Telegram ingestion worker, AI report worker и APScheduler control-plane.

Архитектура частично модульная, но слои смешаны: явного repository/use-case слоя почти нет, SQLAlchemy-запросы часто живут прямо в роутерах и сервисах. Критичные подсистемы: auth, settings, jobs queue в БД, Telegram ingestion/comments, linking/events/processes graph, AI reports, monitoring/heartbeats. Структура рабочая, но не чистая: есть несколько god-service/god-module и дублирование orchestration-кода.

## 2. Дерево структуры
```text
api/
  main.py
  routers/
    auth.py
    channels.py
    posts.py
    dashboard.py
    reports.py
    jobs.py
    linking.py
    links.py
    monitor.py
    settings.py
    keyword_graph.py

db/
  session.py
  models.py

services/
  auth.py
  auth_rate_limit.py
  channel_management.py
  ingestion_core.py
  ingest.py
  TGqueries.py
  jobs.py
  pipeline_runtime.py
  pipeline_runtime_support.py
  pipeline_runtime_common.py
  orchestration.py
  scheduler_runtime.py
  scheduler_dispatch.py
  runtime_heartbeat.py
  runtime_topology.py
  reporting.py
  report_aggregation.py
  linking/
    no_llm_pipeline.py
    candidates.py
    embeddings.py
    entity_dictionaries.py
  linker.py
  events/build_events.py
  processes/build_processes.py
  dashboard/
    posts_dashboard.py
    events_dashboard.py
    processes_dashboard.py
    common.py
  monitoring.py
  archive.py
  jobs_retention.py
  settings_store.py
  settings_defaults.py
  settings_validation.py
  queries.py

client/
  telegram.py
  config.py

schemas/
  auth.py
  channel.py
  post.py
  comment.py
  report.py
  dashboard.py
  linking.py
  keyword_graph.py
  settings.py
  query_params.py

scripts/
  run_api.py
  run_telegram_pipeline.py
  run_telegram_pipeline_inline_comments.py
  run_ai_pipeline.py
  run_scheduler.py
  create_admin.py
  backfill_*.py / check_*.py / add_channel.py

alembic/
  env.py
  versions/*.py

config.py
main.py
parse_today.py
man.py
deps.py
```

## 3. Назначение папок и ключевых файлов
- [api/main.py](d:/Projects/tg_post_analyzer/api/main.py) `CRITICAL`  
  Главный ASGI app, подключает все роутеры, CORS и SPA fallback. Идти сюда при изменении bootstrap/API mount/SPA serving.
- [api/routers](d:/Projects/tg_post_analyzer/api/routers) `IMPORTANT`  
  HTTP transport layer. Здесь много прямых SQL-запросов и enqueue jobs.
- [db/models.py](d:/Projects/tg_post_analyzer/db/models.py) `CRITICAL`  
  Вся доменная схема БД: users/jobs/posts/comments/reports/events/processes/archive. Любое изменение требует проверки миграций, сервисов и API.
- [db/session.py](d:/Projects/tg_post_analyzer/db/session.py) `CRITICAL`  
  Глобальный engine/session factory.
- [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `CRITICAL`  
  Главный job runtime: fetch/lock jobs, обработка comments/linking/rebuild/report jobs, retry/dead-letter/cascade.
- [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py) `CRITICAL`  
  Сбор и reconciliation комментариев из Telegram. Самый опасный модуль для правок.
- [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py) `CRITICAL`  
  Генерация post/event/process reports, stale-marking, readiness logic, каскадные зависимости.
- [services/ingestion_core.py](d:/Projects/tg_post_analyzer/services/ingestion_core.py) `CRITICAL`  
  Ingest постов из Telegram и hydration parent/albums.
- [services/jobs.py](d:/Projects/tg_post_analyzer/services/jobs.py) `CRITICAL`  
  Очередь в таблице `jobs`: enqueue, lock, done/failed/dead-letter.
- [services/events/build_events.py](d:/Projects/tg_post_analyzer/services/events/build_events.py) `IMPORTANT`  
  Перестройка событий по verified post links.
- [services/processes/build_processes.py](d:/Projects/tg_post_analyzer/services/processes/build_processes.py) `IMPORTANT`  
  Перестройка процессов по event update-links.
- [services/linking/no_llm_pipeline.py](d:/Projects/tg_post_analyzer/services/linking/no_llm_pipeline.py) `IMPORTANT`  
  Основная фактическая linking-логика.
- [services/dashboard](d:/Projects/tg_post_analyzer/services/dashboard) `LOCAL`  
  Read-model слой для dashboard API.
- [services/monitoring.py](d:/Projects/tg_post_analyzer/services/monitoring.py) `IMPORTANT`  
  Health/runtime/pipeline snapshots и alerts.
- [services/settings_store.py](d:/Projects/tg_post_analyzer/services/settings_store.py) `IMPORTANT`  
  Эффективный конфиг: merge defaults + DB settings.
- [config.py](d:/Projects/tg_post_analyzer/config.py) `CRITICAL`  
  Env bootstrap и security validation.
- [scripts](d:/Projects/tg_post_analyzer/scripts) `IMPORTANT`  
  Реальные точки запуска процессов и ops-скрипты.
- [main.py](d:/Projects/tg_post_analyzer/main.py), [parse_today.py](d:/Projects/tg_post_analyzer/parse_today.py), [man.py](d:/Projects/tg_post_analyzer/man.py) `SUSPECT`  
  Legacy/deprecated entrypoints.
- [api/routers/links.py](d:/Projects/tg_post_analyzer/api/routers/links.py) `SUSPECT`  
  Deprecated proxy-роуты на новый linking API.
- [services/orchestration.py](d:/Projects/tg_post_analyzer/services/orchestration.py) `SUSPECT`  
  Тонкая обёртка/реэкспорт над `pipeline_runtime.py` + inline-comments cycle; усиливает дублирование.

## 4. Точки входа
- [scripts/run_api.py](d:/Projects/tg_post_analyzer/scripts/run_api.py)  
  `uvicorn.run("api.main:app")` → поднимает FastAPI, роутеры, CORS, SPA.
- [api/main.py](d:/Projects/tg_post_analyzer/api/main.py)  
  Инициализирует `FastAPI`, include_router, CORS, frontend fallback.
- [scripts/run_telegram_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_telegram_pipeline.py)  
  `main_async()` → `build_tg_client()` → heartbeat → бесконечный `run_telegram_cycle()`.
- [scripts/run_telegram_pipeline_inline_comments.py](d:/Projects/tg_post_analyzer/scripts/run_telegram_pipeline_inline_comments.py)  
  Альтернативный ingestion runtime с немедленным `update_post_comments()` после сохранения поста.
- [scripts/run_ai_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_ai_pipeline.py)  
  Опционально прогоняет Alembic upgrade, потом heartbeat и `run_ai_cycle()`.
- [scripts/run_scheduler.py](d:/Projects/tg_post_analyzer/scripts/run_scheduler.py)  
  Поднимает APScheduler, регистрирует cron-задачи и пишет heartbeat.
- [alembic/env.py](d:/Projects/tg_post_analyzer/alembic/env.py)  
  Migration entrypoint; читает `config.settings.DB_URL`.
- [scripts/create_admin.py](d:/Projects/tg_post_analyzer/scripts/create_admin.py)  
  CLI init script для локального admin/analyst user.

## 5. Карта HTTP/API пайплайнов
- `POST /api/auth/login`  
  Route → `auth.login()` → `_check_login_rate_limits()` → `auth_rate_limiter.check()` → `authenticate_local_user()` → `create_access_token()` + `issue_refresh_token()` → `write_audit_log()` → `session.commit()` → `_set_refresh_cookie()`.  
  БД: `users`, `user_roles`, `auth_refresh_tokens`, `audit_logs`, `auth_rate_limit_buckets`.  
  Валидация: `schemas/auth.py::LoginIn`, env-policy из [config.py](d:/Projects/tg_post_analyzer/config.py).  
  Что сломается: login/refresh/logout/cookie rotation, rate limit и audit trail.
- `POST /api/auth/refresh`  
  Route → `auth.refresh()` → `_read_refresh_cookie()` → `_check_refresh_rate_limits()` → `rotate_refresh_token()` → `create_access_token()` → audit → commit → set cookie.  
  Риск: refresh rotation и replay protection.
- `POST /api/channels/add`  
  Route → `channels.add_channel()` → `normalize_channel_identifier()` → `_find_inflight_add_channel_job()` → `enqueue_job(JobType.ADD_CHANNEL)` → audit.  
  Затем background: `_run_add_channel_job()` → `resolve_and_upsert_channel()` → Telethon `get_entity()` → `upsert_channel()`.  
  Что сломается: admin UI add-channel, dedupe, Telegram resolution.
- `GET /api/posts/top`  
  Route → `posts.top_posts()` → `get_setting("api")` → прямой SQLAlchemy query `Post join Channel` → map в `PostCardOut`.  
  Нет service layer, БД запрашивается прямо из роутера.
- `POST /api/posts/{post_id}/comments/update`  
  Route → `posts.update_comments()` → `enqueue_comment_refresh_job()` → job queue.  
  Background: `_run_comment_job()` → `update_post_comments()` → `sync_post_report_staleness()`.  
  Что сломается: comments refresh, report invalidation.
- `GET /api/dashboard/posts|events|processes`  
  Route → `dashboard.*` → `services.dashboard.*_dashboard.build_*()` → набор агрегирующих SQL queries.  
  Валидация query params: [schemas/query_params.py](d:/Projects/tg_post_analyzer/schemas/query_params.py) и Query constraints в роутере.  
  Риск: фронтенд dashboard contracts.
- `GET /api/dashboard/events/{id}/graph`, `GET /api/dashboard/processes/{id}/graph`  
  Route → `build_event_graph()` / `build_process_graph()` → прямой query `EventPost/ProcessEvent/PostLink`.
- `POST /api/reports/post/{id}/update`  
  Route → `reports.update_report()` → `enqueue_post_report_job()` → AI worker `run_ai_jobs()` → `build_post_report()` → `upsert_report()` → cascade stale/jobs for events/processes.  
  Что сломается: post/event/process report chain.
- `POST /api/reports/posts/generate-by-filter`  
  Route → `enqueue_post_report_batch_job()` → AI worker → `dispatch_post_report_batch()` → N enqueue `build_post_report`.
- `POST /api/events/rebuild`, `POST /api/processes/rebuild`, `POST /api/linking/run`  
  Route → enqueue job → telegram worker runs `_run_rebuild_events_job()` / `_run_rebuild_processes_job()` / `_run_link_job()`.
- `GET /api/jobs/*`  
  Mostly direct SQL over `jobs` / `job_dead_letters`; `GET /result` reads result from `payload_json["_job_result"]`.
- `GET /api/monitor/*`  
  Route → `services.monitoring.*snapshot()`; raw SQL in db-size/database snapshot.
- `POST /api/keyword/search/posts`, `/graph/build`, `/graph/report`  
  Route → `_ensure_feature_enabled()` → `search_posts_by_keywords()` / `build_posts_graph()` / `generate_graph_report()` → audit log.  
  Внешний вызов: AI report generation через `agents.reporter`.

## 6. Карта бизнес-процессов / use cases
- Аутентификация  
  HTTP login/refresh/logout → auth service → JWT + refresh tokens + audit + rate-limit buckets.
- Добавление канала  
  API enqueue → job worker → Telegram resolve channel → upsert `channels`.
- Инжест постов  
  Telegram runtime → `run_telegram_cycle()` → `process_channel()` → `IngestionCore.ingest_channel()` → `upsert_post()` → enqueue link/comments jobs.
- Сбор комментариев  
  Scheduled or manual job → `_run_comment_job()` → `update_post_comments()` → `upsert_comment()` / `set_post_comments_count()` / `set_post_views()` / `set_post_involvement()` → stale report sync.
- Построение link graph  
  `build_post_links` job → `NoLlmLinkingPipeline.run_for_post()` → `get_or_prepare_post_features()` → embeddings/entity facts → `retrieve_candidates()` → `insert PostLink`.
- Перестройка events  
  `rebuild_events` job or post-ingest flow → `rebuild_events()` → union-find по verified `PostLink` (`same_event`/`related`) → upsert `Event` + `EventPost`.
- Перестройка processes  
  `rebuild_processes` job → `rebuild_processes()` → union-find по verified `UPDATE` links между событиями → upsert `Process` + `ProcessEvent`.
- Генерация post report  
  AI worker → `build_post_report()` → `report_project.generate_post_report_payload()` → `upsert_report()`.
- Генерация event/process report  
  AI worker → readiness checks → aggregation from post/event reports → `EventReport` / `ProcessReport`.
- Архивация и retention  
  Scheduler or telegram fallback → enqueue maintenance jobs → `run_archive_retention()` / `run_jobs_retention()`.

## 7. Карта background pipelines
- Telegram pipeline  
  Trigger: [scripts/run_telegram_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_telegram_pipeline.py).  
  Flow: `run_telegram_cycle()` → ingest channels → run link jobs until idle → optional rebuild events/processes → fallback retention enqueue → run comment/maintenance jobs.  
  Ошибки: FloodWait и RPC ошибки в comment jobs приводят к requeue/backoff; max attempts → dead-letter.
- Inline-comments pipeline  
  Trigger: [scripts/run_telegram_pipeline_inline_comments.py](d:/Projects/tg_post_analyzer/scripts/run_telegram_pipeline_inline_comments.py).  
  Отличие: после `upsert_post()` сразу пробует `update_post_comments()` в nested transaction.
- AI pipeline  
  Trigger: [scripts/run_ai_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_ai_pipeline.py).  
  Flow: `schedule_due_post_report_jobs()` → `run_ai_jobs()` → `build_post_report` / batch / event / process.  
  Deferred readiness → `requeue_job(... +5 min)`. Timeout → pending + retry_at +30 sec.
- Scheduler  
  Trigger: [scripts/run_scheduler.py](d:/Projects/tg_post_analyzer/scripts/run_scheduler.py).  
  Flow: APScheduler cron → `dispatch_daily_retention()` → `enqueue_daily_retention_jobs()`.
- Retry / dead-letter  
  [services/jobs.py](d:/Projects/tg_post_analyzer/services/jobs.py): `mark_job_failed()` делает exponential backoff, а при исчерпании attempts пишет в `job_dead_letters`.
- Heartbeats  
  Все worker’ы кроме API пишут heartbeat в `app_settings` через [services/runtime_heartbeat.py](d:/Projects/tg_post_analyzer/services/runtime_heartbeat.py).

## 8. Карта зависимостей между слоями
```text
HTTP Router -> Depends(auth/session) -> Service or direct SQLAlchemy query -> DB
HTTP Router -> enqueue_job -> jobs table -> Telegram/AI worker -> domain service -> DB/external API

Telegram worker -> IngestionCore -> ingest.upsert_post -> jobs enqueue
Telegram worker -> TGqueries.update_post_comments -> ingest.upsert_comment/set_* -> reporting.sync_post_report_staleness
Telegram worker -> NoLlmLinkingPipeline -> candidates/embeddings -> PostLink
Telegram worker -> build_events -> build_processes

AI worker -> reporting.build_post_report -> reporter agent/external model -> Report
AI worker -> reporting.build_event_report_draft -> EventReport
AI worker -> reporting.build_process_report_draft -> ProcessReport

Scheduler -> dispatch_daily_retention -> enqueue maintenance jobs -> archive/jobs_retention services
```
Нормальные зависимости: router → service, worker → service, service → DB.  
Слишком широкие: `pipeline_runtime.py`, `reporting.py`, `TGqueries.py`.  
Скрытые зависимости: global `settings`, global SQLAlchemy engine/session, global Telethon client `client.client`, runtime heartbeats in `app_settings`, auth rate limiter uses engine directly without request session.

## 9. Подробная карта функций
- [api/routers/auth.py](d:/Projects/tg_post_analyzer/api/routers/auth.py)  
  `login(data, request, response, session)` — оркеструет login.  
  Вызывает `authenticate_local_user()`, `create_access_token()`, `issue_refresh_token()`, `write_audit_log()`.
- [services/auth.py](d:/Projects/tg_post_analyzer/services/auth.py)  
  `authenticate_local_user(session, username, password)` — читает `User`, проверяет hash, подгружает roles.  
  `rotate_refresh_token(session, refresh_token)` — ревокает старый refresh, создаёт новый.  
  `write_audit_log(...)` — побочный эффект: запись в `audit_logs`.
- [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)  
  `run_telegram_cycle(...)` — главный orchestrator ingestion/runtime.  
  `run_telegram_jobs(...)` — fetch/lock jobs, делит comment jobs и other jobs.  
  `_run_comment_job(...)` — вызывает `update_post_comments()`, умеет flood_wait backoff и stale-sync.  
  `run_ai_jobs(...)` — запускает AI jobs, timeout/requeue/cascade.  
  Это главные orchestrator functions.
- [services/ingestion_core.py](d:/Projects/tg_post_analyzer/services/ingestion_core.py)  
  `ingest_channel(channel, options, on_post_saved)` — итерирует Telegram messages, валидирует текст, hydrat’ит parent posts, вызывает `upsert_post()`, потом callback.
- [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py)  
  `update_post_comments(session, post_id, tg_client)` — достаёт post/channel, резолвит discussion thread, собирает top-level и nested comments, делает `upsert_comment()`, обновляет counters.  
  Это massive side-effect function.
- [services/linking/no_llm_pipeline.py](d:/Projects/tg_post_analyzer/services/linking/no_llm_pipeline.py)  
  `run_for_post(session, post)` — готовит features, ищет кандидатов, создаёт `PostLink`.
- [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py)  
  `build_post_report(...)` — вызывает внешнюю AI генерацию и upsert’ит `Report`.  
  `build_event_report_draft(...)` — строит event report из post reports.  
  `build_process_report_draft(...)` — строит process report из event reports.  
  `sync_post_report_staleness(...)` — сравнивает input signature и enqueue rebuild report jobs.

## 10. Работа с данными
Модели persistence лежат в [db/models.py](d:/Projects/tg_post_analyzer/db/models.py). DTO и response/request схемы лежат в [schemas](d:/Projects/tg_post_analyzer/schemas).

Поток данных обычно такой: FastAPI Query/Body → Pydantic schema → router/service → SQLAlchemy model rows → Pydantic response. Но transport/domain/persistence модели часто смешаны: роуты нередко возвращают ORM objects напрямую, а бизнес-логика работает сразу с SQLAlchemy models.

Валидация есть в трёх местах:
- request DTO через Pydantic;
- query params через `Query(...)` и `CsvIntList/CsvStrList`;
- settings/env через [services/settings_validation.py](d:/Projects/tg_post_analyzer/services/settings_validation.py) и [config.py](d:/Projects/tg_post_analyzer/config.py).

## 11. Работа с БД
Доступ к БД почти везде через `AsyncSession` без repository-абстракции. Основные точки:
- [api/routers/*](d:/Projects/tg_post_analyzer/api/routers) — много direct select/update/delete;
- [services/ingest.py](d:/Projects/tg_post_analyzer/services/ingest.py) — upsert’ы posts/comments/reports;
- [services/jobs.py](d:/Projects/tg_post_analyzer/services/jobs.py) — queue primitives;
- [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py) — report persistence/readiness;
- [services/events/build_events.py](d:/Projects/tg_post_analyzer/services/events/build_events.py), [services/processes/build_processes.py](d:/Projects/tg_post_analyzer/services/processes/build_processes.py).

Raw SQL есть минимум в monitor db-size, pipeline comment-job cleanup/update, database snapshot. Транзакции в основном ручные через `session.commit()`, иногда nested transaction в inline comment mode.

Опасные места:
- каскадные `ondelete="CASCADE"` в posts/comments/reports/event/process relations;
- `jobs.payload_json` хранит state/result, что делает схему неявной;
- возможны лишние запросы в dashboard/detail endpoints и report readiness chains.

## 12. Интеграции и внешние зависимости
- Telegram / Telethon  
  Клиент: [client/telegram.py](d:/Projects/tg_post_analyzer/client/telegram.py).  
  Используют: ingestion, comments, add_channel.  
  Риски: sqlite session lock, FloodWait, RPCError, shared client state.
- Embeddings / Ollama-compatible API  
  Клиент: [services/linking/embeddings.py](d:/Projects/tg_post_analyzer/services/linking/embeddings.py).  
  Использует `httpx` POST `/api/embeddings`. Fallback: отключает embeddings и откатывается к lexical retrieval.
- AI reporter  
  Вызовы идут через `agents.reporter` из [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py) и [api/routers/keyword_graph.py](d:/Projects/tg_post_analyzer/api/routers/keyword_graph.py).  
  От него зависят post reports и graph report.

## 13. Auth / Security pipeline
Auth entry: [api/routers/auth.py](d:/Projects/tg_post_analyzer/api/routers/auth.py).  
Guard layer: [deps.py](d:/Projects/tg_post_analyzer/deps.py) — `get_current_user()` и `require_roles()`.

Pipeline:
- Bearer token приходит в `HTTPBearer`;
- `decode_access_token()` проверяет JWT;
- `get_current_user()` вытаскивает `sub`, грузит `User` из БД, потом roles через `get_user_roles()`;
- `require_roles()` режет доступ по пересечению roles;
- refresh session живёт только в httpOnly cookie;
- rate-limit login/refresh идёт через [services/auth_rate_limit.py](d:/Projects/tg_post_analyzer/services/auth_rate_limit.py).

Что ломается при правках:
- role-based access по всему API;
- refresh rotation;
- cookie security policy;
- audit и rate-limit.

## 14. Конфиги и окружение
Env загружается в [config.py](d:/Projects/tg_post_analyzer/config.py) как singleton `settings`. Там же валидируются:
- DB URL и non-prod restrictions;
- JWT secret policy;
- CORS;
- auth cookie policy;
- auth rate-limit params;
- timezone.

Runtime settings идут отдельно через БД:
- defaults: [services/settings_defaults.py](d:/Projects/tg_post_analyzer/services/settings_defaults.py)
- effective merge: [services/settings_store.py](d:/Projects/tg_post_analyzer/services/settings_store.py)
- update API: [api/routers/settings.py](d:/Projects/tg_post_analyzer/api/routers/settings.py)

Скрытая зависимость: часть поведения берётся не из env, а из `app_settings` в БД, и worker’ы читают это на каждом цикле.

## 15. Где что менять
- Endpoint/HTTP contract  
  Идти в [api/routers](d:/Projects/tg_post_analyzer/api/routers) + соответствующий schema file.
- Бизнес-логика ingest/comments/linking/reports  
  Идти в [services/ingestion_core.py](d:/Projects/tg_post_analyzer/services/ingestion_core.py), [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py), [services/linking/no_llm_pipeline.py](d:/Projects/tg_post_analyzer/services/linking/no_llm_pipeline.py), [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py).
- SQL/query change  
  Сначала искать в router/service, отдельного repository layer нет.
- Валидация  
  Request schema в [schemas](d:/Projects/tg_post_analyzer/schemas), settings validation в [services/settings_validation.py](d:/Projects/tg_post_analyzer/services/settings_validation.py), env validation в [config.py](d:/Projects/tg_post_analyzer/config.py).
- Auth  
  [api/routers/auth.py](d:/Projects/tg_post_analyzer/api/routers/auth.py), [deps.py](d:/Projects/tg_post_analyzer/deps.py), [services/auth.py](d:/Projects/tg_post_analyzer/services/auth.py), [services/auth_rate_limit.py](d:/Projects/tg_post_analyzer/services/auth_rate_limit.py).
- Background jobs  
  [services/jobs.py](d:/Projects/tg_post_analyzer/services/jobs.py), [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py), [scripts/run_*](d:/Projects/tg_post_analyzer/scripts).
- Конфиг поведения worker’ов  
  [services/settings_defaults.py](d:/Projects/tg_post_analyzer/services/settings_defaults.py), [services/settings_store.py](d:/Projects/tg_post_analyzer/services/settings_store.py).
- Логирование/monitoring  
  [services/monitoring.py](d:/Projects/tg_post_analyzer/services/monitoring.py), [services/pipeline_runtime_common.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime_common.py).

## 16. Проблемные места
- Нет чистого разделения слоёв: routers и сервисы часто ходят в БД напрямую.
- [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py) — god-module.
- [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py) — god-service с генерацией, stale logic, rendering, readiness и каскадами.
- [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) + [services/pipeline_runtime_support.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime_support.py) + [services/orchestration.py](d:/Projects/tg_post_analyzer/services/orchestration.py) дублируют обязанности.
- Hidden coupling через `jobs.payload_json`, `app_settings`, global client, global engine.
- Deprecated/legacy слой: [api/routers/links.py](d:/Projects/tg_post_analyzer/api/routers/links.py), [main.py](d:/Projects/tg_post_analyzer/main.py), [parse_today.py](d:/Projects/tg_post_analyzer/parse_today.py), [man.py](d:/Projects/tg_post_analyzer/man.py).
- Naming хаотичен: `TGqueries.py`, `ingest.py`, `queries.py`, `linker.py`, `orchestration.py`.
- Monitoring и runtime state используют таблицу settings как storage для heartbeats, что смешивает config и ops-state.
- AI worker concurrency принудительно зажат до 1 в `run_ai_cycle()`, хотя settings допускают 2.

## 17. Рекомендации по безопасному редактированию
- Можно менять локально  
  [services/dashboard/*](d:/Projects/tg_post_analyzer/services/dashboard), [schemas/dashboard.py](d:/Projects/tg_post_analyzer/schemas/dashboard.py), [schemas/query_params.py](d:/Projects/tg_post_analyzer/schemas/query_params.py), [api/routers/keyword_graph.py](d:/Projects/tg_post_analyzer/api/routers/keyword_graph.py).
- Нужно проверять всю цепочку вызовов  
  [api/routers/reports.py](d:/Projects/tg_post_analyzer/api/routers/reports.py), [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py), [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py).
- Нужно проверять интеграции/БД/очереди  
  [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py), [services/ingestion_core.py](d:/Projects/tg_post_analyzer/services/ingestion_core.py), [services/linking/*](d:/Projects/tg_post_analyzer/services/linking), [services/jobs.py](d:/Projects/tg_post_analyzer/services/jobs.py).
- Высокий риск побочных эффектов  
  [db/models.py](d:/Projects/tg_post_analyzer/db/models.py), [config.py](d:/Projects/tg_post_analyzer/config.py), [deps.py](d:/Projects/tg_post_analyzer/deps.py), [services/auth.py](d:/Projects/tg_post_analyzer/services/auth.py), [services/settings_store.py](d:/Projects/tg_post_analyzer/services/settings_store.py).

## 18. Минимальный план реорганизации
1. Выделить явный application layer для 5 критичных use-case: auth login/refresh, add channel, refresh comments, build post report, rebuild events/processes.
2. Убрать дублирование между `pipeline_runtime.py`, `pipeline_runtime_support.py`, `orchestration.py`: оставить один orchestration module и один helpers module.
3. Разбить `TGqueries.py` на `discussion_resolution`, `comment_collection`, `comment_reconciliation`.
4. Разбить `reporting.py` на `post_reports`, `event_reports`, `process_reports`, `report_staleness`, `report_rendering`.
5. Вынести DB-доступ из роутеров в query services/repositories хотя бы для auth/channels/posts/reports/jobs.
6. Отделить runtime heartbeats от `app_settings` в отдельную таблицу.
7. Удалить deprecated entrypoints и legacy router aliases после проверки использования.
8. Формализовать job payload/result schemas вместо ad-hoc JSON.

## 19. TL;DR для разработчика
Вход в HTTP: [scripts/run_api.py](d:/Projects/tg_post_analyzer/scripts/run_api.py) → [api/main.py](d:/Projects/tg_post_analyzer/api/main.py).  
API живёт в [api/routers](d:/Projects/tg_post_analyzer/api/routers).  
Главная бизнес-логика: [services/pipeline_runtime.py](d:/Projects/tg_post_analyzer/services/pipeline_runtime.py), [services/TGqueries.py](d:/Projects/tg_post_analyzer/services/TGqueries.py), [services/reporting.py](d:/Projects/tg_post_analyzer/services/reporting.py), [services/events/build_events.py](d:/Projects/tg_post_analyzer/services/events/build_events.py), [services/processes/build_processes.py](d:/Projects/tg_post_analyzer/services/processes/build_processes.py).  
БД: [db/models.py](d:/Projects/tg_post_analyzer/db/models.py), [db/session.py](d:/Projects/tg_post_analyzer/db/session.py).  
Background jobs: `jobs` table + workers из [scripts/run_telegram_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_telegram_pipeline.py), [scripts/run_ai_pipeline.py](d:/Projects/tg_post_analyzer/scripts/run_ai_pipeline.py), [scripts/run_scheduler.py](d:/Projects/tg_post_analyzer/scripts/run_scheduler.py).  
Интеграции: Telegram в [client/telegram.py](d:/Projects/tg_post_analyzer/client/telegram.py), embeddings в [services/linking/embeddings.py](d:/Projects/tg_post_analyzer/services/linking/embeddings.py), AI reports через `agents.reporter`.  
Auth: [api/routers/auth.py](d:/Projects/tg_post_analyzer/api/routers/auth.py) + [deps.py](d:/Projects/tg_post_analyzer/deps.py).  
Самые опасные места: `TGqueries.py`, `reporting.py`, `pipeline_runtime.py`, `db/models.py`, `config.py`.