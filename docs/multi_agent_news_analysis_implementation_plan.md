# Multi-Agent News Analysis Implementation Plan

Source basis:
- Spec: `d:\Telegram Desktop\спецификация.docx`
- Repo inspection date: `2026-04-13`

Interpretation boundary:
- The spec speaks about an “article”, but the current repo has no separate article entity or article ingestion path.
- In the existing codebase, the closest real source object is `Post.text` loaded in [services/reporting.py](../services/reporting.py) and hydrated by [services/ingestion_core.py](../services/ingestion_core.py).
- The plan below therefore maps:
  - article -> `posts.text`
  - public opinion -> `comments` rows for one post
  - multi-agent execution -> one existing AI report job in [services/pipeline_runtime.py](../services/pipeline_runtime.py)

## Repo-informed implementation map:
- The only production AI reporting path is `scripts/run_ai_pipeline.py` -> [services/pipeline_runtime.py](../services/pipeline_runtime.py) -> `run_ai_jobs()` -> [services/reporting.py](../services/reporting.py); there is no second AI worker or agent runtime to extend safely.
- Post report generation is centralized in [services/reporting.py](../services/reporting.py)::`build_post_report`, which already loads `Post`, `Channel`, ordered `Comment` rows, computes an input signature, calls [agents/reporter.py](../agents/reporter.py), and persists one `Report` row.
- The current reporter already has deterministic semantic preprocessing in [agents/reporter.py](../agents/reporter.py): keyword extraction, named entities, representative samples, thread-shape metrics, sentiment hints, reactions enrichment, and fallback handling.
- Event and process reports are not LLM-generated today; they are deterministic aggregations in [services/report_aggregation.py](../services/report_aggregation.py) and [services/reporting.py](../services/reporting.py)::`build_event_report_draft` / `build_process_report_draft`, so post-report compatibility is a hard downstream constraint.
- Public report schemas are fixed in [schemas/report.py](../schemas/report.py). `PostReportPayload` is strict (`extra="forbid"`) and currently allows only `ready|skipped_min_comments|failed`, while event/process payloads are also validated and later reused downstream.
- Frontend detail pages already read structured report fields directly from `report_json`: post detail reads `summary` and `topics` in [frontend/src/modules/workspace/post-detail/components/ReportBlock.tsx](../frontend/src/modules/workspace/post-detail/components/ReportBlock.tsx), event detail reads `summary` and `cross_post_topics` in [frontend/src/modules/workspace/event-detail/mappers.ts](../frontend/src/modules/workspace/event-detail/mappers.ts), and process detail reads `summary` and `stage_analysis` in [frontend/src/modules/workspace/process-detail/mappers.ts](../frontend/src/modules/workspace/process-detail/mappers.ts).
- Internal traces cannot simply be written into `report_json` without a public boundary, because [api/routers/reports.py](../api/routers/reports.py) returns `ReportOut.report_json` and [api/routers/linking.py](../api/routers/linking.py) returns `latest_report.report_json` directly to frontend consumers.
- Existing report invalidation already uses `report_json.meta` as a machine-owned channel: [services/reporting.py](../services/reporting.py)::`sync_post_report_staleness` stores `input_signature`, stale markers, and refresh metadata there, and [services/monitoring.py](../services/monitoring.py) reads `report_json["meta"]["coverage_factor"]` from DB.
- Existing runtime topology docs explicitly forbid adding new runtime roles for reporting: [docs/runtime_topology.md](./runtime_topology.md) and [docs/runtime_runbook.md](./runtime_runbook.md) define a single passive `ai_pipeline` that consumes queued jobs only.
- Feature flags and staged rollout already exist as a validated settings system, not as ad hoc env toggles: [services/settings_defaults.py](../services/settings_defaults.py), [services/settings_validation.py](../services/settings_validation.py), [services/settings_store.py](../services/settings_store.py), [api/routers/settings.py](../api/routers/settings.py), and admin UI registry files under `frontend/src/modules/admin/`.
- There is no external retrieval provider, retrieval client, retrieval table, or retrieval service in the repo. Existing “retrieval-like” code is limited to post-linking embeddings in [services/linking/](../services/linking), which solves post-to-post graph building, not external context acquisition for report generation.
- The current async/report UX assumes one accepted report job per entity and one terminal result via `/api/jobs/*` and `/api/reports/progress/ws` in [api/routers/report_progress.py](../api/routers/report_progress.py); multi-agent execution must stay hidden inside that one job contract.
- Tests already pin critical behavior that this rollout must preserve: passive AI worker semantics in [tests/test_ai_runtime_mode.py](../tests/test_ai_runtime_mode.py), report semantics and schema compatibility in [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py), preprocessing behavior in [tests/test_reporter_preprocessing.py](../tests/test_reporter_preprocessing.py), async API contracts in [tests/test_reports_async_api.py](../tests/test_reports_async_api.py), and lifecycle cascades in [tests/integration/test_orchestration_lifecycle_real_db.py](../tests/integration/test_orchestration_lifecycle_real_db.py).

