# задание для frontend-разработчика

## 1.1 Цель

Необходимо реализовать frontend для аналитической системы мониторинга Telegram-каналов на основе уже существующего backend API.

Frontend должен предоставлять единое аналитическое рабочее пространство с 3 переключаемыми режимами дашборда:

Posts  
Events  
Processes

Ключевое изменение относительно предыдущей версии требований:  
теперь backend предоставляет агрегирующие dashboard endpoint’ы, поэтому каждый режим дашборда должен строиться в первую очередь на них, а не на клиентской сборке из большого числа разрозненных запросов.

## 1.2 Основной backend-контракт для dashboard режимов

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

## 1.3 Роли и доступ

[Подтверждено backend]

### admin  
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

### analyst  
Доступ:

все 3 режима dashboard;  
карточки постов, событий, процессов;  
reports catalogs;  
запуск генерации отчетов;  
запуск обновления комментариев;  
keyword graph;  
read-only effective settings.

### viewer  
Доступ:

read-only dashboard режимы;  
detail screens;  
existing reports;  
без mutations;  
без keyword graph.

## 1.4 Экранная структура приложения

### 1.4.1 /login  
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

### 1.4.2 /dashboard/posts  
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

### 1.4.3 /dashboard/events  
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

### 1.4.4 /dashboard/processes  
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

### 1.4.5 Detail screens  
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

### 1.4.6 Reports  
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

### 1.4.7 Admin screens  
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

### 1.4.8 /keyword-graph  
Использовать как отдельный advanced-инструмент поиска и анализа по ключевым словам.

API:

POST /api/keyword/search/posts  
POST /api/keyword/graph/build  
POST /api/keyword/graph/report

## 1.5 Требования к frontend data layer

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

## 1.6 Бизнес-правила UI

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

## 1.7 Рекомендуемая техническая реализация

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

## 1.8 Reusable UI-компоненты

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

## 1.9 Async operations

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

## 1.10 Testing

Минимально покрыть:

auth guard и refresh flow;  
role-based routing;  
dashboard query parsing;  
partial/warnings rendering;  
async job flow;  
empty/error/loading states;  
graph screen state transitions.

## 1.11 Definition of Done

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

---

## 1.12 Handoff checklist для UI/UX + frontend

Ниже — обязательный handoff checklist, который должен считаться частью frontend-задачи.  
Его цель — убрать все зоны, где frontend-разработчику пришлось бы самостоятельно додумывать UX, layout, interaction rules или трактовку backend response.

### 1.12.1 Общий принцип

Frontend должен реализовываться не только по списку API и экранов, но и по формализованному handoff-пакету от UI/UX.  
Если какой-либо пункт ниже не зафиксирован в дизайне или спецификации, он должен считаться **требующим согласования**, а не предметом свободной интерпретации на frontend.

---

### 1.12.2 Обязательные артефакты handoff от UI/UX

#### A. Screen inventory
Должен существовать финальный список экранов и route-level сущностей:

- login
- dashboard/posts
- dashboard/events
- dashboard/processes
- posts detail
- events detail
- processes detail
- reports/posts
- reports/events
- reports/processes
- channels
- users
- settings
- monitor
- jobs
- keyword graph

Для каждого экрана должны быть определены:

- цель экрана;
- обязательные блоки;
- порядок блоков;
- primary action;
- secondary actions;
- states;
- role visibility.

#### B. Route map / navigation map
Должна существовать точная карта маршрутов и навигации.

Нужно зафиксировать:

- все route path;
- какие экраны открываются как full page;
- какие сущности открываются как detail screen;
- где используется drawer/panel;
- какие query params поддерживаются;
- какие фильтры сериализуются в URL;
- что сохраняется при переходе между режимами;
- что сбрасывается при переходе между разделами.

Минимально должны быть зафиксированы:

- `/login`
- `/dashboard/posts`
- `/dashboard/events`
- `/dashboard/processes`
- `/posts/:postId`
- `/events/:eventId`
- `/processes/:processId`
- `/reports/posts`
- `/reports/events`
- `/reports/processes`
- `/channels`
- `/users`
- `/settings`
- `/monitor`
- `/jobs`
- `/keyword-graph`

#### C. Layout specification
Должны быть определены правила layout на desktop-first сценарий.

Нужно зафиксировать:

- минимальную поддерживаемую ширину;
- target width;
- grid system;
- высоту top nav;
- высоту mode switcher;
- высоту filter bar;
- правила spacing;
- split proportions для table / graph / detail;
- sticky zones;
- scroll containers;
- responsive degradation rules.

Минимально должны быть согласованы:

- workspace desktop-first;
- dashboard как единый shell;
- filter bar над summary;
- summary над основной рабочей областью;
- основная рабочая область для Events / Processes включает list + graph + details;
- detail panel не ломает layout и не уводит пользователя на другой экран без явной причины.

#### D. Design tokens
Должны быть переданы точные design tokens, а не только визуальные референсы.

Нужно зафиксировать:

- color palette;
- text colors;
- border colors;
- status colors;
- spacing scale;
- typography scale;
- radius;
- shadows;
- control heights;
- table row heights;
- icon sizes.

Минимальный набор токенов должен покрывать:

- background / surface / elevated surface
- text primary / secondary / muted
- border subtle / strong
- accent primary
- success / warning / danger / info
- page title / section title / body / caption / KPI number
- spacing 4 / 8 / 12 / 16 / 20 / 24 / 32
- row heights и panel paddings

#### E. Component inventory
Должен существовать список reusable UI-компонентов, которые frontend реализует как системные, а не ad hoc по месту.

Обязательный минимум:

- AppShell
- TopNavigation
- RoleAwareNavigation
- DashboardModeSwitcher
- DashboardFilterBar
- DashboardWarningsBanner
- PartialDataNotice
- DashboardSummaryCards
- DashboardTable
- ReportStatusBadge
- JobStatusInline
- GraphPanel
- GraphToolbar
- GraphLegend
- DetailsDrawer / DetailsPanel
- CommentsBlock
- LinksBlock
- ReportBlock
- EmptyState
- ErrorState
- ForbiddenState
- LoadingSkeleton
- AsyncActionIndicator
- ConfirmationModal
- Toast / InlineMessage

Для каждого компонента должны быть понятны:

- props contract;
- loading state;
- empty state;
- error state;
- permission behavior;
- responsive behavior.

---

### 1.12.3 Спецификации, без которых frontend не должен “додумывать”

#### F. Table specification
Для каждой таблицы должны быть явно описаны:

- состав колонок;
- порядок колонок;
- тип колонки;
- сортируемость;
- ширина/минимальная ширина;
- выравнивание;
- truncate / wrap;
- hover behavior;
- row click behavior;
- checkbox selection behavior;
- inline actions;
- empty cell behavior;
- sticky columns;
- pagination / virtualization / infinite scroll.

Минимально отдельно должны быть описаны:

- Posts table
- Events table
- Processes table
- Reports tables
- Channels table
- Users table
- Jobs tables

Дополнительно для dashboard tables должны быть определены:

- как показывается report_status;
- как показывается partial-affected row, если применимо;
- как показываются warnings indicators;
- как отделяются preview, metrics и actions.

#### G. Status system
Должна быть единая матрица статусов.

Обязательно должны быть описаны:

##### report_status
- missing
- pending
- draft
- ready
- failed

##### job_status
- pending
- running
- done
- failed

##### monitor_status
- ok
- warning
- critical
- degraded

Для каждого статуса нужно определить:

- label;
- цвет;
- icon;
- badge style;
- compact table representation;
- expanded details representation;
- tooltip behavior;
- fallback for unknown value.

