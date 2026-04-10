## 1. Executive summary

Ниже приведен execution-spec для реализации уже согласованного backlog в существующей кодовой базе `tg_post_analyzer`.

Ключевой принцип спецификации:
- реализация должна быть минимально инвазивной;
- использовать существующие runtime-роли, jobs table, API endpoints и текущую queue-driven модель;
- не вводить новые архитектурные сущности без отдельного подтверждения;
- packages, зависящие от неразрешенной технической неопределенности, помечены как `NOT READY`.

Главный critical path:
1. отключить автогенерацию отчетов;
2. зафиксировать on-demand режим AI worker;
3. подтвердить spike по reactions;
4. ввести readiness/dependency orchestration;
5. реализовать reactions persistence + collection;
6. обновить report generation;
7. добавить dedupe и async progress UX;
8. обновить logging/metrics.

---

## 2. Implementation packages

### Package P1. Disable Auto Report Generation
- Цель: полностью убрать автоматическую постановку report jobs из фоновых сценариев.
- Почему отдельно: это базовая смена operating model, независимая от reactions/UI.
- Scope:
  - выключение auto-enqueue `BUILD_*_REPORT`
  - сохранение ручного API-triggered запуска
  - обновление runbook/docs по новому режиму
- Explicitly out of scope:
  - reactions
  - websocket/push
  - dedupe
  - readiness orchestration
- Зависимости: нет
- Package-level риски:
  - скрытые auto paths останутся активными
  - сломаются существующие stale/cascade ожидания

### Package P2. Passive AI Worker Runtime
- Цель: оставить AI worker работающим, но только как consumer пользовательских report jobs.
- Почему отдельно: это runtime-поведение worker’а, связанное с P1, но не тождественное ему.
- Scope:
  - убрать scheduler-like generation behavior из AI цикла
  - сохранить обработку входящих `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, `BUILD_PROCESS_REPORT`
- Explicitly out of scope:
  - reactions
  - новые API endpoints
  - websocket/push
- Зависимости: P1
- Риски:
  - остаточный background scheduling
  - неконсистентность между docs и runtime behavior

### Package P3. Reactions Capability Spike
- Цель: подтвердить техническую возможность собирать reactions по постам и comments через текущий Telegram/Telethon стек.
- Почему отдельно: от него зависят data model semantics, collection logic и fallback behavior.
- Scope:
  - spike по post reactions
  - spike по comment reactions
  - фиксация fallback strategy
- Explicitly out of scope:
  - production migration
  - UI
  - постоянная реализация сборщика reactions
- Зависимости: нет
- Риски:
  - partial support
  - нестабильное Telegram behavior
- Статус: `READY`

### Package P4. Priority and Graceful Preemption
- Цель: дать приоритет пользовательским и сервисным jobs, не ломая целостность данных.
- Почему отдельно: это orchestration package, влияющий на все runtime loops.
- Scope:
  - priority matrix в существующей jobs-модели
  - graceful preemption после текущей работы
  - возврат в прежний ingest cycle
- Explicitly out of scope:
  - reactions storage
  - report prompt changes
  - websocket/push
- Зависимости: P1, P2
- Риски:
  - starvation low-priority jobs
  - сломанный job ordering
- Статус: `NOT READY` частично, пока не зафиксирована file-level реализация preemption boundary для каждого worker path

### Package P5. Readiness and Dependency Orchestration
- Цель: построить dependency-driven flow генерации отчетов.
- Почему отдельно: это центральный пакет новой продуктовой логики.
- Scope:
  - readiness rules для post/event/process
  - AI-driven постановка срочных dependency jobs
  - каскад process → event → post → refresh source data
- Explicitly out of scope:
  - новый UX beyond agreed `building_report`
  - новые runtime roles
  - новые очереди
- Зависимости: P2, P4, P3
- Риски:
  - циклическая оркестрация
  - зависимость от результата spike
  - неправильная трактовка partial readiness
- Статус: `NOT READY`

### Package P6. Reactions Persistence
- Цель: добавить хранение reactions в `posts` и `comments`.
- Почему отдельно: это отдельный DB/model package, не равный collection.
- Scope:
  - JSON contract для stored reactions payload
  - migration
  - ORM/model updates
  - serialization support
- Explicitly out of scope:
  - фактический сбор reactions
  - report usage
  - UI
- Зависимости: P3
- Риски:
  - неверный payload schema
  - миграционный риск на больших таблицах
- Статус: `NOT READY` до фиксации результата spike/fallback semantics

### Package P7. Reactions Collection and Refresh Post Data
- Цель: встроить reactions collection в существующий flow обновления post data.
- Почему отдельно: это runtime/integration package поверх существующего `COLLECT_COMMENTS`.
- Scope:
  - расширение текущего refresh flow до comments + post reactions + comment reactions
  - partial collection handling
  - backfill path для reactions
- Explicitly out of scope:
  - новый job type без подтверждения
  - refactor всего comment subsystem
- Зависимости: P3, P6
- Риски:
  - перегрузка текущего job flow
  - ambiguity around partial comment reactions
- Статус: `NOT READY`

### Package P8. Report Enrichment
- Цель: использовать reactions и audience stance в report generation.
- Почему отдельно: это isolated business-logic package в reporting stack.
- Scope:
  - обновление post report inputs/prompt/payload
  - обновление event/process aggregation only as required by agreed backlog
  - coverage factor in report metadata
- Explicitly out of scope:
  - новая report architecture
  - новые сущности report storage
- Зависимости: P5, P7
- Риски:
  - prompt instability
  - unclear partial data semantics
- Статус: `NOT READY`

### Package P9. Async Status Delivery and UI Contract Updates
- Цель: дать пользователю long-running async UX для `building_report`.
- Почему отдельно: затрагивает API/UI delivery semantics.
- Scope:
  - status `building_report`
  - websocket/push progress
  - inline badge/job drawer support
  - retry CTA for allowed failure states
- Explicitly out of scope:
  - расширение UX на несогласованные стадии
  - новые публичные каналы beyond agreed transport
- Зависимости: P5, P8
- Риски:
  - незафиксированный websocket contract
  - auth/reconnect edge cases
- Статус: `NOT READY`

### Package P10. Duplicate Request Guard
- Цель: ограничить повторный запуск отчета по той же сущности на 1 час.
- Почему отдельно: отдельная control-policy поверх existing API/jobs flow.
- Scope:
  - dedupe policy
  - user-facing blocked response
  - frontend blocked state
- Explicitly out of scope:
  - redesign jobs table
  - новое дерево parent/child jobs
- Зависимости: P2, P5
- Риски:
  - незафиксированная policy after failure
- Статус: `NOT READY`

### Package P11. Logging and Observability
- Цель: сократить шум логов и добавить метрики новой модели.
- Почему отдельно: самостоятельный ops package, можно частично делать позже.
- Scope:
  - demote low-value INFO logs
  - сохранить WARNING/ERROR/FloodWait/job-state logs
  - добавить agreed metrics в monitor surface
- Explicitly out of scope:
  - новые dashboards beyond agreed need
  - observability platform refactor
- Зависимости: P2, P4, P5, частично P7/P8
- Риски:
  - потеря отладочной информации
  - незафиксированные metric names/fields
- Статус: `READY` частично

---

## 3. Package-by-package execution specification

## Package P1. Disable Auto Report Generation

### 2.1. Scope
Должно быть реализовано:
- выявить и отключить все code paths, которые автоматически создают `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, `BUILD_PROCESS_REPORT` без пользовательского API-запроса;
- сохранить API-инициированный enqueue report jobs;
- обновить docs/runbook, чтобы отражать новый режим.

Не должно быть реализовано:
- изменение semantics report content;
- reactions;
- websocket;
- dedupe;
- новая queue topology.

### 2.2. Architectural guardrails
- Запрещено:
  - вводить новые runtime roles;
  - вводить новые job types;
  - менять публичные report API endpoints;
  - рефакторить jobs subsystem beyond required removals.
- Нельзя ломать:
  - существующую jobs table;
  - существующие `BUILD_*_REPORT` job handlers;
  - existing accepted-job response format.
- Нельзя менять:
  - auth contracts;
  - monitor API contracts без отдельной задачи.
- Можно:
  - убирать auto-enqueue вызовы;
  - менять scheduling logic там, где она именно создает report jobs.
- Переименовывать существующие сущности нельзя.

