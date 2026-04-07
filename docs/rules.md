# AI Development Rules

These rules are strict. They reflect the current codebase, including its weak points.

## File Placement Rules

### Frontend

- New route pages go into `frontend/src/modules/<feature>/routes/` when the feature already uses route wrappers.
- Feature-specific API calls go into `frontend/src/modules/<feature>/api.ts`.
- Feature-specific React Query logic goes into `frontend/src/modules/<feature>/hooks.ts`.
- DTO/view-model conversion goes into `contracts.ts` and `mappers.ts(x)`.
- Reusable UI only goes into `frontend/src/shared/ui/*` or `frontend/src/shared/dashboard/*` if it is truly cross-feature.
- Route/access/navigation changes must go through `frontend/src/shared/routing/policy.ts`.

### Backend

- New HTTP endpoints go into the nearest router under `api/routers/`.
- Request/response DTOs go into `schemas/`.
- Reusable business logic goes into `services/`.
- Dashboard read-model logic belongs in `services/dashboard/`, not in routers.
- Worker orchestration belongs in `services/pipeline_runtime.py` or helper modules it already delegates to.
- DB schema changes require:
  - model change in `db/models.py`
  - Alembic migration
  - contract review for affected schemas/services/frontend DTOs

## Coding Rules

- Do not add direct `fetch` or ad hoc HTTP code in React components. Use `api.ts` -> hooks -> component.
- Do not add token or refresh logic outside `SessionProvider` and `shared/api/client.ts`.
- Do not put business logic in React screens if it can live in hooks or mappers.
- Do not add Telegram API calls inside routers.
- Do not add AI/reporting logic inside routers.
- Do not write new SQL-heavy query blocks in routers if a service already exists for that area.
- Do not add new places that write free-form job result blobs without documenting the shape.

## Bad Practices Already Present

AI should avoid copying these patterns:

- direct ORM queries in routers like `api/routers/posts.py` and `api/routers/reports.py`
- god modules: `services/TGqueries.py`, `services/reporting.py`, `services/pipeline_runtime.py`
- feature-to-feature frontend coupling:
  - workspace -> admin hooks for channels
  - workspace -> keyword-graph API for search
- mixing runtime state with config in `app_settings`
- large UI screens carrying too much orchestration and rendering at once

## Dependency Rules

### Frontend strict rules

- `shared/*` must not import from `modules/*`
- `modules/*` may import from `shared/*`
- `app/*` may orchestrate `modules/*` and `shared/*`
- pages/screens should not import low-level auth storage directly
- filters must remain URL-driven through `filters.ts` helpers

### Backend strict rules

- routers may depend on:
  - `deps`
  - `schemas`
  - `services`
  - `db`
- services may depend on:
  - `db`
  - other services
  - integrations
  - schemas when shaping output is unavoidable
- models in `db/models.py` must not import from services or routers
- scripts may orchestrate services but must not duplicate service business rules

### Forbidden dependencies

- controller/router -> Telegram client calls
- controller/router -> LLM/reporter integration
- React component -> direct DB/job semantics
- worker runtime -> frontend contracts

## Data Rules

- Validate external request payloads in `schemas/` or FastAPI query constraints first.
- Validate settings updates only through `services/settings_validation.py`.
- Map backend payloads to UI models in `mappers.ts(x)`, not inline in large components.
- Preserve DB-to-DTO boundaries with `schemas/*` where they already exist.
- When changing report payload structure, check all three layers:
  - `services/reporting.py`
  - `schemas/report.py`
  - frontend report/detail consumers

## API Rules

- Frontend must call backend only through feature `api.ts` files or `shared/auth/auth-api.ts`.
- Authenticated requests must use `shared/api/client.ts`.
- New async backend actions that may take time should prefer queue + accepted job response, following current job pattern.
- Accepted job responses should continue exposing:
  - `status`
  - `job_id`
  - `job_type`
  - `status_url`
  - `result_url`

## Frontend State Rules

- Auth/session state lives in `SessionProvider`.
- Remote async state lives in React Query hooks.
- Filter state for dashboards/reports/keyword graph lives in URL query params via `filters.ts`.
- Local display-only state can stay in component `useState`.
- Do not introduce a parallel global state store for data that already lives in React Query or URL state.

## Critical Prohibitions

- Do not query DB directly from a new React feature. Ever.
- Do not write business logic in React route components unless it is purely presentational composition.
- Do not call Telegram from HTTP routers.
- Do not write directly to `jobs.payload_json["_job_result"]` outside queue/runtime helpers without keeping result shape stable.
- Do not bypass `require_roles()` in new backend endpoints.
- Do not change `SessionProvider`, `shared/api/client.ts`, `deps.py`, `config.py`, `services/jobs.py`, or `db/models.py` without end-to-end verification.
- Do not repurpose `app_settings` internal keys unless the change is explicitly about runtime heartbeat/config internals.

## Safe Change Checklist

- If you change an endpoint:
  - update router
  - update schema
  - update frontend `api.ts`
  - update related contracts/mappers
- If you change a job payload:
  - update enqueue site
  - update worker handler
  - check `jobs/result` consumers
- If you change a report payload:
  - check post detail
  - check reports page
  - check event/process cascades
- If you change dashboard filters/contracts:
  - check posts/events/processes together
  - check URL serialization and tests
