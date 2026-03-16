# Соответствие API и UI во фронтенде

Источник истины: `docs/frontend_handoff_checklist.md`.
Источник реализации: contracts, mappers, shared dashboard components, detail modules, jobs hooks.
Обновлено: 2026-03-16.

## Общая оболочка dashboard

| Поле бэкенда | UI-назначение | Правило маппинга | Fallback / обработка null | Эффект на состояние |
| --- | --- | --- | --- | --- |
| `mode` | идентификатор режима workspace | используется для связи маршрута и семантики модуля | напрямую не показывается | определяет dashboard module |
| `generated_at` | `DashboardGeneratedAt` | ISO -> форматированная UTC-метка | если поля нет, блок generated-at не должен синтезировать фиктивное значение | видимость свежести снимка |
| `partial` | `DashboardSystemAlerts` / partial notice | boolean как признак degraded-state | по умолчанию non-partial только когда backend contract явно сообщает `false` | неблокирующее partial-состояние |
| `warnings[]` | `DashboardWarningsBanner` | нормализованный список предупреждений | пустой массив не рендерит banner | слой предупреждений остается видимым и не блокирует контент |
| `filters_applied` | debug по фильтрам / согласованность route-owned state | используется для интерпретации примененных фильтров и в тестах | неподдерживаемые ключи игнорируются | URL и API state остаются синхронизированными |
| `summary` | `DashboardSummaryCards` | DTO summary -> cards view model | отсутствующие числа переводятся в безопасные fallback-значения | KPI-слой |
| `items` | `DashboardTableShell` и detail rails | DTO rows -> view model строки таблицы | nullable-метрики переходят в безопасные placeholder-ы | основной аналитический контент |
| `meta` | служебные метаданные сортировки/поддержки | используется для supported sorts и вторичного контекста | игнорируется, если не нужен текущему экрану | экранные возможности |

## Общие detail / metrics поля

| Поле бэкенда | UI-ярлык / назначение | Правило маппинга | Fallback |
| --- | --- | --- | --- |
| `comments_count` | метрика комментариев | форматирование числа | `0` |
| `views` | метрика просмотров | форматирование числа | тире / empty-safe текст |
| `involvement` | метрика вовлеченности | fixed-point / форматированный percentage-like display | тире / empty-safe текст |
| `date` / `started_at` / `ended_at` | подписи дат | ISO -> форматированная UTC-строка | empty-safe label |
| `report_status` | `ReportStatusBadge` | нормализация через общий слой status metadata | unknown -> fallback badge |
| `channels` / `channel_*` | ячейки с названием канала | составной label из title / username / category | только username или fallback текст |
| `text_preview` | preview cells / detail snippets | усеченный preview text | локализованный текст про отсутствие preview |

## Маппинг dashboard и деталей постов

| Поле бэкенда | UI-назначение | Примечание |
| --- | --- | --- |
| `post_id` | ключ строки, ссылка на детали | канонический id для навигации |
| `links_count` | ячейка с метрикой связей | nullable-safe числовое отображение |
| `comments_refresh_available` | видимость действия refresh comments | точка входа, зависящая от роли и backend capability |
| поля thread в comments DTO | view model `CommentsBlock` | сохраняются в mapped view model, чтобы позже можно было добавить thread mode без переписывания contract |
| payload связей | `LinksBlock` | независимое состояние loading/error/empty |
| payload post report | `ReportBlock` | независимое состояние loading/error/empty |

## Маппинг событий и процессов

| Поле бэкенда | UI-назначение | Примечание |
| --- | --- | --- |
| `event_id` / `process_id` | ключ выбора, detail route | канонический entity id |
| `posts_count` / `events_count` | summary и метрики строк | числовое форматирование |
| `root_post_id` | ссылка на контекстный пост события | рендерится только если подтвержден |
| `nodes/edges` из graph payload | view model graph panel | маппится в framework-native graph cards/lists без выдумывания лишних graph fields |
| массивы related posts / events | контекстные списки в detail panel | рендерятся только из подтвержденных связанных сущностей |
| `graph_ready` | подсказка о partial graph | влияет на inline-сообщение о degraded graph |

## Маппинг асинхронных jobs

| Поле бэкенда | UI-назначение | Правило маппинга |
| --- | --- | --- |
| `job_id` | async indicator / polling key | сохраняется после enqueue mutation |
| payload статуса job | `AsyncActionIndicator` / jobs tables | нормализуется через общий job-status metadata layer |
| payload результата job | краткий summary результата | рендерится как сжатый success/failure outcome |
| ответ retry mutation | feedback на jobs screen | используется для invalidation jobs и monitor queries |

## Маппинг monitor

| Поле бэкенда | UI-назначение | Примечание |
| --- | --- | --- |
| общий monitor status | `MonitorStatusBadge` | нормализуется к метаданным status badge |
| строки alert-ов | таблица alert-ов | прямой табличный рендер с компактным state badge |
| dependency/runtime/backlog поля | overview-секции | только read-only snapshot rendering |

## Маппинг keyword graph

| Поле бэкенда | UI-назначение | Примечание |
| --- | --- | --- |
| элементы результата keyword search | results table + seed set | канонический источник выбора seed post-ов |
| `normalized_query` | search metadata | диагностический search context |
| `lemmas` | search metadata | read-only аналитический контекст |
| nodes/edges из build response | keyword graph panel | маппятся в аналитическую graph view model |
| `title` / `content` / `status` из report response | блок preview отчета | синхронный рендер без выдуманного persistence layer |
