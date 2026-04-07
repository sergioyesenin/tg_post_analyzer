# TG Post Analyzer Pipelines

This document focuses on real runtime pipelines and side-effects. It intentionally names concrete files and functions.

## HTTP Authentication

### Login

**Trigger:**
`POST /api/auth/login`

**Flow:**
client -> `api/routers/auth.py::login` -> rate limit -> `services.auth.authenticate_local_user` -> JWT + refresh token -> audit log -> commit -> cookie

**Real calls:**

- `api/routers/auth.py::login`
- `api/routers/auth.py::_check_login_rate_limits`
- `services/auth_rate_limit.py::auth_rate_limiter.check`
- `services/auth.py::authenticate_local_user`
- `services/auth.py::create_access_token`
- `services/auth.py::issue_refresh_token`
- `services/auth.py::write_audit_log`

**Side-effects:**

- reads `users`, `user_roles`
- writes `auth_refresh_tokens`
- writes `audit_logs`
- writes `auth_rate_limit_buckets`
- sets httpOnly refresh cookie

**Errors:**

- `503` if local auth is disabled by env
- `401` invalid credentials
- `429` via rate limiter

**What breaks if changed:**

- frontend bootstrap
- refresh/logout
- route guards
- admin/user access control

### Refresh

**Trigger:**
`POST /api/auth/refresh`

**Flow:**
cookie -> `auth.refresh` -> refresh rate limit -> rotate refresh token -> new access token -> audit log -> commit -> set new cookie

**Real calls:**

- `api/routers/auth.py::refresh`
- `services/auth.py::rotate_refresh_token`
- `services/auth.py::create_access_token`

**Side-effects:**

- revokes old refresh token
- inserts new refresh token
- writes `audit_logs`

**Errors:**

- `401` missing or invalid refresh cookie
- `429` refresh abuse

**What breaks if changed:**

- silent session restore in `SessionProvider`
- auto-retry on `401` in `shared/api/client.ts`

## Frontend Session Bootstrap

### App session restore

**Trigger:**
SPA startup in browser

**Flow:**
`main.tsx` -> `App` -> `AppProviders` -> `SessionProvider.bootstrap()` -> load access token from storage -> `/api/auth/me` -> if failed then `/api/auth/refresh` -> `/api/auth/me` -> authenticated session or guest state

**Real calls:**

- `frontend/src/app/providers/SessionProvider.tsx::bootstrap`
- `frontend/src/shared/auth/auth-api.ts::me`
- `frontend/src/shared/auth/auth-api.ts::refresh`
- `frontend/src/shared/api/client.ts::request`

**Side-effects:**

- browser storage read/write
- backend refresh token rotation

**Errors:**

- any `401` during bootstrap clears session
- broken refresh contract makes whole SPA look logged out

**What breaks if changed:**

- all protected routes
- API auto-refresh
- logout/login transitions

## Posts Dashboard Read Pipeline

### Posts dashboard

**Trigger:**
route `/dashboard/posts`

**Flow:**
URL filters -> `usePostsDashboardQuery` -> `modules/workspace/posts/api.ts::getPostsDashboard` -> `GET /api/dashboard/posts` -> `services.dashboard.posts_dashboard.build_posts_dashboard` -> SQL aggregation -> response -> mapper -> table/cards

**Real calls:**

- Frontend:
  - `frontend/src/modules/workspace/posts/hooks.ts::usePostsDashboardQuery`
  - `frontend/src/modules/workspace/posts/PostsDashboardScreen.tsx`
- Backend:
  - `api/routers/dashboard.py::get_posts_dashboard`
  - `services/dashboard/posts_dashboard.py::build_posts_dashboard`

**Side-effects:**

- read-only DB access
- uses effective `api` settings for default limit

**Errors:**

- `403` forbidden role
- invalid query params rejected by FastAPI
- broken response shape immediately hits frontend dashboard mappers/tests

**What breaks if changed:**

