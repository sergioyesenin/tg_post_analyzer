# Аудит frontend-спецификации

Источник истины: `docs/frontend_handoff_checklist.md`.

Дата аудита: 2026-03-16.
Область: этап `final quality pass and spec audit` для React-фронтенда в `frontend/`.

## Краткий итог

Реализованный фронтенд покрывает подтвержденный инвентарь маршрутов, dashboard modes, detail flows, модули reports/admin/monitor/jobs/keyword graph, URL-owned filters, рендеринг `generated_at`, обработку `partial/warnings` и общий async job pattern без изменения backend contract.

Текущий frontend quality gate зеленый:

- `npm test` в `frontend/`
- прошло `19` test files
- прошло `91` tests

## Добавленные handoff-артефакты

Следующие артефакты репозитория формализуют решения, которые раньше жили только в коде и тестах:

- `docs/frontend_gap_backlog.md`
- `docs/frontend_route_map.md`
- `docs/frontend_interaction_rules.md`
- `docs/frontend_api_ui_mapping.md`
- `docs/frontend_state_status_matrix.md`
- `docs/frontend_copy_rules.md`

## Матрица аудита

| Область | Результат | Примечания |
| --- | --- | --- |
| Инвентарь маршрутов | Pass | Реализованы `/login`, три dashboard-режима, три detail-route, reports, channels, users, settings, monitor, jobs и keyword graph. |
| Основные RBAC-правила | Pass | Route и action policy обеспечивают границы `admin` / `analyst` / `viewer`; viewer остается read-only и не имеет доступа к keyword graph и admin-модулям. |
| Dashboard-режимы | Pass | Posts, Events и Processes построены вокруг endpoint-ов `/api/dashboard/*` и сохраняют общее поведение alerts/filter/generated_at. |
| Detail flows | Pass | Детали поста, события и процесса реализованы с route-specific data loading и role-aware actions. |
| Async job flows | Pass | Комментарии/отчеты поста, отчет по событию, отчет по процессу и batch generation отчетов используют общий job polling pattern. |
| Модуль reports | Pass | Покрыты маршруты списков Posts / Events / Processes, export links и batch generation отчетов по постам. |
| Admin-модуль | Pass | Реализованы flows для channels, users и settings, включая analyst read-only режим в settings. |
| Monitor-модуль | Pass | `/monitor` использует только подтвержденный `GET /api/monitor/full`. |
| Jobs-модуль | Pass | Для admin реализованы summary, pending, dead-letter и retry actions. |
| Keyword graph | Pass | Реализованы search, build и report generation с route-owned filters и role guard. |
| URL filters | Pass | Dashboard и reports filters сериализуются в URL; при переключении mode сохраняются только поддерживаемые общие фильтры. |
| Partial / warnings | Pass | `partial=true` рендерится как usable degraded state; `warnings[]` рендерятся через общий system alerts layer. |
| generated_at | Pass | Все dashboard-экраны рендерят generated_at даже в partial-state. |
| DTO транспорта vs UI view model | Pass | Dashboard/detail/report modules держат DTO contracts отдельно от view-model mappers. |
| Reusable components | Pass | Общие alerts, table shell, state cards, badges, notices и async indicators переиспользуются между модулями. |
| Артефакт route map | Pass | Инвентарь маршрутов, shell rules, навигация и RBAC route matrix документированы. |
| Артефакт interaction rules | Pass | Документированы правила взаимодействия для dashboard/detail/graph/filter/async. |
| Артефакт API-to-UI mapping | Pass | Документирован общий маппинг полей. |
| Артефакт state/status matrix | Pass | Документированы общие соглашения по state и status. |
| Артефакт copy rules | Pass | Документированы общие правила для текстов. |

## Ключевое тестовое покрытие

Текущее и обновленное key-flow coverage включает:

- auth guard и refresh flow
- покрытие route inventory и RBAC matrix policy
- dashboard route shell и переключение режимов
- парсинг/сериализацию URL filters
- рендеринг generated_at во всех dashboard modes
- рендеринг partial/warnings как неблокирующего состояния
- dashboards для posts/events/processes
- detail flows для post/event/process
- поведение общего async job flow
- list/export/batch generation для reports
- admin CRUD и границы read-only/write в settings
- экраны monitor/jobs и retry flows
- flow keyword graph search/build/report

## Оставшиеся расхождения со спецификацией

Ниже — существенные незакрытые расхождения относительно `docs/frontend_handoff_checklist.md`:

1. В репозитории по-прежнему нет wireframes, hi-fi mocks и clickable prototype для реализованных frontend-модулей.
2. Реализованный UI использует framework-native tables и graph rendering boundaries вместо целевого стека `MUI`, `MUI X DataGrid` и `React Flow`, указанного в stage brief.
3. Monitor остается одним overview-route и не раскрывает дополнительные вкладки вроде health/jobs/pipeline/scheduler/alerts.

## Assumptions, использованные в аудите

- Динамические report routes `/reports/:reportType` закрывают три обязательных report-экрана из checklist-а.
- Текущая role model ограничивается `admin`, `analyst` и `viewer`; дополнительные composite roles не ожидаются.
- `generated_at` обязателен только для dashboard-экранов, а не для detail/admin/report/keyword-маршрутов.
- Repo-level handoff docs и исполняемые тесты считаются приемлемыми implementation artifact-ами для formal frontend audit pass.
- Существующие локальные изменения в keyword graph/i18n файлах являются намеренной пользовательской работой и не трогались.