## Package P1. Establish Contract-Preserving Rollout Boundary

### 2.1. Scope
Должно быть реализовано:
- добавить rollout gate для multi-agent режима в существующую settings/feature систему;
- добавить публичную boundary-функцию, которая удаляет `meta.multi_agent` из API-ответов, если внутренние трассы будут сохраняться в `report_json`;
- зафиксировать, какие report fields и statuses уже потребляются downstream;
- подготовить безопасный default: multi-agent path выключен по умолчанию.

Не должно быть реализовано:
- новая runtime-служба;
- новая DB-таблица для трасс;
- изменение текста промптов или orchestration логики.

### 2.2. Architectural guardrails
- Запрещено:
- добавлять новый worker/process вместо использования `ai_pipeline`;
- публиковать internal traces через `GET /api/reports/post/{id}` или `GET /api/events/{id}` / `GET /api/processes/{id}`.
- Нельзя ломать:
- accepted-job contract в [api/routers/reports.py](../api/routers/reports.py);
- WebSocket progress contract в [api/routers/report_progress.py](../api/routers/report_progress.py).
- Нельзя менять:
- shape top-level `ReportOut`;
- job types в [services/jobs.py](../services/jobs.py).
- Можно:
- добавить новые validated settings keys;
- добавить sanitizer/helper внутри существующего reporting/API слоя.

### 2.3. File-level scope
Likely to modify:
- [services/settings_defaults.py](../services/settings_defaults.py)
- [services/settings_validation.py](../services/settings_validation.py)
- [services/settings_store.py](../services/settings_store.py)
- [api/routers/settings.py](../api/routers/settings.py)
- [api/routers/reports.py](../api/routers/reports.py)
- [api/routers/linking.py](../api/routers/linking.py)
- [frontend/src/modules/admin/settings-registry.ts](../frontend/src/modules/admin/settings-registry.ts)
- [frontend/src/modules/admin/settings-catalog.ts](../frontend/src/modules/admin/settings-catalog.ts)

Allowed to add:
- targeted backend test file for response redaction and rollout settings
- targeted frontend settings-registry test coverage

Must not modify:
- [db/models.py](../db/models.py)
- [alembic/versions/](../alembic/versions)
- [scripts/run_ai_pipeline.py](../scripts/run_ai_pipeline.py)

### 2.4. Data/API/runtime impact
- DB/schema: no migration; reuse existing `app_settings` and `report_json`.
- ORM/models: none if traces remain in JSON and are redacted at API boundary.
- API contracts: preserved; only internal fields become explicitly stripped from public responses.
- Runtime orchestration: none yet; rollout remains opt-in.
- UI/frontend: admin settings UI may expose rollout toggles; report/detail screens should remain unchanged.
- Logs/metrics/monitoring: none yet.
- Docs/runbook: update rollout notes in [docs/runtime_runbook.md](./runtime_runbook.md) or adjacent runbook doc.

### 2.5. Definition of Ready (DoR)
- agreed default rollout position for multi-agent mode;
- explicit decision whether internal traces live in persisted `report_json` or only transient job payload;
- list of public consumers that must not see `meta.multi_agent`.

### 2.6. Definition of Done (DoD)
- new rollout settings are validated, readable via `/api/settings/effective`, and hidden/internal rows remain excluded;
- API serializers strip `meta.multi_agent` consistently from public report responses;
- no existing report/job API contract regresses under default settings.

