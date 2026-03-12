# Engineering Remediation Plan

Полная развернутая версия плана находится в предыдущем сообщении чата. Ниже — сохраненная структурированная версия в markdown.

## 1. Краткое резюме
- Всего задач: 15
- Critical: 4
- High: 7
- Medium: 4
- Low: 0

Самые опасные проблемы:
1. Конфликты конфигурации и запуск в несуществующую точку входа API.
2. Небезопасный дефолт AUTH_JWT_SECRET без fail-fast.
3. Дублирование ingestion-пайплайнов.
4. Критически слабое тестовое покрытие.
5. Конфликт семантики reply-link (background vs update).

## 2. Список задач (кратко)
- TASK-001 (Critical, Architecture): унификация env-контракта и startup validation.
- TASK-002 (High, Maintainability): единый API entrypoint и актуализация README.
- TASK-003 (Critical, Security): запрет небезопасного JWT secret.
- TASK-004 (High, Security): убрать hardcoded DB credentials из docker-compose.
- TASK-005 (Critical, Architecture): консолидация ingestion в единый core.
- TASK-006 (High, Product Logic): единая семантика reply-link.
- TASK-007 (High, Bug Fix): корректный 404/200 в comments endpoint.
- TASK-008 (High, Maintainability): убрать broad except и silent failures.
- TASK-009 (High, Maintainability): единый source of truth для defaults settings.
- TASK-010 (Critical, Testing): базовый тестовый контур и quality gate.
- TASK-011 (High, Performance): снять O(n^2) узкое место keyword graph.
- TASK-012 (Medium, Performance): убрать N+1 в list_users.
- TASK-013 (Medium, Infrastructure): разделить зависимости на base/dev/optional.
- TASK-014 (Medium, Product Logic): корректные статусы draft/ready отчетов.
- TASK-015 (High, Scalability): controlled concurrency + transaction tuning pipeline.

## 3. Dependency Graph
- TASK-001 -> TASK-002 -> TASK-005
- TASK-001 -> TASK-003 -> TASK-010
- TASK-001 -> TASK-004
- TASK-005 -> TASK-006 -> TASK-014
- TASK-005 -> TASK-008 -> TASK-015
- TASK-005 -> TASK-011
- TASK-010 -> TASK-007
- TASK-010 -> TASK-009 -> TASK-015
- TASK-010 -> TASK-011 / TASK-012 / TASK-013 / TASK-014

## 4. Рекомендуемый порядок выполнения
### Этап 1. Блокирующие архитектурные исправления
TASK-001, TASK-002, TASK-005

### Этап 2. Критические исправления надежности и безопасности
TASK-003, TASK-004, TASK-010

### Этап 3. Исправление хрупких мест и техдолга
TASK-006, TASK-007, TASK-008, TASK-009

### Этап 4. Качество и поддерживаемость
TASK-012, TASK-013, TASK-014

### Этап 5. Оптимизация и вторичные улучшения
TASK-011, TASK-015

## 5. Quick Wins
- TASK-002: исправить точку входа и документацию.
- TASK-007: локальный bug fix endpoint.
- TASK-003: жесткий fail-fast для JWT secret.
- TASK-009: устранить рассинхрон defaults.
- TASK-012: убрать N+1 в list_users.

## 6. Архитектурные блокеры
- TASK-001
- TASK-005
- TASK-010
- TASK-006

## 7. Критический путь
- TASK-001 -> TASK-002 -> TASK-005 -> TASK-010 -> TASK-008 -> TASK-015

## 8. Что можно делать параллельно
- TASK-003 и TASK-004 (после TASK-001)
- TASK-007 и TASK-009 (после TASK-010)
- TASK-012 и TASK-013 (после TASK-010)
- TASK-011 и TASK-015 (после зависимостей)

## 9. Самые рискованные места плана
1. TASK-005: большой рефакторинг с риском скрытых регрессий.
2. TASK-015: concurrency + Telegram rate limits.
3. TASK-011: риск деградации качества графа.
4. TASK-006: влияние на исторические данные и downstream-аналитику.
5. TASK-010: рост объема refactoring для тестопригодности.

