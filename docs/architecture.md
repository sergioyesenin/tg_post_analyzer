# TG Post Analyzer Architecture

## Purpose

This document is the working architecture map for AI-assisted development. It is based on:

- `docs/frontend_map.md`
- `docs/backend_map.md`
- direct code inspection of `api/`, `services/`, `db/`, `scripts/`, and `frontend/src/`

It describes the system as it exists now, not as an ideal target architecture.

## System Overview

The project is a single product with two tightly coupled runtimes:

- Frontend: Vite + React 19 + TypeScript SPA in `frontend/`
- Backend: FastAPI + SQLAlchemy async + PostgreSQL in the repository root

Operationally the backend is not just an HTTP API. It is four runtime modes over one shared DB:

- HTTP API: `scripts/run_api.py` -> `api.main:app`
- Telegram pipeline worker: `scripts/run_telegram_pipeline.py`
- AI reporting worker: `scripts/run_ai_pipeline.py`
- Scheduler/control plane: `scripts/run_scheduler.py`

All runtimes share:

- the same DB schema in `db/models.py`
- the same settings source: env in `config.py` + DB settings in `app_settings`
- the same job queue table: `jobs`

## High-Level Subsystems

### Frontend

- `app/`: shell, providers, router, global styles
- `modules/workspace/`: dashboards and entity detail pages
- `modules/reports/`: report list/export/generate flows
- `modules/admin/`: users, channels, settings
- `modules/platform/`: monitor and jobs UI
- `modules/keyword-graph/`: keyword search + graph exploration
- `shared/`: HTTP client, auth, routing policy, reusable UI, dashboard primitives

### Backend

- `api/routers/`: transport layer, auth checks, request parsing
- `services/`: business logic, orchestration, workers, read models
- `db/`: SQLAlchemy models and session factory
- `schemas/`: request/response DTOs for FastAPI
- `scripts/`: real runtime entrypoints and ops utilities
- `client/`: Telegram client bootstrap

## Project Structure

```text
.
├─ api/
│  ├─ main.py
│  └─ routers/
├─ db/
│  ├─ models.py
│  └─ session.py
├─ services/
│  ├─ dashboard/
│  ├─ events/
│  ├─ linking/
│  ├─ processes/
│  ├─ reporting.py
│  ├─ pipeline_runtime.py
│  ├─ TGqueries.py
│  └─ jobs.py
├─ schemas/
├─ scripts/
├─ frontend/
│  ├─ src/app/
│  ├─ src/modules/
│  └─ src/shared/
├─ alembic/
└─ docs/
```

## Layers And Responsibilities

### Frontend layers

#### UI layer

- Files: `frontend/src/modules/*/*Page.tsx`, `frontend/src/modules/*/*Screen.tsx`, `frontend/src/shared/ui/*`
- Responsibility: render, route composition, local UI state, user interaction
- Must not contain backend contract shaping beyond small display mappers

#### Application/client state layer

- Files: `frontend/src/modules/*/hooks.ts`, `frontend/src/app/providers/SessionProvider.tsx`
- Responsibility:
  - React Query orchestration
  - async mutations
  - cache invalidation
  - auth bootstrap/refresh/logout
  - URL filter state orchestration

#### API adapter layer

- Files: `frontend/src/modules/*/api.ts`, `frontend/src/shared/auth/auth-api.ts`, `frontend/src/shared/api/client.ts`
- Responsibility:
  - call backend routes
  - convert HTTP to DTOs
  - centralize token refresh behavior

#### Mapping/contracts layer

- Files: `frontend/src/modules/*/contracts.ts`, `mappers.ts(x)`, `frontend/src/shared/dashboard/contracts.ts`
- Responsibility:
  - define DTO/view-model boundaries
  - convert backend payloads into table/detail/dashboard-friendly models

### Backend layers

#### Transport layer

- Files: `api/routers/*.py`
- Responsibility:
  - route definition
  - auth guard via `deps.py`
  - request parsing and basic validation
  - handoff to services or queue

Reality check: many routers still query SQLAlchemy directly.

#### Application/service layer

- Files: `services/*.py`, `services/dashboard/*`, `services/events/*`, `services/processes/*`
- Responsibility:
  - use-case orchestration
  - read-model building
  - queue scheduling
  - integrations
  - report generation
  - graph rebuilds

#### Data access layer

- Files: `db/models.py`, `db/session.py`, direct ORM in routers/services
- Responsibility:
  - persistence and transactions
  - DB schema

