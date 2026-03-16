# tg_post_analyzer

## Overview

`tg_post_analyzer` is a Telegram analytics workspace with a FastAPI backend and a React frontend.
The frontend provides one authenticated analytical shell with dashboard, detail, reports, admin, monitor, jobs, and keyword-graph flows built on top of confirmed backend APIs.

Current frontend implementation status:

- `dashboard/posts`, `dashboard/events`, `dashboard/processes` are implemented against `/api/dashboard/*`
- post, event, and process detail routes are implemented
- reports, channels, users, settings, monitor, jobs, and keyword graph routes are implemented
- shared RBAC, URL filters, partial/warnings rendering, generated_at rendering, and async job polling are implemented
- formal handoff docs now cover route map, interaction rules, API-to-UI mapping, state/status matrix, and copy rules

## Tech Stack

Backend:

- Python
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL

Frontend:

- React
- TypeScript
- Vite
- React Router
- TanStack Query
- React Hook Form
- Zod
- i18next

Target-but-not-yet-adopted UI stack from the handoff checklist:

- MUI
- MUI X DataGrid
- React Flow

## Project Structure

```text
api/                    FastAPI routers and app entrypoint
services/               domain services, dashboard aggregators, jobs, monitoring
schemas/                backend transport schemas
frontend/               Canonical React application and Vite build output
frontend/src/app/       app bootstrap, providers, shell, router, guards
frontend/src/shared/    shared API client, auth, routing, dashboard system, UI primitives
frontend/src/modules/   feature route modules (workspace, reports, admin, platform, keyword graph)
web/                    Deprecated legacy static prototype; no longer served by FastAPI
tests/                  backend/API tests
docs/                   requirements, plans, and audit artifacts
```

## Architecture Decisions

- One authenticated SPA shell is used for all protected frontend routes.
- `frontend/` is the only supported UI codebase; `web/` is kept only as a deprecated legacy artifact.
- FastAPI serves the built SPA from `frontend/dist` when the frontend has been built for integrated runtime delivery.
- Dashboard modes are built primarily from confirmed aggregator endpoints under `/api/dashboard/*`.
- Transport DTOs and UI view models are separated through per-module contracts and mappers.
- URL query params are the source of truth for dashboard and reports filters.
- Shared state primitives are reused for loading, empty, error, forbidden, partial, warning, and async-action states.
- Role checks are centralized in a route/action policy layer instead of being duplicated in screens.
- The frontend does not invent backend fields or unsupported API flows.
- Telegram ingestion uses one shared Telethon client/session per runtime process, so channel ingest is intentionally serialized instead of exposing unsafe pseudo-concurrency.

## Routing Model

Public route:

- `/login`

Protected routes inside one shell:

- `/dashboard/posts`
- `/dashboard/events`
- `/dashboard/processes`
- `/posts/:postId`
- `/events/:eventId`
- `/processes/:processId`
- `/reports/:reportType`
- `/channels`
- `/users`
- `/settings`
- `/monitor`
- `/jobs`
- `/keyword-graph`

Routing rules:

- `/` redirects to `/dashboard/posts`
- guests are redirected to `/login`
- authenticated users without access see a forbidden screen instead of a silent redirect
- navigation visibility is role-aware and comes from the same route policy source of truth

Detailed route artifact:

- [docs/frontend_route_map.md](/d:/Projects/tg_post_analyzer/docs/frontend_route_map.md)

## Auth / Session Model

