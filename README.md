# tg_post_analyzer

## Запуск
1. Скопируй `.env.example` в `.env` и заполни обязательные переменные.
   - Для `docker-compose` обязательно задай `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
   - Не используй `postgres/postgres` вне локальной разработки: в `APP_ENV` отличном от `dev/local/test` это блокируется на startup.
   - Для `AUTH_JWT_SECRET` укажи криптостойкое значение (минимум 32 символа, минимум 3 класса символов).
   - Пример генерации: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Подними Postgres:

   ```bash
   docker compose up -d
   ```

   Пример безопасной локальной пары:
   - `POSTGRES_USER=tg_analytics_app`
   - `POSTGRES_PASSWORD=<сгенерированный_пароль>`

3. Прогони миграции:

   ```bash
   alembic upgrade head
   ```

4. Запусти API (официальный entrypoint):

   ```bash
   uvicorn api.main:app --reload
   ```

5. Запуск парсера (отдельно от API):

   ```bash
   python main.py
   ```

## Совместимость
- `man:app` оставлен как legacy-алиас и может использоваться во временных локальных скриптах.
- Канонический путь для API и документации: `api.main:app`.
- Канонический ingestion flow: `services/ingestion_core.py`.
- `main.py`, `parse_today.py`, `scripts/pipeline.py` используют общий ingestion core как тонкие оболочки.
- Каноническая семантика reply-link: `reply_to` нормализуется в `update` во всех пайплайнах.

## Collect comments: anti-regression rules

The `collect_comments` path is sensitive to Telegram FloodWait limits.
Keep the following invariants unchanged unless you run a dedicated load test.

1. `services/TGqueries.py` must keep configurable throttling:
   - `COMMENTS_SLEEP_EVERY` from `settings`
   - `COMMENTS_SLEEP_BASE_SEC` from `settings`
   - `COMMENTS_SLEEP_JITTER_SEC` from `settings`

2. Do not call `await c.get_sender()` for every comment in the hot loop.
   - Use `c.sender` metadata and lightweight cache (`sender_meta_cache`).

3. Do not enqueue nested traversal for leaf comments.
   - Keep guard: enqueue child scan only if `c.replies.replies > 0`.

4. Always return flood source in `update_post_comments(...)`:
   - `flood_source="resolve_discussion"` for discussion resolution path
   - `flood_source="iter_comments"` for comments iteration path
   - This is required for diagnosis when flood wait appears.

5. In `scripts/run_telegram_pipeline.py` flood-wait requeue must not run earlier than global cooldown.
   - Keep `effective_retry_at = max(retry_at, collect_comments_global_cooldown_until)`.

6. Default inter-job sleeps for collect-comments in `scripts/run_telegram_pipeline.py` must remain conservative.
   - If DB settings do not override them, keep safe defaults:
   - `collect_comments_sleep_min_ms=2500`
   - `collect_comments_sleep_max_ms=4500`

### Regression signals in logs

Treat these as immediate regression indicators:

- `collect_comments flood source=unknown ...`
- frequent `status=flood_wait` on comments while post parsing is stable
- flood appears after changes to `services/TGqueries.py` that increase per-comment API calls

### Minimum check before merge

Run daemon for at least 2-3 cycles and verify:

- no repeated `collect_comments ... status=flood_wait`
- flood source is present when flood happens
- comment jobs complete with mostly `status=ok` / `status=no_discussion`

## Dependency Profiles

Install only the base API + Telegram + scheduler runtime:

```bash
venv\Scripts\python -m pip install -r requirements-base.txt
```

Install AI/report-generation extras on top of base:

```bash
venv\Scripts\python -m pip install -r requirements-ai.txt
```

Install dev/test tooling on top of base:

```bash
venv\Scripts\python -m pip install -r requirements-dev.txt
```

Compatibility note:
- `requirements.txt` remains the full umbrella install and includes all three profiles.
- Minimal production path for API + Telegram pipeline + scheduler is `requirements-base.txt`.
- AI report generation, keyword graph NLP, PDF/Excel utilities and related tooling live in `requirements-ai.txt`.

## Tests

Run the baseline quality gate after installing `requirements-dev.txt`:

```bash
venv\Scripts\python -m pytest -q tests
```

## Dashboard API

Dashboard aggregators expose one snapshot response per screen mode so frontend can render each mode with 1-2 requests instead of stitching many small calls.

Available endpoints:

- `GET /api/dashboard/posts`
- `GET /api/dashboard/events`
- `GET /api/dashboard/events/{event_id}/graph`
- `GET /api/dashboard/processes`
- `GET /api/dashboard/processes/{process_id}/graph`

Access:

- `admin`, `analyst`, `viewer` can read dashboard endpoints

Shared response contract:

- top-level payload includes `mode`, `generated_at`, `partial`, `warnings`, `filters_applied`, `summary`, `items`, `meta`
- if optional enrichment cannot be loaded, endpoint should return `partial=true` with `warnings` instead of failing the whole screen

Posts dashboard filters:

- required: `date_from`, `date_to`
- optional: `limit`, `channel_ids`, `categories`, `min_comments`, `report_status`, `sort_by`, `sort_order`
- supported `sort_by`: `comments_count`, `date`, `views`, `involvement`

Events dashboard filters:

- optional: `date_from`, `date_to`, `limit`, `status`, `channel_ids`, `categories`, `min_comments`, `sort_by`, `sort_order`
- supported `sort_by`: `started_at`, `comments_count`, `involvement`, `posts_count`

Processes dashboard filters:

- optional: `date_from`, `date_to`, `limit`, `status`, `min_comments`, `sort_by`, `sort_order`
- supported `sort_by`: `started_at`, `comments_count`, `involvement`, `events_count`

## Frontend Workspace

Stage 0 frontend bootstrap lives in `frontend/` and is intentionally isolated from the legacy static `web/` prototype.

Run commands:

```bash
cd frontend
npm install
npm run dev
```

If frontend runs on Vite dev server and backend runs separately, set `frontend/.env` from `frontend/.env.example` or rely on the built-in Vite proxy to `http://localhost:8000`.

