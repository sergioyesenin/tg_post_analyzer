# Матрица состояний и статусов фронтенда

Источник истины: `docs/frontend_handoff_checklist.md`.
Источник реализации: общие UI state-компоненты, status badge-и, route modules и tests.
Обновлено: 2026-03-16.

## Общие route / block состояния

| Состояние | Значение | Общий UI-паттерн |
| --- | --- | --- |
| `loading` | первый fetch выполняется | `LoadingState` или inline loading block |
| `refreshing` | выполняется refetch при уже существующем контенте | inline loading indicator / fetching graph state |
| `empty` | запрос успешен, но контента нет | `EmptyState` |
| `error` | общая ошибка запроса | `ErrorState` |
| `forbidden` | аутентифицированному пользователю запрещен доступ или бэкенд вернул `403` | `ForbiddenState` |
| `partial` | экран пригоден к работе, но неполностью обогащен | `DashboardSystemAlerts` + `PartialDataNotice` |
| `warning` | неблокирующие warning-items от бэкенда | `DashboardWarningsBanner` |
| `stale` | предыдущий snapshot все еще виден во время refresh | существующий контент остается видимым, пока query refetch-ится |
| `no selection` | в graph/detail rail ничего не выбрано | placeholder-состояние для graph/detail |
| `no graph edges` | граф загружен, но relation edges отсутствуют | нефатальное empty/no-edges состояние графа |
| `action in progress` | выполняется async mutation | pending/running state в `AsyncActionIndicator` |
| `action success` | async mutation успешно завершился | success state в `AsyncActionIndicator` + invalidation |
| `action failed` | async mutation завершился ошибкой | failure state в `AsyncActionIndicator` без сброса уже загруженного контента |

## Матрица экранов

| Экран | Обязательные реализованные состояния |
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

## Системы статусов

### `report_status`

| Backend status | Поведение label | UI-назначение |
| --- | --- | --- |
| `missing` | отчета еще нет | `ReportStatusBadge` |
| `pending` | job по отчету поставлен в очередь или выполняется | `ReportStatusBadge` |
| `draft` | draft существует | `ReportStatusBadge` |
| `ready` | доступен финальный/готовый отчет | `ReportStatusBadge` |
| `failed` | генерация отчета завершилась ошибкой | `ReportStatusBadge` |
| неизвестное значение | fallback badge | fallback metadata в `ReportStatusBadge` |

### `job_status`

| Backend status | Поведение label | UI-назначение |
| --- | --- | --- |
| `pending` | в очереди | `JobStatusInline` / `AsyncActionIndicator` |
| `running` | обрабатывается сейчас | `JobStatusInline` / `AsyncActionIndicator` |
| `done` | успешный terminal state | `JobStatusInline` / `AsyncActionIndicator` |
| `failed` | terminal state с ошибкой | `JobStatusInline` / `AsyncActionIndicator` |
| неизвестное значение | fallback label | общий fallback для job status |

### `monitor_status`

| Backend status | Поведение label | UI-назначение |
| --- | --- | --- |
| `ok` | система здорова | `MonitorStatusBadge` |
| `warning` | warning | `MonitorStatusBadge` |
| `critical` | критическое состояние | `MonitorStatusBadge` |
| `degraded` | degraded, но частично доступное состояние | `MonitorStatusBadge` |
| backend-specific fallback | явный fallback label | fallback metadata в `MonitorStatusBadge` |

## Правила для partial / warning

- `partial=true` никогда не должен заменять контент экрана блокирующей error-card.
- `warnings[]` должны оставаться видимыми в общем banner-layer.
- `generated_at` должен оставаться видимым, когда есть partial warnings.
- Состояния partial и warning могут сосуществовать и с пустыми, и с непустыми данными; они ортогональны успешности запроса.
