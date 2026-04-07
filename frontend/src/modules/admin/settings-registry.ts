export const settingsCategoryOrder = [
  'ingest',
  'reports',
  'retention',
  'jobs',
  'api',
  'scheduler',
  'comments',
  'monitor',
  'features',
] as const;

export type SettingsCategoryKey = (typeof settingsCategoryOrder)[number];

export type SettingsControlType = 'number' | 'boolean' | 'json';
export type SettingsUnit = 'days' | 'hours' | 'seconds' | 'milliseconds' | 'percent' | 'words' | null;
export type SettingsFieldGroupHint =
  | 'ingest-window'
  | 'comment-schedule'
  | 'comment-throttling'
  | 'report-thresholds'
  | 'report-length'
  | 'retention'
  | 'jobs-throughput'
  | 'jobs-ai'
  | 'jobs-retention'
  | 'api-defaults'
  | 'scheduler'
  | 'discussion-fallback'
  | 'comment-reconciliation'
  | 'thresholds-disk'
  | 'thresholds-memory'
  | 'thresholds-pending'
  | 'thresholds-retry'
  | 'thresholds-database'
  | 'thresholds-dead-letter'
  | 'thresholds-ingest'
  | 'thresholds-backlog'
  | 'thresholds-flood'
  | 'thresholds-rpc'
  | 'thresholds-archive'
  | 'feature-flags';

export type SettingsValueMetadata =
  | {
      kind: 'integer';
      min: number;
      max: number;
      allowedValuesLabel: string;
    }
  | {
      kind: 'float';
      min: number;
      max: number;
      allowedValuesLabel: string;
    }
  | {
      kind: 'boolean';
      allowedValuesLabel: string;
      trueLabel: string;
      falseLabel: string;
    }
  | {
      kind: 'unknown';
      allowedValuesLabel: string;
    };

export type SettingsFieldMetadata = {
  categoryKey: SettingsCategoryKey;
  key: string;
  label: string;
  helperText?: string;
  controlType: SettingsControlType;
  unit: SettingsUnit;
  value: SettingsValueMetadata;
  order: number;
  groupHint?: SettingsFieldGroupHint;
};

export type SettingsCategoryMetadata = {
  key: SettingsCategoryKey;
  label: string;
  description: string;
  badge?: string;
  order: number;
  fields: SettingsFieldMetadata[];
};

type SettingsCategoryDefinition = Omit<SettingsCategoryMetadata, 'order'>;

const fallbackAllowedValuesLabel = 'См. backend-контракт';
const fallbackHelperText = 'Параметр пришёл с backend, но пока не описан в каталоге настроек.';

function integerValue(min: number, max: number): SettingsValueMetadata {
  return { kind: 'integer', min, max, allowedValuesLabel: `int, ${min}..${max}` };
}

function floatValue(min: number, max: number): SettingsValueMetadata {
  return { kind: 'float', min, max, allowedValuesLabel: `float, ${min.toFixed(1)}..${max.toFixed(1)}` };
}

function booleanValue(): SettingsValueMetadata {
  return { kind: 'boolean', allowedValuesLabel: 'bool, true/false', trueLabel: 'true', falseLabel: 'false' };
}

function field(
  categoryKey: SettingsCategoryKey,
  order: number,
  key: string,
  label: string,
  helperText: string,
  value: SettingsValueMetadata,
  unit: SettingsUnit,
  groupHint?: SettingsFieldGroupHint,
): SettingsFieldMetadata {
  return {
    categoryKey,
    key,
    label,
    helperText,
    controlType: value.kind === 'boolean' ? 'boolean' : 'number',
    unit,
    value,
    order,
    groupHint,
  };
}