- posts dashboard
- dashboard filter options
- dashboard regression tests

## Keyword Search Overlay On Posts Dashboard

### Posts keyword search

**Trigger:**
dashboard query with `filters.query`

**Flow:**
posts dashboard screen -> `usePostsKeywordSearchQuery` -> `POST /api/keyword/search/posts` -> feature gate -> `services.keyword_graph.search_posts_by_keywords` -> result post IDs -> filter existing dashboard rows client-side

**Real calls:**

- `frontend/src/modules/workspace/posts/hooks.ts::usePostsKeywordSearchQuery`
- `frontend/src/modules/keyword-graph/api.ts::searchPostsByKeyword`
- `api/routers/keyword_graph.py::search_posts`

**Side-effects:**

- writes `audit_logs`
- reads feature rollout settings

**Errors:**

- `404` feature disabled or rollout gate
- search errors degrade to snapshot table without keyword overlay

**What breaks if changed:**

- dashboard search UX
- coupling between workspace and keyword-graph feature

## Post Detail Read Pipeline

### Post detail page

**Trigger:**
route `/posts/:postId`

**Flow:**
detail page -> `useQueries` -> parallel calls:

- `/api/posts/{id}`
- `/api/posts/{id}/comments`
- `/api/reports/post/{id}`
- `/api/posts/{id}/links`

Then mappers render detail sections.

**Real calls:**

- `frontend/src/modules/workspace/post-detail/hooks.ts::usePostDetailQueries`
- `api/routers/posts.py::get_post`
- `api/routers/posts.py::get_comments`
- `api/routers/reports.py::get_report`
- `api/routers/linking.py::get_post_links`

**Side-effects:**

- read-only DB access

**Errors:**

- missing report is a normal `404`
- missing post is fatal `404`

**What breaks if changed:**

- post detail screen
- async action follow-ups for comments/report refresh

## Comments Refresh Pipeline

### Manual comment refresh

**Trigger:**
`POST /api/posts/{post_id}/comments/update`

**Flow:**
API -> enqueue `refresh_comments` job -> telegram worker picks job -> `services.TGqueries.update_post_comments` -> reconcile/persist comments -> update counters -> `services.reporting.sync_post_report_staleness`

**Real calls:**

- `api/routers/posts.py::update_comments`
- `services.orchestration.enqueue_comment_refresh_job`
- `services/pipeline_runtime.py::_run_comment_job`
- `services/TGqueries.py::update_post_comments`
- `services/reporting.py::sync_post_report_staleness`

**Side-effects:**

- writes `jobs`
- reads Telegram discussion thread
- writes `comments`
- updates `posts.comments_count`, `posts.views`, `posts.involvement`, `last_comments_scan_at`
- may enqueue post report rebuild

**Errors:**

- Telegram `FloodWait` -> job requeue/backoff
- discussion resolution failure -> result payload with `discussion_error`
- worker exceptions -> failed job/dead-letter

**What breaks if changed:**

- comment freshness
- post detail
- downstream report staleness
- event/process freshness

## Add Channel Pipeline

### Add channel

**Trigger:**
`POST /api/channels/add`

**Flow:**
API -> normalize username -> check in-flight dedupe -> enqueue `add_channel` -> telegram worker `_run_add_channel_job` -> Telegram `get_entity` -> `resolve_and_upsert_channel`

**Real calls:**

- `api/routers/channels.py::add_channel`
- `services/jobs.py::enqueue_job`
- `services/pipeline_runtime.py::_run_add_channel_job`
- `services/channel_management.py::resolve_and_upsert_channel`

**Side-effects:**

- writes `jobs`
- writes `audit_logs`
- writes `channels`
- external Telegram API call

**Errors:**

- invalid/empty identifier -> `400`
- Telegram resolution failure -> failed job

**What breaks if changed:**

- admin channels UI
- ingestion source list

## Telegram Ingestion Pipeline

### Regular telegram cycle

**Trigger:**
`scripts/run_telegram_pipeline.py`

