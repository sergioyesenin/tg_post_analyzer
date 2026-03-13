1. Обновленное задание для frontend-разработчика
1.1 Цель
Необходимо реализовать frontend для аналитической системы мониторинга Telegram-каналов на основе уже существующего backend API.

Frontend должен предоставлять единое аналитическое рабочее пространство с 3 переключаемыми режимами дашборда:

Posts
Events
Processes
Ключевое изменение относительно предыдущей версии требований:
теперь backend предоставляет агрегирующие dashboard endpoint’ы, поэтому каждый режим дашборда должен строиться в первую очередь на них, а не на клиентской сборке из большого числа разрозненных запросов.

1.2 Основной backend-контракт для dashboard режимов
[Подтверждено backend]

Использовать как primary source:

GET /api/dashboard/posts
GET /api/dashboard/events
GET /api/dashboard/events/{event_id}/graph
GET /api/dashboard/processes
GET /api/dashboard/processes/{process_id}/graph
Все dashboard endpoint’ы доступны ролям:

admin
analyst
viewer
Все dashboard response содержат:

mode
generated_at
partial
warnings
filters_applied
summary
items
meta
Следствие для frontend:

нужно поддержать стандартную обработку partial=true;
нужно отображать warnings[];
дашборд должен уметь работать как с полным, так и с частично обогащенным snapshot.
1.3 Роли и доступ
[Подтверждено backend]

admin
Доступ:

все dashboard режимы;
post/event/process details;
reports catalogs;
channels management;
users;
settings;
monitor;
jobs;
keyword graph.
analyst
Доступ:

все 3 режима dashboard;
карточки постов, событий, процессов;
reports catalogs;
запуск генерации отчетов;
запуск обновления комментариев;
keyword graph;
read-only effective settings.
viewer
Доступ:

read-only dashboard режимы;
detail screens;
existing reports;
без mutations;
без keyword graph.
1.4 Экранная структура приложения
1.4.1 /login
Назначение:

вход по local auth.
API:

POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET /api/auth/me
Состояния:

idle
loading
invalid credentials
service unavailable
generic error
1.4.2 /dashboard/posts
Назначение:

основной режим анализа топ-постов.
Основной API:

GET /api/dashboard/posts
Дополнительный API:

GET /api/posts/{post_id}
GET /api/posts/{post_id}/comments
POST /api/posts/{post_id}/comments/update
GET /api/reports/post/{post_id}
POST /api/reports/post/{post_id}/update
GET /api/posts/{post_id}/links
GET /api/jobs/{job_id}
GET /api/jobs/{job_id}/result
Фильтры:

date_from
date_to
limit
channel_ids
categories
min_comments
report_status
sort_by
sort_order
Поддерживаемые сортировки:

comments_count
date
views
involvement
Экран должен содержать:

filter bar;
KPI summary из summary;
таблицу/список постов из items;
индикацию report_status;
переход в detail view;
отображение warnings, если partial=true.
1.4.3 /dashboard/events
Назначение:

режим анализа событий.
Основной API:

GET /api/dashboard/events
Graph API:

GET /api/dashboard/events/{event_id}/graph
Дополнительный API:

POST /api/reports/events/{event_id}/update
GET /api/jobs/{job_id}/result
Фильтры:

date_from
date_to
limit
status
channel_ids
categories
min_comments
sort_by
sort_order
Поддерживаемые сортировки:

started_at
comments_count
involvement
posts_count
Экран должен содержать:

список/таблицу событий;
KPI summary;
область графа;
панель деталей выбранного события;
список связанных постов;
статус event report;
action для запуска/обновления draft report;
обработку partial/warnings.
1.4.4 /dashboard/processes
Назначение:

режим анализа процессов.
Основной API:

GET /api/dashboard/processes
Graph API:

GET /api/dashboard/processes/{process_id}/graph
Дополнительный API:

