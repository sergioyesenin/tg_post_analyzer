# Frontend Gap Backlog

Source of truth: `docs/frontend_handoff_checklist.md`.
Updated: 2026-03-16.

## Converted Tasks

### Closed in this pass

1. Create a route map artifact for all implemented frontend routes and role visibility.
2. Create an interaction-rules artifact for dashboard, details, graph, filters, and async actions.
3. Create an API-to-UI mapping artifact for shared dashboard, detail, graph, and job fields.
4. Create a state/status matrix artifact covering shared UI states and status badges.
5. Create a copy-rules artifact so copy stops living only in components and i18n files.
6. Update audit and README remaining gaps after the new handoff artifacts are added.

### Still open after this pass

1. Migrate shared table layer to `MUI` + `MUI X DataGrid`.
2. Migrate graph layer to `React Flow`.
3. Add optional specialized monitor tabs if they become required by scope.
4. Add wireframes / hi-fi mocks / clickable prototype if design deliverables are expected inside the repo.

## Recommended Execution Order

1. Documentation handoff artifacts.
2. Shared UI stack migration planning.
3. Shared table migration.
4. Shared graph migration.
5. Optional monitor decomposition.
