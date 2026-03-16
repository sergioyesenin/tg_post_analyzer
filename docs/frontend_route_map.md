# Карта frontend-маршрутов

Источник истины: `docs/frontend_handoff_checklist.md`.
Источник реализации: frontend router, route policy и route modules в `frontend/src`.
Обновлено: 2026-03-16.

## Инвентарь маршрутов

| Маршрут | Модуль | Назначение | Роли | Режим доступа |
| --- | --- | --- | --- | --- |
| `/login` | auth | Локальный вход | только guest | public |
| `/dashboard/posts` | workspace/posts | Дашборд аналитики постов | admin, analyst, viewer | viewer read-only |
| `/dashboard/events` | workspace/events | Дашборд аналитики событий | admin, analyst, viewer | viewer read-only |
| `/dashboard/processes` | workspace/processes | Дашборд аналитики процессов | admin, analyst, viewer | viewer read-only |
| `/posts/:postId` | workspace/post-detail | Детали поста, комментарии, связи, отчет | admin, analyst, viewer | viewer read-only |
| `/events/:eventId` | workspace/event-detail | Детали события и граф | admin, analyst, viewer | viewer read-only |
| `/processes/:processId` | workspace/process-detail | Детали процесса и граф | admin, analyst, viewer | viewer read-only |
| `/reports/posts` | reports | Каталог отчетов по постам | admin, analyst, viewer | viewer read-only |
| `/reports/events` | reports | Каталог отчетов по событиям | admin, analyst, viewer | viewer read-only |
| `/reports/processes` | reports | Каталог отчетов по процессам | admin, analyst, viewer | viewer read-only |
| `/channels` | admin/channels | Управление каналами | admin | read-write |
| `/users` | admin/users | Управление пользователями | admin | read-write |
| `/settings` | admin/settings | Настройки и effective settings | admin, analyst | analyst read-only |
| `/monitor` | platform/monitor | Monitoring overview | admin | read-only |
| `/jobs` | platform/jobs | Просмотр очереди jobs и retry | admin | read-write |
| `/keyword-graph` | keyword-graph | Workspace для keyword search/build/report | admin, analyst | read-write |

## Правила layout-оболочек

### Публичная оболочка

- `/login` рендерится вне аутентифицированной application shell.
- Если аутентифицированный пользователь открывает `/login`, он редиректится на `/dashboard/posts`.

### Защищенная оболочка

- Все защищенные маршруты рендерятся внутри одного `AppShell`.
- `AppShell` содержит верхнюю навигацию, session state и role-aware navigation groups.
- `/` редиректит на `/dashboard/posts`.

### Workspace layout

- Маршруты `/dashboard/*` рендерятся внутри `AnalyticsWorkspaceLayout`.
- Workspace layout владеет переключателем dashboard modes и общей рамкой dashboard.
- Posts, Events и Processes используют один и тот же shell pattern:
  system alerts -> hero -> generated_at -> summary -> filters -> content rail(s).

### Layout деталей

- `/posts/:postId` рендерится как full-page split detail view.
- `/events/:eventId` рендерится как full-page detail view с переиспользованием event graph/detail-компонентов из dashboard rail.
- `/processes/:processId` рендерится как full-page detail view с переиспользованием process graph/detail-компонентов из dashboard rail.

### Layout reports/admin/platform

- Reports, admin, monitor, jobs и keyword graph находятся вне dashboard mode switcher.
- Все эти маршруты все равно используют общую protected shell и централизованную RBAC policy.

## Модель навигации

### Раздел навигации dashboard

- Posts
- Events
- Processes

### Основной раздел навигации

- Reports
- Keyword graph

### Вторичный раздел навигации

- Settings
- Channels
- Users
- Monitor
- Jobs

Видимость пунктов навигации вычисляется из той же route policy, что и защита прямого доступа к маршрутам.

## Route guards

- `AuthGuard` защищает всю authenticated shell.
- `RoleGuard` используется на маршрутах с role restrictions.
- Несанкционированный доступ к protected route ведет к экрану forbidden, а не к скрытому redirect.
- Доступ гостя к protected route приводит к redirect-to-login.

## Матрица route-level RBAC

| Семейство маршрутов | admin | analyst | viewer |
| --- | --- | --- | --- |
| dashboard/posts | видно, можно изменять | видно, можно изменять | видно, только чтение |
| dashboard/events | видно, можно изменять | видно, можно изменять | видно, только чтение |
| dashboard/processes | видно, можно изменять | видно, можно изменять | видно, только чтение |
| детали post/event/process | видно, можно изменять | видно, можно изменять | видно, только чтение |
| каталоги отчетов | видно, можно изменять | видно, можно изменять | видно, только чтение |
| keyword graph | видно, можно изменять | видно, можно изменять | forbidden |
| settings | видно, можно изменять | видно, только чтение | forbidden |
| channels | видно, можно изменять | forbidden | forbidden |
| users | видно, можно изменять | forbidden | forbidden |
| monitor | видно, только чтение | forbidden | forbidden |
| jobs | видно, можно изменять | forbidden | forbidden |

## Правила возврата назад

- На страницах деталей события и процесса приоритет отдается browser back, если страница была открыта изнутри приложения.
- При прямом открытии деталь события делает fallback на `/dashboard/events`.
- При прямом открытии деталь процесса делает fallback на `/dashboard/processes`.
- Деталь поста содержит явную ссылку назад на `/dashboard/posts`.
