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

- `src/app`: application bootstrap, providers, global shell, router, guards, top navigation and role-aware sidebar navigation
- `src/shared`: cross-cutting API client, auth roles, dashboard contracts, dashboard filter/query helpers, transport-to-view-model mapping, reusable dashboard blocks, theme tokens and state components
- `src/modules`: route modules grouped by business area; workspace now owns one reusable analytics layout plus mode pages for posts, events and processes

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

### Workspace Architecture

- `AppShell` owns the application frame, top navigation, session chip and role-aware secondary navigation.
- `AnalyticsWorkspaceLayout` owns the dashboard workspace header, mode switcher and the contract for mode-to-mode navigation.
- Dashboard routes are nested under one workspace parent route:
- `/dashboard/posts`
- `/dashboard/events`
- `/dashboard/processes`
- Each mode page composes the same reusable building blocks: warnings banner, partial notice, generated-at display, summary cards, filter bar, split content area and table shell.
- Reports, admin, monitor, jobs and keyword graph routes remain isolated placeholders; workspace detail routes now use live modules that still honor the same shared RBAC and async-state foundations.

### Route Strategy

- `/login` is public.
- Protected routes render inside one `AppShell`.
- `/` redirects to `/dashboard/posts`.
- `/dashboard/*` now renders inside `AnalyticsWorkspaceLayout` instead of each mode owning its own shell.
- Post and event detail routes now use live route modules; reports, admin, monitor, jobs and keyword graph routes still remain isolated and continue to use the same RBAC source of truth.
- `AuthGuard` protects the shell. `RoleGuard` returns a reusable forbidden state for unauthorized role access instead of silently hiding route issues.

### Dashboard Shell

- Transport DTO contracts live in `frontend/src/shared/dashboard/contracts.ts` and still mirror backend `schemas.dashboard`.
- Transport DTOs and UI view models are separated: `dashboard/posts` now maps live `GET /api/dashboard/posts` DTOs into screen-oriented summary/table row models before rendering.
- Post detail uses the same separation rule: `frontend/src/modules/workspace/post-detail/contracts.ts` mirrors backend payloads, while `mappers.ts` reshapes them into block-level view models.
- Dashboard shell foundation currently includes:
- `DashboardWarningsBanner`
- `PartialDataNotice`
- `DashboardSummaryCards`
- `DashboardFilterBar`
- `DashboardTableShell`
- `DashboardGeneratedAt`
- `DashboardModeSwitcher`
- `ReportStatusBadge`
- `query-keys.ts` owns TanStack Query key conventions for dashboard resources.

### dashboard/posts

- `/dashboard/posts` is the first live dashboard module and uses `GET /api/dashboard/posts` as its primary source of truth.
- Supported filter params in the route and request layer:
- `date_from`
- `date_to`
- `limit`
- `channel_ids`
- `categories`
- `min_comments`
- `report_status`
- `sort_by`
- `sort_order`
- Supported posts sorts:
- `comments_count`
- `date`
- `views`
- `involvement`
- The screen renders:
- KPI summary cards from `summary`
- dense table rows from `items`
- `report_status` badges
- `generated_at`
- `warnings[]`
- `partial=true` as a usable degraded state
- detail entry points to `/posts/:postId`

### Query Param Strategy

- Dashboard filters are route-owned and serialize into the URL with backend-aligned parameter names such as `date_from`, `channel_ids`, `status`, `report_status`, `sort_by` and `sort_order`.
- Unknown query params are ignored by dashboard parsing logic rather than reinterpreted as screen state.
- Mode switching keeps only filters that are both shared in meaning and supported by the target mode.
- Preserved across compatible modes: `date_from`, `date_to`, `limit`, `min_comments`, `sort_order`.
- Preserved only between posts/events: `channel_ids`, `categories`.
- Reset on mode switch because semantics differ or support is mode-specific: `sort_by`, `status`, `report_status`.
- Reset action clears dashboard-owned query params for the current mode only.
- `dashboard/posts` request hooks reuse the same serialized query string for both the URL and the TanStack Query cache key.

### Reusable Dashboard Composition

- One mode page now follows one composition pattern:
- system layer for `warnings[]` and `partial=true`
- hero row with mode title and `generated_at`
- summary cards from mapped view model
- URL-driven filter bar
- desktop-first split content area with primary table rail and reusable secondary panel rail
- This keeps `partial=true` explicitly non-fatal and ensures `generated_at` remains visible even in degraded snapshots.