### 2.7. Acceptance tests
- `/api/settings/effective` returns new rollout flags with canonical defaults.
- `/api/reports/post/{id}` omits `meta.multi_agent` while preserving existing `summary/topics/status` payload.
- `/api/events/{id}` and `/api/processes/{id}` omit internal trace payload from `latest_report.report_json`.

### 2.8. Expected artifacts
- validated rollout configuration keys
- API redaction tests and runbook note for internal-vs-public report data

## Package P2. Integrate Spec Vocabulary Into The Existing Reporter Path

### 2.1. Scope
Должно быть реализовано:
- перевести current post-report prompt/config layer в явное соответствие спецификации;
- зафиксировать spec-derived constants for agent order, epistemic labels, sufficiency labels, review budget, and fallback states inside the current reporter path;
- определить internal meta schema shape `meta.multi_agent` as a repo-local implementation contract.

Не должно быть реализовано:
- полный multi-agent execution;
- retrieval provider;
- event/process report refactor.

### 2.2. Architectural guardrails
- Запрещено:
- переключать runtime на [agents/task.yaml](../agents/task.yaml) или [agents/agent.yaml](../agents/agent.yaml), потому что текущий production path их не вызывает;
- держать два разных prompt source-of-truth для одного и того же runtime path.
- Нельзя ломать:
- `PostReportPayload.model_validate()` in [schemas/report.py](../schemas/report.py);
- existing invalid-output fallback path in [agents/reporter.py](../agents/reporter.py).
- Нельзя менять:
- current job envelope and result URLs;
- event/process draft builders.
- Можно:
- расширить internal prompt builder and internal normalized payload helpers;
- добавить spec-aligned optional fields into internal processing structures before public mapping.

### 2.3. File-level scope
Likely to modify:
- [agents/reporter.py](../agents/reporter.py)
- [services/reporting.py](../services/reporting.py)
- [schemas/report.py](../schemas/report.py)
- [tests/test_reporter_preprocessing.py](../tests/test_reporter_preprocessing.py)
- [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py)

Allowed to add:
- one dedicated test module for internal meta schema validation

Must not modify:
- [services/report_aggregation.py](../services/report_aggregation.py)
- [services/pipeline_runtime.py](../services/pipeline_runtime.py)

### 2.4. Data/API/runtime impact
- DB/schema: none; JSON payload only.
- ORM/models: none.
- API contracts: none in this package if internal schema stays redacted.
- Runtime orchestration: none yet; prompt/config only.
- UI/frontend: none.
- Logs/metrics/monitoring: optional debug logging only; no new monitor contract.
- Docs/runbook: document internal schema and spec alignment in `docs/`.

### 2.5. Definition of Ready (DoR)
- P1 redaction boundary is in place or accepted as prerequisite;
- spec-derived enum decisions are frozen: `fact|derived|interpretation|external|uncertain`, `sufficient|limited|weak_signal|insufficient`, `ready|limited|insufficient_data`.

### 2.6. Definition of Done (DoD)
- one repo-local internal schema contract exists and is used consistently by the reporter path;
- prompt builder references the five required analytical components from the spec;
- tests fail if internal meta shape or epistemic labels drift.

### 2.7. Acceptance tests
- reporter prompt builder contains event/context/reaction/interpretation/consequences requirements.
- internal meta schema validator rejects plain-string epistemic arrays where structured entries are required.
- fallback payload keeps schema-valid public output while internal spec metadata remains machine-readable.

### 2.8. Expected artifacts
- internal `meta.multi_agent` contract definition implemented in current reporter path
- spec-aligned preprocessing/prompt tests

## Package P3. Expand Semantic Preprocessing And Sufficiency Signals

### 2.1. Scope
Должно быть реализовано:
- расширить existing deterministic preprocessing in [agents/reporter.py](../agents/reporter.py) so it emits article/comment sufficiency inputs, structured evidence candidates, and public-opinion strength markers;
- вычислять explicit data sufficiency statuses before LLM synthesis;
- подготовить structured inputs for Context, Expert, and Public Opinion stages without yet changing runtime orchestration shape.

Не должно быть реализовано:
- retrieval network calls;
- reviewer reruns;
- public contract expansion.

