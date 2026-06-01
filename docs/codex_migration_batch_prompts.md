# Codex Migration Batch Prompts (S0-S9)

## Назначение

Этот файл — рабочий батч промтов для поэтапной миграции проекта multi-agent аналитики постов к production-ready, spec-compliant, OpenRouter-backed архитектуре.

Как использовать:
1. Выполнять промты строго по порядку `S0 -> S9`.
2. Каждый промт соответствует одному migration stage и имеет собственный acceptance gate.
3. Не перескакивать этапы и не смешивать цели нескольких этапов в одном запуске.
4. Не объявлять систему готовой, пока не пройден `S9`.

---

## Оглавление

- [Общие правила для всех промтов](#общие-правила-для-всех-промтов)
- [S0 — Canonical Contract Unification](#s0--canonical-contract-unification)
- [S1 — Step Execution Abstraction](#s1--step-execution-abstraction)
- [S2 — OpenRouter Wiring for 6 Steps](#s2--openrouter-wiring-for-6-steps)
- [S3 — Retrieval Provider Integration](#s3--retrieval-provider-integration)
- [S4 — Synthesis Canonicalization](#s4--synthesis-canonicalization)
- [S5 — Reviewer Gate + Action Loop](#s5--reviewer-gate--action-loop)
- [S6 — Remove Semantic Overwrite in Mapping](#s6--remove-semantic-overwrite-in-mapping)
- [S7 — Rollout/Fallback Redesign](#s7--rolloutfallback-redesign)
- [S8 — Persistence + Trace Hardening](#s8--persistence--trace-hardening)
- [S9 — Acceptance/Regression on Real Cases](#s9--acceptanceregression-on-real-cases)
- [Cross-Stage Meta Prompts](#cross-stage-meta-prompts)
- [Порядок использования](#порядок-использования)

---

## Общие правила для всех промтов

### mandatory

1. Не объявлять production-ready раньше завершения `S9`.
2. Не делать косметические патчи вместо архитектурных исправлений этапа.
3. Не подменять LLM-агентов rule-based логикой как primary mechanism.
4. Не допускать semantic overwrite после `synthesis` (разрешена только safe normalization).
5. Не допускать `ready` из fallback path, если path не canonical 6-step OpenRouter-backed.
6. Не удалять legacy path до достижения stage-gated parity и rollback-safe состояния.
7. Каждый этап завершать только при доказанном acceptance gate.
8. Все 6 шагов (`context`, `routing`, `expert`, `public_opinion`, `synthesis`, `reviewer`) обязаны быть auditable через provenance.

### recommended

1. Сначала аудит текущей реализации целевых модулей этапа, потом редактирование.
2. Перед редактированием фиксировать список планируемых изменений и границы этапа.
3. После каждого этапа проверять invariants отдельно.
4. В отчете этапа явно отмечать: закрытые acceptance criteria и оставшиеся gaps.

### implementation freedom

1. Формат промежуточных заметок и артефактов.
2. Размер PR/пачки изменений внутри этапа.
3. Имена новых внутренних абстракций и вспомогательных модулей.

---

## Единый шаблон stage prompt (используется ниже)

Каждый `Suggested Codex prompt` должен привести к результату в формате:
1. `Current state audit` (только stage-relevant modules).
2. `Planned changes` (до редактирования).
3. `Implemented changes`.
4. `Invariant check`.
5. `Acceptance gate evidence`.
6. `Residual risks`.
7. `Explicitly not done`.

---

## S0 — Canonical Contract Unification

**Stage ID:** `S0`  
**Stage Name:** `Canonical Contract Unification`  
**Objective:** унифицировать canonical contracts для step I/O, `meta.multi_agent`, retrieval/review/final report.  
**Why this stage matters:** без фиксированных контрактов последующие этапы неустойчивы и дают schema drift.  
**Primary modules to inspect/edit:**  
- `services/reporting_v2/contracts_internal.py`
- `schemas/report.py`
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- `api/routers/reports.py`
- `tests/test_reporting_v2_*`
- `tests/test_report_trace_api.py`  
**Dependencies:** none  
**Must preserve:** текущие API маршруты и backward-compatible чтение существующих persisted payloads где возможно.  
**Acceptance gate:** canonical contract зафиксирован и проверяется тестами; `steps` включает все 6 шагов; provenance fields определены.

### Suggested Codex prompt

```text
Ты работаешь на этапе S0 (Canonical Contract Unification) миграции multi-agent pipeline.

Цель этапа:
- зафиксировать и внедрить канонические контракты для:
  1) step I/O всех 6 шагов,
  2) meta.multi_agent (steps/retrieval/review/provenance),
  3) финального report contract.

Жесткие ограничения:
- НЕ переходи к S1+ задачам.
- НЕ делай оптимизаций промтов/моделей.
- НЕ объявляй систему production-ready.

Сначала сделай аудит текущего состояния по модулям:
- services/reporting_v2/contracts_internal.py
- schemas/report.py
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- api/routers/reports.py
- tests/test_reporting_v2_*
- tests/test_report_trace_api.py

Перед любыми правками выдай:
1) exact gaps между текущими контрактами и canonical target,
2) план конкретных изменений на этом этапе,
3) что сознательно не будет делаться в S0.

После правок выдай:
1) что изменено (по файлам и контрактным полям),
2) как сохранена обратная совместимость (если применимо),
3) проверку invariants,
4) доказательство acceptance gate S0,
5) оставшиеся риски и незакрытые вопросы.

Инварианты обязательно соблюсти:
- ready не может считаться валидным вне canonical path;
- для всех 6 шагов должен быть описан provenance contract;
- content source-of-truth rule формально закреплен.
```

---

## S1 — Step Execution Abstraction

**Stage ID:** `S1`  
**Stage Name:** `Step Execution Abstraction`  
**Objective:** ввести единый execution interface для 6 шагов.  
**Why this stage matters:** без общего runner невозможно безопасно перевести все шаги на OpenRouter и reviewer actions.  
**Primary modules to inspect/edit:**  
- `services/reporting_v2/orchestrator.py`
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- `services/reporting.py`
- (возможно новые) `services/reporting_v2/steps/*`
- `tests/test_reporting_v2_*`  
**Dependencies:** `S0`  
**Must preserve:** рабочий job lifecycle и текущие точки входа build-report.  
**Acceptance gate:** все 6 шагов исполняются через единый abstraction layer (даже если пока часть логики адаптирована).

### Suggested Codex prompt

```text
Ты выполняешь S1 (Step Execution Abstraction).

Цель:
- внедрить единый step execution abstraction для context/routing/expert/public_opinion/synthesis/reviewer,
- переподключить orchestrator/pipeline к этому abstraction без перехода к OpenRouter-переводу всех шагов (это S2).

Ограничения:
- НЕ выполнять задачи S2+.
- НЕ менять целевую бизнес-семантику статусов beyond scope S1.

Сначала аудит:
- services/reporting_v2/orchestrator.py
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- services/reporting.py
- tests/test_reporting_v2_*

Перед правками покажи:
1) текущие execution paths,
2) где отсутствует единый step envelope,
3) план внедрения abstraction (минимально инвазивный).

После правок покажи:
1) какие модули и интерфейсы введены/изменены,
2) как каждый из 6 шагов теперь проходит через общий execution contract,
3) какие старые пути временно обернуты adapter-слоем,
4) проверку invariants,
5) acceptance evidence для S1,
6) что специально НЕ сделано (например, full OpenRouter wiring).
```

---

## S2 — OpenRouter Wiring for 6 Steps

**Stage ID:** `S2`  
**Stage Name:** `OpenRouter Wiring for 6 Steps`  
**Objective:** подключить OpenRouter как provider-backed execution path для всех 6 шагов.  
**Why this stage matters:** это core requirement target architecture.  
**Primary modules to inspect/edit:**  
- `services/llm/openai_client.py`
- `services/reporting_v2/orchestrator.py`
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- (возможно) `services/reporting_v2/steps/*`
- `services/settings_defaults.py`
- `services/settings_validation.py`
- `tests/test_openai_adapter.py`
- `tests/test_reporting_v2_*`  
**Dependencies:** `S1`  
**Must preserve:** bounded timeouts/retries, deterministic failure semantics.  
**Acceptance gate:** traces доказывают provider-backed executed=true для всех 6 шагов, с model/provider/latency/fallback fields.

### Suggested Codex prompt

```text
Ты выполняешь S2 (OpenRouter Wiring for 6 Steps).

Цель:
- сделать OpenRouter реальным provider-backed path для всех 6 шагов,
- фиксировать step-level provenance (provider/model/executed/success/latency/fallback/...).

Ограничения:
- НЕ переходить к полноценной retrieval-интеграции (это S3),
- НЕ завершать reviewer defect-action redesign (это S5),
- НЕ объявлять готовность системы.

Сначала аудит:
- services/llm/openai_client.py
- services/reporting_v2/orchestrator.py
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- services/settings_defaults.py
- services/settings_validation.py
- tests/test_openai_adapter.py
- tests/test_reporting_v2_*

До редактирования представь:
1) где шаги сейчас не provider-backed,
2) план перевода каждого из 6 шагов,
3) fallback policy внутри S2 (без нарушения invariants).

После правок представь:
1) mapping по 6 шагам: как именно они ходят в OpenRouter,
2) как фиксируется provenance,
3) какие fallback-развилки остались и почему они не маскируются как canonical,
4) invariants check,
5) acceptance gate evidence S2,
6) что сознательно оставлено на S3/S5.
```

---

## S3 — Retrieval Provider Integration

**Stage ID:** `S3`  
**Stage Name:** `Retrieval Provider Integration`  
**Objective:** внедрить retrieval как provider-backed компонент внутри pipeline contract.  
**Why this stage matters:** без retrieval reviewer и confidence/status semantics некорректны на high-risk кейсах.  
**Primary modules to inspect/edit:**  
- `services/reporting_v2/contracts_internal.py`
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- `services/reporting_v2/orchestrator.py`
- (возможно новые) `services/reporting_v2/retrieval/*`
- `services/settings_defaults.py`
- `services/settings_validation.py`
- `tests/test_reporting_v2_contracts.py`
- `tests/test_reporting_v2_post.py`
- `tests/test_reporting_v2_event.py`  
**Dependencies:** `S2`  
**Must preserve:** clear terminal behavior when retrieval unavailable.  
**Acceptance gate:** retrieval fields `enabled/requested/attempted/used/status/sources/provider/failure_reason` корректны и проверяются.

### Suggested Codex prompt

```text
Ты выполняешь S3 (Retrieval Provider Integration).

Цель:
- перевести retrieval из placeholder/without_provider в канонический provider-backed контракт,
- встроить retrieval signals в статусную и reviewer логику без false-ready.

Ограничения:
- НЕ делать полную переработку synthesis (S4),
- НЕ делать reviewer defect-action loop redesign сверх минимально необходимого для S3.

Сначала аудит:
- services/reporting_v2/contracts_internal.py
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- services/reporting_v2/orchestrator.py
- services/settings_defaults.py
- services/settings_validation.py
- tests/test_reporting_v2_contracts.py
- tests/test_reporting_v2_post.py
- tests/test_reporting_v2_event.py

Перед правками дай:
1) gap-анализ retrieval semantics,
2) план минимального набора изменений для provider-backed retrieval,
3) правила деградации статуса при retrieval failure/insufficiency.

После правок дай:
1) что изменено по retrieval contract и runtime path,
2) как это отражается в meta/provenance,
3) как предотвращен ready при insufficient evidence,
4) invariants check,
5) acceptance gate evidence S3,
6) что НЕ делалось (S4/S5 scope).
```

---

## S4 — Synthesis Canonicalization

**Stage ID:** `S4`  
**Stage Name:** `Synthesis Canonicalization`  
**Objective:** сделать synthesis каноническим источником аналитического `content` по spec.  
**Why this stage matters:** user-facing quality определяется именно synthesis.  
**Primary modules to inspect/edit:**  
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- `services/reporting_v2/orchestrator.py`
- `services/reporting_v2/contracts_internal.py`
- `schemas/report.py`
- `tests/test_reporting_v2_post.py`
- `tests/test_reporting_v2_event.py`  
**Dependencies:** `S3`  
**Must preserve:** status semantics и trace consistency.  
**Acceptance gate:** `content` соответствует narrative spec (5-7 предложений, event/context/reaction/interpretation/consequences, non-template, grounded).

### Suggested Codex prompt

```text
Ты выполняешь S4 (Synthesis Canonicalization).

Цель:
- устранить template/snapshot synthesis,
- обеспечить аналитический narrative по spec,
- закрепить synthesis как source-of-truth для content (без semantic overwrite downstream).

Ограничения:
- НЕ выполнять полный reviewer action-matrix redesign (S5),
- НЕ заниматься rollout redesign (S7).

Сначала аудит:
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- services/reporting_v2/orchestrator.py
- services/reporting_v2/contracts_internal.py
- schemas/report.py
- tests/test_reporting_v2_post.py
- tests/test_reporting_v2_event.py

Перед правками выдай:
1) где synthesis сейчас deterministic/template,
2) где content может терять связь с synthesis,
3) план правок строго в рамках S4.

После правок выдай:
1) какие изменения сделаны в logic формирования synthesis,
2) как обеспечены 5 обязательных компонентов narrative,
3) как предотвращены template markers,
4) invariants check,
5) acceptance gate evidence S4 (включая тесты/кейсы),
6) что оставлено на S5/S6.
```

---

## S5 — Reviewer Gate + Action Loop

**Stage ID:** `S5`  
**Stage Name:** `Reviewer Gate + Action Loop`  
**Objective:** реализовать реальный defect-driven reviewer с bounded revise/rerun policy.  
**Why this stage matters:** без этого `ready` не является trustworthy состоянием.  
**Primary modules to inspect/edit:**  
- `services/reporting_v2/orchestrator.py`
- `services/reporting_v2/post_pipeline.py`
- `services/reporting_v2/event_pipeline.py`
- `services/reporting_v2/contracts_internal.py`
- (возможно новые) `services/reporting_v2/reviewer/*`
- `tests/test_reporting_v2_*`
- `tests/test_reporting_semantics.py`  
**Dependencies:** `S4`  
**Must preserve:** bounded retries и terminal states consistency.  
**Acceptance gate:** blocking defects никогда не дают `ready`; reviewer actions соответствуют defect-to-action matrix.

### Suggested Codex prompt

```text
Ты выполняешь S5 (Reviewer Gate + Action Loop).

Цель:
- сделать reviewer настоящим quality gate:
  - defect detection,
  - action selection (revise/rerun_step/rerun_branch/reject_insufficient_data/fail/accept),
  - bounded retry loop.

Ограничения:
- НЕ уходить в rollout/fallback redesign (S7),
- НЕ делать persistence/trace hardening beyond нужного минимума S5.

Сначала аудит:
- services/reporting_v2/orchestrator.py
- services/reporting_v2/post_pipeline.py
- services/reporting_v2/event_pipeline.py
- services/reporting_v2/contracts_internal.py
- tests/test_reporting_v2_*
- tests/test_reporting_semantics.py

Перед правками покажи:
1) текущий reviewer behavior и его несоответствия,
2) план внедрения defect schema + action loop,
3) bounded retry policy и terminal states.

После правок покажи:
1) что изменено в reviewer logic,
2) как именно blocking defects блокируют ready,
3) как работает rerun/revise в пределах budget,
4) invariants check,
5) acceptance gate evidence S5,
6) какие риски остались.
```

---

## S6 — Remove Semantic Overwrite in Mapping

**Stage ID:** `S6`  
**Stage Name:** `Remove Semantic Overwrite in Mapping`  
**Objective:** исключить смысловую перезапись `content` после synthesis.  
**Why this stage matters:** это прямой contract violation и источник ложной аналитики.  
**Primary modules to inspect/edit:**  
- `services/reporting.py`
- `services/reporting_v2/mapper.py`
- `api/public_report_boundary.py`
- `schemas/report.py`
- `tests/test_reporting_semantics.py`
- `tests/test_public_report_boundary.py`  
**Dependencies:** `S5`  
**Must preserve:** публичная безопасность (скрытие internal trace где нужно), но без искажения content.  
**Acceptance gate:** финальный user-facing `content` семантически = synthesis output (кроме safe normalization).

### Suggested Codex prompt

```text
Ты выполняешь S6 (Remove Semantic Overwrite in Mapping).

Цель:
- убрать semantic overwrite после synthesis,
- оставить только safe normalization,
- закрепить source-of-truth: content = synthesis.

Ограничения:
- НЕ делать rollout/fallback redesign (S7),
- НЕ переделывать reviewer logic beyond S6 scope.

Сначала аудит:
- services/reporting.py
- services/reporting_v2/mapper.py
- api/public_report_boundary.py
- schemas/report.py
- tests/test_reporting_semantics.py
- tests/test_public_report_boundary.py

Перед правками выдай:
1) где и как происходит semantic overwrite,
2) какие transformations можно оставить как safe normalization,
3) план изменений в рамках S6.

После правок выдай:
1) какие overwrite-paths устранены,
2) как гарантирован source-of-truth из synthesis,
3) invariants check,
4) acceptance gate evidence S6,
5) что сознательно не трогалось (S7+).
```

---

## S7 — Rollout/Fallback Redesign

**Stage ID:** `S7`  
**Stage Name:** `Rollout/Fallback Redesign`  
**Objective:** переопределить rollout/fallback так, чтобы non-canonical paths не могли имитировать готовность.  
**Why this stage matters:** иначе система может выглядеть “готовой” при нарушенных инвариантах.  
**Primary modules to inspect/edit:**  
- `services/reporting.py`
- `services/settings_defaults.py`
- `services/settings_validation.py`
- `services/ai_runtime.py`
- docs/runbook/checklists (если есть)
- `tests/test_reporting_v2_skeleton.py`
- `tests/test_ai_runtime_mode.py`  
**Dependencies:** `S6`  
**Must preserve:** rollback safety и управляемость rollout.  
**Acceptance gate:** fallback path не выдает `ready`, если не canonical; rollout policy stage-gated.

### Suggested Codex prompt

```text
Ты выполняешь S7 (Rollout/Fallback Redesign).

Цель:
- привести rollout/fallback policy к инвариантам:
  - non-canonical path не может выдавать ready,
  - fallback явно маркируется и деградирует статус,
  - rollout управляется stage-gated правилами.

Ограничения:
- НЕ выполнять persistence trace hardening beyond S7 needs (это S8),
- НЕ делать финальный real-case acceptance campaign (это S9).

Сначала аудит:
- services/reporting.py
- services/settings_defaults.py
- services/settings_validation.py
- services/ai_runtime.py
- tests/test_reporting_v2_skeleton.py
- tests/test_ai_runtime_mode.py

Перед правками покажи:
1) текущие path selection/fallback сценарии,
2) где возможен false-ready,
3) план policy-изменений и rollback-safe поведения.

После правок покажи:
1) как изменена rollout/fallback логика,
2) как обеспечен запрет false-ready,
3) invariants check,
4) acceptance gate evidence S7,
5) оставшиеся rollout-риски.
```

---

## S8 — Persistence + Trace Hardening

**Stage ID:** `S8`  
**Stage Name:** `Persistence + Trace Hardening`  
**Objective:** обеспечить доказуемость canonical provider-backed execution в persisted trace и API trace endpoints.  
**Why this stage matters:** без доказуемого trace невозможно честно подтверждать соответствие архитектуре.  
**Primary modules to inspect/edit:**  
- `services/reporting.py`
- `services/reporting_v2/contracts_internal.py`
- `api/routers/reports.py`
- `schemas/report.py`
- `api/public_report_boundary.py`
- `tests/test_report_trace_api.py`
- `tests/test_reporting_semantics.py`  
**Dependencies:** `S7`  
**Must preserve:** public/private boundary (trace доступ там, где положено).  
**Acceptance gate:** persisted `meta.multi_agent` полно и канонично отражает provenance каждого из 6 шагов.

### Suggested Codex prompt

```text
Ты выполняешь S8 (Persistence + Trace Hardening).

Цель:
- зафиксировать в persistence и trace API канонический meta.multi_agent,
- обеспечить auditable доказательство provider-backed execution по 6 шагам.

Ограничения:
- НЕ делать финальное production acceptance объявление (S9).

Сначала аудит:
- services/reporting.py
- services/reporting_v2/contracts_internal.py
- api/routers/reports.py
- schemas/report.py
- api/public_report_boundary.py
- tests/test_report_trace_api.py
- tests/test_reporting_semantics.py

Перед правками дай:
1) где trace неполный/неканоничный,
2) план доработки persistence + trace endpoint behavior,
3) как сохраняется публичная sanitization граница.

После правок дай:
1) что изменено в persisted meta/provenance,
2) что изменено в trace API,
3) invariants check,
4) acceptance gate evidence S8,
5) residual observability gaps.
```

---

## S9 — Acceptance/Regression on Real Cases

**Stage ID:** `S9`  
**Stage Name:** `Acceptance/Regression on Real Cases`  
**Objective:** доказать stage-gated readiness на реальных кейсах и regression suite.  
**Why this stage matters:** только здесь можно подтвердить “готовность” по жесткому критерию output quality + architecture compliance.  
**Primary modules to inspect/edit:**  
- тестовый и validation harness слой
- `tests/test_reporting_v2_*`
- `tests/test_report_trace_api.py`
- `tests/test_reporting_semantics.py`
- docs/runbooks/checklists  
**Dependencies:** `S8`  
**Must preserve:** честность статусов и отсутствие ложной “готовности”.  
**Acceptance gate:** real-case acceptance checklist пройден; invariants соблюдены; trace доказуемо canonical.

### Suggested Codex prompt

```text
Ты выполняешь S9 (Acceptance/Regression on Real Cases).

Цель:
- провести финальную проверку migration outcome:
  - acceptance checklist на реальных кейсах,
  - regression + trace proof,
  - фиксация оставшихся gaps.

Ограничения:
- НЕ заявляй production-ready, если acceptance evidence неполное.
- НЕ подменяй реальные кейсы синтетикой без явной пометки.

Сначала аудит:
- tests/test_reporting_v2_*
- tests/test_report_trace_api.py
- tests/test_reporting_semantics.py
- актуальные runtime/trace артефакты
- docs/checklists/runbook (если есть)

Перед изменениями (если они нужны) дай:
1) план валидации и набор кейсов,
2) критерии pass/fail по acceptance gate,
3) список инвариантов для финальной проверки.

После выполнения дай:
1) evidence по каждому обязательному acceptance критерию,
2) результаты regression и trace-аудита,
3) перечень незакрытых рисков,
4) четкий вердикт: что готово, что не готово, что блокирует production-ready.
```

---

## Cross-Stage Meta Prompts

### Meta 1 — Invariant Sweep
**Purpose:** проверить, не нарушены ли критические инварианты после нескольких этапов.  
**When to use:** после каждого этапа, обязательно после `S2`, `S5`, `S7`, `S9`.  
**Prompt:**

```text
Сделай invariant sweep текущего состояния migration.
Проверь строго:
1) ready только через canonical 6-step OpenRouter-backed path;
2) content source-of-truth = synthesis (без semantic overwrite);
3) blocking defects => no ready;
4) insufficient evidence => not ready;
5) fallback не маскируется как canonical;
6) provenance полно для всех 6 шагов.

Сначала покажи, где в коде и тестах это проверяется.
Потом перечисли нарушения (если есть) с точными файлами/ветками логики.
В конце: remediation priorities (P0/P1/P2) без кодирования за рамками текущего запроса.
```

### Meta 2 — Contract Compliance Audit
**Purpose:** сверить runtime реализацию с canonical contracts.  
**When to use:** после `S0`, затем после `S4`, `S8`.  
**Prompt:**

```text
Проведи contract compliance audit:
- step contracts (6 шагов),
- meta.multi_agent schema,
- retrieval/review contracts,
- final report contract.

Формат:
1) compliant items,
2) deviations,
3) severity,
4) blocking status,
5) что нужно исправить в первую очередь.

Не писать код, только точный аудит по модулям и тестам.
```

### Meta 3 — Semantic Overwrite Detector
**Purpose:** убедиться, что mapping/finalization не перезаписывает смысл synthesis.  
**When to use:** после `S4`, `S6`, перед `S9`.  
**Prompt:**

```text
Проведи аудит semantic overwrite после synthesis.
Найди все места, где user-facing content может быть смыслово изменен downstream.
Раздели изменения на:
- safe normalization (допустимо),
- semantic overwrite (запрещено).

Выдай:
1) точные файлы/функции,
2) классификацию каждого случая,
3) текущий риск для acceptance,
4) приоритет исправления.
```

### Meta 4 — Provenance Completeness Audit
**Purpose:** проверить полноту и достоверность provenance.  
**When to use:** после `S2`, `S8`, перед rollout increase.  
**Prompt:**

```text
Проведи provenance completeness audit для всех 6 шагов.
Обязательные поля на каждый шаг:
provider, model, executed, success, latency_ms, input_ref/hash, output_ref/hash, fallback_used, fallback_reason, attempt_index, status.

Покажи:
1) где поля формируются,
2) где сохраняются,
3) где читаются через trace API,
4) какие поля отсутствуют или недостоверны.
```

### Meta 5 — Pre-Rollout Safety Audit
**Purpose:** проверить безопасность перед расширением rollout.  
**When to use:** после `S7`, перед любым rollout > 0%.  
**Prompt:**

```text
Сделай pre-rollout safety audit.
Проверь:
1) fallback policy не позволяет false-ready;
2) rollback-safe состояние подтверждено;
3) canonical path используется как primary;
4) метрики/трейсы достаточны для обнаружения деградации.

В конце дай вердикт:
- rollout allowed / rollout blocked,
- blocking reasons,
- минимальные условия разблокировки.
```

### Meta 6 — Real-Case Acceptance Audit
**Purpose:** финальная проверка соответствия реального output спецификации.  
**When to use:** в `S9` и перед production declaration.  
**Prompt:**

```text
Проведи real-case acceptance audit на выборке реальных постов/отчетов.
Проверь по acceptance checklist:
- 5-7 предложений,
- event/context/reaction/interpretation/consequences,
- grounded claims,
- no template language,
- no contradictions,
- no ready при blocking defects/insufficient evidence,
- content sourced from synthesis.

Отчет:
1) pass/fail по каждому критерию,
2) примеры критических fail-кейсов,
3) aggregate readiness verdict,
4) что еще блокирует production-ready.
```

---

## Порядок использования

### Обязательная последовательность

1. `S0`
2. `S1`
3. `S2`
4. `S3`
5. `S4`
6. `S5`
7. `S6`
8. `S7`
9. `S8`
10. `S9`

### Stabilization point (recommended)

- После `S5` сделать stabilization checkpoint:
  - запуск `Meta 1`, `Meta 2`, `Meta 3`,
  - фиксация residual defects до перехода в `S6-S8`.

### Что нельзя выполнять параллельно

1. `S0` нельзя параллелить с `S1-S9`.
2. `S2` нельзя параллелить с `S1` (зависимость abstraction).
3. `S4` нельзя параллелить с `S6` (иначе конфликт source-of-truth).
4. `S7` нельзя параллелить с `S8` (policy vs trace hardening конфликтует).
5. `S9` только после завершения `S8`.

### Когда запускать meta-prompts

- После каждого stage: `Meta 1 (Invariant Sweep)`.
- После `S0`, `S4`, `S8`: `Meta 2 (Contract Compliance Audit)`.
- После `S4`, `S6`, перед `S9`: `Meta 3 (Semantic Overwrite Detector)`.
- После `S2`, `S8`: `Meta 4 (Provenance Completeness Audit)`.
- После `S7`: `Meta 5 (Pre-Rollout Safety Audit)`.
- В `S9` и перед production declaration: `Meta 6 (Real-Case Acceptance Audit)`.

---

## Краткая памятка исполнителю

На каждом этапе Codex должен:
1. audit current implementation;
2. map exact changes before editing;
3. edit only stage-relevant modules;
4. verify invariants;
5. report acceptance evidence;
6. explicitly list unresolved items.

Если acceptance gate этапа не доказан — этап считается незавершенным.