### dashboard/posts Data Mapping

- Transport fetching lives in `frontend/src/modules/workspace/posts/api.ts`.
- Query ownership lives in `frontend/src/modules/workspace/posts/hooks.ts`.
- DTO-to-UI mapping lives in `frontend/src/modules/workspace/posts/mappers.tsx`.
- Mapping rules currently include:
- date formatting from ISO to UTC display string
- nullable `views`, `involvement`, `links_count` fallback handling
- channel label composition from title/username/category
- `report_status` normalization through `ReportStatusBadge`
- row-level detail entry points for open post, comments panel and report panel
- viewer-safe row shaping that hides mutation entry-point links

### dashboard/posts Table Schema

- Typed table schema is defined once in `postsDashboardColumns`.
- Current columns:
- `date`
- `channel`
- `preview`
- `comments`
- `views`
- `involvement`
- `links`
- `report_status`
- `actions`
- `actions` always includes `Open post`.
- `actions` additionally includes `Comments` and `Report` detail entry points only for `admin` and `analyst`.

### dashboard/posts State Handling

- `loading`: route shell and filter bar stay mounted while snapshot data is loading.
- `empty`: request succeeded, summary renders, table is replaced by an empty state.
- `error`: request failure renders a blocking posts-dashboard error state.
- `forbidden`: backend `403` renders a blocking forbidden state for the posts snapshot.
- `partial`: warnings banner plus partial notice render without replacing the table.
- `viewer`: read-only notice renders and mutation entry points stay hidden while detail navigation remains available.

### dashboard/events

- `/dashboard/events` is now implemented against live `GET /api/dashboard/events`.
- Supported filter params:
- `date_from`
- `date_to`
- `limit`
- `status`
- `channel_ids`
- `categories`
- `min_comments`
- `sort_by`
- `sort_order`
- Supported events sorts:
- `started_at`
- `comments_count`
- `involvement`
- `posts_count`
- The screen renders:
- KPI summary cards from `summary`
- dense event table from `items`
- selected-event graph area backed by `GET /api/dashboard/events/{event_id}/graph`
- selected-event detail panel with related posts list
- event report status badges
- `generated_at`
- `warnings[]`
- `partial=true` as a non-blocking exploration state
- async draft report action for analyst/admin users

### Event Graph Architecture

- Dashboard snapshot and graph snapshot are intentionally split:
- `GET /api/dashboard/events` provides table/summary/selection candidates
- `GET /api/dashboard/events/{event_id}/graph` loads only for the currently selected event
- This avoids unnecessary graph fetch chains on route entry and keeps graph loading scoped to one selected entity.
- Graph UI is composed from reusable parts:
- `EventGraphPanel`
- `EventGraphToolbar`
- `EventGraphLegend`
- no-selection placeholder
- no-edges state
- partial-graph notice
- Current rendering uses a framework-native graph surface because React Flow is not installed in this repository yet.

### Event Selection Model

- Selection is local UI state, not a backend filter.
- The first available event auto-selects after dashboard data loads, so the graph area opens without an extra click.
- If filters or refetches keep the selected event in the snapshot, selection is preserved.
- If the selected event disappears from the new snapshot, selection falls back to the first available row.
- Graph query is enabled only when a valid selected event exists.

### Event Detail Panel Behavior

- The detail rail stays mounted beside the table and graph so layout does not collapse during graph loading or error states.
- Event metadata comes from the dashboard snapshot; graph-specific enrichments come from the selected graph response when available.
- Related posts list reuses graph nodes when loaded and falls back to dashboard `post_ids` when graph data is absent or degraded.
- Viewer access remains read-only: selection, graph exploration and related-post navigation stay visible, while draft-report mutation is hidden.
- Analyst and admin users can trigger `POST /api/reports/events/{event_id}/update`, with jobs polling and invalidation handled through the shared async jobs layer.

### dashboard/processes

- `/dashboard/processes` is now implemented against live `GET /api/dashboard/processes`.
- Supported filter params:
- `date_from`
- `date_to`
- `limit`
- `status`
- `min_comments`
- `sort_by`
- `sort_order`
- Supported processes sorts:
- `started_at`
- `comments_count`
- `involvement`
- `events_count`
- The screen renders:
- KPI summary cards from `summary`
- dense process table from `items`
- selected-process hierarchy area backed by `GET /api/dashboard/processes/{process_id}/graph`
- selected-process detail panel with related events list
- event and post context links where graph data confirms them
- process report status badges
- `generated_at`
- `warnings[]`
- `partial=true` as a non-blocking exploration state
- async draft report action for analyst/admin users