**Flow:**
start client -> heartbeat -> `run_telegram_cycle` -> load settings -> iterate active channels -> `IngestionCore.ingest_channel` -> `upsert_post` -> enqueue link/comment jobs -> run link jobs until idle -> optionally rebuild events/processes -> enqueue retention fallback if scheduler disabled -> run queued telegram jobs

**Real calls:**

- `scripts/run_telegram_pipeline.py::main_async`
- `services/pipeline_runtime.py::run_telegram_cycle`
- `services/ingestion_core.py::IngestionCore.ingest_channel`
- `services/ingest.py::upsert_post`
- `services/pipeline_runtime_support.py` enqueue helpers
- `services/pipeline_runtime.py::run_telegram_jobs`

**Side-effects:**

- external Telegram reads
- writes `posts`
- writes `jobs`
- writes runtime heartbeat into `app_settings`
- may trigger graph rebuilds and retention jobs

**Errors:**

- Telethon session lock
- Telegram flood wait
- per-channel failure is logged and cycle continues

**What breaks if changed:**

- core data ingestion
- all downstream linking/events/processes/reports

## Linking Pipeline

### Build post links

**Trigger:**

- automatically after ingestion
- manual `POST /api/linking/run?post_id=...`

**Flow:**
enqueue `build_post_links` -> worker `_run_link_job` -> `NoLlmLinkingPipeline.run_for_post()` -> feature prep -> candidate retrieval -> persist `post_links`

**Real calls:**

- `api/routers/linking.py::run_linking`
- `services/pipeline_runtime.py::_run_link_job`
- `services/linking/no_llm_pipeline.py::run_for_post`

**Side-effects:**

- writes `post_links`
- may call embeddings endpoint
- writes job result payload
- writes `audit_logs` for manual run

**Errors:**

- embeddings service unavailable falls back in parts of pipeline
- unexpected errors fail job

**What breaks if changed:**

- post detail links
- event rebuild quality
- process rebuild quality
- dashboard graph views

## Event Rebuild Pipeline

### Rebuild events

**Trigger:**

- automatic inside telegram cycle after links are drained
- manual `POST /api/events/rebuild`

**Flow:**
enqueue `rebuild_events` -> worker `_run_rebuild_events_job` -> `services.events.build_events.rebuild_events` -> union/group posts by verified links -> rewrite event memberships

**Real calls:**

- `api/routers/linking.py::rebuild_events_api`
- `services/pipeline_runtime.py::_run_rebuild_events_job`
- `services/events/build_events.py::rebuild_events`

**Side-effects:**

- writes `events`
- writes `event_posts`
- writes job result

**Errors:**

- malformed job payload dates
- rebuild exceptions leave queue failed/dead-letter

**What breaks if changed:**

- events dashboard
- event detail
- event graph
- event reports

## Process Rebuild Pipeline

### Rebuild processes

**Trigger:**

- automatic after event rebuild
- manual `POST /api/processes/rebuild`

**Flow:**
enqueue `rebuild_processes` -> worker `_run_rebuild_processes_job` -> `services.processes.build_processes.rebuild_processes` -> group events into processes via update links

**Real calls:**

- `api/routers/linking.py::rebuild_processes_api`
- `services/pipeline_runtime.py::_run_rebuild_processes_job`
- `services/processes/build_processes.py::rebuild_processes`

**Side-effects:**

- writes `processes`
- writes `process_events`

**Errors:**

- same as event rebuild

**What breaks if changed:**

- processes dashboard
- process detail
- process graph
- process reports

## Post Report Pipeline

### Build post report

**Trigger:**

- manual `POST /api/reports/post/{id}/update`
- scheduled by AI pipeline when post is old enough
- auto-enqueued after comment/input changes

**Flow:**
enqueue `build_post_report` -> AI worker `run_ai_jobs` -> `services.reporting.build_post_report` -> reporter project generates payload -> `upsert_report` -> if ready then mark related event reports stale + enqueue event report jobs