const settingsRegistryDefinitions: Record<SettingsCategoryKey, SettingsCategoryDefinition> = {
  ingest: {
    key: 'ingest',
    label: 'Загрузка данных',
    description: 'Параметры получения постов и расписания сбора комментариев.',
    fields: [
      field('ingest', 1, 'lookback_days', 'Глубина загрузки постов, дней', 'На сколько дней назад ingest смотрит при проходе по каналам.', integerValue(1, 3650), 'days', 'ingest-window'),
      field('ingest', 2, 'poll_seconds', 'Интервал опроса Telegram, сек', 'Пауза между циклами telegram pipeline.', integerValue(5, 3600), 'seconds', 'ingest-window'),
      field('ingest', 3, 'max_posts_per_channel', 'Лимит постов на канал за цикл', 'Сколько постов максимум брать из одного канала за один проход.', integerValue(1, 2000), null, 'ingest-window'),
      field('ingest', 4, 'comment_first_delay_hours', 'Первая проверка комментариев, ч', 'Через сколько часов после поста запускать первую проверку комментариев.', integerValue(1, 24), 'hours', 'comment-schedule'),
      field('ingest', 5, 'comment_interval_hours', 'Интервал проверки комментариев, ч', 'Период повторной проверки комментариев.', integerValue(1, 24), 'hours', 'comment-schedule'),
      field('ingest', 6, 'comment_window_hours', 'Окно проверки комментариев, ч', 'Сколько часов пост остаётся в окне регулярной проверки комментариев.', integerValue(1, 168), 'hours', 'comment-schedule'),
      field('ingest', 7, 'collect_comments_sleep_min_ms', 'Минимальная пауза между запросами комментариев, мс', 'Нижняя граница антифлуд-паузы при обработке comment jobs.', integerValue(0, 10000), 'milliseconds', 'comment-throttling'),
      field('ingest', 8, 'collect_comments_sleep_max_ms', 'Максимальная пауза между запросами комментариев, мс', 'Верхняя граница антифлуд-паузы при обработке comment jobs.', integerValue(0, 15000), 'milliseconds', 'comment-throttling'),
      field('ingest', 9, 'comment_schedule_jitter_seconds', 'Джиттер планирования комментариев, сек', 'Случайное смещение времени постановки jobs на комментарии.', integerValue(0, 21600), 'seconds', 'comment-schedule'),
    ],
  },
  reports: {
    key: 'reports',
    label: 'Отчёты',
    description: 'Правила генерации AI-отчётов и минимальные условия для запуска.',
    fields: [
      field('reports', 1, 'post_report_delay_hours', 'Задержка генерации отчёта по посту, ч', 'Минимальный возраст поста перед постановкой AI-отчёта.', integerValue(1, 72), 'hours', 'report-thresholds'),
      field('reports', 2, 'min_comments', 'Минимум комментариев для отчёта', 'Порог, ниже которого отчёт по посту не строится.', integerValue(0, 100000), null, 'report-thresholds'),
      field('reports', 3, 'report_word_target', 'Целевая длина отчёта, слов', 'Ориентир длины текста AI-отчёта.', integerValue(50, 3000), 'words', 'report-length'),
      field('reports', 4, 'report_word_min', 'Минимальная длина отчёта, слов', 'Нижняя граница длины AI-отчёта.', integerValue(50, 3000), 'words', 'report-length'),
      field('reports', 5, 'report_word_max', 'Максимальная длина отчёта, слов', 'Верхняя граница длины AI-отчёта.', integerValue(50, 5000), 'words', 'report-length'),
    ],
  },
  retention: {
    key: 'retention',
    label: 'Хранение данных',
    description: 'Сроки хранения и пакетная архивация исторических данных.',
    fields: [
      field('retention', 1, 'retention_days', 'Срок хранения постов, дней', 'Через сколько дней данные считаются кандидатами на архивацию.', integerValue(1, 3650), 'days', 'retention'),
      field('retention', 2, 'archive_batch_size', 'Размер батча архивации', 'Сколько записей обрабатывать за один retention job.', integerValue(10, 50000), null, 'retention'),
    ],
  },
  jobs: {
    key: 'jobs',
    label: 'Задания',
    description: 'Параметры очереди, AI-пайплайна и очистки завершённых заданий.',
    fields: [
      field('jobs', 1, 'job_batch_size', 'Размер батча jobs', 'Сколько jobs воркер забирает за один проход.', integerValue(1, 5000), null, 'jobs-throughput'),
      field('jobs', 2, 'job_worker_concurrency', 'Параллелизм job-воркера', 'Сколько jobs можно выполнять параллельно.', integerValue(1, 16), null, 'jobs-throughput'),
      field('jobs', 3, 'collect_comments_quota_per_run', 'Квота comment jobs за проход', 'Ограничение числа jobs на сбор комментариев в одном цикле.', integerValue(1, 5000), null, 'jobs-throughput'),
      field('jobs', 4, 'ai_poll_seconds', 'Интервал опроса AI-очереди, сек', 'Пауза между циклами AI pipeline.', integerValue(5, 3600), 'seconds', 'jobs-ai'),
      field('jobs', 5, 'ai_job_timeout_seconds', 'Таймаут AI-job, сек', 'Максимальное время ожидания выполнения одной AI-задачи.', integerValue(5, 7200), 'seconds', 'jobs-ai'),
      field('jobs', 6, 'ai_scheduler_limit', 'Лимит постановки AI-отчётов', 'Сколько AI jobs можно поставить за один цикл планировщика.', integerValue(1, 10000), null, 'jobs-ai'),
      field('jobs', 7, 'done_retention_days', 'Хранение завершённых jobs, дней', 'Через сколько дней чистить jobs в статусе done.', integerValue(1, 3650), 'days', 'jobs-retention'),
      field('jobs', 8, 'dead_letter_retention_days', 'Хранение dead-letter jobs, дней', 'Через сколько дней чистить dead-letter jobs.', integerValue(1, 3650), 'days', 'jobs-retention'),
      field('jobs', 9, 'cleanup_batch_size', 'Размер батча очистки jobs', 'Сколько jobs удалять за один cleanup job.', integerValue(10, 50000), null, 'jobs-retention'),
    ],
  },
  api: {
    key: 'api',
    label: 'API',
    description: 'Базовые ограничения и значения по умолчанию для API-ответов.',
    fields: [
      field('api', 1, 'top_posts_default_limit', 'Лимит записей по умолчанию', 'Стандартный limit для dashboard-эндпоинтов, если параметр не передан.', integerValue(1, 500), null, 'api-defaults'),
    ],
  },
  scheduler: {
    key: 'scheduler',
    label: 'Планировщик',
    description: 'Глобальные настройки планировщика retention-задач.',
    fields: [
      field('scheduler', 1, 'enabled', 'Включить планировщик retention', 'Глобальный переключатель APScheduler-процесса.', booleanValue(), null, 'scheduler'),
      field('scheduler', 2, 'retention_hour', 'Час запуска retention', 'Час ежедневного запуска retention jobs.', integerValue(0, 23), 'hours', 'scheduler'),
      field('scheduler', 3, 'retention_minute', 'Минута запуска retention', 'Минута ежедневного запуска retention jobs.', integerValue(0, 59), null, 'scheduler'),
    ],
  },
  comments: {
    key: 'comments',
    label: 'Комментарии',
    description: 'Параметры обхода discussion-тредов, антифлуда и сверки комментариев.',
    fields: [
      field('comments', 1, 'discussion_fallback_id_window', 'Окно поиска discussion message', 'На сколько соседних message id проверять fallback при поиске discussion thread.', integerValue(0, 20), null, 'discussion-fallback'),
      field('comments', 2, 'discussion_fallback_max_seconds', 'Допуск по времени discussion fallback, сек', 'Максимальное допустимое расхождение по времени при fallback-поиске discussion.', integerValue(0, 300), 'seconds', 'discussion-fallback'),
      field('comments', 3, 'sleep_every', 'Частота мягкой паузы при обходе комментариев', 'После скольких комментариев делать защитную паузу.', integerValue(1, 1000), null, 'comment-throttling'),
      field('comments', 4, 'sleep_base_sec', 'Базовая пауза при обходе комментариев, сек', 'Базовая антифлуд-пауза во время чтения треда.', floatValue(0, 30), 'seconds', 'comment-throttling'),
      field('comments', 5, 'sleep_jitter_sec', 'Джиттер паузы при обходе комментариев, сек', 'Случайная добавка к антифлуд-паузе.', floatValue(0, 30), 'seconds', 'comment-throttling'),
      field('comments', 6, 'reconciliation_enabled', 'Включить сверку снимка комментариев', 'Удалять устаревшие комментарии после подтверждённого пересканирования треда.', booleanValue(), null, 'comment-reconciliation'),
      field('comments', 7, 'album_discussion_expansion_steps', 'Глубина поиска discussion для альбомов', 'Сколько расширений окна использовать при поиске сообщения альбома с discussion.', integerValue(2, 30), null, 'discussion-fallback'),
    ],
  },
  monitor: {
    key: 'monitor',
    label: 'Мониторинг',
    description: 'Технические пороги алертов, лага и состояния инфраструктуры.',
    badge: 'Технический раздел',
    fields: [
      field('monitor', 1, 'disk_used_percent_warn', 'Диск: warning, %', 'Порог warning по занятости диска.', floatValue(1, 99), 'percent', 'thresholds-disk'),
      field('monitor', 2, 'disk_used_percent_crit', 'Диск: critical, %', 'Порог critical по занятости диска.', floatValue(1, 99), 'percent', 'thresholds-disk'),
      field('monitor', 3, 'memory_used_percent_warn', 'Память: warning, %', 'Порог warning по использованию памяти.', floatValue(1, 99), 'percent', 'thresholds-memory'),
      field('monitor', 4, 'memory_used_percent_crit', 'Память: critical, %', 'Порог critical по использованию памяти.', floatValue(1, 99), 'percent', 'thresholds-memory'),
      field('monitor', 5, 'pending_jobs_warn', 'Pending jobs: warning', 'Порог warning по количеству pending jobs.', integerValue(0, 5000000), null, 'thresholds-pending'),
      field('monitor', 6, 'pending_jobs_crit', 'Pending jobs: critical', 'Порог critical по количеству pending jobs.', integerValue(0, 5000000), null, 'thresholds-pending'),
      field('monitor', 7, 'pending_lag_seconds_warn', 'Pending lag: warning, сек', 'Порог warning по задержке pending jobs.', integerValue(0, 86400), 'seconds', 'thresholds-pending'),
      field('monitor', 8, 'pending_lag_seconds_crit', 'Pending lag: critical, сек', 'Порог critical по задержке pending jobs.', integerValue(0, 604800), 'seconds', 'thresholds-pending'),
      field('monitor', 9, 'retry_lag_seconds_warn', 'Retry lag: warning, сек', 'Порог warning по задержке retry jobs.', integerValue(0, 86400), 'seconds', 'thresholds-retry'),
      field('monitor', 10, 'retry_lag_seconds_crit', 'Retry lag: critical, сек', 'Порог critical по задержке retry jobs.', integerValue(0, 604800), 'seconds', 'thresholds-retry'),
      field('monitor', 11, 'database_latency_ms_warn', 'База данных: warning, мс', 'Порог warning по latency БД.', floatValue(0, 60000), 'milliseconds', 'thresholds-database'),
      field('monitor', 12, 'database_latency_ms_crit', 'База данных: critical, мс', 'Порог critical по latency БД.', floatValue(0, 60000), 'milliseconds', 'thresholds-database'),
      field('monitor', 13, 'dead_letter_count_warn', 'Dead-letter: warning', 'Порог warning по размеру dead-letter очереди.', integerValue(0, 1000000), null, 'thresholds-dead-letter'),
      field('monitor', 14, 'dead_letter_count_crit', 'Dead-letter: critical', 'Порог critical по размеру dead-letter очереди.', integerValue(0, 1000000), null, 'thresholds-dead-letter'),
      field('monitor', 15, 'ingest_lag_seconds_warn', 'Ingest lag: warning, сек', 'Порог warning по отставанию ingestion.', integerValue(0, 31536000), 'seconds', 'thresholds-ingest'),
      field('monitor', 16, 'ingest_lag_seconds_crit', 'Ingest lag: critical, сек', 'Порог critical по отставанию ingestion.', integerValue(0, 31536000), 'seconds', 'thresholds-ingest'),
      field('monitor', 17, 'backlog_delta_1h_warn', 'Рост backlog за час: warning', 'Порог warning по росту очереди jobs за час.', integerValue(0, 10000000), null, 'thresholds-backlog'),
      field('monitor', 18, 'backlog_delta_1h_crit', 'Рост backlog за час: critical', 'Порог critical по росту очереди jobs за час.', integerValue(0, 10000000), null, 'thresholds-backlog'),
      field('monitor', 19, 'collect_comments_flood_rate_warn', 'Flood rate комментариев: warning', 'Порог warning по доле FloodWait ошибок.', floatValue(0, 1), null, 'thresholds-flood'),
      field('monitor', 20, 'collect_comments_flood_rate_crit', 'Flood rate комментариев: critical', 'Порог critical по доле FloodWait ошибок.', floatValue(0, 1), null, 'thresholds-flood'),
      field('monitor', 21, 'collect_comments_rpc_rate_warn', 'RPC error rate комментариев: warning', 'Порог warning по доле RPC-ошибок.', floatValue(0, 1), null, 'thresholds-rpc'),
      field('monitor', 22, 'collect_comments_rpc_rate_crit', 'RPC error rate комментариев: critical', 'Порог critical по доле RPC-ошибок.', floatValue(0, 1), null, 'thresholds-rpc'),
      field('monitor', 23, 'archive_lag_seconds_warn', 'Archive lag: warning, сек', 'Порог warning по задержке архивации.', integerValue(0, 31536000), 'seconds', 'thresholds-archive'),
      field('monitor', 24, 'archive_lag_seconds_crit', 'Archive lag: critical, сек', 'Порог critical по задержке архивации.', integerValue(0, 31536000), 'seconds', 'thresholds-archive'),
      field('monitor', 25, 'telegram_disconnected_is_warn', 'Telegram disconnect считать warning', 'Показывать warning, если telegram pipeline недоступен.', booleanValue(), null, 'thresholds-ingest'),
    ],
  },
  features: {
    key: 'features',
    label: 'Функции',
    description: 'Фичефлаги и rollout-параметры для отдельных возможностей.',
    fields: [
      field('features', 1, 'keyword_graph_api_enabled', 'Включить API графа ключевых слов', 'Глобальный переключатель keyword graph API.', booleanValue(), null, 'feature-flags'),
      field('features', 2, 'keyword_graph_rollout_percent', 'Rollout графа ключевых слов, %', 'Доля пользователей, которым доступен keyword graph.', integerValue(0, 100), 'percent', 'feature-flags'),
    ],
  },
};