### 2.3. File-level scope
Likely to modify:
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [services/pipeline_runtime_support.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime_support.py)
- [services/orchestration.py](/d:/Projects/tg_post_analyzer/services/orchestration.py)
- [scripts/run_ai_pipeline.py](/d:/Projects/tg_post_analyzer/scripts/run_ai_pipeline.py)
- [docs/runtime_runbook.md](/d:/Projects/tg_post_analyzer/docs/runtime_runbook.md)

Allowed to add:
- tests only

Must not modify:
- [db/models.py](/d:/Projects/tg_post_analyzer/db/models.py)
- [api/routers/reports.py](/d:/Projects/tg_post_analyzer/api/routers/reports.py) except if a test reveals hidden auto path through router coupling

### 2.4. Data/API/runtime impact
- DB/schema: none
- ORM/models: none
- API contracts: none
- Runtime orchestration: yes, AI/telegram report auto scheduling disabled
- UI/frontend: none
- Logs/metrics/monitoring: docs/runtime expectation only
- Docs/runbook: yes

### 2.5. Definition of Ready (DoR)
- найдены все auto-enqueue paths;
- подтверждено, что пользовательский API запуск остается in scope;
- нет blockers по operating mode.

### 2.6. Definition of Done (DoD)
- нет ни одного auto path, создающего report jobs после ingest без user API request;
- tests покрывают отсутствие auto-enqueue;
- docs обновлены.

### 2.7. Acceptance tests
- После обычного ingest нового поста в `jobs` не появляется `BUILD_POST_REPORT`.
- После rebuild events/processes в `jobs` не появляются новые `BUILD_EVENT_REPORT` / `BUILD_PROCESS_REPORT`, если пользователь их не запросил.
- `POST /api/reports/post/{id}/update` по-прежнему ставит `BUILD_POST_REPORT`.

### 2.8. Expected artifacts
- tests delta
- docs/runbook delta

---

## Package P2. Passive AI Worker Runtime

### 2.1. Scope
Должно быть реализовано:
- AI worker продолжает работать как daemon;
- AI worker обрабатывает только входящие report jobs;
- циклы worker’а не создают новые report jobs по таймеру/фоновой эвристике.

Не должно быть реализовано:
- dependency orchestration;
- reactions;
- websocket;
- dedupe.

### 2.2. Architectural guardrails
- Нельзя:
  - выключать AI worker процесс целиком;
  - менять существующие `BUILD_*_REPORT` job names;
  - добавлять новые cron jobs.
- Нельзя ломать:
  - existing `run_ai_pipeline.py` entrypoint;
  - runtime heartbeat semantics.
- Можно:
  - ограничить AI worker до passive consumer behavior;
  - удалить auto scheduling внутри AI cycle.

### 2.3. File-level scope
Likely to modify:
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [scripts/run_ai_pipeline.py](/d:/Projects/tg_post_analyzer/scripts/run_ai_pipeline.py)
- [services/monitoring.py](/d:/Projects/tg_post_analyzer/services/monitoring.py) only if runtime description needs metric/health adjustment
- [docs/runtime_topology.md](/d:/Projects/tg_post_analyzer/docs/runtime_topology.md)
- [docs/runtime_runbook.md](/d:/Projects/tg_post_analyzer/docs/runtime_runbook.md)

Allowed to add:
- tests only

Must not modify:
- report business logic in [services/reporting.py](/d:/Projects/tg_post_analyzer/services/reporting.py)
- API router contracts

### 2.4. Data/API/runtime impact
- DB/schema: none
- ORM/models: none
- API contracts: none
- Runtime orchestration: yes
- UI/frontend: none
- Logs/metrics/monitoring: heartbeat/monitor wording maybe
- Docs/runbook: yes

### 2.5. DoR
- P1 completed
- подтверждено, что AI worker должен оставаться daemon, а не on-demand process startup

### 2.6. DoD
- AI worker не инициирует report creation сам;
- только consumes queued `BUILD_*_REPORT`;
- runtime docs обновлены.

### 2.7. Acceptance tests
- `run_ai_cycle` не создает новые report jobs в пустой системе.
- При наличии queued `BUILD_POST_REPORT` job worker выполняет его.
- Heartbeat AI worker продолжает обновляться при отсутствии jobs.

### 2.8. Expected artifacts
- tests
- docs delta

---

## Package P3. Reactions Capability Spike

### 2.1. Scope
Должно быть реализовано:
- подтвердить практический доступ к reactions для:
  - channel posts
  - discussion comments
- зафиксировать наблюдаемое поведение и ограничения;
- зафиксировать fallback strategy, если comments reactions недоступны или частично доступны.

Не должно быть реализовано:
- production persistence;
- migration;
- UI changes;
- report changes.

### 2.2. Architectural guardrails
- Запрещено:
  - менять production schema;
  - менять production API contracts;
  - внедрять временный экспериментальный протокол как final behavior без отдельного согласования.
- Можно:
  - написать временный spike script/test;
  - задокументировать результаты.
- Нельзя делать unsafe выбор fallback без spike result.

### 2.3. File-level scope
Likely to modify:
- scripts or tests area only
- maybe [client/telegram.py](/d:/Projects/tg_post_analyzer/client/telegram.py) only if read-helper needed for spike

Allowed to add:
- spike script
- spike notes doc
- exploratory tests

Must not modify:
- [db/models.py](/d:/Projects/tg_post_analyzer/db/models.py)
- [services/TGqueries.py](/d:/Projects/tg_post_analyzer/services/TGqueries.py) for production behavior
- API routers

### 2.4. Data/API/runtime impact
- DB/schema: none
- ORM/models: none
- API contracts: none
- Runtime orchestration: none in prod
- UI/frontend: none
- Logs/metrics/monitoring: none
- Docs/runbook: yes, spike note

### 2.5. DoR
- доступ к рабочим/тестовым Telegram данным;
- список target scenarios for spike;
- согласовано, что результат spike gate’ит дальнейшие packages.

### 2.6. DoD
- spike выполнен;
- documented result exists;
- fallback strategy explicitly recorded.

### 2.7. Acceptance tests
- Есть reproducible proof для post reactions support or explicit failure.
- Есть reproducible proof для comment reactions support or explicit failure.
- Есть written fallback statement based on observed result, not assumption.

### 2.8. Expected artifacts
- spike script or exploratory test
- spike note/document

---

## Package P4. Priority and Graceful Preemption

### 2.1. Scope
Должно быть реализовано:
- priority model inside existing jobs mechanism;
- graceful preemption after current work unit;
- return to previous ingest cycle after urgent job processing;
- распространяется на все relevant queues per backlog.

Не должно быть реализовано:
- новые очереди;
- новые worker processes;
- полная переработка scheduling architecture.

### 2.2. Architectural guardrails
- Нельзя:
  - вводить новые queues;
  - вводить новую jobs table;
  - менять runtime topology;
  - прерывать работу “посреди” DB mutation / unsafe boundary.
- Нельзя ломать:
  - existing fetch/lock semantics;
  - job retry/dead-letter behavior.
- Можно:
  - менять priority values/selection logic;
  - менять loop control points.
- Переименование существующих jobs запрещено.

### 2.3. File-level scope
Likely to modify:
- [services/jobs.py](/d:/Projects/tg_post_analyzer/services/jobs.py)
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [services/pipeline_runtime_common.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime_common.py)
- [services/orchestration.py](/d:/Projects/tg_post_analyzer/services/orchestration.py)
- tests around scheduler/runtime/jobs

Allowed to add:
- tests only

Must not modify:
- [db/models.py](/d:/Projects/tg_post_analyzer/db/models.py) unless absolutely necessary and separately approved
- API contracts

Uncertainty:
- exact file touch surface for “return to previous ingest cycle” may depend on current loop boundaries inside `run_telegram_cycle` and helpers.

### 2.4. Data/API/runtime impact
- DB/schema: maybe none if reusing current priority field
- ORM/models: maybe none
- API contracts: none
- Runtime orchestration: high impact
- UI/frontend: none
- Logs/metrics/monitoring: yes, preemption metrics later
- Docs/runbook: yes

### 2.5. DoR
- known worker loop boundaries;
- known current priority usage;
- decision that no new queues/job types are allowed in this package.

### 2.6. DoD
- urgent user/service jobs are processed ahead of background jobs using existing jobs system;
- worker does not interrupt mid-operation;
- previous ingest cycle resumes after urgent work.

### 2.7. Acceptance tests
- When a high-priority report-related job is queued while backlog exists, it is selected before lower-priority background jobs.
- Current DB transaction/work unit completes before preemption.
- After urgent job completion, worker continues prior backlog processing.
- No dead-letter/retry regressions in existing job families.