POST /api/reports/processes/{process_id}/update
GET /api/jobs/{job_id}/result
Фильтры:

date_from
date_to
limit
status
min_comments
sort_by
sort_order
Поддерживаемые сортировки:

started_at
comments_count
involvement
events_count
Экран должен содержать:

список процессов;
KPI summary;
граф;
панель деталей процесса;
список связанных событий;
переходы к event/post context;
статус process report;
обработку partial/warnings.
1.4.5 Detail screens
/posts/:postId
API:

GET /api/posts/{id}
GET /api/posts/{id}/comments
GET /api/reports/post/{id}
GET /api/posts/{id}/links
Действия:

refresh comments
generate/update report
/events/:eventId
API:

GET /api/events/{id}
при необходимости graph payload уже брать из dashboard graph endpoint
/processes/:processId
API:

GET /api/processes/{id}
graph payload брать из dashboard graph endpoint
1.4.6 Reports
/reports/posts
/reports/events
/reports/processes
API:

GET /api/reports/posts/list
GET /api/reports/posts/export
GET /api/reports/events/list
GET /api/reports/events/export
GET /api/reports/processes/list
GET /api/reports/processes/export
POST /api/reports/posts/generate-by-filter
1.4.7 Admin screens
/channels
GET /api/channels/
POST /api/channels/add
PATCH /api/channels/{id}
PUT /api/channels/{id}/active
DELETE /api/channels/{id}
/users
GET /api/auth/users
POST /api/auth/users
PUT /api/auth/users/{id}/roles
PUT /api/auth/users/{id}/active
/settings
GET /api/settings/effective
GET /api/settings/
PUT /api/settings/{key}
/monitor
GET /api/monitor/full
при необходимости specialized tabs через health/jobs/pipeline/scheduler/alerts
/jobs
GET /api/jobs/summary
GET /api/jobs/pending
GET /api/jobs/dead-letter
retry actions
1.4.8 /keyword-graph
Использовать как отдельный advanced-инструмент поиска и анализа по ключевым словам.

API:

POST /api/keyword/search/posts
POST /api/keyword/graph/build
POST /api/keyword/graph/report
1.5 Требования к frontend data layer
Нужно строить frontend так, чтобы dashboard режимы были основаны на schemas.dashboard как на основном контракте.

Обязательные frontend модели
PostsDashboardResponse
EventsDashboardResponse
ProcessesDashboardResponse
EventGraphResponse
ProcessGraphResponse
Дополнительно
transport DTO и UI view model разделять;
поддержать единый тип для warnings;
поддержать единый тип для partial dashboard state.
1.6 Бизнес-правила UI
[Подтверждено backend + обязательны к реализации]

все dashboard screens должны отображать generated_at;
при partial=true экран не считается ошибочным, а считается частично доступным;
warnings[] отображаются в виде системного предупреждающего блока;
event/process report status может быть draft;
dashboard filters должны сериализоваться в URL;
graph screen должен открываться без дополнительных цепочек из 5-10 запросов;
viewer не должен видеть mutation actions;
comments thread fields backend уже хранит, поэтому компонент комментариев нужно проектировать с запасом на thread mode;
reactions/media в scope не включать;
поиск по постам как отдельная аналитическая функция строится через keyword graph API.
1.7 Рекомендуемая техническая реализация
Стек:

React
TypeScript
Vite
React Router
TanStack Query
MUI + MUI X DataGrid
React Hook Form
Zod
graph layer: React Flow или Cytoscape.js
Архитектура:

один AnalyticsWorkspaceLayout
mode switcher: Posts / Events / Processes
каждый режим как отдельный dashboard module
details, reports, admin, settings, monitor как отдельные route modules
1.8 Reusable UI-компоненты
Нужно предусмотреть:

DashboardModeSwitcher
DashboardWarningsBanner
DashboardSummaryCards
DashboardFilterBar
DashboardTable
GraphPanel
DetailsDrawer
ReportStatusBadge
JobStatusInline
PartialDataNotice
EmptyState
ErrorState
ForbiddenState
1.9 Async operations
Все async actions реализовать через единый job flow:

mutation endpoint;
получение job_id;
polling GET /api/jobs/{id}/result;
invalidation relevant queries;
отображение финального результата.
Это обязательно для:

refresh comments;
post report generation;
event report generation;
process report generation;
batch report generation.
1.10 Testing
Минимально покрыть:

auth guard и refresh flow;
role-based routing;
dashboard query parsing;
partial/warnings rendering;
async job flow;
empty/error/loading states;
graph screen state transitions.
1.11 Definition of Done
Frontend-задача считается выполненной, если:

реализован единый shell приложения;
реализованы 3 режима дашборда на основе /api/dashboard/*;
реализованы event/process graph views;
partial data и warnings корректно отображаются;
RBAC соблюден;
detail и async flows работают;
admin screens работают в подтвержденном backend scope;
keyword graph интегрирован как отдельный инструмент;
UI не опирается на неподтвержденные backend-возможности.


## 2. задание для UI-дизайнера
2.1 Цель дизайна
Необходимо спроектировать внутренний аналитический web-интерфейс для системы мониторинга Telegram-каналов.

Ключевой сценарий продукта:
пользователь работает в едином аналитическом workspace и переключается между 3 режимами:

Posts
Events
Processes
Теперь backend уже предоставляет агрегированные dashboard endpoint’ы, поэтому экраны можно проектировать как полноценные mode-based аналитические панели, а не как хрупкую композицию большого числа независимых источников данных.

2.2 Характер интерфейса
Интерфейс должен быть:

строгим;
профессиональным;
аналитическим;
data-heavy;
минималистичным;
ориентированным на длительную работу с таблицами, фильтрами, статусами и графами.
Приоритеты:

читаемость данных;
ясная иерархия;
быстрый переход от summary к detail;
понятные статусы;
удобная работа с графом.
2.3 Общие принципы дизайна
Нужно проектировать desktop-first интерфейс.

Основной паттерн:

единый workspace layout;
в верхней части mode switcher;
внутри режима:
filter bar,
summary/KPI,
основной список,
граф или detail area,
action zone.
Обязательно предусмотреть состояния:

loading
empty
error
forbidden
partial data
warnings from backend
Так как dashboard API возвращает partial и warnings, дизайнер должен отдельно продумать:

как выглядит экран, если данные загружены не полностью;
как выглядит системное предупреждение, не блокирующее работу пользователя.
2.4 Экраны для проработки
1. Login
Нужно спроектировать:

форму входа;
ошибки логина;
loading state.
2. Main Analytics Workspace
Общий layout для всего аналитического интерфейса:

top navigation;
role-aware navigation;
mode switcher Posts / Events / Processes;
общая структура фильтров и области данных.
3. Dashboard Mode: Posts
Экран должен включать:

filters;
KPI summary;
список/таблицу постов;
статус отчета;
quick actions;
переход в карточку поста;
системные warnings и partial state.
4. Dashboard Mode: Events
Экран должен включать:

filters;
KPI summary;
список событий;
graph area;
detail panel выбранного события;
связанные посты;
статус draft report;
warnings / partial state.
5. Dashboard Mode: Processes
Экран должен включать:

filters;
KPI summary;
список процессов;
graph area;
detail panel процесса;
связанные события;
статус draft report;
warnings / partial state.
6. Post Detail
header поста;
текст;
комментарии;
links;
report panel;
async action states.
7. Reports Catalogs
posts reports
events reports
processes reports
8. Channels Management
9. Users
10. Settings
11. Monitor
12. Keyword Graph
2.5 Что дизайнер должен выдать по каждому экрану
Для каждого экрана требуется:

цель экрана;
состав блоков;
порядок блоков;
иерархия информации;
desktop layout;
поведение интерактивных элементов;
состояние фильтров;
состояние таблиц;
состояние графа;
loading/empty/error/forbidden/partial states;
responsive notes.
2.6 Особые требования для 3 режимов дашборда
Режим Posts
Нужно продумать:

плотную таблицу/список постов;
как показывать report_status;
как визуально отделить preview, метрики и действия;
как показывать warnings, не ломая обзорность.
Режим Events
Нужно продумать:

комбинацию list + graph + detail;
как пользователь выбирает событие;
как показывается root context события;
как отображаются связанные посты;
как показывать draft статус отчета.
Режим Processes
Нужно продумать:

как показывать процесс как сущность более высокого уровня;
как отличать process view от event view;
как показывать вложенные события и их связь;
как строится графическая иерархия.
2.7 Отдельно продумать паттерны
1. Mode switcher
Нужно определить:

tab style или segmented control;
как показывать активный режим;
как выглядит переключение между режимами.
2. Warnings / Partial Data
Так как backend отдает:

partial: boolean
warnings: []
нужно продумать:

предупреждающий banner;
его место на экране;
как он выглядит, если warnings несколько;
как пользователь понимает, что экран usable, но не полностью обогащен.
3. Status system
Нужно единообразно оформить статусы:

report: missing, pending, draft, ready, failed
jobs: pending, running, done, failed
monitor: ok, warning, critical, degraded
4. Graph interaction patterns
Для событий и процессов нужно описать:

node selection;
edge highlighting;
legend;
zoom / pan controls;
toolbar;
empty graph state;
no edges state.
5. Detail panel
Нужно определить:

right drawer или embedded side panel;
какие блоки всегда видны;
какие через tabs;
как показываются comments/report/links.
2.8 Общие требования к стилю
Нужно:

не делать интерфейс “маркетинговым”;
не перегружать декоративностью;
использовать визуальный язык enterprise analytics;
делать акцент на таблицы, карточки summary, статусы и граф;
сохранить высокую плотность данных без визуального хаоса.
Тема:

светлая тема обязательна;
темная тема может быть предусмотрена как optional future extension.
2.9 Что отдельно не включать в текущий дизайн scope
На текущем этапе не нужно проектировать как обязательные функциональные зоны:

AD/LDAP flows;
push notifications;
reactions analytics;
media links;
расширенный business monitoring beyond current backend;
финальные rich event/process reports, если их контент еще не согласован.
2.10 Итоговые артефакты от дизайнера
Дизайнер должен подготовить:

перечень всех экранов;
референсы по каждому экрану;
подробное текстовое описание экранов;
layout rules;
typography / spacing / grid rules;
status rules;
table rules;
graph rules;
detail panel rules;
component inventory;
список спорных мест, которые нужно согласовать до handoff.
2.11 Definition of Done для дизайн-задачи
Задача считается выполненной, если:

спроектирован единый workspace;
проработаны 3 dashboard режима;
продуман UX для partial/warnings;
проработаны graph screens для events/processes;
описаны states и interaction rules;
подготовлен handoff без двусмысленностей для frontend-разработчика.




3. Implementation backlog after stage 1

Ниже зафиксирован не просто список "хвостов", а приоритизированный backlog для следующих этапов.
Его цель: убрать двусмысленность при дальнейшей реализации frontend и не позволять следующему проходу Codex/разработчика додумывать приоритеты самостоятельно.

Общие правила интерпретации:

- `P0` означает обязательный ближайший scope. Без закрытия этих пунктов frontend нельзя считать готовым к реальной аналитической эксплуатации.
- `P1` означает важный следующий слой качества и UX, но не блокирующий немедленное продолжение разработки dashboard-модулей.
- `P2` означает улучшения надежности, процесса или polish, которые не должны подменять собой работу над основным продуктовым контуром.
- Если возникает конфликт между "сделать красиво" и "закрыть P0", приоритет всегда у `P0`.
- Если какой-либо пункт требует недостающего UX handoff, это должно фиксироваться явно как внешний blocker, а не заполняться предположениями на frontend.

3.1 P0 — ближайшие обязательные задачи

Эти пункты должны идти следующими этапами реализации.
Их нельзя откладывать "на потом" без прямого решения, потому что они влияют на основной полезный сценарий продукта: работу с dashboard, permissions и async flows.

P0.1 Dashboard data layer и backend integration

Что отсутствует сейчас:

- нет реальных dashboard query hooks
- нет DTO/view-model mapping
- нет фактической интеграции с `/api/dashboard/*`

Почему это `P0`:

- current frontend shell без этого не дает аналитической ценности;
- основной backend-контракт уже подтвержден и именно он объявлен source of truth для dashboard mode screens;
- без явного transport -> UI mapping высок риск хаотичной привязки интерфейса к raw backend response.

Что считать закрытием:

- отдельные query hooks для `posts/events/processes`;
- transport DTO и UI view model разделены;
- используется единый dashboard envelope contract;
- `partial`, `warnings`, `generated_at`, `summary`, `items`, `meta` реально проходят через UI data flow, а не только существуют в типах.

P0.2 Основные dashboard UI-модули

Что отсутствует сейчас:

- нет `filter bar`
- нет `summary cards`
- нет table specs и реальных dashboard tables
- нет graph panels
- нет detail screens
- нет async job flow

Почему это `P0`:

- это и есть основной пользовательский сценарий из разделов `/dashboard/posts`, `/dashboard/events`, `/dashboard/processes`;
- Definition of Done прямо требует рабочие dashboard-режимы, graph views, detail flows и async operations;
- без этого приложение остается только каркасом.

Что считать закрытием:

- `Posts`, `Events`, `Processes` работают против реальных API;
- фильтры сериализуются в URL;
- summary/table/graph/detail построены по spec;
- async actions работают по job flow: mutation -> `job_id` -> polling -> invalidate -> final state.

P0.3 RBAC уровня действий и mutations

Что отсутствует сейчас:

- нет `action-level RBAC matrix`
- нет `mutation-level RBAC`, пока есть только `route/navigation-level`

Почему это `P0`:

- route guard сам по себе недостаточен для enterprise analytics UI;
- viewer по spec не должен видеть mutation actions;
- analyst/admin-различия должны определяться не только на уровне доступа к маршруту, но и на уровне кнопок, mutation entry points и action zones.

Что считать закрытием:

- зафиксирована матрица доступов по ролям для route/action/mutation;
- hidden/disabled/read-only/forbidden разделены явно;
- mutation controls рендерятся строго в соответствии с ролью;
- policy не размазана по компонентам ad hoc, а собрана в одном прозрачном слое.

P0.4 Auth error taxonomy

Что отсутствует сейчас:

- error taxonomy для auth пока минимальная и покрывает только базовые login states;
- нет согласованного правила для дальнейших auth edge cases beyond stage 1.

Почему это `P0`:

- auth уже подключен к app bootstrap и влияет на вход в рабочее пространство;
- дальнейшая интеграция dashboard/data layer потребует предсказуемого поведения при `401/403/503/network`.

Что считать закрытием:

- зафиксированы и реализованы правила для `invalid credentials`, `service unavailable`, `expired session`, `refresh failed`, `forbidden`, `generic network error`;
- одинаковая трактовка этих состояний используется в login/bootstrap/protected data queries.

3.2 P1 — следующий слой качества и UX

Эти пункты важны и должны идти сразу после `P0`, но не должны задерживать старт реальной dashboard-интеграции.

P1.1 Auth UX maturation

Что относится сюда:

- нет proactive refresh timer и expiry-aware UX, есть только lazy refresh on `401`
- logout без confirm/dialog pattern
- нет полноценного login validation/copy matrix из handoff

Почему это `P1`, а не `P0`:

- текущий auth flow уже работоспособен;
- эти задачи повышают качество и предсказуемость UX, но не являются blocker для внедрения реальных dashboard-модулей.

Что считать закрытием:

- session expiry обрабатывается не только реактивно, но и предсказуемо для пользователя;
- logout flow согласован по UX;
- login copy, validation messages и edge states соответствуют handoff.

P1.2 Status/copy/handoff formalization

Что отсутствует сейчас:

- нет `copy rules`
- нет `status matrix`
- нет UI/UX handoff artifacts из большого checklist

Почему это `P1`:

- это важно для последовательной реализации крупных data-heavy экранов;
- но при отсутствии полного handoff frontend не должен "додумывать", а должен фиксировать blockers и двигаться только в согласованной зоне.

Что считать закрытием:

- есть status matrix для `report`, `job`, `monitor`;
- есть copy rules для empty/error/forbidden/partial/retry;
- есть минимальный handoff package, достаточный для реализации без произвольной интерпретации.

3.3 P2 — улучшения надежности и процесса

Эти задачи полезны, но их нельзя ставить выше `P0/P1`.

P2.1 Session sync across tabs

Что отсутствует сейчас:

- нет `cross-tab session sync`

Почему это `P2`:

- это улучшение поведения в multi-tab сценарии;
- отсутствие этой функции не мешает одному пользователю работать в одном окне и не блокирует основную dashboard delivery.

Что считать закрытием:

- login/logout/token rotation синхронизируются между вкладками без ручного reload.

P2.2 Real frontend auth integration tests against live backend

Что отсутствует сейчас:

- нет real auth integration tests against live backend, только frontend-level mocks + client refresh test

Почему это `P2`:

- backend auth API уже покрыт backend tests;
- frontend smoke/integration against real API полезны, но не являются ближайшим blocker при наличии зеленых unit/integration tests в frontend.

Что считать закрытием:

- есть отдельный test layer, который гоняет login/refresh/logout/me against real backend contract в среде frontend.

3.4 Что не должен делать следующий Codex без явного основания

- Не понижать `P0`-задачи в приоритете ради polish-задач из `P1/P2`.
- Не трактовать отсутствие handoff как разрешение "придумать UX самостоятельно".
- Не считать stage 1 auth implementation достаточным основанием, чтобы отложить RBAC/action permissions.
- Не заменять dashboard integration моками или placeholder UI там, где по плану уже должен появляться реальный data flow.

3.5 Рекомендуемый порядок следующих этапов

1. `P0.1` Dashboard data layer и интеграция с `/api/dashboard/*`
2. `P0.2` Реальные dashboard экраны: filters, summary, table, graph, details, async job flow
3. `P0.3` RBAC/action/mutation policy
4. `P0.4` Auth error taxonomy stabilization
5. `P1.1` Auth UX maturation
6. `P1.2` Status/copy/handoff formalization
7. `P2.1` Cross-tab session sync
8. `P2.2` Live auth integration tests

Реализуй этап 14: final quality pass and spec audit.

Source of truth: docs/frontend_handoff_checklist.md.

Нужно:
- провести audit реализованного frontend against spec
- проверить все routes
- проверить все major RBAC rules
- проверить all dashboard modes
- проверить details flows
- проверить async job flows
- проверить reports/admin/monitor/jobs/keyword graph
- проверить URL filters
- проверить partial/warnings
- проверить generated_at
- проверить tests и добавить missing key flow tests
- привести README в финальный вид

README должен содержать:
- overview
- tech stack
- project structure
- architecture decisions
- routing model
- auth/session model
- data layer model
- dashboard model
- graph model
- RBAC model
- async job flow
- testing strategy
- known limitations
- remaining gaps относительно spec

В финале выдай:
1. список реализованных модулей
2. список key flow tests
3. remaining gaps относительно spec
4. список assumptions
5. список технического долга
6. рекомендуемый следующий этап
7. финальный commit message