#### H. Partial data / warnings specification
Так как backend гарантированно возвращает:

- `partial: boolean`
- `warnings: []`

frontend должен иметь единый паттерн их показа.

Нужно зафиксировать:

- место warning banner на dashboard;
- поведение при нескольких warnings;
- визуальное отличие partial state от error state;
- текстовое правило, что экран usable, но не полностью enriched;
- поведение banner при refresh;
- возможность collapse / expand, если warnings много;
- поведение на dashboard и detail screen.

Обязательное правило:

- `partial=true` никогда не трактуется как hard error;
- warnings не блокируют основную аналитическую работу;
- generated_at должен оставаться видимым даже при partial state.

#### I. State matrix
Для каждого экрана и ключевых блоков должны быть описаны состояния:

- idle
- loading
- refreshing
- empty
- error
- forbidden
- partial
- warning
- stale
- no selection
- no graph edges
- action in progress
- action success
- action failed

Отдельно должны быть описаны state transitions для:

- login form
- dashboard/posts
- dashboard/events
- dashboard/processes
- post detail
- event detail
- process detail
- graph panel
- comments panel
- reports list
- admin screens
- jobs screen
- keyword graph

#### J. Detail panel / detail screen rules
Нужно окончательно зафиксировать паттерн показа деталей.

Должно быть явно описано:

- где используется full page detail;
- где используется side panel / drawer;
- фиксированная ширина detail panel или нет;
- какие блоки всегда видны;
- какие блоки вынесены в tabs;
- как отображаются comments / links / report;
- поведение loading внутри detail;
- placeholder при no selection;
- поведение back navigation;
- обновление selection без полного rerender workspace.

#### K. Graph specification
Для Events и Processes должны быть согласованы графовые правила.

Обязательно нужно описать:

- node types;
- edge types;
- selected node state;
- hovered node state;
- connected edges highlight;
- unrelated nodes dimming;
- legend;
- zoom / pan controls;
- fit-to-screen;
- reset view;
- empty graph state;
- no edges state;
- partial graph state;
- loading state;
- error state;
- toolbar actions.

Отдельно должны быть определены различия:

##### Events graph
- событие как аналитический объект;
- связи между событием и связанными постами/сущностями;
- отображение root context события;
- переход к связанным постам.

##### Processes graph
- процесс как сущность более высокого уровня;
- вложенные события;
- иерархия процесса;
- визуальное отличие от event graph;
- переход к event/post context.

#### L. Filter specification
Для каждого dashboard режима должны быть определены:

- тип каждого фильтра;
- default value;
- empty value;
- сериализация в URL;
- reset behavior;
- зависимость фильтров друг от друга;
- apply mode: instant или explicit apply;
- multi-select behavior;
- searchable behavior;
- dirty state;
- invalid value handling.

Отдельно должны быть согласованы:

- сохраняются ли фильтры при switch между Posts / Events / Processes;
- какие фильтры общие;
- какие mode-specific;
- что происходит с URL при смене mode;
- как обрабатываются неизвестные query params.

#### M. Interaction rules
Нужно письменно зафиксировать микровзаимодействия.

Обязательно определить:

- row click;
- row double click;
- checkbox click;
- card click;
- mode switch click;
- graph node click;
- graph node double click;
- tab click;
- detail panel close;
- action button click;
- refresh behavior;
- mutation pending behavior;
- сохранение selection при refetch;
- поведение браузерной кнопки back.

Без этих правил frontend не должен самостоятельно принимать UX-решения.

#### N. Async job flow rules
Помимо технической схемы из п.1.9 должны быть определены UX-правила:

- где отображается статус job;
- есть ли inline progress;
- есть ли toast;
- как часто poll’ить;
- когда прекращать polling;
- что invalidates после успеха;
- что делать при failed result;
- можно ли запускать повторно;
- есть ли optimistic UI;
- что видит viewer вместо action;
- как отображать last updated / generated_at после завершения job.