### 2.2. Architectural guardrails
- Запрещено:
- заменять semantic preprocessing keyword matching-only heuristics;
- строить public opinion из единичного comment without repetition/noise checks.
- Нельзя ломать:
- current `build_post_signal_summary()` callers;
- min-comments fallback semantics already relied on by tests.
- Нельзя менять:
- comment persistence path in [services/TGqueries.py](../services/TGqueries.py);
- ingest pipeline in [services/ingestion_core.py](../services/ingestion_core.py).
- Можно:
- enrich preprocessing outputs with sufficiency, evidence spans, noise heuristics, and discussion-state signals;
- reuse existing representative samples, entities, reactions coverage, and thread depth data.

### 2.3. File-level scope
Likely to modify:
- [agents/reporter.py](../agents/reporter.py)
- [services/reporting.py](../services/reporting.py)
- [tests/test_reporter_preprocessing.py](../tests/test_reporter_preprocessing.py)
- [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py)
- [tests/test_tgqueries_comment_collection_regression.py](../tests/test_tgqueries_comment_collection_regression.py)

Allowed to add:
- dedicated preprocessing test file for sufficiency scoring

Must not modify:
- [db/models.py](../db/models.py)
- [api/routers/posts.py](../api/routers/posts.py)

### 2.4. Data/API/runtime impact
- DB/schema: none.
- ORM/models: none.
- API contracts: none yet.
- Runtime orchestration: preprocessing payload grows, but still inside one `build_post_report()` call.
- UI/frontend: none.
- Logs/metrics/monitoring: optional debug counters only.
- Docs/runbook: note mapping `article -> Post.text`, `comments -> ordered Comment rows`.

### 2.5. Definition of Ready (DoR)
- spec thresholds or repo-safe heuristics for weak/limited/insufficient are agreed;
- current deterministic inputs and test fixtures are cataloged.

### 2.6. Definition of Done (DoD)
- preprocessing returns enough machine-readable data to feed Context/Expert/Public Opinion stages;
- article/comment sufficiency can be computed without external services;
- public opinion branch can explicitly output `discussion_state` and `weak_signal` instead of over-claiming.

### 2.7. Acceptance tests
- empty or whitespace-only `Post.text` produces article insufficiency.
- low-signal comments produce `weak_signal` instead of confident public-opinion output.
- noisy/conflicted comments produce `discussion_state=conflicted` or equivalent structured limited state.

### 2.8. Expected artifacts
- enriched preprocessing payload with sufficiency inputs
- tests for semantic preprocessing and discussion-state heuristics

## Package P4. Add Retrieval Policy And Explicit Gap Layer

### 2.1. Scope
Должно быть реализовано:
- реализовать retrieval decision/policy evaluation inside the existing report build path;
- записывать в internal trace, когда retrieval required / not required / attempted / unavailable;
- оформить отсутствие реального retrieval provider как explicit gap, а не как скрытое предположение;
- поддержать spec-compliant fallback when retrieval is required but unavailable.

Не должно быть реализовано:
- новый external retrieval service;
- web crawler;
- новая очередь или background runtime для retrieval.

### 2.2. Architectural guardrails
- Запрещено:
- использовать existing linking embeddings in [services/linking/](../services/linking) as fake external retrieval;
- генерировать `external` claims without an actual retrieval source object.
- Нельзя ломать:
- current offline/local AI runtime assumptions;
- passive AI worker contract in [tests/test_ai_runtime_mode.py](../tests/test_ai_runtime_mode.py).
- Нельзя менять:
- runtime topology in [docs/runtime_topology.md](./runtime_topology.md);
- `scripts/run_ai_pipeline.py` entrypoint responsibilities.
- Можно:
- add policy evaluation and trace statuses such as `required`, `used=false`, `status=insufficient`;
- add future-compatible provider interface only if it stays unbound by default.

### 2.3. File-level scope
Likely to modify:
- [agents/reporter.py](../agents/reporter.py)
- [services/reporting.py](../services/reporting.py)
- [services/settings_defaults.py](../services/settings_defaults.py)
- [services/settings_validation.py](../services/settings_validation.py)
- [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py)
- [tests/test_ai_runtime_mode.py](../tests/test_ai_runtime_mode.py)

