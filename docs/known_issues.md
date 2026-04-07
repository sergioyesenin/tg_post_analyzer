# Known Issues And Risk Areas

This is intentionally blunt. These issues are visible in the current code.

## Architectural Problems

### 1. Layering is inconsistent

- Many routers perform direct SQLAlchemy reads/writes instead of delegating to services.
- There is no real repository layer.
- Transport, application logic, and persistence logic are often mixed.

Impact:

- harder to change contracts safely
- duplicated query logic
- more hidden side-effects

### 2. God modules

- `services/TGqueries.py`
- `services/reporting.py`
- `services/pipeline_runtime.py`

Impact:

- high regression risk
- hard to test in isolation
- easy to introduce accidental coupling

### 3. Runtime state is mixed with settings

- runtime heartbeats are stored in `app_settings` using internal keys

Impact:

- config and runtime health are not cleanly separated
- monitor logic depends on settings table semantics

### 4. Frontend feature coupling

- workspace imports admin hooks to fetch channel options
- workspace imports keyword graph API for search
- detail modules reuse dashboard components/mappers across feature boundaries

Impact:

- changes in one feature can break another unexpectedly

## Technical Debt

### 1. Ad hoc job result contracts

- job results are stored inside `jobs.payload_json["_job_result"]`
- result shapes vary by job type

Risk:

- UI polling can silently break
- no compile-time or schema-level protection

### 2. AI worker concurrency is effectively forced to 1

- `run_ai_cycle()` clamps worker concurrency to max 1 even though settings imply configurability

Risk:

- settings are misleading
- throughput assumptions are easy to get wrong

### 3. Large global stylesheet

- `frontend/src/app/styles/global.css` is a cross-feature override surface

Risk:

- visual regressions far away from edited code

### 4. Legacy/unused code likely remains

Suspect files:

- root `main.py`
- `parse_today.py`
- `man.py`
- deprecated router `api/routers/links.py`
- frontend placeholder branch:
  - `shared/dashboard/placeholders.ts`
  - `shared/dashboard/view-models.ts`
  - `modules/workspace/components/DashboardModePage.tsx`
  - `shared/ui/placeholders/RoutePlaceholder.tsx`

Risk:

- AI may modify dead code instead of active path

## Dangerous Zones

### Auth/security

- `config.py`
- `deps.py`
- `api/routers/auth.py`
- `services/auth.py`
- `services/auth_rate_limit.py`

Why dangerous:

- one change can break every protected route or weaken security behavior

### Comments pipeline

- `services/TGqueries.py`
- `services/pipeline_runtime.py::_run_comment_job`

Why dangerous:

- Telegram discussion behavior is messy
- retries, flood waits, reconciliation, counters, and staleness all meet here

### Reporting cascade

- `services/reporting.py`
- `services/pipeline_runtime.py::run_ai_jobs`

Why dangerous:

- report readiness and stale propagation are multi-step and stateful

### Graph rebuilds

- `services/events/build_events.py`
- `services/processes/build_processes.py`
- `services/linking/no_llm_pipeline.py`

Why dangerous:

- downstream dashboards and reports depend on consistency across all three

### DB schema

- `db/models.py`

Why dangerous:

- shared by API, workers, retention, archive, monitor, frontend contracts

## Suspicious Or Hard-To-Understand Code

### Backend

- `services/orchestration.py`
  - mostly wrapper/re-export layer over runtime modules
  - increases indirection
- `services/queries.py`
  - helper layer exists, but data access is still scattered

### Frontend

- mixed naming between `Page`, `Screen`, and `Layout`
- route wrappers and direct pages are inconsistent
- some i18n strings appear corrupted or mixed-language in code paths flagged by the architecture maps

## AI-Specific Warnings

- Do not assume a clean service boundary in backend; inspect router + service together.
- Do not assume feature-local frontend changes are isolated; workspace/admin/keyword-graph interact.
- Do not assume any job result payload shape unless you read the producer and consumer.
- Do not assume settings are static env only; many runtime behaviors come from DB-backed settings.

## Recommended Refactor Priorities

### Highest value

- extract explicit application services for:
  - auth login/refresh
  - add channel
  - refresh comments
  - build post report
  - rebuild events/processes
- formalize job payload/result schemas
- split `TGqueries.py`
- split `reporting.py`

### Medium value

- move dashboard/report list SQL out of routers
- separate runtime heartbeat storage from settings
- remove deprecated entrypoints and placeholder frontend branch after verification

### Low-medium value

- reduce `global.css`
- reduce large dashboard screen sizes