### 2.8. Expected artifacts
- tests
- docs delta
- maybe monitor metric hook points, but not final metrics package

---

## Package P5. Readiness and Dependency Orchestration

### 2.1. Scope
Должно быть реализовано:
- explicit readiness evaluation for:
  - post report
  - event report
  - process report
- dependency-driven orchestration:
  - process → event reports
  - event → post reports
  - post → refresh post data
- long-running async behavior instead of immediate failure when dependencies missing.

Не должно быть реализовано:
- новые runtime roles;
- новые public endpoints;
- user-visible tree of child jobs;
- unsanctioned degraded semantics beyond explicitly agreed partial reactions behavior.

### 2.2. Architectural guardrails
- Нельзя:
  - изобретать новые сущности готовности;
  - вводить новые readiness markers in schema, because backlog explicitly rejected separate markers;
  - invent new websocket events here;
  - invent new API statuses here.
- Нельзя ломать:
  - existing job table;
  - existing report endpoint entrypoints.
- Можно:
  - использовать current job system to enqueue dependency work;
  - reuse existing `BUILD_*_REPORT` jobs.
- New job types:
  - запрещено добавлять без отдельного подтверждения.
- Переименование job names запрещено.

### 2.3. File-level scope
Likely to modify:
- [services/reporting.py](/d:/Projects/tg_post_analyzer/services/reporting.py)
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [services/orchestration.py](/d:/Projects/tg_post_analyzer/services/orchestration.py)
- [api/routers/reports.py](/d:/Projects/tg_post_analyzer/api/routers/reports.py) only if response handling for duplicate/deferred messaging is already agreed elsewhere
- tests for report flow

Allowed to add:
- helper module(s) inside `services/` only if minimal and clearly scoped to readiness/orchestration

Must not modify:
- DB schema
- public API route paths
- monitor routes

Uncertainty:
- exact placement of readiness evaluator is not yet fixed and is decision-sensitive.

### 2.4. Data/API/runtime impact
- DB/schema: none directly
- ORM/models: none directly
- API contracts: indirect only via async behavior; no new endpoint allowed
- Runtime orchestration: high impact
- UI/frontend: depends on status handling package, not here
- Logs/metrics/monitoring: some log changes likely
- Docs/runbook: yes

### 2.5. DoR
- P3 completed
- preemption model available or at least stable enough
- agreed interpretation of partial post readiness for missing comment reactions
- agreed dedupe/duplicate behavior package not conflicting

### 2.6. DoD
- report jobs do not fail immediately on missing dependencies when dependencies are collectible;
- dependency jobs are enqueued using existing job mechanism;
- process/event/post cascades work per agreed hierarchy.

### 2.7. Acceptance tests
- Requesting process report with missing child reports triggers background dependency cascade and does not expose child job tree to user contract.
- Requesting event report with missing post reports triggers post-level build path.
- Requesting post report with stale/missing source data triggers refresh post data path.
- If a dependency cannot be collected quickly, parent job remains async/long-running rather than silently failing.

### 2.8. Expected artifacts
- tests
- docs delta
- maybe internal helper module
- rollout note on long-running job behavior

---

## Package P6. Reactions Persistence

### 2.1. Scope
Должно быть реализовано:
- add reactions payload fields to `posts` and `comments`;
- support storing:
  - `results[]`
  - `total`
  - `collected_at`
  - `source`
  - `is_complete`
- update ORM/schema serialization support.

Не должно быть реализовано:
- collection logic;
- report usage;
- UI usage.

### 2.2. Architectural guardrails
- Нельзя:
  - создавать новую reactions table without explicit approval;
  - создавать separate readiness marker columns;
  - добавлять per-emoji columns.
- Нельзя ломать:
  - existing posts/comments API serialization for old rows.
- Можно:
  - add JSON-compatible fields to existing models if approved by migration task.
- New enum/status/table:
  - запрещено.
- Rename existing entities:
  - запрещено.

