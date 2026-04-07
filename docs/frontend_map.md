## 1. Краткое резюме проекта

Фронтенд в целом устроен неплохо: это Vite + React 19 + TypeScript с модульной раскладкой `app / modules / shared / test`. Рендер идёт через [main.tsx](d:/Projects/tg_post_analyzer/frontend/src/main.tsx):15 → [App.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/App.tsx):4 → провайдеры → роутер → `AppShell` → модульные страницы.

Главная архитектурная идея: бизнес-фичи разложены по `modules/*`, общие примитивы и инфра лежат в `shared/*`, глобальный state почти целиком держится на React Query + URL query params + `SessionProvider`. Но есть и сломанные/висящие куски: placeholder-ветка dashboard, несколько неиспользуемых файлов, сильная связность между `workspace`, `admin` и `keyword-graph`, плюс очень перегруженный глобальный CSS.

## 2. Дерево структуры

```text
frontend/
  package.json
  vite.config.ts
  src/
    main.tsx
    app/
      App.tsx
      providers/
      router/
      shell/
      styles/global.css
    modules/
      auth/routes/LoginPage.tsx
      workspace/
        routes/
        layouts/
        posts/
        events/
        processes/
        post-detail/
        event-detail/
        process-detail/
        components/
      reports/
      admin/
      platform/
      keyword-graph/
    shared/
      api/
      auth/
      dashboard/
      errors/
      i18n/
      jobs/
      query/
      routing/
      tables/
      theme/
      types/
      ui/
      utils/
    test/
```

## 3. Назначение папок и ключевых файлов

- `app/`  
  Каркас приложения: провайдеры, роутинг, shell, глобальные стили. Идти сюда, если меняется структура всего приложения.

- [main.tsx](d:/Projects/tg_post_analyzer/frontend/src/main.tsx) `CRITICAL`  
  Точка входа. Подключает глобальные стили, i18n и `reactflow`-стили, рендерит `App`.

- [App.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/App.tsx) `CRITICAL`  
  Склеивает `AppProviders` и `AppRouter`.

- [AppProviders.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/AppProviders.tsx) `CRITICAL`  
  Порядок провайдеров: i18n → theme → react-query → session. Менять осторожно.

- [SessionProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/SessionProvider.tsx):34 `CRITICAL`  
  Главный auth/session слой. Тут bootstrap, login/logout, refresh токена, роль пользователя.

- [QueryClientProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/QueryClientProvider.tsx):17 `CRITICAL`  
  Глобальные настройки React Query.

- [AppRouter.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/router/AppRouter.tsx):179 `CRITICAL`  
  Полная карта маршрутов, lazy loading страниц, guards.

- [AppShell.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/shell/AppShell.tsx):24 `CRITICAL`  
  Основной layout: sidebar, header, switcher режимов, logout, language switcher.

- [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css) `CRITICAL`  
  Один большой глобальный stylesheet. Любая правка здесь может ударить по всему UI.

- `modules/workspace/`  
  Основной аналитический workspace: 3 dashboard-режима и 3 detail-страницы.

- [DashboardPostsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/routes/DashboardPostsPage.tsx) `IMPORTANT`  
  Тонкий route-wrapper для posts dashboard.

- [PostsDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/PostsDashboardScreen.tsx):95 `CRITICAL`  
  Полный экран постов: summary, filter bar, таблица, search, роли.

- [EventsDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/events/EventsDashboardScreen.tsx):43 `CRITICAL`  
  Экран событий: таблица + graph panel + detail panel + async actions.

- [ProcessesDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/processes/ProcessesDashboardScreen.tsx):42 `CRITICAL`  
  Аналогично events, но для процессов.

- [PostDetailsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/post-detail/PostDetailsPage.tsx) `IMPORTANT`  
  Детальная страница поста.

- [EventDetailsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/event-detail/EventDetailsPage.tsx) `IMPORTANT`  
  Детальная страница события, но переиспользует компоненты из `workspace/events`.

- [ProcessDetailsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/process-detail/ProcessDetailsPage.tsx) `IMPORTANT`  
  Детальная страница процесса, но переиспользует компоненты из `workspace/processes`.

