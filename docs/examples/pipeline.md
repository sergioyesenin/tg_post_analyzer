# Example: Correct Pipeline

## Recommended reference

- Post report generation:
  - enqueue: `api/routers/reports.py::update_report`
  - runtime: `services/pipeline_runtime.py::run_ai_jobs`
  - business logic: `services/reporting.py::build_post_report`

## Why this is the best pipeline example in the current codebase

- clear split between HTTP trigger, queue orchestration, and domain logic
- stable accepted-job response
- background execution with timeout/retry behavior
- explicit downstream cascade into event report jobs

## Pattern to copy

1. HTTP/API layer only queues work
2. Worker owns retries/timeouts
3. Domain service returns structured result
4. Runtime stores result and handles cascades

## Watch-outs

- report payload shape is a real contract
- changing cascade logic affects event/process freshness
