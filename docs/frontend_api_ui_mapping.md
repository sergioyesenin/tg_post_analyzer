# Frontend API To UI Mapping

Source of truth: `docs/frontend_handoff_checklist.md`.
Implementation source: contracts, mappers, shared dashboard components, detail modules, jobs hooks.
Updated: 2026-03-16.

## Shared Dashboard Envelope

| Backend field | UI target | Mapping rule | Fallback / null handling | State effect |
| --- | --- | --- | --- | --- |
| `mode` | workspace mode identity | used to bind route/module semantics | not shown directly | determines dashboard module |
| `generated_at` | `DashboardGeneratedAt` | ISO -> formatted UTC label | if absent, generated-at block should not synthesize a fake value | snapshot freshness visible |
| `partial` | `DashboardSystemAlerts` / partial notice | boolean used as degraded-state flag | defaults to non-partial only when backend contract says false | non-blocking partial state |
| `warnings[]` | `DashboardWarningsBanner` | normalized warning list | empty array renders no banner | warning layer stays visible without blocking content |
| `filters_applied` | filter debug / route-owned state coherence | used for applied filter interpretation and test verification | unsupported keys ignored | URL and API state stay aligned |
| `summary` | `DashboardSummaryCards` | DTO summary -> cards view model | missing numeric values become safe formatted fallbacks | KPI layer |
| `items` | `DashboardTableShell` and detail rails | DTO rows -> table row view model | nullable metrics become safe placeholders | main analytical content |
| `meta` | sort/support metadata | used for supported sorts and secondary context | ignored if not needed by the current screen | screen capabilities |

## Shared Detail / Metrics Fields

| Backend field | UI label / target | Mapping rule | Fallback |
| --- | --- | --- | --- |
| `comments_count` | comments metrics | number formatting | `0` |
| `views` | views metrics | number formatting | dash / empty-safe text |
| `involvement` | involvement metrics | fixed-point / formatted percentage-like display | dash / empty-safe text |
| `date` / `started_at` / `ended_at` | date labels | ISO -> formatted UTC string | empty-safe label |
| `report_status` | `ReportStatusBadge` | normalized through shared status metadata | unknown -> fallback badge |
| `channels` / `channel_*` | channel label cells | composed label from title / username / category | username-only or fallback text |
| `text_preview` | preview cells / detail snippets | trimmed preview text | localized no-preview copy |

## Posts Dashboard / Detail Mapping

| Backend field | UI target | Mapping note |
| --- | --- | --- |
| `post_id` | row key, detail link | canonical navigation id |
| `links_count` | links metric cell | nullable-safe numeric display |
| `comments_refresh_available` | comments action visibility | role + backend capability-aware action entry point |
| comments DTO thread fields | `CommentsBlock` view model | preserved in mapped view model so thread mode can be added without contract rewrite |
| links payload | `LinksBlock` | independent block loading/error/empty state |
| post report payload | `ReportBlock` | independent block loading/error/empty state |

## Events / Processes Mapping

| Backend field | UI target | Mapping note |
| --- | --- | --- |
| `event_id` / `process_id` | selection key, detail route | canonical entity id |
| `posts_count` / `events_count` | summary and row metrics | numeric formatting |
| `root_post_id` | event context link | link rendered only when confirmed |
| graph payload nodes/edges | graph panel view model | mapped into framework-native graph cards/lists without inventing extra graph fields |
| related posts / events arrays | detail panel context lists | rendered only from confirmed linked entities |
| `graph_ready` | partial graph hint | informs inline partial/degraded graph message |

## Async Job Mapping

| Backend field | UI target | Mapping rule |
| --- | --- | --- |
| `job_id` | async indicator / polling key | stored after mutation enqueue |
| job status payload | `AsyncActionIndicator` / jobs tables | normalized through shared job-status metadata |
| job result payload | result summary text | rendered as concise success/failure outcome |
| retry mutation response | jobs screen feedback | used to invalidate jobs and monitor queries |

## Monitor Mapping

| Backend field | UI target | Mapping note |
| --- | --- | --- |
| overall monitor status | `MonitorStatusBadge` | normalized to status badge metadata |
| alert rows | alerts table | direct tabular rendering with compact state badge |
| dependency/runtime/backlog fields | overview sections | read-only snapshot rendering only |

## Keyword Graph Mapping

| Backend field | UI target | Mapping note |
| --- | --- | --- |
| keyword search result items | results table + seed set | canonical post seed selection source |
| `normalized_query` | search metadata | diagnostic search context |
| `lemmas` | search metadata | read-only analysis context |
| build response nodes/edges | keyword graph panel | mapped to analytical graph view model |
| report response `title` / `content` / `status` | report preview block | synchronous render, no invented persistence layer |
