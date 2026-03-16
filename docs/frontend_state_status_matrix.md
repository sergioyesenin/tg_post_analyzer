# Frontend State And Status Matrix

Source of truth: `docs/frontend_handoff_checklist.md`.
Implementation source: shared UI state components, status badges, route modules, and tests.
Updated: 2026-03-16.

## Shared Route / Block States

| State | Meaning | Shared UI pattern |
| --- | --- | --- |
| `loading` | first fetch in progress | `LoadingState` or inline loading block |
| `refreshing` | refetch in progress while content exists | inline loading indicator / fetching graph state |
| `empty` | request succeeded but has no content | `EmptyState` |
| `error` | generic request failure | `ErrorState` |
| `forbidden` | authenticated user lacks access or backend returns `403` | `ForbiddenState` |
| `partial` | screen is usable but incompletely enriched | `DashboardSystemAlerts` + `PartialDataNotice` |
| `warning` | non-blocking warning items returned by backend | `DashboardWarningsBanner` |
| `stale` | previous snapshot still visible during refresh | existing content remains visible while query refetches |
| `no selection` | graph/detail rail has nothing selected | graph/detail placeholder state |
| `no graph edges` | graph loaded but relation edges are absent | non-fatal graph empty/no-edges state |
| `action in progress` | async mutation running | `AsyncActionIndicator` pending/running state |
| `action success` | async mutation finished successfully | `AsyncActionIndicator` success state + invalidation |
| `action failed` | async mutation terminal failure | `AsyncActionIndicator` failure state without dropping loaded content |

## Screen Matrix

| Screen | Required implemented states |
| --- | --- |
| login | idle, loading, invalid credentials, service unavailable, generic error |
| dashboard/posts | loading, empty, error, forbidden, partial, warning, viewer read-only |
| dashboard/events | loading, empty, error, forbidden, partial, warning, no selection, graph loading, graph empty/no-edges |
| dashboard/processes | loading, empty, error, forbidden, partial, warning, no selection, graph loading, graph empty/no-edges |
| post detail | loading, not found, forbidden, comments/report action progress, secondary-block error |
| event detail | loading, not found, forbidden, graph loading, graph error, read-only |
| process detail | loading, not found, forbidden, graph loading, graph error, read-only |
| reports | loading, empty, error, forbidden, batch action progress |
| admin screens | loading, empty, error, forbidden, form validation error, mutation progress |
| jobs | loading, empty, error, forbidden, retry progress, retry success/failure |
| keyword graph | start/idle, loading, empty, error, build loading, report loading, forbidden |

## Status Systems

### report_status

| Backend status | Label behavior | UI target |
| --- | --- | --- |
| `missing` | no report yet | `ReportStatusBadge` |
| `pending` | report job is queued/in progress | `ReportStatusBadge` |
| `draft` | draft exists | `ReportStatusBadge` |
| `ready` | final/ready report available | `ReportStatusBadge` |
| `failed` | report generation failed | `ReportStatusBadge` |
| unknown value | fallback badge | `ReportStatusBadge` fallback metadata |

### job_status

| Backend status | Label behavior | UI target |
| --- | --- | --- |
| `pending` | queued | `JobStatusInline` / `AsyncActionIndicator` |
| `running` | currently processing | `JobStatusInline` / `AsyncActionIndicator` |
| `done` | successful terminal state | `JobStatusInline` / `AsyncActionIndicator` |
| `failed` | failed terminal state | `JobStatusInline` / `AsyncActionIndicator` |
| unknown value | fallback label | shared job status fallback |

### monitor_status

| Backend status | Label behavior | UI target |
| --- | --- | --- |
| `ok` | healthy | `MonitorStatusBadge` |
| `warning` | warning | `MonitorStatusBadge` |
| `critical` | critical | `MonitorStatusBadge` |
| `degraded` | degraded but partially available | `MonitorStatusBadge` |
| backend-specific fallback | explicit fallback label | `MonitorStatusBadge` fallback metadata |

## Partial / Warning Rules

- `partial=true` must never replace screen content with a blocking error card.
- `warnings[]` must remain visible in a shared banner layer.
- `generated_at` must remain visible when partial warnings exist.
- Partial and warning states may coexist with empty/non-empty data; they are orthogonal to request success.