## 10. Готовые задачи для новых чатов с Codex
TASK-001 — Атомарная и безопасная ротация refresh token
Контекст:
в services/auth.py refresh token можно конкурентно использовать несколько раз.
Нужно сделать:
переписать rotation на атомарный flow с row locking и тестом на concurrent refresh.
Ограничения:
не ломать login/refresh/logout, не раскрывать внутренние детали ошибок.
Ожидаемый результат:
один refresh token успешно используется только один раз.
Перед началом проверь:
services/auth.py, api/routers/auth.py, модель AuthRefreshToken, auth-тесты.
Если данных недостаточно, запроси:
допустимость миграции схемы и target DB behavior для locking.

TASK-002 — Унификация runtime-контура Telegram pipeline
Контекст:
в проекте несколько конкурирующих pipeline/runtime-path, включая legacy scripts/pipeline.py.
Нужно сделать:
оставить один канонический runtime core и убрать/депрекейтнуть дубли.
Ограничения:
не ломать официальный запуск и jobs/ingest flow.
Ожидаемый результат:
один production runtime, остальные пути либо thin wrapper, либо удалены.
Перед началом проверь:
services/pipeline_runtime.py, scripts/run_telegram_pipeline.py, scripts/pipeline.py, main.py, README.
Если данных недостаточно, запроси:
какие entrypoint’ы реально используются в эксплуатации.

TASK-003 — Единая модель Telegram client/session lifecycle
Контекст:
client создается и живет по разным правилам в API, pipeline и скриптах.
Нужно сделать:
ввести единый client factory/lifecycle contract и привести потребителей к нему.
Ограничения:
сохранить session-lock safety и не сломать worker flow.
Ожидаемый результат:
единая модель Telethon client/session lifecycle.
Перед началом проверь:
client/telegram.py, client/config.py, services/pipeline_runtime.py, api/routers/channels.py, services/TGqueries.py.
Если данных недостаточно, запроси:
какие процессы реально живут параллельно.

TASK-004 — Исправление ложного channel_concurrency
Контекст:
channel_concurrency заявлен, но весь ingest_channel сериализован общим lock.
Нужно сделать:
сузить lock до реально конфликтующих операций или убрать фиктивный параллелизм.
Ограничения:
не сломать FloodWait-safe поведение и работу Telethon session.
Ожидаемый результат:
параллелизм либо реально работает, либо честно удален из контракта.
Перед началом проверь:
services/pipeline_runtime.py, services/ingestion_core.py, README.
Если данных недостаточно, запроси:
какие Telethon операции безопасно выполнять параллельно.

TASK-005 — Устранение блокирующего ожидания jobs в API
Контекст:
API ждет background jobs через polling БД и держит долгие HTTP-запросы.
Нужно сделать:
перевести endpoints на 202 + job_id и отдельный status/result API.
Ограничения:
сохранить доступность результата операции для клиента.
Ожидаемый результат:
API быстро отвечает, тяжелая работа идет через jobs.
Перед началом проверь:
api/routers/posts.py, api/routers/reports.py, services/pipeline_runtime.py, services/jobs.py.
Если данных недостаточно, запроси:
какие клиенты уже завязаны на sync-response контракт.

TASK-006 — Исправление семантики draft event/process reports
Контекст:
draft reports сохраняются и возвращаются как ready.
Нужно сделать:
ввести отдельный draft-статус и согласовать API/модели/экспорт.
Ограничения:
не сломать чтение старых данных без плана миграции.
Ожидаемый результат:
статусы отчетов честно отражают их состояние.
Перед началом проверь:
services/reporting.py, api/routers/reports.py, report-модели и схемы.
Если данных недостаточно, запроси:
продуктовую state machine отчетов.

TASK-007 — Устранение утечки внутренних ошибок в содержимое отчетов
Контекст:
исключения сериализуются в content отчета и могут уходить наружу.
Нужно сделать:
убрать repr(exception) из content, оставить техническую ошибку отдельно.
Ограничения:
не потерять диагностируемость.
Ожидаемый результат:
пользовательский контент не содержит внутренних ошибок.
Перед началом проверь:
services/reporting.py, api/routers/reports.py, job-result flow.
Если данных недостаточно, запроси:
где допустимо хранить технические ошибки отчетов.

TASK-008 — Приведение runtime-настроек к одному фактическому контракту
Контекст:
README, defaults и runtime расходятся по реальному поведению настроек.
Нужно сделать:
синхронизировать поведение, defaults и документацию; убрать мертвые/ложные настройки.
Ограничения:
сохранить управляемость и по возможности обратную совместимость.
Ожидаемый результат:
одна настройка = одно поведение.
Перед началом проверь:
config.py, client/config.py, services/settings_defaults.py, services/pipeline_runtime.py, README.
Если данных недостаточно, запроси:
какие настройки официально поддерживаются.