Tests:

```bash
cd frontend
npm test
```

### Architecture

- `src/app`: application bootstrap, providers, app shell, router, guards, global styles
- `src/shared`: cross-cutting API client, auth roles, dashboard contracts, theme tokens, routing metadata, reusable states, query-string utils
- `src/modules`: route modules grouped by business area; stage 0 contains placeholders only

### Directory Structure

```text
frontend/
  src/
    app/
      providers/
      router/
      shell/
      styles/
    shared/
      api/
      auth/
      routing/
      theme/
      types/
      ui/
      utils/
    modules/
      auth/
      workspace/
      platform/
```

### Data Flow Principles

- App bootstrap starts in `src/app/App.tsx` and composes providers in a strict order: theme, query client, session, router.
- Session bootstrap uses persisted tokens plus `GET /api/auth/me` as the initial auth checkpoint. Until it resolves, protected routes stay in a loading state.
- Shared API access goes through `src/shared/api/client.ts`. Transport access is centralized so headers, credentials and error policy stay consistent.
- Dashboard pages are expected to consume `DashboardEnvelope<TSummary, TItem, TMeta, TFilters>` from `src/shared/types/dashboard.ts`.
- `partial` and `warnings` are modeled as a first-class shared contract. They are not treated as hard errors.
- URL query parsing/serialization is centralized in `src/shared/utils/queryParams.ts` so dashboard filters can remain route-driven.

### Auth Architecture

- Auth state is owned by `src/app/providers/SessionProvider.tsx`.
- Tokens are persisted in local storage and restored on app bootstrap through `src/shared/auth/token-storage.ts`.
- Auth HTTP calls are centralized in `src/shared/auth/auth-api.ts`.
- `src/shared/api/client.ts` injects the current bearer token into protected requests and performs one transparent refresh attempt on `401`.
- `/login` uses the session provider instead of talking to fetch directly. Login errors are normalized into explicit UI states: `idle`, `loading`, `invalid_credentials`, `service_unavailable`, `generic_error`.

### Session Lifecycle

1. App starts and session provider loads persisted tokens.
2. If no tokens exist, the app becomes `guest` and protected routes redirect to `/login`.
3. If tokens exist, provider calls `GET /api/auth/me`.
4. If `/me` returns `401`, API client attempts `POST /api/auth/refresh` once, stores rotated tokens, then retries `/me`.
5. If refresh succeeds, session is restored and the user stays in the requested route.
6. If refresh fails, local tokens are cleared and the app falls back to `guest`.
7. Login stores fresh tokens, fetches `/api/auth/me`, then promotes the session to `authenticated`.
8. Logout tries `POST /api/auth/logout` with the current refresh token, but local cleanup still happens even if revoke fails.

### RBAC Strategy

- Guests are redirected from protected routes to `/login`.
- Authenticated users hitting routes outside their role scope see a reusable forbidden state instead of a redirect.
- Hidden access: navigation items outside the user role are omitted from AppShell navigation.
- Forbidden access: direct route entry to protected but unauthorized sections such as `/channels` remains visible as a `403`-style UI state.
- Redirected access: `/login` is public-only; authenticated users are redirected back to the requested route or to `/dashboard/posts`.
- Current route policy:
- `admin`: dashboard, details, reports, channels, users, settings, monitor, jobs, keyword graph
- `analyst`: dashboard, details, reports, settings, keyword graph
- `viewer`: dashboard, details, reports only