### Process Graph Architecture

- Process graph is intentionally distinct from event graph:
- event graph centers one event and its related posts
- process graph centers one higher-level process and shows nested events inside that process before exposing post context
- The hierarchy model is `process -> event -> post`.
- `GET /api/dashboard/processes/{process_id}/graph` provides:
- process summary for the top layer
- nested event rows with relation metadata
- confirmed post nodes and post-link edges
- event-to-post mapping used for related-event and context navigation
- This keeps process view structurally different from events mode while still reusing shared loading/error/async patterns.

### Process Detail

- `/processes/:processId` is now implemented against live `GET /api/processes/{id}`.
- The full page treats `/api/processes/{id}` as the canonical process snapshot and reuses `GET /api/dashboard/processes/{process_id}/graph` only for hierarchy exploration plus confirmed event/post context.
- The screen renders:
- process header and summary cards
- reusable process hierarchy graph panel
- reusable process detail panel with related events
- related context links back to processes dashboard and confirmed event/post routes where graph data resolves them
- loading, not found, forbidden, graph error and read-only states
- analyst/admin draft report action through the shared jobs flow

### Process Detail Reuse

- The full detail page reuses the same `ProcessGraphPanel` and `ProcessDetailPanel` that already power the dashboard secondary rail.
- `GET /api/processes/{id}` supplies canonical process and relation metadata, while the reused dashboard graph endpoint enriches only hierarchy-specific fields such as event titles and confirmed post ids.
- This keeps hierarchy loading/error behavior, report status rendering and related-context navigation aligned between dashboard inspection and full-page detail instead of creating a second process-specific UI stack.

### Reports Architecture

- `/reports/posts`, `/reports/events`, and `/reports/processes` are now implemented as live route modules under one reusable reports architecture.
- Each route keeps filters in the URL and maps transport DTOs into a table-oriented UI model instead of rendering backend list payloads directly.
- One reusable reports table pattern drives all three modules:
- route-level hero and type switcher
- URL-driven filter bar
- shared table shell with type-specific columns
- shared action rail for export and batch-generation entry points
- loading, empty, error, forbidden and read-only states

### Reports Flows

- List flow:
- `GET /api/reports/posts/list`
- `GET /api/reports/events/list`
- `GET /api/reports/processes/list`
- Export flow uses the same serialized filters as the list request and exposes direct CSV/JSON links:
- `GET /api/reports/posts/export`
- `GET /api/reports/events/export`
- `GET /api/reports/processes/export`
- Batch generation flow is implemented only where backend support exists:
- `POST /api/reports/posts/generate-by-filter`
- Batch generation reuses the shared async jobs layer, polls job status/result, and invalidates reports list queries after completion.
- Viewer access remains read-only: reports catalogs and export stay visible, while batch generation stays hidden.

### Admin Modules

- `/channels`, `/users`, and `/settings` are now implemented as live admin modules with one shared CRUD pattern.
- Transport DTOs stay separate from screen state: list queries mirror backend payloads, while forms own their own validated input models.
- Table rendering uses one reusable admin grid wrapper so channels, users, and settings keep aligned loading, empty, error, and forbidden behavior.
- Mutation flows stay explicit and conservative:
- RHF + Zod validate create/edit payloads before submit
- destructive or state-flip mutations use confirmation prompts
- successful mutations invalidate only the affected admin resource queries
- no backend-only fields are synthesized on the client

### Admin Permission Boundaries

- `admin`: full access to `/channels`, `/users`, and `/settings`, including create/update/delete/activate flows.
- `analyst`: no access to channels or users; `/settings` is limited to `GET /api/settings/effective` read-only mode.
- `viewer`: no access to admin modules and receives a forbidden state on direct route entry.
- Backend `403` remains visible as a screen state even inside allowed role scopes, so route-level RBAC and backend enforcement stay aligned.

### Admin Mutation Patterns

