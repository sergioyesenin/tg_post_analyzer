# Правила взаимодействия во фронтенде

Источник истины: `docs/frontend_handoff_checklist.md`.
Источник реализации: dashboard-экраны, detail pages, shared filter helpers и tests.
Обновлено: 2026-03-16.

## Взаимодействия в dashboard

### Переключение режимов

- Нажатие на ссылку режима dashboard ведет на целевой маршрут.
- При переключении сохраняются только поддерживаемые общие фильтры.
- Неподдерживаемые или специфичные для режима параметры удаляются, а не переосмысляются.

### Панель фильтров

- Фильтры dashboard принадлежат URL.
- Пользователь сначала меняет значения формы, а затем явно применяет их.
- Apply обновляет query string маршрута.
- Reset очищает только параметры текущего dashboard mode.
- Неизвестные query params игнорируются при парсинге.

### Строки таблиц

- Действия в строках dashboard постов открывают детали поста.
- Выбор строки в dashboard событий меняет выбранное событие внутри workspace.
- Выбор строки в dashboard процессов меняет выбранный процесс внутри workspace.
- Выбор сохраняется после refetch, если выбранная сущность все еще присутствует в обновленном payload.

## Правила работы с графами

### Граф события

- Граф загружается только для выбранного события.
- Ручной refresh сохраняет panel видимой и показывает refresh/loading state inline.
- Пустой граф и граф без ребер не считаются фатальным состоянием.
- Ссылки на related posts ведут только на подтвержденные detail-маршруты постов.

### Граф процесса

- Граф загружается только для выбранного процесса.
- Ручной refresh не размонтирует detail rail.
- Пустой граф и граф без ребер не считаются фатальным состоянием.
- Ссылки на related events и lead posts ведут только на подтвержденные detail-маршруты.

### Keyword graph

- Search выполняется по явному submit, хотя фильтры и хранятся в URL.
- Seed set собирается из выбранных search results.
- Build action disabled, пока не выбран хотя бы один пост.
- Генерация отчета disabled, пока не выбран хотя бы один пост.

## Правила detail-экранов

### Деталь поста

- Full-page detail layout с main rail и side rail.
- Main rail: блок комментариев, async indicator комментариев, блок связей.
- Side rail: блок отчета, async indicator отчета.
- Viewer видит контент, но не видит mutation buttons.
- Ошибки secondary-блоков комментариев или отчета не заменяют всю страницу целиком.

### Деталь события

- Full-page detail layout.
- Переиспользует `EventGraphPanel` и `EventDetailPanel` из dashboard-модуля.
- Действие Back использует browser history, если это возможно, иначе делает fallback на `/dashboard/events`.
- Ссылка на root post показывается только если она подтверждена mapped payload.

### Деталь процесса

- Full-page detail layout.
- Переиспользует `ProcessGraphPanel` и `ProcessDetailPanel` из dashboard-модуля.
- Действие Back использует browser history, если это возможно, иначе делает fallback на `/dashboard/processes`.
- Контекстные ссылки на related event/post показываются только если они подтверждены mapped payload.

## Правила асинхронных действий

### Общий job pattern

- Async actions вызывают подтвержденный mutation endpoint.
- UI сохраняет возвращенный `job_id`.
- Polling продолжается до terminal state.
- Terminal result запрашивается через подтвержденный job-result endpoint, если он доступен.
- После успеха выполняется invalidation связанных queries.
- Уже загруженный контент экрана остается видимым, пока job выполняется или падает.

### Текущие async-поверхности

- refresh комментариев поста
- генерация/обновление отчета по посту
- генерация/обновление draft-отчета по событию
- генерация/обновление draft-отчета по процессу
- batch generation отчетов по постам через фильтр
- retry-действия в jobs

## Правила partial / warning

- `partial=true` никогда не блокирует workspace.
- `warnings[]` рендерятся в общем системном alert-area.
- `generated_at` остается видимым даже при наличии partial warnings.
- Partial dashboard — это degraded, но usable screen, а не error screen.

## Правила permission-поведения

- Viewer никогда не видит mutation buttons.
- Analyst может генерировать отчеты и обновлять комментарии там, где это разрешено маршрутом.
- Analyst может открывать `/settings` только в read-only режиме.
- Несанкционированный прямой вход на маршрут приводит к forbidden state.
- Недоступные пункты навигации скрываются из role-aware navigation.

## Правила browser state

- Query string — это устойчивый источник состояния фильтров dashboard/report.
- Переключение dashboard mode сохраняет только те общие фильтры, которые поддерживаются целевым режимом.
- Прямая загрузка маршрута должна полностью восстанавливать экран только из URL и backend data.
