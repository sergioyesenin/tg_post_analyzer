# Frontend Spec Audit

Source of truth: `docs/frontend_handoff_checklist.md`.

Audit date: 2026-03-16.
Scope: stage 15 `final quality pass and spec audit` for the React frontend in `frontend/`.

## Summary

The implemented frontend covers the confirmed route inventory, dashboard modes, detail flows, reports/admin/monitor/jobs/keyword graph modules, URL-owned filters, generated_at rendering, partial/warnings handling, and the shared async job pattern without changing the backend contract.

Frontend quality gate is currently green:

- `npm test` in `frontend/`
- `19` test files passed
- `91` tests passed

## Added Handoff Artifacts

The following repo artifacts now formalize implementation decisions that were previously living only in code/tests:

- `docs/frontend_gap_backlog.md`
- `docs/frontend_route_map.md`
- `docs/frontend_interaction_rules.md`
- `docs/frontend_api_ui_mapping.md`
- `docs/frontend_state_status_matrix.md`
- `docs/frontend_copy_rules.md`

## Audit Matrix

| Area | Audit result | Notes |
| --- | --- | --- |
| Route inventory | Pass | `/login`, all three dashboard modes, three detail routes, reports, channels, users, settings, monitor, jobs, keyword graph are implemented. |
| Major RBAC rules | Pass | Route and action policies enforce `admin` / `analyst` / `viewer` boundaries; viewer remains read-only and cannot access keyword graph or admin modules. |
| Dashboard modes | Pass | Posts, Events, Processes are built around `/api/dashboard/*` endpoints and keep shared alerts/filter/generated_at behavior. |
| Detail flows | Pass | Post, event, and process details are implemented with route-specific data loading and role-aware actions. |
| Async job flows | Pass | Post comments/report, event report, process report, and reports batch generation use the shared job polling pattern. |
| Reports module | Pass | Posts / Events / Processes list routes, export links, and batch post-report generation are covered. |
| Admin module | Pass | Channels, users, and settings flows are implemented with analyst read-only settings behavior. |
| Monitor module | Pass | `/monitor` uses confirmed `GET /api/monitor/full` only. |
| Jobs module | Pass | Summary, pending, dead-letter, and retry actions are implemented for admin. |
| Keyword graph | Pass | Search, build, and report generation are implemented with route-owned filters and role guard. |
| URL filters | Pass | Dashboard and reports filters are serialized to URL; mode switch preserves only supported shared filters. |
| Partial / warnings | Pass | `partial=true` is rendered as a usable degraded state; `warnings[]` render via shared system alerts. |
| generated_at | Pass | All dashboard screens render generated_at even under partial state. |
| Transport DTO vs UI view model | Pass | Dashboard/detail/report modules keep DTO contracts separate from view-model mappers. |
| Reusable components | Pass | Shared alerts, table shell, state cards, badges, notices, and async indicators are reused across modules. |
| Route map artifact | Pass | Route inventory, shell rules, navigation and RBAC route matrix are now documented. |
| Interaction rules artifact | Pass | Dashboard/detail/graph/filter/async interaction rules are now documented. |
| API-to-UI mapping artifact | Pass | Shared field mapping is now documented. |
| State/status matrix artifact | Pass | Shared state and status conventions are now documented. |
| Copy rules artifact | Pass | Shared copy rules are now documented. |

## Key Test Coverage

Existing and updated key-flow coverage now includes:

- auth guard and refresh flow
- route inventory and RBAC matrix policy coverage
- dashboard route shell and mode switching
- URL filter parsing/serialization
- generated_at rendering across dashboard modes
- partial/warnings rendering as non-blocking state
- posts/events/processes dashboards
- post/event/process detail flows
- shared async job flow behavior
- reports list/export/batch generation
- admin CRUD and settings read-only/write boundaries
- monitor/jobs screens and retry flows
- keyword graph search/build/report flow

## Remaining Gaps Relative To Spec

These are the material gaps still open against `docs/frontend_handoff_checklist.md`:

1. The repo still does not include wireframes, hi-fi mocks, or a clickable prototype for the implemented frontend modules.
2. The implemented UI uses framework-native tables and graph rendering boundaries instead of the target stack items `MUI`, `MUI X DataGrid`, and `React Flow` from the stage brief.
3. Monitor remains a single overview route and does not expose optional specialized tabs such as health/jobs/pipeline/scheduler/alerts.

## Assumptions Used In This Audit

- Dynamic report routes `/reports/:reportType` satisfy the three required report screens from the checklist.
- The current role model is limited to `admin`, `analyst`, and `viewer`; no extra composite roles are expected.
- `generated_at` is mandatory only for dashboard screens, not for detail/admin/report/keyword routes.
- Repo-level handoff docs plus executable tests are acceptable implementation artifacts for the formal frontend audit pass.
- Existing local modifications in keyword graph/i18n files are intentional user work and were left untouched.