- Channels:
- `GET /api/channels/`
- `POST /api/channels/add`
- `PATCH /api/channels/{id}`
- `PUT /api/channels/{id}/active`
- `DELETE /api/channels/{id}`
- Users:
- `GET /api/auth/users`
- `POST /api/auth/users`
- `PUT /api/auth/users/{id}/roles`
- `PUT /api/auth/users/{id}/active`
- Settings:
- `GET /api/settings/effective`
- `GET /api/settings/`
- `PUT /api/settings/{key}`
- Channels and users expose inline forms plus row actions; settings uses a focused single-record editor with JSON validation so unsupported shape assumptions do not leak into the UI.

### Monitor And Jobs

- `/monitor` is now implemented as an admin-only overview screen backed by `GET /api/monitor/full`.
- The monitor module stays inside confirmed backend scope and renders one overview snapshot instead of inventing extra API tabs.
- `/jobs` is now implemented as an admin-only operations screen backed by:
- `GET /api/jobs/summary`
- `GET /api/jobs/pending`
- `GET /api/jobs/dead-letter`
- Confirmed retry actions are exposed only where backend support exists:
- `POST /api/jobs/failed/{job_id}/retry`
- `POST /api/jobs/dead-letter/{dead_letter_id}/retry`

### Monitor Status System

- Monitor status presentation now treats these states as first-class badges:
- `ok`
- `warning`
- `critical`
- `degraded`
- Backend-specific monitor states such as `disabled`, `late_or_missing`, and `process_*` are rendered through the same reusable status badge with explicit fallback labels.
- The overview screen surfaces:
- overall health status
- alerts status
- scheduler status
- dependency table
- active alerts table
- runtime/backlog snapshot details

### Jobs Management Flow

- Jobs management keeps queue inspection and retry actions on one route.
- Summary cards render aggregate counts from `GET /api/jobs/summary`.
- Pending/running/failed queue rows render from `GET /api/jobs/pending`.
- Dead-letter rows render from `GET /api/jobs/dead-letter`.
- Retry is conservative and explicit:
- only `admin` sees retry buttons
- retry uses confirmation before mutation
- successful retry invalidates jobs summary, queue tables, and monitor overview queries
- jobs list limit is serialized in the URL for route-owned queue inspection state

### Event Detail

- `/events/:eventId` is now implemented against live `GET /api/events/{id}`.
- The full page treats `/api/events/{id}` as the canonical detail payload and uses `GET /api/dashboard/events/{event_id}/graph` only for graph/report context, avoiding unnecessary fetch chains.
- The screen renders:
- event header and summary cards
- reusable event graph panel
- reusable event detail panel with related posts
- related context links back to events dashboard and root post when graph data confirms it
- loading, not found, forbidden, graph error and read-only states
- analyst/admin draft report action through the shared jobs flow

### Event Detail Reuse

- The full detail page reuses the same `EventGraphPanel` and `EventDetailPanel` that power the dashboard secondary rail.
- This keeps graph loading/no-edges/error behavior, report status rendering and related-post presentation aligned between dashboard inspection and full-page detail.
- Dashboard rows now expose a direct `Event detail` link so the route-level view extends the existing workspace flow instead of introducing a parallel UI pattern.

### Post Detail

- `/posts/:postId` is now implemented as the detail entry point for `dashboard/posts`.
- The screen loads four independent read models:
- `GET /api/posts/{id}`
- `GET /api/posts/{id}/comments`
- `GET /api/reports/post/{id}`
- `GET /api/posts/{id}/links`
- Layout is desktop-first and split into:
- main rail with post header, comments block and links block
- side rail with report block and async action feedback
- Comments rendering keeps thread-related transport fields (`parent_*`, `thread_root_tg_message_id`, `depth`) in the mapped view model so thread mode can be added without replacing the component contract.
- Viewer access remains read-only: detail data stays visible, while mutation actions are hidden.
- Analyst and admin users see action entry points for comment refresh and report generation/update.

### Post Detail Async Job Flow

- `POST /api/posts/{id}/comments/update` and `POST /api/reports/post/{id}/update` enqueue async jobs and return `job_id`.
- Frontend async handling is centralized in `frontend/src/shared/jobs/hooks.ts` via `useAsyncJobAction`.
- Flow:
- mutation enqueue request
- poll `GET /api/jobs/{id}` until terminal status
- read `GET /api/jobs/{id}/result`
- invalidate relevant TanStack Query resources
- re-render final post/comments/report data
- Async state is rendered inline through reusable indicators rather than replacing detail content.
- Success and failure job results are both surfaced to the user; failure remains non-destructive to already loaded detail data.

