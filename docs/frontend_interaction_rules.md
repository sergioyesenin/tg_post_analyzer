# Frontend Interaction Rules

Source of truth: `docs/frontend_handoff_checklist.md`.
Implementation source: dashboard screens, detail pages, shared filter helpers, and tests.
Updated: 2026-03-16.

## Dashboard Interactions

### Mode switch

- Clicking a dashboard mode link navigates to the target route.
- Only shared supported filters are preserved during mode switch.
- Unsupported or mode-specific params are dropped instead of being reinterpreted.

### Filter bar

- Dashboard filters are URL-owned.
- User edits form inputs first, then applies them explicitly.
- Apply updates the route query string.
- Reset clears dashboard-owned params for the current mode only.
- Unknown query params are ignored during parse.

### Table rows

- Posts dashboard row actions open post detail.
- Events dashboard row selection changes the selected event inside the workspace.
- Processes dashboard row selection changes the selected process inside the workspace.
- Selection survives refetch when the selected entity still exists in the refreshed payload.

## Graph Rules

### Event graph

- Graph loads only for the selected event.
- Manual refresh keeps the panel visible and shows refresh/loading state inline.
- Empty graph and no-edges graph are non-fatal states.
- Related-post links navigate to confirmed post detail routes.

### Process graph

- Graph loads only for the selected process.
- Manual refresh keeps the detail rail mounted.
- Empty graph and no-edges graph are non-fatal states.
- Related-event and lead-post links navigate to confirmed detail routes.

### Keyword graph

- Search is explicit-submit even though filters are kept in the URL.
- Seed set is derived from selected search results.
- Build action is disabled until at least one post is selected.
- Report generation is disabled until at least one post is selected.

## Detail Rules

### Post detail

- Full-page detail layout with main rail and side rail.
- Main rail: comments block, comments async indicator, links block.
- Side rail: report block, report async indicator.
- Viewer sees the content but no mutation buttons.
- Comments/report secondary block failures do not replace the entire page.

### Event detail

- Full-page detail layout.
- Reuses `EventGraphPanel` and `EventDetailPanel` from the dashboard module.
- Back action uses browser history when possible, otherwise falls back to `/dashboard/events`.
- Root post link is shown only when confirmed by the mapped payload.

### Process detail

- Full-page detail layout.
- Reuses `ProcessGraphPanel` and `ProcessDetailPanel` from the dashboard module.
- Back action uses browser history when possible, otherwise falls back to `/dashboard/processes`.
- Related event/post context links are shown only when confirmed by the mapped payload.

## Async Action Rules

### Shared job pattern

- Async actions submit the confirmed mutation endpoint.
- UI stores the returned `job_id`.
- Polling continues until a terminal state is reached.
- Terminal result is fetched from the confirmed job-result endpoint where available.
- Relevant queries are invalidated after success.
- Existing screen content remains visible while the job is pending or fails.

### Current async surfaces

- post comments refresh
- post report generation/update
- event draft report generation/update
- process draft report generation/update
- post reports batch generation by filter
- jobs retry actions

## Partial / Warning Rules

- `partial=true` never blocks the workspace.
- `warnings[]` are rendered in a shared system alert area.
- `generated_at` stays visible even when partial warnings are present.
- Partial dashboards are usable degraded screens, not error screens.

## Permission Behavior Rules

- Viewer never sees mutation buttons.
- Analyst can generate reports and refresh comments where the route allows it.
- Analyst can open `/settings` in read-only mode only.
- Unauthorized direct route entry resolves to forbidden state.
- Unauthorized navigation items are hidden from role-aware navigation.

## Browser State Rules

- Query string is the durable source for dashboard/report filter state.
- Dashboard mode switch preserves only target-supported shared filters.
- Direct route load must reconstruct screen state from URL and backend data only.