- Local auth is implemented through `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Session state is owned by `frontend/src/app/providers/SessionProvider.tsx`.
- Access tokens are kept only in in-memory frontend state; they are not persisted in `localStorage`.
- Refresh tokens are stored only in an `HttpOnly` cookie managed by the backend.
- The API client sends bearer auth for protected API calls and performs one cookie-based refresh attempt on `401`.
- If refresh fails, in-memory session state is cleared and the user returns to guest mode.
- `/login` is public-only; authenticated users are redirected into the workspace.

## Data Layer Model

- Backend contracts live in module-specific `contracts.ts` files and shared dashboard contracts.
- Data fetching is owned by feature hooks using TanStack Query.
- Mapping from transport DTOs to UI-friendly view models happens in `mappers.ts` files.
- Query keys are centralized per domain to keep cache invalidation predictable.
- Error handling uses a shared `ApiError` policy and reusable route/block state components.

Detailed mapping artifact:

- [docs/frontend_api_ui_mapping.md](/d:/Projects/tg_post_analyzer/docs/frontend_api_ui_mapping.md)

## Linking API

- The canonical linking bounded context is implemented in `api/routers/linking.py`.
- Canonical read routes are `GET /api/posts/{post_id}/links`, `GET /api/events/{id}`, `GET /api/processes/{process_id}`, and `GET /api/events`.
- Canonical write routes are `POST /api/linking/run`, `POST /api/events/rebuild`, and `POST /api/processes/rebuild`.
- Legacy `/api/links/*` aliases remain available only as a deprecated compatibility bridge and should not be used by new frontend code.

## Dashboard Model

Shared dashboard rules:

- posts, events, and processes use `/api/dashboard/*` as the primary source of truth
- `generated_at` is shown on every dashboard screen
- `partial=true` is rendered as a usable degraded state, not as a hard error
- `warnings[]` are always displayed in a shared alerts layer
- filters serialize into the URL

Mode-specific surfaces:

- Posts: summary cards, filters, table, report status, detail entry points
- Events: summary cards, filters, events table, selected-event graph, details rail, draft report action
- Processes: summary cards, filters, processes table, process graph, details rail, draft report action

## Graph Model

- Event and process graph views use the confirmed dashboard graph endpoints only.
- Dashboard graph panels and full detail pages reuse the same graph and detail components.
- Keyword graph is a separate analytical route and uses only the confirmed keyword search/build/report APIs.
- Graph screens support loading, empty, no-edges, error, refresh, and partial-hint states.
- Current graph rendering stays framework-native and does not yet use React Flow.

Interaction and state artifacts:

- [docs/frontend_interaction_rules.md](/d:/Projects/tg_post_analyzer/docs/frontend_interaction_rules.md)
- [docs/frontend_state_status_matrix.md](/d:/Projects/tg_post_analyzer/docs/frontend_state_status_matrix.md)

## RBAC Model

Role scope:

- `admin`: dashboard, details, reports, channels, users, settings, monitor, jobs, keyword graph
- `analyst`: dashboard, details, reports, keyword graph, read-only effective settings
- `viewer`: read-only dashboard, details, reports; no mutations; no keyword graph; no admin modules

Action scope:

- `reports.generate`: admin, analyst
- `comments.refresh`: admin, analyst
- `settings.update`: admin only
- `channels.manage`: admin only
- `users.manage`: admin only
- `jobs.retry`: admin only

Behavior rules:

- hidden navigation for routes outside the role scope
- forbidden route screen for direct access to disallowed protected routes
- read-only notices on surfaces where a role can read but cannot mutate

## Runtime Assumptions

- There is one frontend delivery path: the React SPA in `frontend/`.
- Local frontend development runs through Vite on `http://localhost:5173` and proxies `/api` to the FastAPI backend.
- Cross-origin auth relies on `allow_credentials=True` plus explicit allowed origins, because refresh uses an `HttpOnly` cookie on `/api/auth`.
- CORS origins and `allow_credentials` are configured through env-backed settings instead of hardcoded localhost values.
- `dev`/`local`/`test` default to localhost-friendly origins; non-dev environments must set `CORS_ALLOWED_ORIGINS` explicitly.
- Integrated runtime serving uses `frontend/dist`; after `npm run build`, FastAPI serves the SPA shell at `/` and returns `index.html` for client-side routes.
- `web/` is deprecated and is not mounted or returned from `api/main.py`.
- If `frontend/dist` is missing, the backend still serves the API, but `/` returns a build-missing error instead of falling back to legacy UI files.
- Telegram runtime does not support per-channel concurrency on a shared session; the `ingest` settings surface no longer advertises `channel_concurrency`.

## Async Job Flow

Shared async flow used by post comments refresh, report generation/update, and report batch generation:

1. Submit a mutation endpoint.
2. Receive `job_id`.
3. Poll job status.
4. Fetch job result on terminal state.
5. Invalidate relevant queries.
6. Re-render the updated screen while keeping existing content visible.

Confirmed async surfaces:

- `POST /api/posts/{post_id}/comments/update`
- `POST /api/reports/post/{post_id}/update`
- `POST /api/reports/events/{event_id}/update`
- `POST /api/reports/processes/{process_id}/update`
- `POST /api/reports/posts/generate-by-filter`

## Testing Strategy

Frontend tests live in `frontend/src/test` and focus on key user flows rather than snapshot-only coverage.

Covered areas:

- auth guard and refresh flow
- route inventory and RBAC policy matrix
- dashboard filter parsing and URL serialization
- generated_at rendering on all dashboard modes
- partial/warnings behavior
- posts/events/processes dashboard flows
- post/event/process detail flows
- shared async job flow behavior
- reports list/export/batch generation
- channels/users/settings flows
- monitor/jobs admin flows and retry actions
- keyword graph search/build/report flow

Run frontend tests:

```bash
cd frontend
npm install
npm test
```

Run backend tests:

```bash
venv\Scripts\python -m pytest -q tests
```

## Known Limitations

- The frontend currently uses framework-native tables and graph rendering instead of MUI, MUI X DataGrid, and React Flow.
- Monitor is implemented as a single overview route, not as a multi-tab operations console.
- Export flows use direct endpoint links rather than richer in-app download state management.
- Settings editing uses a conservative JSON editor rather than schema-specific form editors.
- No proactive token refresh scheduler or expiry countdown is implemented; refresh is reactive on `401`.

## Remaining Gaps Relative To Spec

Open gaps relative to `docs/frontend_handoff_checklist.md`:

- wireframes, hi-fi mocks, and clickable prototype are still absent from the repo
- the target UI libraries from the brief are not yet integrated
- optional monitor specialized sub-tabs are not implemented

Supporting docs:

- [docs/frontend_spec_audit.md](/d:/Projects/tg_post_analyzer/docs/frontend_spec_audit.md)
- [docs/frontend_gap_backlog.md](/d:/Projects/tg_post_analyzer/docs/frontend_gap_backlog.md)
- [docs/frontend_copy_rules.md](/d:/Projects/tg_post_analyzer/docs/frontend_copy_rules.md)

## Quick Start

Backend:

```bash
copy .env.example .env
alembic upgrade head
uvicorn api.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Production-style integrated frontend serving:

```bash
cd frontend
npm install
npm run build
cd ..
uvicorn api.main:app
```

## Quality Gate

Stage 15 final quality pass status on 2026-03-16:

- frontend audit completed against `docs/frontend_handoff_checklist.md`
- `npm test` passed in `frontend/`
- route and RBAC matrix coverage was extended with an explicit policy test
- handoff/spec documentation was expanded for route map, interactions, mapping, state/status, and copy rules



