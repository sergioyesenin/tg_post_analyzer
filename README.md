# tg_post_analyzer

## Запуск
1. Скопируй `.env.example` в `.env` и заполни обязательные переменные.
   - Для `docker-compose` обязательно задай `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.
   - Не используй `postgres/postgres` вне локальной разработки: в `APP_ENV` отличном от `dev/local/test` это блокируется на startup.
   - Для `AUTH_JWT_SECRET` укажи криптостойкое значение (минимум 32 символа, минимум 3 класса символов).
   - Пример генерации: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Подними Postgres:

   ```bash
   docker compose up -d
   ```

   Пример безопасной локальной пары:
   - `POSTGRES_USER=tg_analytics_app`
   - `POSTGRES_PASSWORD=<сгенерированный_пароль>`

3. Прогони миграции:

   ```bash
   alembic upgrade head
   ```

4. Запусти API (официальный entrypoint):

   ```bash
   uvicorn api.main:app --reload
   ```

5. Запуск парсера (отдельно от API):

   ```bash
   python main.py
   ```

## Совместимость
- `man:app` оставлен как legacy-алиас и может использоваться во временных локальных скриптах.
- Канонический путь для API и документации: `api.main:app`.
- Канонический ingestion flow: `services/ingestion_core.py`.
- `main.py`, `parse_today.py`, `scripts/pipeline.py` используют общий ingestion core как тонкие оболочки.
- Каноническая семантика reply-link: `reply_to` нормализуется в `update` во всех пайплайнах.

## Collect comments: anti-regression rules

The `collect_comments` path is sensitive to Telegram FloodWait limits.
Keep the following invariants unchanged unless you run a dedicated load test.

1. `services/TGqueries.py` must keep configurable throttling:
   - `COMMENTS_SLEEP_EVERY` from `settings`
   - `COMMENTS_SLEEP_BASE_SEC` from `settings`
   - `COMMENTS_SLEEP_JITTER_SEC` from `settings`

2. Do not call `await c.get_sender()` for every comment in the hot loop.
   - Use `c.sender` metadata and lightweight cache (`sender_meta_cache`).

3. Do not enqueue nested traversal for leaf comments.
   - Keep guard: enqueue child scan only if `c.replies.replies > 0`.

4. Always return flood source in `update_post_comments(...)`:
   - `flood_source="resolve_discussion"` for discussion resolution path
   - `flood_source="iter_comments"` for comments iteration path
   - This is required for diagnosis when flood wait appears.

5. In `scripts/run_telegram_pipeline.py` flood-wait requeue must not run earlier than global cooldown.
   - Keep `effective_retry_at = max(retry_at, collect_comments_global_cooldown_until)`.

6. Default inter-job sleeps for collect-comments in `scripts/run_telegram_pipeline.py` must remain conservative.
   - If DB settings do not override them, keep safe defaults:
   - `collect_comments_sleep_min_ms=2500`
   - `collect_comments_sleep_max_ms=4500`

### Regression signals in logs

Treat these as immediate regression indicators:

- `collect_comments flood source=unknown ...`
- frequent `status=flood_wait` on comments while post parsing is stable
- flood appears after changes to `services/TGqueries.py` that increase per-comment API calls

### Minimum check before merge

Run daemon for at least 2-3 cycles and verify:

- no repeated `collect_comments ... status=flood_wait`
- flood source is present when flood happens
- comment jobs complete with mostly `status=ok` / `status=no_discussion`

## Tests

Install dependencies and run the baseline quality gate with one command:

```bash
venv\Scripts\python -m pytest -q tests
```

## Pipeline Concurrency Settings

Use `/api/settings` to tune safe concurrency limits for `scripts/run_telegram_pipeline.py` and `scripts/run_ai_pipeline.py`:

- `ingest.channel_concurrency` (default: `2`, range: `1..8`)
- `jobs.job_worker_concurrency` (default: `2`, range: `1..16`)
- `ingest.poll_seconds` controls Telegram pipeline poll interval
- `ingest.lookback_days` controls Telegram ingest lookback window
- `jobs.ai_poll_seconds` controls AI pipeline poll interval
- `jobs.ai_scheduler_limit` controls how many background post-report jobs AI pipeline enqueues per cycle

Notes:

- `collect_comments` and `refresh_comments` jobs remain sequential inside one Telegram worker to respect Telegram FloodWait limits.
- Telegram-side linking and AI report jobs run in separate pipelines and no longer compete in one worker loop.
- Runtime settings are resolved in this order: `settings table -> explicit CLI value, if settings key is absent -> canonical default`.

## Pipeline Run Commands

Run API in one process:

```bash
uvicorn api.main:app --reload
```

Run Telegram pipeline in a separate process:

```bash
python scripts/run_telegram_pipeline.py --daemon
```

Useful flags:
- `--poll-seconds 240` overrides the delay between cycles only if `ingest.poll_seconds` is absent in settings.
- `--days 3` overrides the ingest lookback window only if `ingest.lookback_days` is absent in settings.
- `--skip-rebuild-graphs` disables event/process graph rebuild after ingest.

Run AI pipeline in another separate process:

```bash
python scripts/run_ai_pipeline.py --daemon
```

Useful flags:
- `--poll-seconds 120` overrides AI cycle delay only if `jobs.ai_poll_seconds` is absent in settings.
- `--post-report-age-hours 12` overrides the minimum post age for background post reports only if `reports.post_report_delay_hours` is absent in settings.
- `--scheduler-limit 200` overrides AI scheduling limit only if `jobs.ai_scheduler_limit` is absent in settings.

Recommended setup:
- `uvicorn api.main:app --reload`
- `python scripts/run_telegram_pipeline.py --daemon`
- `python scripts/run_ai_pipeline.py --daemon`

Pipeline responsibilities:
- `scripts/run_telegram_pipeline.py`: ingest, collect/refresh comments, build post links, retention jobs.
- `scripts/run_ai_pipeline.py`: background `build_post_report` for posts older than 12 hours, plus high-priority `build_event_report` and `build_process_report` jobs triggered by API.

## Canonical Telegram Runtime

- Production Telegram runtime core: `services/pipeline_runtime.py`.
- Production Telegram entrypoint: `python scripts/run_telegram_pipeline.py --daemon`.
- `main.py`, `parse_today.py`, and `scripts/pipeline.py` are deprecated compatibility wrappers over the canonical runtime.

## Runtime Settings Contract

- Canonical runtime defaults live in `services/settings_defaults.py`.
- Effective runtime resolution order is: `settings table -> explicit CLI value -> canonical default`.
- Telegram pipeline defaults currently include:
  - `ingest.poll_seconds=240`
  - `ingest.lookback_days=3`
  - `ingest.collect_comments_sleep_min_ms=2500`
  - `ingest.collect_comments_sleep_max_ms=4500`
  - `jobs.job_batch_size=20`
  - `jobs.ai_poll_seconds=120`
  - `reports.post_report_delay_hours=12`
- Telegram env defaults currently include:
  - `TG_SESSION_NAME=tg_analytics.session`
  - `TG_FLOOD_SLEEP_THRESHOLD=5`
- Throttling scopes are different and both are supported:
  - `COMMENTS_SLEEP_*` env vars control intra-request comment iteration in `services/TGqueries.py`
  - `ingest.collect_comments_sleep_*_ms` settings control inter-job pacing in Telegram pipeline workers