**Real calls:**

- `api/routers/reports.py::update_report`
- `services/pipeline_runtime.py::run_ai_jobs`
- `services/reporting.py::build_post_report`
- `services/ingest.py::upsert_report`
- `services/reporting.py::sync_post_report_staleness`

**Side-effects:**

- writes `reports`
- calls external AI report generator
- writes queue cascades for event reports

**Errors:**

- timeout -> requeue in 30s
- model output failure -> report status failed
- below min comments -> skipped result, no report row update cascade

**What breaks if changed:**

- post detail report
- reports list/export
- event/process report dependency chain

## Event Report Pipeline

### Build event report

**Trigger:**

- manual `POST /api/reports/events/{event_id}/update`
- cascade after post reports become ready

**Flow:**
enqueue `build_event_report` -> AI worker -> `build_event_report_draft` -> readiness check across child post reports -> draft or ready event report -> mark related process reports stale -> enqueue process report jobs

**Real calls:**

- `api/routers/reports.py::update_event_report`
- `services/reporting.py::build_event_report_draft`

**Side-effects:**

- writes `event_reports`
- cascade into process report jobs

**Errors:**

- not enough ready child post reports -> deferred and requeued

**What breaks if changed:**

- event detail latest report
- reports exports
- process reports freshness

## Process Report Pipeline

### Build process report

**Trigger:**

- manual `POST /api/reports/processes/{process_id}/update`
- cascade after event reports

**Flow:**
enqueue `build_process_report` -> AI worker -> `build_process_report_draft` -> readiness check across event reports -> write `process_reports`

**Real calls:**

- `api/routers/reports.py::update_process_report`
- `services/reporting.py::build_process_report_draft`

**Side-effects:**

- writes `process_reports`

**Errors:**

- waiting on enough event reports -> deferred

**What breaks if changed:**

- process detail latest report
- process exports

## Batch Post Report Generation

### Generate reports by filter

**Trigger:**
`POST /api/reports/posts/generate-by-filter`

**Flow:**
API stores filter payload -> enqueue batch job -> AI worker `dispatch_post_report_batch` -> enqueue many `build_post_report` jobs

**Real calls:**

- `api/routers/reports.py::generate_post_reports_by_filter`
- `services/pipeline_runtime.py::dispatch_post_report_batch`

**Side-effects:**

- writes batch job
- writes multiple child jobs

**Errors:**

- bad filter payload shape in job JSON can poison the batch

**What breaks if changed:**

- reports page bulk generation

## Monitor Pipeline

### Full monitor snapshot

**Trigger:**
`GET /api/monitor/full`

**Flow:**
router -> `get_all_settings` -> `scheduler_snapshot` -> `health_snapshot` -> `system_snapshot` -> `jobs_snapshot` -> `pipeline_snapshot` -> `evaluate_alerts`

**Real calls:**

- `api/routers/monitor.py::monitor_full`
- `services/monitoring.py::*snapshot`

**Side-effects:**

- read-only DB and process/system probes

**Errors:**

- DB snapshot raw SQL issues
- missing runtime heartbeat data degrades health accuracy

**What breaks if changed:**

- admin ops monitor page

## Scheduler / Retention Pipeline

### Periodic retention dispatch

**Trigger:**
`scripts/run_scheduler.py`

**Flow:**
load effective settings -> build APScheduler -> register periodic jobs -> scheduler dispatch -> enqueue archive retention and jobs retention jobs

**Real calls:**

- `scripts/run_scheduler.py::main_async`
- `services/scheduler_runtime.py::register_periodic_jobs`
- `services/scheduler_dispatch.py::enqueue_daily_retention_jobs`

**Side-effects:**

- runtime heartbeat writes
- writes retention jobs into queue

**Errors:**

- scheduler disabled in settings -> process exits early

**What breaks if changed:**

- data retention
- queue cleanup
- monitor alerts relying on retention freshness