Reality check: there is no dedicated repository layer. Data access is spread across routers and services.

#### Integration layer

- Telegram: `client/telegram.py`, `services/ingestion_core.py`, `services/TGqueries.py`
- AI/reporting: `agents.reporter`, `services/reporting.py`
- Embeddings/search: `services/linking/embeddings.py`

## Data Flows

### UI -> DB flow

Typical frontend path:

`Page/Screen` -> `hooks.ts` -> `api.ts` -> `shared/api/client.ts` -> FastAPI router -> service/direct ORM -> DB

Examples:

- posts dashboard: `PostsDashboardScreen` -> `usePostsDashboardQuery` -> `/api/dashboard/posts`
- post detail actions: `useRefreshCommentsAction` -> `/api/posts/{id}/comments/update` -> queue -> worker -> DB
- settings update: `SettingsPage` -> admin hooks -> `/api/settings/{key}` -> validation -> DB

### API -> response flow

Typical backend path:

request -> FastAPI router -> request/query validation -> service or direct ORM -> SQLAlchemy rows -> schema/JSON response

Examples:

- dashboard routes use dedicated read-model builders in `services/dashboard/*`
- auth routes use `services/auth.py`
- reports list/export routes perform direct SQL in router

### Worker flow

job producer -> `services.jobs.enqueue_job()` -> `jobs` table -> worker fetch/lock -> domain service -> DB update -> optional cascade enqueue

Critical cascades:

- post comments changed -> mark post report stale -> enqueue post report rebuild
- post report ready -> mark event reports stale -> enqueue event report jobs
- event report ready/draft -> mark process reports stale -> enqueue process report jobs

## Dependency Rules

### Allowed dependencies

- frontend `app/*` may depend on `modules/*` and `shared/*`
- frontend `modules/*` may depend on `shared/*`
- frontend `shared/*` must stay reusable and must not depend on `modules/*`
- backend routers may depend on `deps`, `schemas`, `services`, `db`
- backend services may depend on `db`, `schemas`, other services, integrations
- scripts may depend on `services`, `db`, `config`, `client`

### Forbidden or discouraged dependencies

- `frontend/src/shared/*` -> `frontend/src/modules/*`
- React components -> direct `fetch` calls bypassing `api.ts`
- frontend pages -> token parsing / refresh logic outside `SessionProvider` and `shared/api/client.ts`
- backend routers -> Telegram or AI integration code directly
- backend routers -> new business logic blocks longer than thin orchestration
- worker logic -> direct writes to arbitrary settings keys except runtime heartbeat path

### Existing violations to remember

- workspace frontend depends on admin hooks for channel options
- workspace frontend depends on keyword graph API for dashboard search
- several backend routers perform direct ORM queries instead of delegating to services
- runtime heartbeats are stored in `app_settings`, which mixes config and runtime state

## Entry Points

### Frontend

- `frontend/src/main.tsx`
- `frontend/src/app/App.tsx`
- `frontend/src/app/providers/AppProviders.tsx`
- `frontend/src/app/router/AppRouter.tsx`

### Backend HTTP

- `scripts/run_api.py`
- `api/main.py`

### Background workers

- Telegram pipeline: `scripts/run_telegram_pipeline.py`
- Inline-comments variant: `scripts/run_telegram_pipeline_inline_comments.py`
- AI pipeline: `scripts/run_ai_pipeline.py`
- Scheduler: `scripts/run_scheduler.py`

### One-off / ops entrypoints

- `scripts/create_admin.py`
- `scripts/add_channel.py`
- `scripts/backfill_*.py`
- `scripts/check_*.py`

### Legacy/suspect entrypoints

- root `main.py`
- `parse_today.py`
- `man.py`

Treat them as legacy unless a task explicitly requires them.

## Critical Files

- Backend:
  - `db/models.py`
  - `config.py`
  - `deps.py`
  - `services/pipeline_runtime.py`
  - `services/reporting.py`
  - `services/TGqueries.py`
  - `services/jobs.py`
- Frontend:
  - `frontend/src/app/providers/SessionProvider.tsx`
  - `frontend/src/shared/api/client.ts`
  - `frontend/src/shared/routing/policy.ts`
  - `frontend/src/shared/dashboard/contracts.ts`
  - `frontend/src/shared/dashboard/filters.ts`
  - `frontend/src/app/styles/global.css`

Changes here have cross-cutting impact and require end-to-end verification.