Allowed to add:
- test module for retrieval policy and retrieval-gap fallback behavior
- docs note describing the explicit provider gap

Must not modify:
- [services/linking/no_llm_pipeline.py](../services/linking/no_llm_pipeline.py)
- [services/keyword_graph.py](../services/keyword_graph.py)
- [db/models.py](../db/models.py)

### 2.4. Data/API/runtime impact
- DB/schema: none if retrieval trace stays in internal JSON.
- ORM/models: none.
- API contracts: none if retrieval block is redacted from public output.
- Runtime orchestration: one extra decision stage inside `build_post_report()`.
- UI/frontend: none.
- Logs/metrics/monitoring: optional retrieval-attempt / retrieval-unavailable logs.
- Docs/runbook: explicit “no provider attached” limitation and rollout note.

### 2.5. Definition of Ready (DoR)
- agreed decision rules for when retrieval is mandatory vs optional;
- explicit acceptance that provider implementation is a later gap package unless a real repo-backed integration is added.

### 2.6. Definition of Done (DoD)
- post-report path can explain, in machine-readable form, why retrieval was or was not required;
- required-but-missing retrieval never produces fabricated `external` claims;
- limited fallback path is deterministic and test-covered.

### 2.7. Acceptance tests
- retrieval-required scenario with no provider ends in `limited` or `insufficient_data`, never `ready`.
- internal trace marks `retrieval.required=true`, `used=false`, `status=insufficient`.
- no public payload field claims external context unless a source list exists.

### 2.8. Expected artifacts
- retrieval policy evaluator inside current report path
- explicit documented provider gap and fallback tests

## Package P5. Implement Sequential Multi-Agent Orchestration In The Existing AI Job

### 2.1. Scope
Должно быть реализовано:
- реализовать stages `Context -> Routing -> Expert -> Public Opinion -> Synthesis` внутри текущего `build_post_report()` / `generate_post_report_payload()` flow;
- использовать один existing report job and one persisted report row per request;
- позволить selective rerun of an internal stage inside the same job object, not via a new queue.

Не должно быть реализовано:
- отдельные agent services/processes;
- child jobs per stage;
- изменение accepted-job API.

### 2.2. Architectural guardrails
- Запрещено:
- fan-out into new runtime workers or queue types;
- обходить [services/reporting.py](../services/reporting.py) as the canonical report build entry.
- Нельзя ломать:
- `run_ai_jobs()` loop and timeout semantics in [services/pipeline_runtime.py](../services/pipeline_runtime.py);
- existing job result persistence in [services/jobs.py](../services/jobs.py).
- Нельзя менять:
- `JobType.BUILD_POST_REPORT`;
- event/process report build entrypoints.
- Можно:
- refactor internals of [agents/reporter.py](../agents/reporter.py) into stage functions;
- store internal stage outputs in machine-readable trace form.

### 2.3. File-level scope
Likely to modify:
- [agents/reporter.py](../agents/reporter.py)
- [services/reporting.py](../services/reporting.py)
- [services/pipeline_runtime.py](../services/pipeline_runtime.py)
- [tests/test_ai_runtime_mode.py](../tests/test_ai_runtime_mode.py)
- [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py)

Allowed to add:
- orchestration-focused unit test file

Must not modify:
- [scripts/run_telegram_pipeline.py](../scripts/run_telegram_pipeline.py)
- [scripts/run_scheduler.py](../scripts/run_scheduler.py)
- [services/report_aggregation.py](../services/report_aggregation.py)

### 2.4. Data/API/runtime impact
- DB/schema: none.
- ORM/models: none.
- API contracts: none if output still resolves to `ReportOut`.
- Runtime orchestration: internal stage graph added inside one AI job call.
- UI/frontend: none.
- Logs/metrics/monitoring: optional stage timing logs.
- Docs/runbook: update AI worker behavior note to explain internal sequential stages.

### 2.5. Definition of Ready (DoR)
- stage input/output contracts are frozen from P2/P3/P4;
- timeout budget allocation per stage is defined relative to `ai_job_timeout_seconds`.

