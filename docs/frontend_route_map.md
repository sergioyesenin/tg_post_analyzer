# Frontend Route Map

Source of truth: `docs/frontend_handoff_checklist.md`.
Implementation source: frontend router, route policy, and route modules in `frontend/src`.
Updated: 2026-03-16.

## Route Inventory

| Route | Module | Purpose | Roles | Access mode |
| --- | --- | --- | --- | --- |
| `/login` | auth | Local sign-in | guest only | public |
| `/dashboard/posts` | workspace/posts | Top-post analytics dashboard | admin, analyst, viewer | viewer read-only |
| `/dashboard/events` | workspace/events | Event analytics dashboard | admin, analyst, viewer | viewer read-only |
| `/dashboard/processes` | workspace/processes | Process analytics dashboard | admin, analyst, viewer | viewer read-only |
| `/posts/:postId` | workspace/post-detail | Post detail, comments, links, report | admin, analyst, viewer | viewer read-only |
| `/events/:eventId` | workspace/event-detail | Event detail and graph | admin, analyst, viewer | viewer read-only |
| `/processes/:processId` | workspace/process-detail | Process detail and graph | admin, analyst, viewer | viewer read-only |
| `/reports/posts` | reports | Post reports catalog | admin, analyst, viewer | viewer read-only |
| `/reports/events` | reports | Event reports catalog | admin, analyst, viewer | viewer read-only |
| `/reports/processes` | reports | Process reports catalog | admin, analyst, viewer | viewer read-only |
| `/channels` | admin/channels | Channels management | admin | read-write |
| `/users` | admin/users | Users management | admin | read-write |
| `/settings` | admin/settings | Settings and effective settings | admin, analyst | analyst read-only |
| `/monitor` | platform/monitor | Monitoring overview | admin | read-only |
| `/jobs` | platform/jobs | Jobs queue inspection and retry | admin | read-write |
| `/keyword-graph` | keyword-graph | Keyword search/build/report workspace | admin, analyst | read-write |

## Shell Layout Rules

### Public shell

- `/login` renders outside the authenticated application shell.
- Authenticated users attempting to open `/login` are redirected to `/dashboard/posts`.

### Protected shell

- All protected routes render inside one `AppShell`.
- `AppShell` contains top navigation, session state, and role-aware navigation groups.
- `/` redirects to `/dashboard/posts`.

### Workspace layout

- `/dashboard/*` routes render inside `AnalyticsWorkspaceLayout`.
- Workspace layout owns dashboard mode switcher and shared dashboard framing.
- Posts, Events, and Processes reuse the same shell pattern:
  system alerts -> hero -> generated_at -> summary -> filters -> content rail(s).

### Detail layout

- `/posts/:postId` renders as a full-page split detail view.
- `/events/:eventId` renders as a full-page detail view reusing event graph/detail components from the dashboard rail.
- `/processes/:processId` renders as a full-page detail view reusing process graph/detail components from the dashboard rail.

### Reports/admin/platform layout

- Reports, admin, monitor, jobs, and keyword graph stay outside dashboard mode switcher.
- Each of these routes still uses the protected shell and centralized RBAC policy.

## Navigation Model

### Dashboard navigation section

- Posts
- Events
- Processes

### Primary navigation section

- Reports
- Keyword graph

### Secondary navigation section

- Settings
- Channels
- Users
- Monitor
- Jobs

Navigation visibility is computed from the same route policy used for direct route protection.

## Route Guards

- `AuthGuard` protects the whole authenticated shell.
- `RoleGuard` is used on role-restricted routes.
- Unauthorized protected access resolves to a forbidden screen, not to an implicit redirect.
- Guest access to protected routes resolves to redirect-to-login.

## Route-Level RBAC Matrix

| Route family | admin | analyst | viewer |
| --- | --- | --- | --- |
| dashboard/posts | visible, writable | visible, writable | visible, read-only |
| dashboard/events | visible, writable | visible, writable | visible, read-only |
| dashboard/processes | visible, writable | visible, writable | visible, read-only |
| post/event/process details | visible, writable | visible, writable | visible, read-only |
| reports catalogs | visible, writable | visible, writable | visible, read-only |
| keyword graph | visible, writable | visible, writable | forbidden |
| settings | visible, writable | visible, read-only | forbidden |
| channels | visible, writable | forbidden | forbidden |
| users | visible, writable | forbidden | forbidden |
| monitor | visible, read-only | forbidden | forbidden |
| jobs | visible, writable | forbidden | forbidden |

## Back Navigation Rules

- Event and process detail pages prefer browser back if the page was reached from inside the app.
- If opened directly, event detail falls back to `/dashboard/events`.
- If opened directly, process detail falls back to `/dashboard/processes`.
- Post detail provides an explicit link back to `/dashboard/posts`.