- `modules/reports/`  
  Каталог отчётов, фильтры, таблица, batch action.

- [ReportsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/reports/ReportsPage.tsx):22 `IMPORTANT`

- `modules/admin/`  
  Каналы, пользователи, настройки, react-hook-form/zod-валидация.

- [SettingsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/routes/SettingsPage.tsx):27 `CRITICAL`
- [ChannelsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/routes/ChannelsPage.tsx) `IMPORTANT`
- [UsersPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/routes/UsersPage.tsx) `IMPORTANT`
- [validation.ts](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/validation.ts) `CRITICAL`
- [settings-registry.ts](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/settings-registry.ts) `CRITICAL`

- `modules/platform/`  
  Monitor + Jobs для ops/admin.

- [MonitorPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/platform/routes/MonitorPage.tsx) `IMPORTANT`
- [JobsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/platform/routes/JobsPage.tsx) `IMPORTANT`

- `modules/keyword-graph/`  
  Поиск постов, сбор seed set, билд графа, генерация отчёта.

- [KeywordGraphPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/keyword-graph/KeywordGraphPage.tsx):29 `CRITICAL`

- `shared/`  
  Общие контракты, API-клиент, routing-policy, dashboard primitives, UI-блоки, i18n, utils.

- [client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts):31 `CRITICAL`  
  Базовый HTTP-клиент для всего фронта.

- [auth-api.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/auth/auth-api.ts) `CRITICAL`

- [policy.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/policy.ts):47 `CRITICAL`  
  Единый источник truth для маршрутов, доступа, навигации, capabilities.

- [contracts.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/contracts.ts) `CRITICAL`  
  Базовые DTO для dashboard.

- [filters.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/filters.ts) `CRITICAL`  
  URL-driven фильтры dashboard и mode switch preservation.

- [hooks.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/hooks.ts) `IMPORTANT`
- [DashboardFilterBar.tsx](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/components/DashboardFilterBar.tsx) `IMPORTANT`
- [BaseDataTable.tsx](d:/Projects/tg_post_analyzer/frontend/src/shared/tables/components/BaseDataTable.tsx) `IMPORTANT`
- [i18n.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/i18n/i18n.ts) `CRITICAL`
- [tokens.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/theme/tokens.ts) `IMPORTANT`
- [hooks.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/jobs/hooks.ts) `IMPORTANT`

- `test/`  
  Хорошее покрытие витестами по роутингу, auth-flow, dashboards, detail pages, admin.

## 4. Точки входа и поток данных

- Entry point: [main.tsx](d:/Projects/tg_post_analyzer/frontend/src/main.tsx) → [App.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/App.tsx)
- Инициализация: [AppProviders.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/AppProviders.tsx) подключает i18n, MUI theme, React Query, session
- Роутинг: [AppRouter.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/router/AppRouter.tsx)
- Layout: [AppShell.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/shell/AppShell.tsx), для dashboard-вложенности ещё [AnalyticsWorkspaceLayout.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/layouts/AnalyticsWorkspaceLayout.tsx)
- Страницы: `modules/*/routes/*Page.tsx` или `modules/*/*Page.tsx`
- Вложенные компоненты: `modules/*/components/*` и `shared/ui/*`, `shared/dashboard/components/*`
- Запросы: модульные `api.ts` → [shared/api/client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts)
- Состояние:
  - auth/session: [SessionProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/SessionProvider.tsx)
  - remote state/cache: React Query hooks в `modules/*/hooks.ts`
  - UI filter state: URL query params через `shared/dashboard/filters.ts`, `reports/filters.ts`, `keyword-graph/filters.ts`
  - локальный UI state: `useState` внутри экранов
- Стили:
  - глобально: [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css)
  - тема: [ThemeProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/ThemeProvider.tsx) + [tokens.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/theme/tokens.ts)
  - MUI используется точечно, но визуальный слой в основном кастомный CSS

## 5. Карта зависимостей

