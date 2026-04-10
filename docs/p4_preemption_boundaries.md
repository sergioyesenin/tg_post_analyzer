# P4 Preemption Boundaries

## Status

- Task: `P4-T1`
- Purpose: freeze `current work unit` boundaries for safe preemption
- Scope: analysis/spec note only

## Rule of interpretation

- Preemption is allowed only **between** frozen work units below.
- Preemption is **not** allowed inside a work unit that is already running.
- If a path performs multiple DB mutations or external calls inside one handler without an intermediate safe handoff point, the entire handler execution is the work unit.
- This note freezes boundaries for implementation of graceful preemption and does not itself change runtime behavior.

## Frozen boundaries by path

### 1. Telegram ingest loop

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `run_telegram_cycle()`
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_process_channel()`
- Current work unit:
  - **one channel ingest pass**
- Safe preemption point:
  - after `_process_channel(...)` returns for the current channel
  - before starting the next channel in the `for channel in channels` loop
- Why:
  - ingest for a single channel is treated as one continuous unit delegated to `process_channel_impl`
  - interrupting inside that path would risk partial post ingestion and partial follow-up scheduling decisions for the same channel

### 2. Telegram link jobs

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `run_telegram_link_jobs_until_idle()`
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_link_job()`
- Current work unit:
  - **one `BUILD_POST_LINKS` job handler execution**
- Safe preemption point:
  - after `_run_link_job(...)` finishes for an individual job
  - before fetching the next link-job batch or starting another not-yet-started job
- Why:
  - one link job wraps the full DB/load/run/persist flow for a single post
  - preempting mid-handler would risk inconsistent link verification state

### 3. Comment refresh / collect-comments job

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `run_telegram_jobs()`
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_comment_job()`
  - [services/TGqueries.py](/d:/Projects/tg_post_analyzer/services/TGqueries.py) `update_post_comments()`
- Current work unit:
  - **one `COLLECT_COMMENTS` or `REFRESH_COMMENTS` job handler execution for one post**
- Safe preemption point:
  - after `_run_comment_job(...)` commits terminal/deferred state for the current job
  - before starting the next comment job in the loop
- Not a safe boundary:
  - not inside `update_post_comments(...)`
  - not between top-level and nested comment traversal
  - not between partial comment upserts within the same job
- Why:
  - this path contains nested operations, top-level thread resolution, iterative comment traversal, upserts, reconciliation, and final job-state persistence
  - mid-operation interruption would be exactly the unsafe case called out by `B5`

### 4. Rebuild events job

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_rebuild_events_job()`
  - [services/events/build_events.py](/d:/Projects/tg_post_analyzer/services/events/build_events.py) `rebuild_events()`
- Current work unit:
  - **one `REBUILD_EVENTS` job handler execution**
- Safe preemption point:
  - after `_run_rebuild_events_job(...)` finishes and commits job result/state
  - before starting another job
- Not a safe boundary:
  - not inside `rebuild_events(...)` component rebuild loops
  - not between event membership rewrites inside the same rebuild run
- Why:
  - the rebuild performs graph expansion and membership/event updates as one logical rebuild transaction flow
  - partial interruption would risk mixed rebuilt/not-rebuilt event graph state

### 5. Rebuild processes job

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_rebuild_processes_job()`
  - [services/processes/build_processes.py](/d:/Projects/tg_post_analyzer/services/processes/build_processes.py) `rebuild_processes()`
- Current work unit:
  - **one `REBUILD_PROCESSES` job handler execution**
- Safe preemption point:
  - after `_run_rebuild_processes_job(...)` finishes and commits job result/state
  - before starting another job
- Not a safe boundary:
  - not inside `rebuild_processes(...)` component expansion/build loops
  - not between process-event membership mutations within the same rebuild run
- Why:
  - the rebuild is a long-running but logically single unit of process graph recomputation
  - mid-operation interruption risks partially updated process topology

### 6. Add-channel job

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_add_channel_job()`
- Current work unit:
  - **one `ADD_CHANNEL` job handler execution**
- Safe preemption point:
  - after `_run_add_channel_job(...)` commits completion/failure
- Why:
  - channel resolution and persistence are handled as one unit for one requested channel

### 7. Maintenance jobs

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `_run_maintenance_job()`
- Current work unit:
  - **one maintenance job handler execution**
- Safe preemption point:
  - after current maintenance job handler returns and job state is committed
- Why:
  - maintenance flows already map to discrete job executions and should not be interrupted inside a single run

### 8. AI report jobs

- Path:
  - [services/pipeline_runtime.py](/d:/Projects/tg_post_analyzer/services/pipeline_runtime.py) `run_ai_jobs()`
- Current work unit:
  - **one AI job handler execution**
  - applies to:
    - `BUILD_POST_REPORT`
    - `BUILD_EVENT_REPORT`
    - `BUILD_PROCESS_REPORT`
    - current passive terminal handling of `BUILD_POST_REPORT_BATCH`
- Safe preemption point:
  - after the current job finishes with `done`, `failed`, or `requeue` commit
  - before starting another not-yet-started AI job
- Not a safe boundary:
  - not inside `build_post_report(...)`
  - not inside `build_event_report_draft(...)`
  - not inside `build_process_report_draft(...)`
  - not between report write and stale-marking for the same handler
- Why:
  - each AI handler persists report/job side effects as a single logical unit
  - interrupting inside the handler would risk mismatched report/job/staleness state

## Loop-control implication for P4 implementation

- `run_telegram_cycle()`:
  - preemption check may run between channel ingest passes
  - preemption check may run before/after link-jobs phase
  - preemption check may run before entering `run_telegram_jobs()` and after each completed job work unit there
- `run_telegram_jobs()`:
  - preemption check may run between completed job handlers
  - it must not interrupt an in-flight comment/rebuild/add-channel/maintenance handler
- `run_ai_jobs()`:
  - preemption check may run between completed AI jobs
  - it must not interrupt an in-flight report job

## Edge-case clarifications

### Comment refresh with nested operations

- Frozen boundary remains the entire comment job, not nested traversal phases.
- Reason:
  - nested replies, reconciliation, and final counters belong to one consistency unit for the post.

### Long-running rebuild

- Frozen boundary remains the entire rebuild job, not individual internal loops/components.
- Reason:
  - rebuild integrity matters more than fine-grained preemption latency in the current architecture.

## Non-goals of this note

- This note does not define the final priority matrix.
- This note does not define starvation prevention policy.
- This note does not introduce new queues, worker roles, or job types.
- This note does not change current runtime behavior by itself.
