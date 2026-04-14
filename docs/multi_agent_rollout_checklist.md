# Multi-Agent Rollout Checklist

## Goal

Enable internal multi-agent post reporting gradually while preserving the public report contract, passive AI worker behavior, and existing manual/API-triggered generation model.

## Preconditions

- P1-P7 changes are deployed.
- Frontend status coverage for `limited` and `insufficient_data` is already present.
- Operators can read `/api/settings/effective`, `/api/monitor/pipeline`, and public report endpoints.

## Staged enablement

1. Confirm safe defaults:
   - `features.multi_agent_mode_enabled=false`
   - `features.multi_agent_rollout_percent=0`
2. Propagation-only check:
   - set `multi_agent_mode_enabled=true`
   - keep `multi_agent_rollout_percent=0`
   - verify `/api/settings/effective` reflects the new values
3. Small rollout:
   - set `multi_agent_rollout_percent=5` or `10`
   - manually trigger a small batch of post-report rebuilds through existing API surfaces
4. Evaluate:
   - public payloads remain schema-valid
   - `meta.multi_agent` is still absent from public APIs
   - `limited` and `insufficient_data` appear only when justified
5. Expand gradually:
   - move to `25`, then `50`, then `100` only after regressions and operator checks remain stable

## Verification matrix

- Rollout off:
  - settings still read safe defaults
  - accepted-job API and WebSocket event names remain unchanged
- Rollout on:
  - one `BUILD_POST_REPORT` job still produces one persisted report row
  - internal stages and reviewer loop stay inside the same job
- `limited`:
  - post detail renders summary/topics/content
  - downstream event/process aggregation may still consume the report
- `insufficient_data`:
  - public contract stays valid
  - downstream event/process readiness must not treat the report as ready
- Reviewer exhaustion:
  - final public status is non-`ready`
  - no public review history is exposed

## Rollback

1. Set `multi_agent_rollout_percent=0`.
2. If needed, set `multi_agent_mode_enabled=false`.
3. Continue using the same manual/API-triggered report generation model.
4. Do not add emergency worker types, child jobs, or direct trace exposure.

## Diagnostics

- `/api/settings/effective`
- `/api/monitor/pipeline`
- `GET /api/reports/post/{id}`
- `GET /api/events/{id}`
- `GET /api/processes/{id}`

## Regression commands

- Backend fast regression:
  - `venv\Scripts\python -m pytest -q tests`
- Backend integration regression:
  - `venv\Scripts\python -m pytest -q tests/integration --run-integration`
- Frontend regression:
  - `cd frontend && npm test`