export const settingsRegistry: Record<SettingsCategoryKey, SettingsCategoryMetadata> = settingsCategoryOrder.reduce(
  (registry, categoryKey, index) => {
    registry[categoryKey] = {
      ...settingsRegistryDefinitions[categoryKey],
      order: index + 1,
    };

    return registry;
  },
  {} as Record<SettingsCategoryKey, SettingsCategoryMetadata>,
);

export function getSettingsCategoryMetadata(categoryKey: SettingsCategoryKey): SettingsCategoryMetadata {
  return settingsRegistry[categoryKey];
}

export function listSettingsFieldMetadata(categoryKey: SettingsCategoryKey): SettingsFieldMetadata[] {
  return [...settingsRegistry[categoryKey].fields].sort((left, right) => left.order - right.order);
}

export function getSettingsFieldMetadata(
  categoryKey: SettingsCategoryKey,
  fieldKey: string,
): SettingsFieldMetadata | null {
  return settingsRegistry[categoryKey].fields.find((field) => field.key === fieldKey) ?? null;
}

export function createFallbackSettingsFieldMetadata(
  categoryKey: SettingsCategoryKey,
  fieldKey: string,
  order = Number.MAX_SAFE_INTEGER,
): SettingsFieldMetadata {
  return {
    categoryKey,
    key: fieldKey,
    label: fieldKey,
    helperText: fallbackHelperText,
    controlType: 'json',
    unit: null,
    value: {
      kind: 'unknown',
      allowedValuesLabel: fallbackAllowedValuesLabel,
    },
    order,
  };
}

export function getSettingsFieldMetadataOrFallback(
  categoryKey: SettingsCategoryKey,
  fieldKey: string,
  order = Number.MAX_SAFE_INTEGER,
): SettingsFieldMetadata {
  return getSettingsFieldMetadata(categoryKey, fieldKey) ?? createFallbackSettingsFieldMetadata(categoryKey, fieldKey, order);
}

export const settingsRegistryStats = {
  categoryCount: settingsCategoryOrder.length,
  fieldCount: settingsCategoryOrder.reduce((total, categoryKey) => total + settingsRegistry[categoryKey].fields.length, 0),
};