TASK-009 — Укрепление auth API и RBAC-пути после security-fix
Контекст:
текущие auth-тесты в основном smoke и не ловят реальные race/DB-сценарии.
Нужно сделать:
добавить integration-тесты на login/refresh/logout/RBAC и revoked/expired/concurrent cases.
Ограничения:
без внешних сервисов, с упором на реальную логику.
Ожидаемый результат:
auth-контур защищен реалистичными тестами.
Перед началом проверь:
services/auth.py, api/routers/auth.py, текущие auth-тесты.
Если данных недостаточно, запроси:
какая тестовая БД допустима.

TASK-010 — Перенос тестов с legacy pipeline на канонический runtime
Контекст:
часть pipeline-тестов направлена на scripts/pipeline.py, а не на production runtime.
Нужно сделать:
переписать/перенести тесты на services/pipeline_runtime.py.
Ограничения:
не потерять покрытие error-path.
Ожидаемый результат:
тесты защищают реальный runtime.
Перед началом проверь:
tests/test_pipeline_error_paths.py, scripts/pipeline.py, services/pipeline_runtime.py.
Если данных недостаточно, запроси:
нужно ли сохранять legacy runtime хотя бы как compatibility-layer.

TASK-011 — Рационализация и синхронизация documentation/runtime defaults
Контекст:
README местами описывает неактуальное или ложное поведение.
Нужно сделать:
обновить README и examples после архитектурной стабилизации.
Ограничения:
не документировать deprecated path как основной.
Ожидаемый результат:
документация совпадает с кодом.
Перед началом проверь:
README, services/settings_defaults.py, services/pipeline_runtime.py, client/config.py.
Если данных недостаточно, запроси:
какой runtime считается официальным после рефакторинга.

TASK-012 — Оптимизация /api/auth/users и устранение N+1 по ролям
Контекст:
на каждого пользователя отдельно читаются роли.
Нужно сделать:
сделать bulk-загрузку пользователей с ролями и добавить тест.
Ограничения:
не менять response schema.
Ожидаемый результат:
endpoint не делает N+1 запросов.
Перед началом проверь:
api/routers/auth.py, services/auth.py, auth-схемы.
Если данных недостаточно, запроси:
допустим ли join+aggregation вместо чистого ORM-пути.

TASK-013 — Стабилизация observability и исправление ложных метрик мониторинга
Контекст:
monitoring частично смотрит не на тот runtime и считает rates по всей истории.
Нужно сделать:
привести monitoring к реальному worker/API runtime и window-based metrics.
Ограничения:
по возможности не ломать формат monitoring API.
Ожидаемый результат:
метрики и alerts операционно полезны.
Перед началом проверь:
services/monitoring.py, api/routers/monitor.py, runtime model процессов.
Если данных недостаточно, запроси:
как именно разворачиваются API и worker-процессы.

TASK-014 — Сокращение inline-тяжелых операций в report API и перевод batch-flow в jobs
Контекст:
массовая генерация отчетов выполняется прямо в HTTP handler.
Нужно сделать:
перевести batch generation на job-driven flow с лимитами и статусом batch-run.
Ограничения:
не допустить job storm и долгих HTTP-запросов.
Ожидаемый результат:
batch flow полностью идет через jobs.
Перед началом проверь:
api/routers/reports.py, services/pipeline_runtime.py, services/jobs.py.
Если данных недостаточно, запроси:
какой batch status contract нужен продуктово.

TASK-015 — Разделение dependency-профилей и минимизация базовой установки
Контекст:
один requirements.txt смешивает base/dev/ML/ops/platform-specific зависимости.
Нужно сделать:
разделить зависимости на профили и облегчить базовую установку.
Ограничения:
не ломать реально используемые production-фичи.
Ожидаемый результат:
минимальный install path для базового API/pipeline.
Перед началом проверь:
requirements.txt, импортируемые модули, README.
Если данных недостаточно, запроси:
какие фичи считаются обязательными для production.



TASK-006
TASK-007
TASK-010
TASK-013

TASK-009
TASK-011
TASK-012

TASK-014
TASK-015