#### O. RBAC / permission matrix
Нужно иметь отдельную матрицу прав, а не только текстовую роль-модель.

Для каждой роли и каждого route/action должны быть определены:

- visible
- hidden
- disabled
- read-only
- forbidden route

Нужно покрыть:

- dashboard modes
- detail screens
- report generation
- comments refresh
- reports export
- channels mutations
- users mutations
- settings mutations
- monitor visibility
- jobs visibility
- keyword graph visibility

#### P. API-to-UI mapping
Для устранения двусмысленности должен существовать mapping backend fields → UI behavior.

Для ключевых полей должно быть зафиксировано:

- backend field
- UI label
- formatter
- nullable handling
- fallback text
- component target
- state effect

Минимально mapping должен покрывать:

- `generated_at`
- `partial`
- `warnings`
- `filters_applied`
- `summary`
- `items`
- `meta`
- `report_status`
- `job_id`
- `job result payload`
- graph response fields
- linked posts / linked events counts
- comment counts / involvement / views / date fields

#### Q. Copy rules
Чтобы frontend не придумывал текст на лету, должны быть согласованы:

- labels;
- button texts;
- empty state copy;
- error state copy;
- partial banner copy;
- warnings copy style;
- forbidden copy;
- retry copy;
- tooltip texts;
- helper texts;
- placeholders;
- validation messages.

---

### 1.12.4 Обязательные deliverables к моменту frontend implementation

К началу активной frontend-разработки должны существовать и быть доступны:

1. финальный screen inventory  
2. route map  
3. final desktop layout rules  
4. component inventory  
5. design tokens  
6. table specs  
7. graph specs  
8. detail panel/detail screen rules  
9. state matrix  
10. status matrix  
11. warnings / partial data rules  
12. RBAC matrix  
13. API-to-UI mapping  
14. copy rules  
15. wireframes или low-fi схемы всех ключевых экранов  
16. hi-fi mocks для dashboard modes и detail flows  
17. mock состояния loading / empty / error / forbidden / partial  
18. если возможно — clickable prototype для switch/list/graph/details flows

### 1.12.5 Практический checklist для frontend перед стартом реализации

Перед реализацией каждого модуля frontend-разработчик должен проверить, что по нему есть:

#### Для dashboard module
- route defined
- filters defined
- query params defined
- summary defined
- items schema understood
- table columns frozen
- warnings/partial behavior defined
- generated_at placement defined
- empty/loading/error states defined
- RBAC behavior defined

#### Для graph module
- graph API schema understood
- node types defined
- edge types defined
- selection behavior defined
- toolbar defined
- legend defined
- loading/empty/no-edges/error states defined
- cross-navigation defined

#### Для details module
- full page vs drawer pattern fixed
- sections/tabs fixed
- comments behavior fixed
- links behavior fixed
- report block behavior fixed
- async actions fixed
- back navigation fixed

#### Для admin/report modules
- table schema fixed
- mutations fixed
- permissions fixed
- export flow fixed
- error states fixed

### 1.12.6 Definition of Ready для frontend по UI/UX handoff

Frontend-модуль считается готовым к реализации только если:

- нет двусмысленности в layout;
- нет двусмысленности в states;
- нет двусмысленности в table columns;
- нет двусмысленности в graph interactions;
- нет двусмысленности в permissions;
- нет двусмысленности в action flows;
- нет двусмысленности в copy;
- backend field mapping в UI понятен;
- partial/warnings трактуются единообразно;
- у разработчика нет необходимости самому придумывать UX-решения.

### 1.12.7 Прямое правило для реализации

Если в handoff отсутствует одно из следующих:

- layout rule
- state rule
- interaction rule
- permission rule
- field mapping
- copy rule

то frontend не должен молча интерпретировать это по своему усмотрению как “очевидное”, а должен считать это незакрытым пунктом handoff.