### 2.6. Definition of Done (DoD)
- one post-report job runs all non-review stages sequentially inside current runtime;
- internal trace shows each completed stage exactly once unless explicitly rerun;
- failure in one stage yields spec-aligned fallback status without breaking the job contract.

### 2.7. Acceptance tests
- one `build_post_report` call produces stage outputs for context/routing/expert/public_opinion/synthesis.
- stage failure triggers fallback without creating extra jobs.
- `run_ai_jobs()` still sees exactly one processed `build_post_report` job and stable `_job_result`.

### 2.8. Expected artifacts
- sequential stage execution inside the current reporter path
- orchestration tests that preserve one-job semantics

## Package P6. Add Reviewer Loop And Failure Policy Enforcement

### 2.1. Scope
Должно быть реализовано:
- добавить bounded Reviewer stage after Synthesis;
- implement max-2 review iterations inside the existing report build call;
- enforce spec failure policy for epistemic violations, invalid output, review exhaustion, and insufficient data.

Не должно быть реализовано:
- unbounded self-reflection loops;
- retry via new jobs;
- public exposure of review history.

### 2.2. Architectural guardrails
- Запрещено:
- exceeding reviewer iteration budget from the spec;
- returning `ready` when reviewer exhausted or epistemic violations remain.
- Нельзя ломать:
- current `failed`/`blocked`/completed job signaling;
- existing invalid-output fallback behavior already covered by tests.
- Нельзя менять:
- websocket event names in [api/routers/report_progress.py](../api/routers/report_progress.py);
- `Job` lifecycle semantics.
- Можно:
- downgrade final status to `limited` or `insufficient_data`;
- persist internal review history only in redacted internal trace.

### 2.3. File-level scope
Likely to modify:
- [agents/reporter.py](../agents/reporter.py)
- [services/reporting.py](../services/reporting.py)
- [api/routers/report_progress.py](../api/routers/report_progress.py)
- [tests/test_reporting_semantics.py](../tests/test_reporting_semantics.py)
- [tests/test_report_progress_ws_api.py](../tests/test_report_progress_ws_api.py)

Allowed to add:
- reviewer-loop focused unit tests

Must not modify:
- [db/models.py](../db/models.py)
- [services/jobs.py](../services/jobs.py)

### 2.4. Data/API/runtime impact
- DB/schema: none.
- ORM/models: none.
- API contracts: possibly richer failure reasons in existing job result payload, but no new route shape.
- Runtime orchestration: reviewer becomes final in-job loop with bounded reruns.
- UI/frontend: only if new failure codes are surfaced via existing error/status fields.
- Logs/metrics/monitoring: optional review-iteration count logs.
- Docs/runbook: reviewer exhaustion behavior documented.

### 2.5. Definition of Ready (DoR)
- defect classes are agreed: epistemic violation, sufficiency misuse, invalid structure, retrieval misuse;
- rerun targets are limited to existing internal stages, not arbitrary prompt branches.

### 2.6. Definition of Done (DoD)
- reviewer writes iteration history into internal trace;
- reviewer can accept, request one targeted rerun, or end with `limited` / `insufficient_data`;
- final status never remains `ready` after unresolved review exhaustion.

### 2.7. Acceptance tests
- reviewer accepts a compliant synthesis without rerun.
- reviewer requests rerun once for epistemic misuse and caps total iterations at 2.
- reviewer exhaustion returns schema-valid fallback with non-ready status.

### 2.8. Expected artifacts
- bounded reviewer loop
- tests covering review accept, rerun, and exhaustion paths

## Package P7. Map Internal Multi-Agent Output To Existing Public Contract

### 2.1. Scope
Должно быть реализовано:
- преобразовать internal multi-agent outputs into the existing public `post_report_v2` shape;
- preserve required top-level fields while introducing spec-aligned public semantics for `summary`, `content`, `topics`, `confidence`, and `status`;
- update downstream compatibility rules for event/process aggregation and UI status handling.

Не должно быть реализовано:
- прямое exposing of internal step payloads;
- breaking field names or mandatory top-level report keys;
- unrelated frontend redesign.