### 2.3. File-level scope
Likely to modify:
- [db/models.py](/d:/Projects/tg_post_analyzer/db/models.py)
- [alembic/versions/*](/d:/Projects/tg_post_analyzer/alembic/versions)
- [schemas/post.py](/d:/Projects/tg_post_analyzer/schemas/post.py)
- [schemas/comment.py](/d:/Projects/tg_post_analyzer/schemas/comment.py)
- maybe [schemas/dashboard.py](/d:/Projects/tg_post_analyzer/schemas/dashboard.py) later but preferably not in this package

Allowed to add:
- one Alembic migration
- maybe shared schema helper if minimal

Must not modify:
- collection logic in `services/TGqueries.py`
- report generation logic

Uncertainty:
- exact response-schema expansion points depend on agreed API package boundaries.

### 2.4. Data/API/runtime impact
- DB/schema: yes
- ORM/models: yes
- API contracts: maybe internal serialization only; public expansion should be coordinated with P9
- Runtime orchestration: none
- UI/frontend: none directly
- Logs/metrics/monitoring: none
- Docs/runbook: maybe schema note

### 2.5. DoR
- P3 completed
- reactions payload contract explicitly fixed
- fallback semantics do not require additional fields beyond agreed payload

### 2.6. DoD
- migration applied;
- ORM reads/writes payload;
- old rows remain valid;
- serializers handle missing payload.

### 2.7. Acceptance tests
- A post row can persist and load reactions payload.
- A comment row can persist and load reactions payload.
- Existing API/model serialization does not fail when reactions payload is null/absent.
- Migration is reversible or rollback-safe per current Alembic practice.

### 2.8. Expected artifacts
- migration
- model updates
- serializer/schema updates
- tests

---

## Package P7. Reactions Collection and Refresh Post Data

### 2.1. Scope
Должно быть реализовано:
- collect/update reactions for posts;
- collect/update reactions for comments if supported;
- apply fallback if comment reactions unsupported/partial;
- integrate collection into existing refresh post data flow;
- backfill mechanism for historical data.

Не должно быть реализовано:
- new queue topology;
- new job type without approval;
- redesign of TG pipeline architecture.

### 2.2. Architectural guardrails
- Нельзя:
  - invent a new job type unless separately approved;
  - rename `COLLECT_COMMENTS` or change its external references without explicit approval;
  - add separate readiness markers.
- Нельзя ломать:
  - current comments collection semantics where comments themselves still must be collected.
- Можно:
  - expand implementation of existing refresh path;
  - store partial completeness in agreed payload.
- Fallback strategy must come from P3, not assumption.

### 2.3. File-level scope
Likely to modify:
- [services/TGqueries.py](/d:/Projects/tg_post_analyzer/services/TGqueries.py)
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [services/ingest.py](/d:/Projects/tg_post_analyzer/services/ingest.py)
- maybe [services/queries.py](/d:/Projects/tg_post_analyzer/services/queries.py)
- scripts for backfill
- tests around comment job semantics

Allowed to add:
- minimal helper module for reactions collection if needed inside `services/`
- backfill script

Must not modify:
- unrelated dashboard services
- auth/services not related to collection

Uncertainty:
- exact insertion point for reactions collection in current comment flow is implementation-sensitive and depends on spike result.

### 2.4. Data/API/runtime impact
- DB/schema: writes to new reactions payload fields
- ORM/models: uses P6 model fields
- API contracts: none directly here
- Runtime orchestration: yes, refresh job behavior changes
- UI/frontend: none directly
- Logs/metrics/monitoring: maybe additional warnings for partial support
- Docs/runbook: yes, collection semantics note

### 2.5. DoR
- P3 completed
- P6 completed
- fallback strategy approved
- clear decision whether to reuse current `COLLECT_COMMENTS` as-is or just broaden internals without renaming

### 2.6. DoD
- refresh flow updates comments plus reactions per agreed support;
- partial support is persisted in payload;
- backfill mechanism exists.

### 2.7. Acceptance tests
- Refreshing post data updates post reactions.
- If comment reactions are supported, they are collected and saved.
- If comment reactions are not fully supported, payload reflects partial/incomplete state without crashing job.
- Existing comment refresh still updates comments themselves.
- Historical backfill can run in batches without breaking current data.

### 2.8. Expected artifacts
- code changes in collection flow
- tests
- backfill script
- docs note/fallback note

---

## Package P8. Report Enrichment

### 2.1. Scope
Должно быть реализовано:
- update post report generation to consume reactions and audience stance inputs;
- include argumentation about commenters’ position;
- include coverage factor in report metadata;
- ensure event/process reports use enriched child reports only to the extent already in backlog.

Не должно быть реализовано:
- new report storage tables;
- new report types;
- new public report APIs;
- architectural rewrite of reporting subsystem.

### 2.2. Architectural guardrails
- Нельзя:
  - invent new payload statuses;
  - invent new report entity types;
  - redesign report chaining logic beyond agreed cascade.
- Можно:
  - adjust prompt/input assembly;
  - extend report payload metadata if compatible with current report_json usage and explicitly agreed.
- Нельзя ломать:
  - existing `Report`, `EventReport`, `ProcessReport` persistence model.

### 2.3. File-level scope
Likely to modify:
- [services/reporting.py](/d:/Projects/tg_post_analyzer/services/reporting.py)
- [schemas/report.py](/d:/Projects/tg_post_analyzer/schemas/report.py) only if current contract requires explicit schema update
- maybe `agents.reporter` integration touchpoints if prompt inputs are assembled there
- tests/fixtures around reports

Allowed to add:
- test fixtures
- minimal helper(s) if absolutely required

Must not modify:
- DB schema here
- router paths

Uncertainty:
- exact schema impact on `schemas/report.py` is blocked by contract decision for coverage metadata exposure.

### 2.4. Data/API/runtime impact
- DB/schema: no new table/field required if using existing report_json
- ORM/models: none likely
- API contracts: maybe report_json/content shape changes if exposed
- Runtime orchestration: none major
- UI/frontend: maybe if coverage surfaced in UI, but not required here
- Logs/metrics/monitoring: maybe coverage metrics downstream
- Docs/runbook: yes, report semantics docs

### 2.5. DoR
- P7 completed
- agreed behavior for partial comment reactions in report generation
- agreed whether coverage factor is exposed only in report_json or public contract too

### 2.6. DoD
- post reports consume reactions-aware inputs;
- summary/insights reflect audience stance and argumentation;
- coverage factor is recorded in agreed location;
- event/process builds remain functional.

### 2.7. Acceptance tests
- Post report generated from collected reactions/comments includes audience stance information.
- Report generation does not crash when comment reactions are partial/unavailable per agreed fallback.
- Coverage factor is present in agreed metadata.
- Event/process report generation still works on enriched child reports.

### 2.8. Expected artifacts
- reporting logic changes
- updated tests/fixtures
- docs delta

---

## Package P9. Async Status Delivery and UI Contract Updates

### 2.1. Scope
Должно быть реализовано:
- product status `building_report`;
- websocket/push progress delivery;
- frontend support in inline badge/job drawer;
- retry CTA for agreed failure cases;
- reactions display in table/detail views.

Не должно быть реализовано:
- additional UX stages not agreed;
- user-visible tree of dependency jobs;
- new public channels/protocols beyond agreed transport.

### 2.2. Architectural guardrails
- Нельзя:
  - invent websocket event schema without explicit contract;
  - change existing route paths without separate task;
  - add new user-facing statuses beyond agreed set without decision.
- Можно:
  - extend existing API payloads where explicitly agreed;
  - add frontend handling for blocked duplicate/building states.
- Нельзя ломать:
  - existing auth model without approval.

### 2.3. File-level scope
Likely to modify:
- backend API/status delivery area: exact files uncertain
- frontend modules showing reports/jobs/posts/comments dashboards
- possibly [api/main.py](/d:/Projects/tg_post_analyzer/api/main.py) if transport mount needed
- [docs/api.md](/d:/Projects/tg_post_analyzer/docs/api.md)

Allowed to add:
- websocket handling files/modules only after contract approved
- frontend adapters/components/tests

Must not modify:
- unrelated admin/auth flows beyond what status delivery requires

Uncertainty:
- exact backend file scope for websocket support is unknown because current codebase transport layer for push is not established.

### 2.4. Data/API/runtime impact
- DB/schema: maybe none
- ORM/models: none
- API contracts: yes
- Runtime orchestration: maybe status publication hooks
- UI/frontend: high impact
- Logs/metrics/monitoring: maybe connection/emit logging
- Docs/runbook: yes

### 2.5. DoR
- explicit websocket/push contract agreed
- explicit duplicate blocked response contract agreed
- touched backend transport files identified
- no blockers on auth/security for push transport

### 2.6. DoD
- user sees `building_report` progress in agreed UI points;
- reactions visible in agreed UI placements;
- retry CTA appears for agreed cases only.

### 2.7. Acceptance tests
- Generate/Update transitions UI into `building_report`.
- Progress updates arrive without manual refresh.
- Table views display total reactions.
- Detail view displays per-emoji breakdown.
- UI distinguishes:
  - not collected yet
  - unavailable technically
  - absent/zero
- Retry CTA appears for `dependency_timeout` / `reactions_unavailable` only if those states are part of agreed contract.

### 2.8. Expected artifacts
- API contract update
- frontend changes/tests
- websocket contract doc
- docs delta

---

## Package P10. Duplicate Request Guard

### 2.1. Scope
Должно быть реализовано:
- prevent repeated report request on same entity within 1 hour;
- return user-facing message instead of creating duplicate heavy job;
- frontend blocked state.

Не должно быть реализовано:
- tree of related jobs;
- new dedupe tables;
- new enum/status unless explicitly approved.

### 2.2. Architectural guardrails
- Нельзя:
  - invent new persistence table for dedupe without approval;
  - decide dedupe-after-failure behavior without decision;
  - change existing job contract silently.
- Можно:
  - use current jobs table and existing timing fields if sufficient.
- Нельзя ломать:
  - API accepted-job behavior for valid requests.

### 2.3. File-level scope
Likely to modify:
- [api/routers/reports.py](/d:/Projects/tg_post_analyzer/api/routers/reports.py)
- maybe [api/routers/linking.py](/d:/Projects/tg_post_analyzer/api/routers/linking.py) only if same rule extends there, but backlog only speaks about reports
- [services/jobs.py](/d:/Projects/tg_post_analyzer/services/jobs.py) maybe helper query logic
- tests

Allowed to add:
- minimal helper in services if needed

Must not modify:
- DB schema, unless explicitly approved later

Uncertainty:
- dedupe window anchor for failed/completed job is not fixed.

### 2.4. Data/API/runtime impact
- DB/schema: ideally none
- ORM/models: none
- API contracts: yes, duplicate response/message
- Runtime orchestration: minor
- UI/frontend: yes, blocked state
- Logs/metrics/monitoring: blocked duplicate metric maybe later
- Docs/runbook: API behavior note

### 2.5. DoR
- explicit dedupe policy for:
  - active build
  - completed build
  - failed build
- exact duplicate response contract agreed

### 2.6. DoD
- duplicate request within policy window does not enqueue new job;
- user gets agreed response;
- frontend handles it.

### 2.7. Acceptance tests
- Second request for same entity inside 1 hour does not create second report job.
- Response contains agreed message/shape.
- First valid request still creates job as before.
- Behavior after failed report follows agreed policy.

### 2.8. Expected artifacts
- API behavior change
- tests
- docs delta
- maybe frontend UI update

---

## Package P11. Logging and Observability

### 2.1. Scope
Должно быть реализовано:
- demote low-value technical INFO logs to DEBUG where appropriate;
- preserve job-state INFO logs and important warnings/errors;
- add agreed metrics:
  - AI idle time
  - on-demand report latency
  - dependency completion latency
  - reaction coverage
  - percentage reports built with complete inputs
  - user request preemption count
  - blocked duplicate requests
  - coverage factor impact metric
- expose metrics in existing monitor surface if agreed.

Не должно быть реализовано:
- new observability stack;
- new frontend admin dashboard unless separately agreed.

### 2.2. Architectural guardrails
- Нельзя:
  - remove WARNING/ERROR/FloodWait diagnostics;
  - invent new monitor endpoints unless separately approved.
- Можно:
  - adjust log levels;
  - extend existing monitor payloads if contract update is in scope.
- Нельзя ломать:
  - current runtime health endpoints.

### 2.3. File-level scope
Likely to modify:
- [services/TGqueries.py](/d:/Projects/tg_post_analyzer/services/TGqueries.py)
- [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py)
- [services/monitoring.py](/d:/Projects/tg_post_analyzer/services/monitoring.py)
- [api/routers/monitor.py](/d:/Projects/tg_post_analyzer/api/routers/monitor.py) if payload changes need explicit pass-through
- docs/runbook

Allowed to add:
- tests
- docs notes

Must not modify:
- core auth/data model for metrics only

Uncertainty:
- exact monitor payload schema additions are not fixed.

### 2.4. Data/API/runtime impact
- DB/schema: maybe none if metrics derived
- ORM/models: none
- API contracts: maybe monitor payload expansion
- Runtime orchestration: minor hooks
- UI/frontend: none required
- Logs/metrics/monitoring: high impact
- Docs/runbook: yes

### 2.5. DoR
- agreed metric names and where exposed;
- agreed log policy examples;
- clarity whether monitor API may be extended.

### 2.6. DoD
- noisy technical INFO logs removed from normal operation;
- agreed metrics observable;
- docs updated.

### 2.7. Acceptance tests
- Example low-value INFO lines no longer appear at INFO level.
- Job state lines still appear.
- WARNING/ERROR/FloodWait still appear.
- Monitor payload contains agreed metrics with stable keys.
- Metrics do not require new background collectors outside current runtime model.

### 2.8. Expected artifacts
- code changes
- tests
- monitor docs delta
- rollout note

---

## 4. BLOCKERS

### Blocker B1. Reactions capability result is unknown
- Неопределенность: реальная поддержка reactions для discussion comments через текущий Telethon stack не подтверждена.
- Блокирует packages:
  - P6
  - P7
  - P8
  - частично P5
- Почему нельзя безопасно делать assumptions:
  - это меняет runtime behavior, fallback semantics и readiness interpretation.
- Какой ответ нужен:
  - documented spike result:
    - posts supported? yes/no
    - comments supported? yes/no/partial
    - observable limitations

### Blocker B2. Fallback behavior for partial comment reactions is not formally frozen
- Неопределенность: заказчик сказал “делать отчет по тому, что удалось собрать”, но не зафиксировано, как именно это отражается в system behavior and contracts.
- Блокирует packages:
  - P5
  - P7
  - P8
  - P9
- Почему нельзя безопасно делать assumptions:
  - влияет на readiness, report semantics, API/UI states.
- Какой ответ нужен:
  - explicit rule:
    - what counts as “collect attempt completed”
    - whether post report may proceed when comment reactions partial
    - how partiality is exposed to API/UI/report metadata

### Blocker B3. WebSocket/push contract is undefined
- Неопределенность: указан только transport requirement and UI placement, но не event schema, auth model, lifecycle events.
- Блокирует packages:
  - P9
- Почему нельзя безопасно делать assumptions:
  - это публичный runtime/API behavior.
- Какой ответ нужен:
  - minimal websocket/push contract:
    - channel/auth model
    - payload shape
    - event list
    - reconnect expectation

### Blocker B4. Duplicate request policy after failure/completion is undefined
- Неопределенность: есть правило “ограничение 1 час”, но не зафиксировано от чего отсчитывать окно и действует ли оно после failed job.
- Блокирует packages:
  - P10
  - частично P9
- Почему нельзя безопасно делать assumptions:
  - меняет API behavior и UX semantics.
- Какой ответ нужен:
  - exact dedupe window anchor and failure semantics.

### Blocker B5. Priority/preemption implementation boundary per runtime path is not frozen
- Неопределенность: “после текущей работы” согласовано логически, но не зафиксировано, что считается current work unit в каждом цикле/обработчике.
- Блокирует packages:
  - P4
  - частично P5
- Почему нельзя безопасно делать assumptions:
  - выбор boundary влияет на integrity and latency.
- Какой ответ нужен:
  - explicit implementation boundary for:
    - telegram ingest loop
    - comment refresh job
    - rebuild job
    - AI report job

---

## 5. DECISION-NEEDED ITEMS

### Decision D1. Reuse `COLLECT_COMMENTS` vs broaden internals only
- Варианты:
  1. Оставить имя/job type `COLLECT_COMMENTS`, расширив только внутреннюю реализацию.
  2. Переименовать job type или ввести новый тип.
- Последствия:
  - Вариант 1: минимально инвазивно, но имя не соответствует смыслу.
  - Вариант 2: чище семантически, но затрагивает contracts/tests/runtime and violates current backlog minimalism.
- Рекомендуемый вопрос:
  - “Подтверждаем ли, что для MVP не меняем имя job type и только расширяем внутреннюю семантику?” - да

### Decision D2. Coverage factor exposure surface
- Варианты:
  1. Только monitor metric.
  2. Monitor metric + report_json metadata.
  3. Monitor metric + report_json + UI/API exposure.
- Последствия:
  - Чем шире exposure, тем больше contract work.
- Рекомендуемый вопрос:
  - “Coverage factor должен быть только внутренней метрикой или частью report_json/публичного контракта?” - внутренней

### Decision D3. Duplicate request blocked response contract
- Варианты:
  1. HTTP error response.
  2. 200/202-style payload с сообщением `already_building`.
  3. existing job reference reuse.
- Последствия:
  - влияет на API/frontend compatibility.
- Рекомендуемый вопрос:
  - “Какой response shape должен получить frontend при повторном запросе в течение 1 часа?” - 3

### Decision D4. Monitor API expansion policy
- Варианты:
  1. Расширять существующие monitor snapshots.
  2. Не менять monitor API сейчас, только logs/internal metrics.
- Последствия:
  - влияет на P11 scope and contract updates.
- Рекомендуемый вопрос:
  - “Можно ли расширять существующий `/api/monitor/*` payload новыми метриками без отдельной контрактной задачи?” - нет

### Decision D5. Backfill operating limits
- Варианты:
  1. отдельный script/manual batched run
  2. background jobs through current jobs table
- Последствия:
  - влияет на rollout safety и runtime load.
- Рекомендуемый вопрос:
  - “Backfill reactions должен идти через отдельный script или через текущий jobs механизм?” - отдельный script.

---

## 6. Safe assumptions

- Existing API endpoints for report generation remain the entrypoints.
- Existing `BUILD_POST_REPORT`, `BUILD_EVENT_REPORT`, `BUILD_PROCESS_REPORT` job types remain in use.
- Existing jobs table is the only allowed queueing mechanism unless separately approved.
- Existing runtime roles (`api`, `scheduler`, `telegram_pipeline`, `ai_pipeline`) remain unchanged.
- Existing accepted-job async interaction pattern remains valid for report requests.
- No user-visible child-job tree is required.
- Logging cleanup may safely demote low-value technical INFO lines to DEBUG as long as WARNING/ERROR/FloodWait remain.

---

## 7. Unsafe assumptions

- Выбирать fallback behavior for comment reactions before P3 spike result.
- Самостоятельно определять websocket event payload/schema.
- Самостоятельно решать dedupe policy after failure/completion.
- Самостоятельно вводить новые job types, queues, tables, enums, statuses.
- Самостоятельно переименовывать `COLLECT_COMMENTS` or other existing job names.
- Самостоятельно добавлять separate readiness marker fields in DB.
- Самостоятельно расширять public API contracts beyond explicitly agreed scope.
- Самостоятельно вводить new monitor endpoints.
- Самостоятельно выбирать, что такое “current work unit” per runtime path without explicit decision.

---

## 8. Executable task breakdown

## Package P1. Disable Auto Report Generation

### Task P1-T1. Inventory auto report enqueue paths
- Цель: найти все production code paths, автоматически создающие `BUILD_*_REPORT`.
- Зачем нужна: без полного inventory нельзя безопасно отключить авто-генерацию.
- Preconditions:
  - package P1 started
- Inputs:
  - current codebase
  - jobs flow
- Outputs:
  - exact list of enqueue call sites
- Конкретные изменения:
  - no code changes required if this is analysis-only task
  - produce file list + call graph
- Dependencies: none
- Edge cases:
  - indirect enqueue through helper wrappers
  - auto scheduling in AI cycle vs telegram/runtime support
- Test coverage required:
  - none, analysis task
- Expected artifacts:
  - change plan note
  - touched-files inventory
- Done criteria:
  - every auto path is identified and labeled keep/remove

### Task P1-T2. Remove auto post/event/process report enqueue
- Цель: убрать production code paths, auto-creating report jobs.
- Зачем нужна: реализует новую operating model.
- Preconditions:
  - P1-T1 complete
- Inputs:
  - identified enqueue paths
- Outputs:
  - code no longer enqueues report jobs from background flows
- Конкретные изменения:
  - edit identified enqueue call sites
  - preserve API-triggered enqueue
- Dependencies:
  - P1-T1
- Edge cases:
  - stale-marking logic may still remain without enqueue
  - cascade helper may be used by API-driven flow and must not be fully removed if still needed
- Test coverage required:
  - regression test on no auto report creation after ingest
- Expected artifacts:
  - code diff
  - regression tests
- Done criteria:
  - background ingest/rebuild does not auto-create report jobs

### Task P1-T3. Update runtime docs
- Цель: синхронизировать docs с новой mode.
- Зачем нужна: избежать operational confusion.
- Preconditions:
  - P1-T2 complete
- Inputs:
  - final behavior
- Outputs:
  - updated runbook/runtime docs
- Конкретные изменения:
  - edit runtime docs
- Dependencies:
  - P1-T2
- Edge cases:
  - avoid overpromising readiness behavior not yet implemented
- Test coverage required:
  - none
- Expected artifacts:
  - docs delta
- Done criteria:
  - docs no longer mention background report generation

---

## Package P2. Passive AI Worker Runtime

### Task P2-T1. Identify AI cycle scheduling behavior
- Цель: isolate which parts of AI cycle still schedule report work.
- Зачем нужна: avoid accidental behavior drift.
- Preconditions:
  - P1 complete
- Inputs:
  - current `run_ai_cycle` / related helpers
- Outputs:
  - exact functions to modify
- Конкретные изменения:
  - analysis only
- Dependencies:
  - P1
- Edge cases:
  - helper functions reused elsewhere
- Test coverage required:
  - none
- Expected artifacts:
  - file-level change plan
- Done criteria:
  - all scheduling logic identified

### Task P2-T2. Convert AI worker to passive consumer
- Цель: worker only consumes queued `BUILD_*_REPORT` jobs.
- Зачем нужна: implement agreed mode.
- Preconditions:
  - P2-T1
- Inputs:
  - current worker loop
- Outputs:
  - passive consumer behavior
- Конкретные изменения:
  - remove/disable job creation in AI cycle
  - keep polling and consuming
- Dependencies:
  - P2-T1
- Edge cases:
  - empty queue heartbeat
  - no-op cycle behavior
- Test coverage required:
  - no job creation when queue empty
  - still processes queued report jobs
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - empty AI cycle creates no new jobs

### Task P2-T3. Adjust monitoring wording if needed
- Цель: align monitoring/docs with passive AI mode.
- Зачем нужна: avoid wrong operational assumptions.
- Preconditions:
  - P2-T2
- Inputs:
  - final runtime behavior
- Outputs:
  - updated wording only
- Конкретные изменения:
  - docs/monitor wording
- Dependencies:
  - P2-T2
- Edge cases:
  - avoid changing monitor payload contract if not needed
- Test coverage required:
  - none
- Expected artifacts:
  - docs delta
- Done criteria:
  - runtime docs describe passive consumer mode

---

## Package P3. Reactions Capability Spike

### Task P3-T1. Spike post reactions retrieval
- Цель: verify retrieval path for post reactions.
- Зачем нужна: gate persistence/collection implementation.
- Preconditions:
  - access to test Telegram data
- Inputs:
  - existing Telethon client/session
- Outputs:
  - confirmed support or failure note
- Конкретные изменения:
  - add exploratory script/test
- Dependencies:
  - none
- Edge cases:
  - channels with no reactions
  - custom emojis
- Test coverage required:
  - exploratory only
- Expected artifacts:
  - spike output note
- Done criteria:
  - documented reproducible result

### Task P3-T2. Spike comment reactions retrieval
- Цель: verify retrieval path for comment reactions.
- Зачем нужна: this is main technical uncertainty.
- Preconditions:
  - P3-T1 not required
- Inputs:
  - discussion comments
- Outputs:
  - confirmed support / partial / unsupported result
- Конкретные изменения:
  - add exploratory script/test
- Dependencies:
  - none
- Edge cases:
  - source entity vs discussion chat
  - comments with no reactions
- Test coverage required:
  - exploratory only
- Expected artifacts:
  - spike output note
- Done criteria:
  - documented reproducible result

### Task P3-T3. Record fallback strategy from spike
- Цель: freeze behavior for unsupported/partial comments reactions.
- Зачем нужна: unblock downstream packages.
- Preconditions:
  - P3-T1, P3-T2
- Inputs:
  - spike results
- Outputs:
  - documented fallback decision
- Конкретные изменения:
  - produce decision note/doc
- Dependencies:
  - P3-T1
  - P3-T2
- Edge cases:
  - supported for posts but partial for comments
- Test coverage required:
  - none
- Expected artifacts:
  - fallback note
- Done criteria:
  - blocker B1 resolved

---

## Package P4. Priority and Graceful Preemption

### Task P4-T1. Freeze current-work-unit boundaries
- Цель: define implementation boundary for safe preemption.
- Зачем нужна: avoid mid-operation interruption.
- Preconditions:
  - blocker B5 resolved
- Inputs:
  - runtime loops
- Outputs:
  - per-path boundary list
- Конкретные изменения:
  - analysis/spec note
- Dependencies:
  - B5
- Edge cases:
  - comment refresh job with nested operations
  - long-running rebuild
- Test coverage required:
  - none
- Expected artifacts:
  - implementation boundary note
- Done criteria:
  - explicit boundary exists for each relevant worker path

### Task P4-T2. Implement priority selection using existing jobs system
- Цель: high-priority jobs are selected first.
- Зачем нужна: user/service requests must preempt backlog.
- Preconditions:
  - P4-T1
- Inputs:
  - existing jobs priority/fetch
- Outputs:
  - updated selection behavior
- Конкретные изменения:
  - edit jobs fetch/ordering logic and/or enqueue priorities
- Dependencies:
  - P4-T1
- Edge cases:
  - active locks
  - retry jobs
- Test coverage required:
  - ordering tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - priority ordering proven by tests

### Task P4-T3. Implement graceful loop preemption and resume
- Цель: finish current work, then process urgent, then resume previous cycle.
- Зачем нужна: meet product requirement without data corruption.
- Preconditions:
  - P4-T2
- Inputs:
  - current loop control points
- Outputs:
  - resume behavior
- Конкретные изменения:
  - update runtime loops
- Dependencies:
  - P4-T2
- Edge cases:
  - burst of urgent jobs
  - backlog starvation
- Test coverage required:
  - resume behavior tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - worker returns to original cycle after urgent work

---

## Package P5. Readiness and Dependency Orchestration

### Task P5-T1. Implement readiness evaluator
- Цель: centralize readiness logic.
- Зачем нужна: one place for report dependency rules.
- Preconditions:
  - blocker B2 resolved
- Inputs:
  - agreed readiness rules
- Outputs:
  - evaluator/helper
- Конкретные изменения:
  - add minimal helper or integrate into reporting flow
- Dependencies:
  - B2
- Edge cases:
  - partial comment reactions
- Test coverage required:
  - unit tests for post/event/process
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - evaluator exists and is used

### Task P5-T2. Wire post dependency orchestration
- Цель: missing post inputs trigger refresh post data path.
- Зачем нужна: one-click post report generation.
- Preconditions:
  - P5-T1
  - P4 ready enough
  - P7 behavior known
- Inputs:
  - report request
  - readiness evaluator
- Outputs:
  - urgent dependency job path
- Конкретные изменения:
  - update report build flow
- Dependencies:
  - P5-T1
  - P7
- Edge cases:
  - dependency already in progress
- Test coverage required:
  - post report with missing deps
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - post report request triggers dependency collection instead of hard fail

### Task P5-T3. Wire event/process cascading dependencies
- Цель: parent reports trigger child report builds as needed.
- Зачем нужна: agreed cascade behavior.
- Preconditions:
  - P5-T1
- Inputs:
  - event/process request
- Outputs:
  - dependency cascade
- Конкретные изменения:
  - update event/process report flow
- Dependencies:
  - P5-T1
  - P2
- Edge cases:
  - already running child jobs
  - no child entities
- Test coverage required:
  - event and process cascade tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - process request can trigger event/post build chain through existing jobs

---

## Package P6. Reactions Persistence

### Task P6-T1. Add reactions fields to models
- Цель: extend `posts` and `comments` models.
- Зачем нужна: storage layer for reactions.
- Preconditions:
  - P3 done
- Inputs:
  - agreed payload fields
- Outputs:
  - ORM fields
- Конкретные изменения:
  - update model definitions
- Dependencies:
  - P3
- Edge cases:
  - nullable old rows
- Test coverage required:
  - model serialization tests
- Expected artifacts:
  - model diff
- Done criteria:
  - models support payload

### Task P6-T2. Create Alembic migration
- Цель: persist model changes in DB.
- Зачем нужна: schema support.
- Preconditions:
  - P6-T1
- Inputs:
  - model changes
- Outputs:
  - migration
- Конкретные изменения:
  - add migration file
- Dependencies:
  - P6-T1
- Edge cases:
  - defaults/nullability
- Test coverage required:
  - migration smoke
- Expected artifacts:
  - migration
- Done criteria:
  - migration applies cleanly

### Task P6-T3. Update serialization/schema support
- Цель: code can read/write missing and present payload safely.
- Зачем нужна: avoid crashes on mixed data.
- Preconditions:
  - P6-T1
- Inputs:
  - models
- Outputs:
  - serializers/schema support
- Конкретные изменения:
  - update relevant schemas/helpers
- Dependencies:
  - P6-T1
- Edge cases:
  - absent payload
- Test coverage required:
  - serialization tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - missing payload is handled safely

---

## Package P7. Reactions Collection and Refresh Post Data

### Task P7-T1. Implement post reactions collection
- Цель: collect/store reactions for posts.
- Зачем нужна: mandatory post report input.
- Preconditions:
  - P3 done
  - P6 done
- Inputs:
  - Telegram message/post
  - reactions storage fields
- Outputs:
  - stored post reactions payload
- Конкретные изменения:
  - integrate into refresh path
- Dependencies:
  - P3
  - P6
- Edge cases:
  - no reactions
  - unsupported payload shape
- Test coverage required:
  - collection test
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - post refresh stores reactions payload

### Task P7-T2. Implement comment reactions collection with fallback
- Цель: collect/store comment reactions when possible and persist partial completeness when not.
- Зачем нужна: agreed MVP + fallback behavior.
- Preconditions:
  - P3 fallback fixed
  - P6 done
- Inputs:
  - discussion comments
  - fallback strategy
- Outputs:
  - stored comment reactions payload or explicit partial state
- Конкретные изменения:
  - integrate into comment refresh flow
- Dependencies:
  - P3
  - P6
- Edge cases:
  - partial support
  - unsupported comments reactions
- Test coverage required:
  - fallback tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - comment reactions path obeys fallback decision

### Task P7-T3. Integrate into existing refresh job semantics
- Цель: existing refresh path updates comments + reactions.
- Зачем нужна: avoid new job types.
- Preconditions:
  - P7-T1
  - P7-T2
- Inputs:
  - existing `COLLECT_COMMENTS`/refresh flow
- Outputs:
  - widened refresh implementation
- Конкретные изменения:
  - update job handler and collection service
- Dependencies:
  - P7-T1
  - P7-T2
- Edge cases:
  - increased job duration
  - retries
- Test coverage required:
  - integration tests for full refresh
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - one refresh pass updates all agreed post data

### Task P7-T4. Add reactions backfill mechanism
- Цель: fill historical data.
- Зачем нужна: reactions needed beyond new posts.
- Preconditions:
  - P7-T3
- Inputs:
  - existing posts/comments
- Outputs:
  - batch backfill path
- Конкретные изменения:
  - add script or current-jobs-based mechanism after decision D5
- Dependencies:
  - P7-T3
  - D5
- Edge cases:
  - batching
  - rate limiting
- Test coverage required:
  - smoke test
- Expected artifacts:
  - backfill script/notes
- Done criteria:
  - historical backfill can run safely in batches

---

## Package P8. Report Enrichment

### Task P8-T1. Update post report input assembly
- Цель: include reactions and audience stance inputs.
- Зачем нужна: enrich report content.
- Preconditions:
  - P7 complete
  - blocker B2 resolved
- Inputs:
  - post text/comments/reactions
- Outputs:
  - updated generation input
- Конкретные изменения:
  - edit report input assembly
- Dependencies:
  - P7
- Edge cases:
  - partial comment reactions
- Test coverage required:
  - input assembly tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - generation input now includes agreed reactions context

### Task P8-T2. Update post report output semantics
- Цель: summary/insights includes audience stance and argumentation.
- Зачем нужна: meet product requirement.
- Preconditions:
  - P8-T1
- Inputs:
  - updated generation output contract
- Outputs:
  - enriched report output
- Конкретные изменения:
  - edit reporting logic/validation fixtures
- Dependencies:
  - P8-T1
- Edge cases:
  - no reactions
  - partial coverage
- Test coverage required:
  - representative report tests
- Expected artifacts:
  - fixtures/tests
- Done criteria:
  - output satisfies agreed semantics

### Task P8-T3. Record coverage factor
- Цель: persist coverage factor in agreed place.
- Зачем нужна: support observability and report semantics.
- Preconditions:
  - decision D2
- Inputs:
  - reaction completeness state
- Outputs:
  - coverage factor field in agreed metadata surface
- Конкретные изменения:
  - edit report metadata generation
- Dependencies:
  - D2
- Edge cases:
  - zero reactions
  - partial comments support
- Test coverage required:
  - metadata tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - coverage factor present where agreed

---

## Package P9. Async Status Delivery and UI Contract Updates

### Task P9-T1. Freeze websocket/push contract
- Цель: unblock implementation.
- Зачем нужна: no safe implementation without contract.
- Preconditions:
  - blocker B3 resolved
- Inputs:
  - agreed transport contract
- Outputs:
  - written contract
- Конкретные изменения:
  - docs/spec only
- Dependencies:
  - B3
- Edge cases:
  - reconnect
- Test coverage required:
  - none
- Expected artifacts:
  - websocket contract doc
- Done criteria:
  - contract exists and is implementation-ready

### Task P9-T2. Implement backend progress publishing
- Цель: emit agreed progress events.
- Зачем нужна: power async UX.
- Preconditions:
  - P9-T1
- Inputs:
  - report job lifecycle
- Outputs:
  - backend progress publication
- Конкретные изменения:
  - backend transport code
- Dependencies:
  - P9-T1
- Edge cases:
  - long-running dependencies
  - completion/failure
- Test coverage required:
  - backend transport tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - progress events emitted in agreed flow

### Task P9-T3. Implement frontend building_report UI
- Цель: show async progress in agreed UI spots.
- Зачем нужна: required user experience.
- Preconditions:
  - P9-T2
- Inputs:
  - progress events
  - `building_report` contract
- Outputs:
  - inline badge / job drawer updates
- Конкретные изменения:
  - frontend components/adapters
- Dependencies:
  - P9-T2
- Edge cases:
  - reconnect
  - stale page
- Test coverage required:
  - frontend component/integration tests
- Expected artifacts:
  - frontend diff
  - tests
- Done criteria:
  - user sees live `building_report`

### Task P9-T4. Add reactions UI rendering
- Цель: show reactions in agreed places.
- Зачем нужна: product requirement.
- Preconditions:
  - P6 and P7 complete
- Inputs:
  - API payload
- Outputs:
  - total in table, breakdown in detail
- Конкретные изменения:
  - frontend tables/details
- Dependencies:
  - P6
  - P7
- Edge cases:
  - unavailable/not collected/zero
- Test coverage required:
  - frontend rendering tests
- Expected artifacts:
  - frontend diff
  - tests
- Done criteria:
  - reactions are visible per agreed UX

### Task P9-T5. Add retry CTA for agreed failure states
- Цель: let user retry after supported failures.
- Зачем нужна: agreed UX.
- Preconditions:
  - exact failure contract known
- Inputs:
  - duplicate/dependency/reactions error states
- Outputs:
  - retry CTA
- Конкретные изменения:
  - frontend state handling
- Dependencies:
  - contract decision
- Edge cases:
  - duplicate request should not show retry
- Test coverage required:
  - UI state tests
- Expected artifacts:
  - frontend diff
- Done criteria:
  - retry shown only for agreed cases

---

## Package P10. Duplicate Request Guard

### Task P10-T1. Freeze dedupe policy
- Цель: resolve blocker B4.
- Зачем нужна: safe implementation impossible otherwise.
- Preconditions:
  - B4 resolved
- Inputs:
  - final business rule
- Outputs:
  - written policy
- Конкретные изменения:
  - spec note only
- Dependencies:
  - B4
- Edge cases:
  - failed/completed/recent jobs
- Test coverage required:
  - none
- Expected artifacts:
  - dedupe policy note
- Done criteria:
  - policy implementation-ready

### Task P10-T2. Implement backend duplicate guard
- Цель: prevent duplicate report job enqueue.
- Зачем нужна: reduce waste/load.
- Preconditions:
  - P10-T1
- Inputs:
  - current jobs state
  - request entity id/type
- Outputs:
  - no duplicate enqueue inside policy window
- Конкретные изменения:
  - update report request paths
- Dependencies:
  - P10-T1
- Edge cases:
  - active build
  - recent success/failure depending on policy
- Test coverage required:
  - backend duplicate tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - duplicate requests no longer enqueue duplicates

### Task P10-T3. Implement user-facing blocked response handling
- Цель: return agreed response and frontend UI.
- Зачем нужна: complete product behavior.
- Preconditions:
  - response contract fixed
- Inputs:
  - duplicate guard result
- Outputs:
  - API response + frontend display
- Конкретные изменения:
  - router + frontend handling
- Dependencies:
  - P10-T2
- Edge cases:
  - repeated clicks
- Test coverage required:
  - API and UI tests
- Expected artifacts:
  - code diff
  - tests
- Done criteria:
  - user gets clear blocked message

---

## Package P11. Logging and Observability

### Task P11-T1. Demote low-value technical logs
- Цель: reduce noise.
- Зачем нужна: operational clarity.
- Preconditions:
  - examples of low-value lines agreed
- Inputs:
  - current log points
- Outputs:
  - DEBUG-level low-value technical logs
- Конкретные изменения:
  - adjust log levels in TG pipeline/comment flow
- Dependencies:
  - none
- Edge cases:
  - preserve debug trace availability
- Test coverage required:
  - log-level behavior checks if practical
- Expected artifacts:
  - code diff
- Done criteria:
  - example noisy logs absent at INFO

### Task P11-T2. Preserve high-value logs
- Цель: keep useful diagnostics.
- Зачем нужна: avoid operational blindness.
- Preconditions:
  - none
- Inputs:
  - current warnings/errors/job logs
- Outputs:
  - retained warning/error/job-state logs
- Конкретные изменения:
  - selective log review
- Dependencies:
  - P11-T1
- Edge cases:
  - FloodWait warnings
- Test coverage required:
  - smoke/log assertions if feasible
- Expected artifacts:
  - code diff
- Done criteria:
  - job state and warning/error logs remain

### Task P11-T3. Add agreed metrics to monitor flow
- Цель: observe new on-demand model.
- Зачем нужна: verify business goal and detect regressions.
- Preconditions:
  - metric names and exposure agreed
- Inputs:
  - current monitoring snapshots
- Outputs:
  - monitor payload contains agreed metrics
- Конкретные изменения:
  - extend monitoring service and maybe monitor router docs
- Dependencies:
  - contract agreement
  - P2/P4/P5/P7/P10 as needed
- Edge cases:
  - metrics derivable from current data only
- Test coverage required:
  - monitor payload tests
- Expected artifacts:
  - code diff
  - tests
  - docs delta
- Done criteria:
  - agreed metrics are observable

---

## 9. Rollout / rollback notes

## P1
- Rollout:
  - code deploy only
  - no migration
- Rollback:
  - restore removed auto-enqueue paths
- Monitor:
  - report job creation rate should drop after ingest
- Degradation symptoms:
  - unexpected background `BUILD_*_REPORT` still appearing

## P2
- Rollout:
  - deploy AI worker code, restart worker
- Rollback:
  - restore previous `run_ai_cycle`
- Monitor:
  - AI heartbeat still healthy
  - queued report jobs still processed
- Degradation:
  - AI worker idle forever despite queued jobs
  - empty cycles still creating jobs

## P3
- Rollout:
  - non-prod or controlled manual run only
- Rollback:
  - delete spike scripts if not needed
- Monitor:
  - none in prod
- Degradation:
  - none, exploratory package

## P4
- Rollout:
  - no schema change
  - deploy with careful runtime observation
- Rollback:
  - restore previous priority/preemption logic
- Monitor:
  - backlog ordering
  - ingest throughput
  - preemption count
- Degradation:
  - backlog starvation
  - growing pending lag
  - worker loops not resuming

## P5
- Rollout:
  - after P4 stable
  - feature flag recommended if feasible without architecture changes
- Rollback:
  - disable dependency orchestration path and revert to current immediate behavior
- Monitor:
  - long-running report jobs
  - dependency queue growth
- Degradation:
  - parent jobs stuck forever
  - repeated dependency requeue loops

## P6
- Rollout:
  - migration before code paths using new fields
- Rollback:
  - code rollback first; DB rollback only if safe per migration design
- Monitor:
  - migration success
  - serializer errors
- Degradation:
  - ORM/schema mismatches
  - null handling failures

## P7
- Rollout:
  - after P6
  - controlled enablement recommended
  - backfill only after live path validated
- Rollback:
  - disable reactions collection logic
  - keep schema fields unused if needed
- Monitor:
  - refresh job latency
  - FloodWait/RPC warnings
  - reactions payload completeness
- Degradation:
  - comment refresh jobs become too slow
  - increased Telegram errors
  - partial payload corruption

## P8
- Rollout:
  - after P7 stable
  - no migration needed if using current report_json
- Rollback:
  - revert prompt/input changes
- Monitor:
  - report generation failure rate
  - latency
  - coverage factor presence
- Degradation:
  - report failures increase
  - low-quality outputs

## P9
- Rollout:
  - backend transport first, then frontend
  - websocket contract must be frozen before rollout
- Rollback:
  - disable push path, fall back to current job polling behavior if still available
- Monitor:
  - connection success
  - event delivery rate
  - frontend error rate
- Degradation:
  - no progress updates
  - auth/reconnect failures
  - UI stuck in `building_report`

## P10
- Rollout:
  - backend guard first, then frontend blocked UX
- Rollback:
  - remove dedupe guard
- Monitor:
  - duplicate blocked count
  - user error complaints
- Degradation:
  - false-positive duplicate blocks
  - duplicate jobs still being created

## P11
- Rollout:
  - can be phased
  - log level changes first, metrics second
- Rollback:
  - restore previous log levels / metric additions
- Monitor:
  - log usefulness
  - monitor payload integrity
- Degradation:
  - missing warnings/errors
  - broken monitor routes/payloads

---

## 10. Execution order

### Critical path
1. P1 Disable Auto Report Generation
2. P2 Passive AI Worker Runtime
3. P3 Reactions Capability Spike
4. Resolve blockers B1, B2, B5
5. P4 Priority and Graceful Preemption
6. P6 Reactions Persistence
7. P7 Reactions Collection and Refresh Post Data
8. P5 Readiness and Dependency Orchestration
9. P8 Report Enrichment
10. Resolve blockers B3, B4
11. P10 Duplicate Request Guard
12. P9 Async Status Delivery and UI Contract Updates
13. P11 Logging and Observability

### Parallelizable work
- P1 and preparatory analysis for P2 can overlap slightly.
- P3 spike can start as soon as possible, in parallel with P1/P2.
- Parts of P11 logging cleanup can start after P2 without waiting for reactions.
- Frontend discovery for P9 can start before implementation, but actual coding is blocked by contract decisions.
- Dedupe policy design work can happen in parallel with P5/P8, but implementation is blocked by B4.

### Hard blockers
- P6/P7/P8 blocked by P3 result.
- P4 blocked by B5 if current-work-unit boundaries are not agreed.
- P9 blocked by B3.
- P10 blocked by B4.

### What cannot start before blockers close
- Do not start production reactions persistence/collection before P3.
- Do not start websocket coding before contract freeze.
- Do not start duplicate guard coding before dedupe policy freeze.
- Do not finalize readiness orchestration before partial reactions semantics are frozen.

### What should start with change plan before code changes
- P1
- P2
- P4
- P5
- P7
- P9
- P10

---

## 11. Codex operating instructions

- Перед началом каждого package Codex обязан выдать:
  1. change plan
  2. explicit assumptions
  3. touched files
  4. blockers / decision-needed items
- Codex не имеет права:
  - менять scope package;
  - делать скрытый рефакторинг;
  - добавлять новые job types, таблицы, enum’ы, статусы, websocket channels, cron jobs, queues, runtime roles без явного подтверждения;
  - самостоятельно решать `DECISION-NEEDED ITEMS`;
  - выбирать fallback strategy до результата spike;
  - придумывать публичные API/websocket contracts.
- Если package `NOT READY`, Codex должен:
  - остановиться;
  - вернуть список blockers;
  - не переходить к коду.
- Если file-level scope неясен, Codex должен сначала сделать code inventory и показать touched-files plan.
- Если реализация требует изменения публичного контракта, а контракт не зафиксирован, Codex должен остановиться и запросить решение.
- Для каждого task Codex должен:
  - перечислить preconditions;
  - проверить, что dependencies уже выполнены;
  - только потом вносить код.
- После реализации Codex должен вернуть:
  - список реально измененных файлов;
  - список тестов, которые были добавлены/обновлены;
  - список оставшихся рисков;
  - rollback note для выполненного package.
- Если во время работы обнаружен скрытый architectural refactor pressure, Codex не должен “попутно улучшать систему”, а должен остановиться и зафиксировать out-of-scope issue.
