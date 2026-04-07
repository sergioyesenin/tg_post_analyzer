# Admin Settings Catalog

Каталог актуальных параметров, которые доступны или должны отображаться в админском разделе `/settings`.

| Scope | Key | Русское название | Допустимые значения | Назначение |
| --- | --- | --- | --- | --- |
| `ingest` | `lookback_days` | Глубина загрузки постов, дней | `int`, `1..3650` | На сколько дней назад ingest смотрит при проходе по каналам |
| `ingest` | `poll_seconds` | Интервал опроса Telegram, сек | `int`, `5..3600` | Пауза между циклами telegram pipeline |
| `ingest` | `max_posts_per_channel` | Лимит постов на канал за цикл | `int`, `1..2000` | Сколько постов максимум брать из одного канала за один проход |
| `ingest` | `comment_first_delay_hours` | Первая проверка комментариев, ч | `int`, `1..24` | Через сколько часов после поста запускать первую проверку комментариев |
| `ingest` | `comment_interval_hours` | Интервал проверки комментариев, ч | `int`, `1..24` | Период повторной проверки комментариев |
| `ingest` | `comment_window_hours` | Окно проверки комментариев, ч | `int`, `1..168` | Сколько часов пост остаётся в окне регулярной проверки комментариев |
| `ingest` | `collect_comments_sleep_min_ms` | Минимальная пауза между запросами комментариев, мс | `int`, `0..10000` | Нижняя граница антифлуд-паузы при обработке comment jobs |
| `ingest` | `collect_comments_sleep_max_ms` | Максимальная пауза между запросами комментариев, мс | `int`, `0..15000` | Верхняя граница антифлуд-паузы при обработке comment jobs |
| `ingest` | `comment_schedule_jitter_seconds` | Джиттер планирования комментариев, сек | `int`, `0..21600` | Случайное смещение времени постановки jobs на комментарии |
| `reports` | `post_report_delay_hours` | Задержка генерации отчёта по посту, ч | `int`, `1..72` | Минимальный возраст поста перед постановкой AI-отчёта |
| `reports` | `min_comments` | Минимум комментариев для отчёта | `int`, `0..100000` | Порог, ниже которого отчёт по посту не строится |
| `reports` | `report_word_target` | Целевая длина отчёта, слов | `int`, `50..3000` | Ориентир длины текста AI-отчёта |
| `reports` | `report_word_min` | Минимальная длина отчёта, слов | `int`, `50..3000` | Нижняя граница длины AI-отчёта |
| `reports` | `report_word_max` | Максимальная длина отчёта, слов | `int`, `50..5000` | Верхняя граница длины AI-отчёта |
| `retention` | `retention_days` | Срок хранения постов, дней | `int`, `1..3650` | Через сколько дней данные считаются кандидатами на архивацию |
| `retention` | `archive_batch_size` | Размер батча архивации | `int`, `10..50000` | Сколько записей обрабатывать за один retention job |
| `jobs` | `job_batch_size` | Размер батча jobs | `int`, `1..5000` | Сколько jobs воркер забирает за один проход |
| `jobs` | `job_worker_concurrency` | Параллелизм job-воркера | `int`, `1..16` | Сколько jobs можно выполнять параллельно |
| `jobs` | `collect_comments_quota_per_run` | Квота comment jobs за проход | `int`, `1..5000` | Ограничение числа jobs на сбор комментариев в одном цикле |
| `jobs` | `ai_poll_seconds` | Интервал опроса AI-очереди, сек | `int`, `5..3600` | Пауза между циклами AI pipeline |
| `jobs` | `ai_job_timeout_seconds` | Таймаут AI-job, сек | `int`, `5..7200` | Максимальное время ожидания выполнения одной AI-задачи |
| `jobs` | `ai_scheduler_limit` | Лимит постановки AI-отчётов | `int`, `1..10000` | Сколько AI jobs можно поставить за один цикл планировщика |
| `jobs` | `done_retention_days` | Хранение завершённых jobs, дней | `int`, `1..3650` | Через сколько дней чистить jobs в статусе `done` |
| `jobs` | `dead_letter_retention_days` | Хранение dead-letter jobs, дней | `int`, `1..3650` | Через сколько дней чистить dead-letter jobs |
| `jobs` | `cleanup_batch_size` | Размер батча очистки jobs | `int`, `10..50000` | Сколько jobs удалять за один cleanup job |
| `api` | `top_posts_default_limit` | Лимит записей по умолчанию | `int`, `1..500` | Стандартный `limit` для dashboard-эндпоинтов, если параметр не передан |
| `scheduler` | `enabled` | Включить планировщик retention | `bool`, `true/false` | Глобальный переключатель APScheduler-процесса |
| `scheduler` | `retention_hour` | Час запуска retention | `int`, `0..23` | Час ежедневного запуска retention jobs |
| `scheduler` | `retention_minute` | Минута запуска retention | `int`, `0..59` | Минута ежедневного запуска retention jobs |
| `comments` | `discussion_fallback_id_window` | Окно поиска discussion message | `int`, `0..20` | На сколько соседних message id проверять fallback при поиске discussion thread |
| `comments` | `discussion_fallback_max_seconds` | Допуск по времени discussion fallback, сек | `int`, `0..300` | Максимальное допустимое расхождение по времени при fallback-поиске discussion |
| `comments` | `sleep_every` | Частота мягкой паузы при обходе комментариев | `int`, `1..1000` | После скольких комментариев делать защитную паузу |
| `comments` | `sleep_base_sec` | Базовая пауза при обходе комментариев, сек | `float`, `0.0..30.0` | Базовая антифлуд-пауза во время чтения треда |
| `comments` | `sleep_jitter_sec` | Джиттер паузы при обходе комментариев, сек | `float`, `0.0..30.0` | Случайная добавка к антифлуд-паузе |
| `comments` | `reconciliation_enabled` | Включить сверку снимка комментариев | `bool`, `true/false` | Удалять устаревшие комментарии после подтверждённого пересканирования треда |
| `comments` | `album_discussion_expansion_steps` | Глубина поиска discussion для альбомов | `int`, `2..30` | Сколько расширений окна использовать при поиске сообщения альбома с discussion |
| `monitor` | `disk_used_percent_warn` | Диск: warning, % | `float`, `1..99` | Порог warning по занятости диска |
| `monitor` | `disk_used_percent_crit` | Диск: critical, % | `float`, `1..99` | Порог critical по занятости диска |
| `monitor` | `memory_used_percent_warn` | Память: warning, % | `float`, `1..99` | Порог warning по использованию памяти |
| `monitor` | `memory_used_percent_crit` | Память: critical, % | `float`, `1..99` | Порог critical по использованию памяти |
| `monitor` | `pending_jobs_warn` | Pending jobs: warning | `int`, `0..5000000` | Порог warning по количеству pending jobs |
| `monitor` | `pending_jobs_crit` | Pending jobs: critical | `int`, `0..5000000` | Порог critical по количеству pending jobs |
| `monitor` | `pending_lag_seconds_warn` | Pending lag: warning, сек | `int`, `0..86400` | Порог warning по задержке pending jobs |
| `monitor` | `pending_lag_seconds_crit` | Pending lag: critical, сек | `int`, `0..604800` | Порог critical по задержке pending jobs |
| `monitor` | `retry_lag_seconds_warn` | Retry lag: warning, сек | `int`, `0..86400` | Порог warning по задержке retry jobs |
| `monitor` | `retry_lag_seconds_crit` | Retry lag: critical, сек | `int`, `0..604800` | Порог critical по задержке retry jobs |
| `monitor` | `database_latency_ms_warn` | База данных: warning, мс | `float`, `0..60000` | Порог warning по latency БД |
| `monitor` | `database_latency_ms_crit` | База данных: critical, мс | `float`, `0..60000` | Порог critical по latency БД |
| `monitor` | `dead_letter_count_warn` | Dead-letter: warning | `int`, `0..1000000` | Порог warning по размеру dead-letter очереди |
| `monitor` | `dead_letter_count_crit` | Dead-letter: critical | `int`, `0..1000000` | Порог critical по размеру dead-letter очереди |
| `monitor` | `ingest_lag_seconds_warn` | Ingest lag: warning, сек | `int`, `0..31536000` | Порог warning по отставанию ingestion |
| `monitor` | `ingest_lag_seconds_crit` | Ingest lag: critical, сек | `int`, `0..31536000` | Порог critical по отставанию ingestion |
| `monitor` | `backlog_delta_1h_warn` | Рост backlog за час: warning | `int`, `0..10000000` | Порог warning по росту очереди jobs за час |
| `monitor` | `backlog_delta_1h_crit` | Рост backlog за час: critical | `int`, `0..10000000` | Порог critical по росту очереди jobs за час |
| `monitor` | `collect_comments_flood_rate_warn` | Flood rate комментариев: warning | `float`, `0.0..1.0` | Порог warning по доле FloodWait ошибок |
| `monitor` | `collect_comments_flood_rate_crit` | Flood rate комментариев: critical | `float`, `0.0..1.0` | Порог critical по доле FloodWait ошибок |
| `monitor` | `collect_comments_rpc_rate_warn` | RPC error rate комментариев: warning | `float`, `0.0..1.0` | Порог warning по доле RPC-ошибок |
| `monitor` | `collect_comments_rpc_rate_crit` | RPC error rate комментариев: critical | `float`, `0.0..1.0` | Порог critical по доле RPC-ошибок |
| `monitor` | `archive_lag_seconds_warn` | Archive lag: warning, сек | `int`, `0..31536000` | Порог warning по задержке архивации |
| `monitor` | `archive_lag_seconds_crit` | Archive lag: critical, сек | `int`, `0..31536000` | Порог critical по задержке архивации |
| `monitor` | `telegram_disconnected_is_warn` | Telegram disconnect считать warning | `bool`, `true/false` | Показывать warning, если telegram pipeline недоступен |
| `features` | `keyword_graph_api_enabled` | Включить API графа ключевых слов | `bool`, `true/false` | Глобальный переключатель keyword graph API |
| `features` | `keyword_graph_rollout_percent` | Rollout графа ключевых слов, % | `int`, `0..100` | Доля пользователей, которым доступен keyword graph |

## Рекомендации для UI

- Основные разделы меню: `ingest`, `reports`, `retention`, `jobs`, `api`, `scheduler`, `comments`, `monitor`, `features`.
- Для обычного admin-UX раздел `monitor` лучше пометить как расширенный или технический.
- Для кнопок и заголовков можно использовать колонку `Русское название` как базовый label, а колонку `Назначение` как helper text.