### RBAC Matrix

- `admin`: workspace routes are visible and writable; admin areas are visible; settings/channels/users/jobs actions are writable; monitor is visible as read-only.
- `analyst`: workspace routes are visible and writable; keyword graph is visible; settings route is visible as read-only; admin-only areas stay hidden in navigation and forbidden on direct entry.
- `viewer`: workspace routes, details, and reports are visible as read-only; keyword graph and admin areas stay hidden in navigation and forbidden on direct entry.
- Action-level foundation is centralized in `frontend/src/shared/routing/policy.ts` so future mutations can reuse the same role matrix instead of re-encoding permissions per screen.

### Route Strategy

- `/login` is public.
- Protected routes render inside one `AppShell`.
- `/` redirects to `/dashboard/posts`.
- Dashboard modes are explicit top-level routes: `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes`.
- Detail, reports, admin, monitor, jobs and keyword graph routes already exist as placeholders to stabilize ownership and RBAC early.
- `AuthGuard` protects the shell. `RoleGuard` returns a reusable forbidden state for unauthorized role access instead of silently hiding route issues.

### Dashboard Data Foundation

- Transport DTO contracts live in `frontend/src/shared/dashboard/contracts.ts` and mirror backend `schemas.dashboard`.
- Transport-to-UI mapping entry points live in `frontend/src/shared/dashboard/mappers.ts`; current stage keeps them as thin pass-through adapters so stage 2 can add view-model shaping without rewriting contracts.
- Query key naming conventions live in `frontend/src/shared/dashboard/query-keys.ts`.
- Shared ownership is explicit:
- session/auth source of truth: `frontend/src/app/providers/SessionProvider.tsx`
- RBAC/navigation/route policy source of truth: `frontend/src/shared/routing/policy.ts`
- dashboard transport contracts and partial/warnings envelope: `frontend/src/shared/dashboard/contracts.ts`
- URL query parsing/serialization: `frontend/src/shared/utils/queryParams.ts`

### Error Handling Policy

- `invalid_credentials`: blocking inline error on `/login`.
- `service_unavailable`: blocking inline error on auth/data entry points until backend recovers.
- `refresh_failed`: blocking redirect to `/login` with local session cleanup.
- `unauthorized`: blocking redirect to `/login` for guests or expired sessions.
- `forbidden`: blocking forbidden state for authenticated users outside route scope.
- `generic request failure`: blocking inline/block-level error state.
- `partial_data`: non-blocking warning state; dashboard stays usable and keeps `generated_at`, `warnings`, and `filters_applied` visible.
- Shared taxonomy and transition policy live in `frontend/src/shared/errors/error-policy.ts`.

### Assumptions And Deferred Edges

- No proactive token refresh scheduler or expiry countdown is implemented yet; current scope is refresh-on-401 only.
- No final UX copy handoff exists for all data-block errors, so shared messages remain minimal safe defaults.
- Action-level mutation guards are defined only as a foundation matrix; real mutation screens are intentionally deferred to stage 2 and later.
- Analytics workspace layout, mode switcher behavior, URL filter ownership per dashboard mode, and dashboard hooks/UI integration remain intentionally unimplemented.

### Remaining Gaps Against Spec

- No access-token expiry countdown or proactive refresh scheduling yet.
- No real dashboard queries, filters, summary cards, tables, generated-at rendering or graph panels yet.
- No DTO-to-view-model mapping layer for concrete dashboard payloads yet.
- No async job flow, polling strategy or mutation invalidation yet.
- No table specs, graph specs, detail panel rules, copy rules or API-to-UI mapping implementation from the handoff checklist yet.
- No action-level RBAC matrix for mutations and toolbar controls yet.
- No final UI/UX handoff artifacts such as wireframes, hi-fi mocks, status matrix or interaction matrix in the repo yet.

## Pipeline Concurrency Settings

Use `/api/settings` to tune safe concurrency limits for `scripts/run_telegram_pipeline.py` and `scripts/run_ai_pipeline.py`:

- `ingest.channel_concurrency` is pinned to `1`
- `jobs.job_worker_concurrency` (default: `2`, range: `1..16`)
- `ingest.poll_seconds` controls Telegram pipeline poll interval
- `ingest.lookback_days` controls Telegram ingest lookback window
- `jobs.ai_poll_seconds` controls AI pipeline poll interval
- `jobs.ai_scheduler_limit` controls how many background post-report jobs AI pipeline enqueues per cycle

Notes:

- Channel ingest is serialized intentionally because one Telegram worker shares one Telethon session.
- `collect_comments` and `refresh_comments` jobs remain sequential inside one Telegram worker to respect Telegram FloodWait limits.
- Telegram-side linking and AI report jobs run in separate pipelines and no longer compete in one worker loop.
- Runtime settings are resolved in this order: `settings table -> explicit CLI value, if settings key is absent -> canonical default`.

## Pipeline Run Commands

Run API in one process:

```bash
uvicorn api.main:app --reload
```

Run Telegram pipeline in a separate process:

```bash
python scripts/run_telegram_pipeline.py --daemon
```

Useful flags:
- `--poll-seconds 240` overrides the delay between cycles only if `ingest.poll_seconds` is absent in settings.
- `--days 3` overrides the ingest lookback window only if `ingest.lookback_days` is absent in settings.
- `--skip-rebuild-graphs` disables event/process graph rebuild after ingest.

Run AI pipeline in another separate process:

```bash
python scripts/run_ai_pipeline.py --daemon
```

Useful flags:
- `--poll-seconds 120` overrides AI cycle delay only if `jobs.ai_poll_seconds` is absent in settings.
- `--post-report-age-hours 12` overrides the minimum post age for background post reports only if `reports.post_report_delay_hours` is absent in settings.
- `--scheduler-limit 200` overrides AI scheduling limit only if `jobs.ai_scheduler_limit` is absent in settings.

Recommended setup:
- `uvicorn api.main:app --reload`
- `python scripts/run_telegram_pipeline.py --daemon`
- `python scripts/run_ai_pipeline.py --daemon`
- `python scripts/run_scheduler.py`

Pipeline responsibilities:
- `scripts/run_telegram_pipeline.py`: ingest, collect/refresh comments, build post links, and retention enqueue fallback while scheduler rollout is disabled.
- `scripts/run_ai_pipeline.py`: background `build_post_report` for posts older than 12 hours, plus high-priority `build_event_report` and `build_process_report` jobs triggered by API.
- `scripts/run_scheduler.py`: APScheduler control plane for feature-flagged periodic scheduling such as daily retention enqueue.
- `/api/monitor/health` and `/api/monitor/full` use runtime heartbeats from Telegram, AI, and scheduler processes instead of API-local process state.

## Canonical Telegram Runtime

- Production Telegram runtime core: `services/pipeline_runtime.py`.
- Production Telegram entrypoint: `python scripts/run_telegram_pipeline.py --daemon`.
- `main.py`, `parse_today.py`, and `scripts/pipeline.py` are deprecated compatibility wrappers over the canonical runtime.

## Runtime Settings Contract

- Canonical runtime defaults live in `services/settings_defaults.py`.
- Effective runtime resolution order is: `settings table -> explicit CLI value -> canonical default`.
- Telegram pipeline defaults currently include:
  - `ingest.poll_seconds=240`
  - `ingest.lookback_days=3`
  - `ingest.max_posts_per_channel=30`
  - `ingest.comment_first_delay_hours=2`
  - `ingest.comment_interval_hours=2`
  - `ingest.comment_window_hours=24`
  - `ingest.comment_schedule_jitter_seconds=7200`
  - `ingest.collect_comments_sleep_min_ms=2500`
  - `ingest.collect_comments_sleep_max_ms=4500`
  - `jobs.collect_comments_quota_per_run=2`
  - `jobs.job_batch_size=20`
  - `jobs.job_worker_concurrency=2`
- AI pipeline defaults currently include:
  - `jobs.ai_poll_seconds=120`
  - `jobs.ai_scheduler_limit=200`
  - `reports.post_report_delay_hours=12`
- Scheduler defaults currently include:
  - `scheduler.enabled=false`
  - `scheduler.retention_hour=3`
  - `scheduler.retention_minute=0`
- Telegram env defaults currently include:
  - `TG_SESSION_NAME=tg_analytics.session`
  - `TG_FLOOD_SLEEP_THRESHOLD=5`
- Throttling scopes are different and both are supported:
  - `COMMENTS_SLEEP_*` env vars control intra-request comment iteration in `services/TGqueries.py`
  - `ingest.collect_comments_sleep_*_ms` settings control inter-job pacing in Telegram pipeline workers

## APScheduler Retention Rollout

- Enable `features.scheduler_retention_v2=true` and `scheduler.enabled=true` in `/api/settings`.
- Configure daily retention enqueue time with `scheduler.retention_hour` and `scheduler.retention_minute`.
- While the feature flag is disabled, retention jobs continue to be enqueued by `run_telegram_pipeline.py`.
- Inspect scheduler rollout state via `/api/monitor/scheduler` or `/api/monitor/full`.
- Monitoring includes scheduler process heartbeat, so it can distinguish a stale/missing scheduler process from a healthy process with a retention enqueue issue.
