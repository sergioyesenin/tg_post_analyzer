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

5. In `scripts/pipeline.py` flood-wait requeue must not run earlier than global cooldown.
   - Keep `effective_retry_at = max(retry_at, collect_comments_global_cooldown_until)`.

6. Default inter-job sleeps for collect-comments in `scripts/pipeline.py` must remain conservative.
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

Use `/api/settings` to tune safe concurrency limits for `scripts/pipeline.py`:

- `ingest.channel_concurrency` (default: `2`, range: `1..8`)
- `jobs.job_worker_concurrency` (default: `2`, range: `1..16`)

Notes:

- `collect_comments` jobs remain sequential inside one worker to respect Telegram FloodWait limits.
- Non-Telegram jobs (`build_*_report`, `archive_retention`) can run in parallel up to `job_worker_concurrency`.