`main.tsx` → `App.tsx` → `AppProviders` → `AppRouter`  
`AppRouter` → `AuthGuard` / `RoleGuard` → `AppShell` → route pages  
`route page` → `Screen/Page` → `hooks.ts` → `api.ts` → `shared/api/client.ts`  
`Screen/Page` → `mappers.ts(x)` → `shared/dashboard/*` / `shared/ui/*` / `shared/tables/*`

Кто от кого зависит:
- `app/*` зависит почти от всех нижних слоёв, это верхний orchestration-layer.
- `modules/*` зависят от `shared/*`.
- `shared/*` в целом не должен зависеть от `modules/*`, и почти везде это соблюдено.
- Исключения по связности:
  - `workspace/posts|events` зависят от `admin/hooks` ради channels.
  - `workspace/*/hooks` зависят от `keyword-graph/api` ради keyword search.
  - `event-detail` зависит от `workspace/events/components` и `workspace/events/mappers`.
  - `process-detail` зависит от `workspace/processes/components` и `workspace/processes/mappers`.

Слишком широко используются:
- [policy.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/policy.ts) `CRITICAL`
- [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css) `CRITICAL`
- [shared/dashboard/*](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/contracts.ts) `CRITICAL`
- [shared/api/client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts) `CRITICAL`

## 6. Где что менять

- Если менять header/sidebar: [AppShell.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/shell/AppShell.tsx), [TopNavigation.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/shell/TopNavigation.tsx), [RoleAwareNavigation.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/shell/RoleAwareNavigation.tsx), [policy.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/policy.ts), [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css)
- Если менять dashboard posts: route-wrapper [DashboardPostsPage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/routes/DashboardPostsPage.tsx) → экран [PostsDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/PostsDashboardScreen.tsx) → логика [hooks.ts](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/hooks.ts) → API [api.ts](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/api.ts) → маппинг [mappers.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/mappers.tsx)
- Если менять dashboard events/processes: такой же паттерн в `modules/workspace/events/*` и `modules/workspace/processes/*`
- Если менять detail-страницы: соответствующий `*-detail/*`, но проверьте переиспользуемые компоненты из `events/components` и `processes/components`
- Если менять формы admin: `modules/admin/routes/*Page.tsx` + [validation.ts](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/validation.ts) + [SettingsFieldRenderer.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/admin/components/SettingsFieldRenderer.tsx)
- Если менять API-запросы: сначала нужный `modules/*/api.ts`, потом при необходимости [shared/api/client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts)
- Если менять глобальные стили: [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css) и иногда [tokens.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/theme/tokens.ts)
- Если менять типы: доменные DTO в [shared/dashboard/contracts.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/contracts.ts) и в `modules/*/contracts.ts`
- Если менять состояние приложения: auth в [SessionProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/SessionProvider.tsx), remote cache в `hooks.ts` через React Query, URL-state в `filters.ts`

## 7. Проблемные места

- `SUSPECT`: [DashboardModePage.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/components/DashboardModePage.tsx), [placeholders.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/placeholders.ts), [view-models.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/view-models.ts)  
  Похоже на старую placeholder-ветку. В runtime не используется.
- `SUSPECT`: [RoutePlaceholder.tsx](d:/Projects/tg_post_analyzer/frontend/src/shared/ui/placeholders/RoutePlaceholder.tsx), [shared/types/dashboard.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/types/dashboard.ts), [shared/routing/navigation.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/navigation.ts)  
  Выглядят как мёртвый код/тонкие re-export-остатки.
- Дублирование логики: три dashboard-экрана очень похожи по скелету загрузки/ошибок/summary/filter-flow; реюз есть, но не доведён до конца.
- Сильная связность:
  - `workspace` тянет `admin/hooks` ради channels.
  - `workspace` тянет `keyword-graph/api` ради keyword search.
  - detail-модули событий/процессов тянут dashboard-компоненты и dashboard-mappers.
- Смешение UI и бизнес-логики: крупные экраны вроде [PostsDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/posts/PostsDashboardScreen.tsx), [EventsDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/events/EventsDashboardScreen.tsx), [ProcessesDashboardScreen.tsx](d:/Projects/tg_post_analyzer/frontend/src/modules/workspace/processes/ProcessesDashboardScreen.tsx) уже слишком толстые.
- `global.css` архитектурно хаотичен: много повторных переопределений одних и тех же селекторов, например `app-header--analytics`, `workspace-layout--analytics`, `app-session-chip--compact`. Правка зависит от позиции правила в файле.
- Конфликт стилистических систем: есть MUI theme, но основной UI написан через глобальные классы; это усложняет предсказуемость правок.
- Naming confusing:
  - `routes/*Page.tsx` и просто `*Page.tsx` вперемешку
  - `Screen`/`Page`/`Layout` используются не всегда последовательно
- I18n-контент местами грязный:
  - в `en/common.json` есть русский текст, например [common.json](d:/Projects/tg_post_analyzer/frontend/src/shared/i18n/locales/en/common.json):850
  - при чтении экранов видны битые fallback-строки в некоторых dashboard-компонентах, особенно в posts/events/processes screens

## 8. Рекомендации по безопасному редактированию

- Можно править изолированно:
  - `modules/admin/routes/ChannelsPage.tsx` и `UsersPage.tsx`, если не трогать `admin/api.ts` и `validation.ts`
  - визуальные мелкие компоненты в `shared/ui/states/*`, `shared/ui/status/*`, `shared/ui/notices/*`
  - отдельные `mappers.ts(x)` внутри модулей, если не меняются DTO
  - `modules/platform/routes/MonitorPage.tsx` и `JobsPage.tsx` при локальных UI-правках
- Нужна проверка всей цепочки:
  - [policy.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/policy.ts): меняет nav, guards, mode switcher, root redirect, capabilities
  - [SessionProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/SessionProvider.tsx): ломает auth во всём приложении
  - [shared/api/client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts): ломает все запросы
  - [shared/dashboard/contracts.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/contracts.ts) и [shared/dashboard/filters.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/filters.ts): бьют сразу по posts/events/processes
  - [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css): любое изменение потенциально глобальное
  - `events/components/*` и `processes/components/*`: их используют и dashboard, и detail-страницы

## 9. Короткий план реорганизации

- Удалить или явно пометить legacy/unused ветку: `DashboardModePage`, `shared/dashboard/placeholders`, `shared/dashboard/view-models`, `RoutePlaceholder`, `shared/types/dashboard`, `shared/routing/navigation`.
- Вынести общий `channels`-read API из `admin` в нейтральный shared/domain слой, чтобы `workspace` не зависел от admin.
- Вынести keyword search API из `keyword-graph` в shared-search слой, чтобы dashboard не зависел от другой фичи.
- Разделить большие `*DashboardScreen.tsx` на `container + presentational sections`.
- Разрезать [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css) хотя бы на `shell.css`, `dashboard.css`, `details.css`, `admin.css`, `graph.css`.
- Причесать i18n: убрать русские строки из `en`, убрать битые fallback-строки из TSX и держать тексты только в locale JSON.

## 10. TL;DR для разработчика

- Вход: [main.tsx](d:/Projects/tg_post_analyzer/frontend/src/main.tsx) → [App.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/App.tsx) → [AppRouter.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/router/AppRouter.tsx)
- Страницы: `frontend/src/modules/*`, особенно `workspace`, `reports`, `admin`, `platform`, `keyword-graph`
- Общий UI: `frontend/src/shared/ui/*`, `shared/dashboard/components/*`, `shared/tables/*`
- Логика: `modules/*/hooks.ts`, `modules/*/mappers.ts(x)`, `SessionProvider`
- API: `modules/*/api.ts` + [shared/api/client.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/api/client.ts)
- Самые опасные места: [policy.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/routing/policy.ts), [SessionProvider.tsx](d:/Projects/tg_post_analyzer/frontend/src/app/providers/SessionProvider.tsx), [shared/dashboard/contracts.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/contracts.ts), [shared/dashboard/filters.ts](d:/Projects/tg_post_analyzer/frontend/src/shared/dashboard/filters.ts), [global.css](d:/Projects/tg_post_analyzer/frontend/src/app/styles/global.css)

Если хочешь, следующим сообщением я могу собрать это ещё и в формате “карта зависимостей по файлам” с короткой ASCII-схемой импортов для каждого модуля.