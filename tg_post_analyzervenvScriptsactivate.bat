2026-02-18 | Первый коммит
2026-02-19 | Добавил эндпоинт для добавления канала в базу
2026-02-19 | Создан фронтенд (вывод списка отслеживаемых каналов и топ постов с сопутствующей информацией)
2026-02-20 | удален фронтенд. добалены эндпоинты по досбору комментов по запросу пользователя а также ии-анализ поста по запросу пользователя. оптимизированы функции по работе с БД и запросы к ТГ АПИ
2026-02-20 | Создан новый, более простой и близкий к ТЗ фронтенд
2026-02-21 | реализовано нахождение связей между постами
2026-03-02 | feat(linking): перейти на evidence-first linking v2 и модульный пайплайн
2026-03-02 | Добавлен job-слой на PostgreSQL и базовая система авторизации/RBAC" Реализованы очередь задач с блокировками и ретраями, daemon-режим пайплайна с расписанием дособора комментариев и отложенной генерацией отчетов. Добавлены таблицы пользователей/ролей, JWT-аутентификация, защита админских эндпоинтов и скрипт инициализации администратора.
2026-03-02 | Объединены таблицы posts и post_features без потери данных Добавлены поля признаков и эмбеддингов в posts, выполнен перенос данных миграцией и удалена таблица post_features. Обновлены linking/candidates и служебные скрипты backfill/audit для работы через posts.
2026-03-02 | Добавлены архивирование и ретенция данных с поддержкой process reports Реализованы архивные таблицы, хранение отчетов по процессам, сервис переноса данных в архив и очистки hot-данных, ежедневная постановка и исполнение job archive_retention, а также ручной запуск архива через админский API.
2026-03-02 | Усилен RBAC для API и добавлен аудит админ-операций
2026-03-02 | Добавлено хранение системных настроек аналитики в БД Реализована таблица app_settings и API управления конфигурацией. Пайплайн и генерация отчетов переведены на чтение параметров из БД (интервалы сбора, задержки отчетов, лимиты, ретенция, top-N по умолчанию), что устраняет ключевой хардкод.
2026-03-02 | Добавлена строгая валидация системных настроек Для ключей ingest/reports/retention/jobs/api введены pydantic-схемы с проверкой типов, диапазонов и запретом лишних полей. Обновление настроек через API теперь нормализует payload и отклоняет некорректные значения с кодом 422.
2026-03-02 | Прокачал пайплайн - Снизил частоту flood wait
2026-03-08 | Унифицировал API entrypoint и обновил pydantic-конфиги под v2
2026-03-08 | TASK-003: усилить безопасность JWT-конфигурации (fail-fast на startup)
2026-03-08 | TASK-004: убрать небезопасные DB credentials из docker-compose и добавить non-dev guard
2026-03-08 | TASK-005: консолидировать ingestion в единый core-модуль и перевести entrypoint’ы
2026-03-10 | TASK-006: стабилизировать pipeline и collect_comments, добавить jobs retention и лимиты keyword graph
2026-03-10 | TASK-006: перевести API-triggered Telegram/AI задачи на очередь и синхронизировать runtime с settings
2026-03-10 | Stage 1: fix blocking runtime architecture
2026-03-12 | Stage 2: вынести retention в scheduler и добавить мониторинг рантайма
2026-03-12 | Этап 2: вынести retention в scheduler и добавить мониторинг рантайма
2026-03-12 | Исправить семантику draft reports и перевести monitoring на runtime heartbeat
2026-03-12 | Укрепить auth API тестами и убрать N+1 при загрузке ролей
2026-03-12 | Перевести batch reports в jobs и разделить зависимости на профили
2026-03-12 | feat(api): добавить dashboard-агрегаторы для posts/events/processes
2026-03-12 | добавил тз для фронта
2026-03-13 | feat(frontend): реализовать этап 0 bootstrap и архитектурный каркас
2026-03-13 | feat(frontend): реализовать этап 1 auth, session management и role-based routing
2026-03-13 | Stabilize frontend auth and dashboard foundation
2026-03-13 | feat(frontend): add analytics workspace layout and dashboard shell foundation
2026-03-13 | feat(frontend): implement live posts dashboard with query mapping and typed table
2026-03-13 | feat(frontend): implement post detail screen with async post job flows
2026-03-13 | feat(frontend): implement live events dashboard with graph panel and detail rail
2026-03-13 | feat(frontend): implement live processes dashboard with hierarchy graph
2026-03-13 | feat(frontend): implement process detail page with reused dashboard graph integration
2026-03-13 | feat(frontend): implement reports modules with reusable list export and batch flows
2026-03-13 | feat(frontend): implement monitor overview and jobs management modules
2026-03-13 | refactor(frontend): unify shared state handling badges and dashboard UI polish
2026-03-15 | feat(i18n): translate frontend UI to Russian and add i18n framework
2026-03-16 | feat(frontend): finalize audit pass and polish dashboard graph UX
2026-03-16 | почистил репозиторий
2026-03-16 | unify frontend delivery on React SPA and deprecate legacy web serving
2026-03-16 | consolidate linking routes under canonical api and deprecate legacy links aliases
2026-03-16 | migrate auth session model to httpOnly refresh cookies and in-memory access tokens
2026-03-16 | parameterize cors policy and validate env-driven origin settings
2026-03-16 | define explicit runtime topology and canonical process entrypoints
2026-03-16 | Перевести добавление каналов в async jobs и усилить API/тестовый контур
2026-03-20 | начало работы над версткой
2026-03-23 | повысил приоритет линковки
2026-03-25 | сделал selection workspace явным и перенес время формирования в фильтры
2026-03-25 | сделал выбор процесса явным и стабилизировал сборку графов
2026-03-26 | добавил peer-aware сбор комментариев и поиск в dashboard по query params
2026-03-30 | chore: snapshot current workspace state
2026-03-30 | feat: compose event and process reports from post reports
2026-04-04 | TASK-011/TASK-013: сделать auth limiter fail-specific, добавить repo-local CI и уточнить verification loop
2026-04-04 | коммит
2026-04-07 | feat(settings): переработать админку настроек и усилить reporting/ingestion
2026-04-07 | delete extra docs
2026-04-10 | Добавить прогресс сборки отчетов и поддержку reactions в runtime
2026-04-14 | выполнил бэклог docs\multi_agent_news_analysis_implementation_plan.md
2026-04-17 | feat(reporting): включен v2 persisted path под rollout с безопасным fallback и shadow mode
2026-04-22 | S0 Canonical Contract Unification
2026-04-22 | S1 — Step Execution Abstraction
2026-04-22 |  S2 OpenRouter Wiring
2026-04-25 | feat(reporting_v2): интегрировать retrieval provider (SearxNG) и заземлить генерацию на evidence
2026-04-25 | фикс багов
2026-04-25 | поправил контракт выгрузки отчетов по событиям
2026-04-25 | поправил промты для анализа событий
2026-04-25 | пофиксил апи
2026-05-13 | фикс апи
2026-05-16 | реализовано:
2026-05-27 | добавлено отображение трейсов на веб-страницу
2026-06-01 | Усилен retrieval Произвелена ревизия зависимостей Усилены промты Починен scheduler
2026-06-11 | устранены баги в секции с трейсами на веб странице