### 2.2. Architectural guardrails
- Запрещено:
- leaking `meta.multi_agent` through public API payloads;
- changing `summary` into an interpretive field; it must remain factual per spec.
- Нельзя ломать:
- post detail `summary/topics/content` rendering in [frontend/src/modules/workspace/post-detail/components/ReportBlock.tsx](../frontend/src/modules/workspace/post-detail/components/ReportBlock.tsx);
- event/process detail extraction of `cross_post_topics` and `stage_analysis`;
- archive persistence of `report_json` in [services/archive.py](../services/archive.py).
- Нельзя менять:
- top-level field names in [schemas/report.py](../schemas/report.py);
- list/export route response shapes in [api/routers/reports.py](../api/routers/reports.py).
- Можно:
- expand allowed public statuses if UI and downstream compatibility are updated in the same package;
- keep internal richer state while mapping to a stable public subset.

### 2.3. File-level scope
Likely to modify:
- [schemas/report.py](../schemas/report.py)
- [services/reporting.py](../services/reporting.py)
- [services/report_aggregation.py](../services/report_aggregation.py)
- [services/dashboard/common.py](../services/dashboard/common.py)
- [api/routers/reports.py](../api/routers/reports.py)
- [api/routers/linking.py](../api/routers/linking.py)
- [frontend/src/shared/ui/status/statusMeta.ts](../frontend/src/shared/ui/status/statusMeta.ts)
- [frontend/src/shared/dashboard/filter-options.ts](../frontend/src/shared/dashboard/filter-options.ts)
- [frontend/src/modules/workspace/post-detail/contracts.ts](../frontend/src/modules/workspace/post-detail/contracts.ts)
- [frontend/src/modules/workspace/event-detail/mappers.ts](../frontend/src/modules/workspace/event-detail/mappers.ts)
- [frontend/src/modules/workspace/process-detail/mappers.ts](../frontend/src/modules/workspace/process-detail/mappers.ts)

Allowed to add:
- dedicated mapping/regression tests for public payload compatibility

Must not modify:
- [db/models.py](../db/models.py) in the initial rollout
- [alembic/versions/](../alembic/versions)

### 2.4. Data/API/runtime impact
- DB/schema: no migration by default; reuse JSONB payloads.
- ORM/models: none unless a later dedicated trace store is introduced as a separate migration package.
- API contracts: top-level contract preserved; allowed enum/status expansion must be implemented together with frontend compatibility.
- Runtime orchestration: event/process readiness rules may need adjustment so `limited` is handled deliberately and `insufficient_data` is not mistaken for a ready dependency.
- UI/frontend: report badges, filters, and summary counters may need explicit support for new public statuses.
- Logs/metrics/monitoring: preserve `meta.coverage_factor`; do not rename it.
- Docs/runbook: public-vs-internal mapping rules documented.

### 2.5. Definition of Ready (DoR)
- decision made whether public `status` expands now or stays backward-compatible behind rollout flag;
- downstream consumers of `summary/topics/status/confidence` are enumerated.

### 2.6. Definition of Done (DoD)
- public post report remains schema-valid and frontend-compatible;
- event/process aggregation still works on mapped post payloads;
- internal traces remain hidden while public fields reflect spec-compliant limited/insufficient behavior.

### 2.7. Acceptance tests
- `PostReportPayload` validates mapped output for `ready`, `limited`, and `insufficient_data` if public expansion is enabled.
- post detail page still renders summary/topics/content without seeing internal traces.
- event/process aggregation tests confirm mapped post reports do not break `build_event_report_payload()` or `build_process_report_payload()`.

### 2.8. Expected artifacts
- stable Internal -> Public mapping layer inside existing reporting path
- downstream compatibility tests across backend and frontend consumers

## Package P8. Regression, Rollout, And Runbook Hardening

### 2.1. Scope
Должно быть реализовано:
- собрать regression matrix for rollout off / rollout on / limited / insufficient / reviewer exhaustion;
- update ops and developer docs for AI worker behavior, fallback semantics, and staged rollout;
- define a staged enablement path using existing settings surfaces.

Не должно быть реализовано:
- broad repo refactor;
- unrelated monitor/dashboard redesign;
- mandatory migration package unless previous packages prove one is unavoidable.