### Post Detail Composition

- `PostDetailsPage` owns route-level blocking states for the main post query only.
- `CommentsBlock`, `LinksBlock`, and `ReportBlock` load independently and keep their own loading/error/empty handling.
- This prevents one secondary block from collapsing the entire screen and keeps the detail route usable under partial backend degradation.

### Error Handling Policy

- `invalid_credentials`: blocking inline error on `/login`.
- `service_unavailable`: blocking inline error on auth/data entry points until backend recovers.
- `refresh_failed`: blocking redirect to `/login` with local session cleanup.
- `unauthorized`: blocking redirect to `/login` for guests or expired sessions.
- `forbidden`: blocking forbidden state for authenticated users outside route scope.
- `generic request failure`: blocking inline/block-level error state.
- `partial_data`: non-blocking warning state; dashboard stays usable and keeps `generated_at`, `warnings`, and `filters_applied` visible.
- Shared taxonomy and transition policy live in `frontend/src/shared/errors/error-policy.ts`.

### Implementation Status

- Stage 2 workspace foundation is implemented: one analytics workspace layout, role-aware navigation, mode switcher, URL-owned dashboard filters, generated-at rendering and non-blocking partial/warnings layer.
- Stage 3 posts dashboard is implemented against live `GET /api/dashboard/posts`.
- Stage 4 post detail is implemented against live post/comments/report/links endpoints with role-aware async mutation flows and jobs polling.
- Stage 5 events dashboard is implemented against live dashboard and event-graph endpoints with stable selection and async event report draft actions.
- Stage 6 event detail is implemented against live event detail plus dashboard graph endpoints, with reusable graph/detail blocks and role-safe report actions.
- Stage 7 processes dashboard is implemented against live dashboard and process-graph endpoints with hierarchy-aware graph and detail panels.
- Stage 8 process detail is implemented against live process detail plus dashboard process-graph endpoints, with reusable hierarchy/detail blocks and role-safe report actions.
- Stage 9 reports modules are implemented against live reports list/export endpoints, with reusable table/filter/action patterns and post batch generation flow.
- Stage 10 admin modules are implemented against live channels/users/settings endpoints, with role-protected CRUD flows, analyst-safe effective settings access, and RHF + Zod validation.
- Stage 11 monitor and jobs modules are implemented against live monitor/jobs endpoints, with admin-only overview screens, status badges, queue tables, and confirmed retry flows.
- Desktop-first split layout foundation is in place for future table/detail/graph composition.

### Assumptions And Deferred Edges

- No proactive token refresh scheduler or expiry countdown is implemented yet; current scope is refresh-on-401 only.
- No final UX copy handoff exists for all data-block errors, so shared messages remain minimal safe defaults.
- MUI, MUI X DataGrid, and React Flow are still not installed in this repository, so current admin/report/dashboard tables and graphs use framework-native foundations while keeping component boundaries ready for later migration.
- Detail mutation support currently covers post comment refresh, post report generation/update, event report draft generation/update, and process report draft generation/update.
- Reports export is implemented as direct endpoint links rather than streamed fetch/download state inside the SPA shell.
- Admin settings editing currently validates JSON payloads in a textarea instead of a richer schema-aware editor.
- Monitor currently uses one full snapshot page rather than separate specialized tabs for `/health`, `/jobs`, `/pipeline`, `/scheduler`, and `/alerts`.

### Remaining Gaps Against Spec

- No access-token expiry countdown or proactive refresh scheduling yet.
- No MUI/MUI X DataGrid integration yet; dashboard table is a reusable HTML shell only.
- No MUI/MUI X DataGrid integration for admin modules yet; admin grids currently use reusable HTML table wrappers instead of DataGrid.
- No MUI/MUI X DataGrid integration for jobs tables yet; jobs queue rendering still uses the same reusable HTML shell.
- Event and process graphs are implemented, but broader graph tooling and full React Flow integration remain unfinished.
- No finalized table specs, graph specs, detail panel rules, copy rules or API-to-UI mapping implementation from the handoff checklist yet.
- Action-level RBAC is implemented for current detail/report/admin/jobs retry surfaces, but future monitor/keyword graph actions still need the same rollout.
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