### 2.2. Architectural guardrails
- Запрещено:
- flipping multi-agent mode to default-on without regression evidence;
- shipping a status expansion without frontend/status-label coverage.
- Нельзя ломать:
- passive AI worker guarantees documented in [docs/runtime_topology.md](./runtime_topology.md);
- current manual/API-triggered report generation model.
- Нельзя менять:
- scheduler ownership boundaries;
- Telegram pipeline responsibilities.
- Можно:
- add tests, docs, runbook notes, and rollout checklist;
- add monitor/debug logs if they use existing channels.

### 2.3. File-level scope
Likely to modify:
- [docs/runtime_runbook.md](./runtime_runbook.md)
- [docs/runtime_topology.md](./runtime_topology.md)
- [docs/pipelines.md](./pipelines.md)
- [README.md](../README.md)
- [tests/test_ai_runtime_mode.py](../tests/test_ai_runtime_mode.py)
- [tests/test_reports_async_api.py](../tests/test_reports_async_api.py)
- [tests/test_report_progress_ws_api.py](../tests/test_report_progress_ws_api.py)
- [tests/integration/test_orchestration_lifecycle_real_db.py](../tests/integration/test_orchestration_lifecycle_real_db.py)
- [frontend/src/test/post-detail.test.tsx](../frontend/src/test/post-detail.test.tsx)
- [frontend/src/test/event-detail.test.tsx](../frontend/src/test/event-detail.test.tsx)
- [frontend/src/test/process-detail.test.tsx](../frontend/src/test/process-detail.test.tsx)

Allowed to add:
- rollout checklist doc
- backend/frontend regression tests for new statuses and fallback modes

Must not modify:
- [db/models.py](../db/models.py) unless a separate migration package is explicitly approved
- [alembic/versions/](../alembic/versions)

### 2.4. Data/API/runtime impact
- DB/schema: none in this package.
- ORM/models: none.
- API contracts: no new route shapes; only documented behavior.
- Runtime orchestration: no structural changes beyond what earlier packages already introduced.
- UI/frontend: regression coverage and optional copy/status updates.
- Logs/metrics/monitoring: optional rollout counters or monitor notes using existing monitor paths.
- Docs/runbook: explicit staged rollout and fallback playbook.

### 2.5. Definition of Ready (DoR)
- P1-P7 merged or ready behind a rollout flag;
- expected operator actions for rollback and diagnosis are known.

### 2.6. Definition of Done (DoD)
- backend and frontend regression suites cover rollout-off and rollout-on behavior;
- docs explain how to enable, verify, and disable multi-agent mode safely;
- there is a clear operator checklist for diagnosing limited/insufficient/reviewer-exhausted outputs.

### 2.7. Acceptance tests
- rollout disabled path reproduces current single-report behavior.
- rollout enabled path keeps API/public contracts stable and produces spec-aligned statuses.
- integration lifecycle test proves event/process staleness and rebuild behavior still works after post-report changes.

### 2.8. Expected artifacts
- rollout checklist and runbook updates
- regression suite covering contract, orchestration, fallback, and UI compatibility

## Explicit Gaps To Keep Visible During Implementation

- External retrieval provider is absent from the repo. Until a real provider exists, retrieval-required scenarios must degrade to `limited` or `insufficient_data` and must not fabricate `external` evidence.
- Internal multi-agent traces need a redaction boundary because current report APIs expose `report_json` directly. Persisting traces without redaction would violate the spec.
- Public status expansion from current `ready|skipped_min_comments|failed` to spec-aligned `ready|limited|insufficient_data` is safe only if backend summaries, frontend status badges, filters, and downstream readiness logic are updated together.
- Event/process aggregation currently assumes child reports are deterministic inputs. Any new post-report status semantics must be intentionally mapped into `_is_payload_dependency_ready()` and related readiness rules in [services/reporting.py](../services/reporting.py).
Gap: No retrieval provider

Resolution: implement provider-absent degradation path; forbid synthetic external evidence.

Gap: No redaction boundary for internal traces

Resolution: introduce public-safe projection or API redaction for meta.multi_agent.

Gap: Public status semantics will change

Resolution: rollout status expansion only as coordinated backend/frontend/downstream migration.

Gap: Downstream readiness assumes deterministic child reports

Resolution: explicitly remap new post-report statuses into dependency readiness rules.