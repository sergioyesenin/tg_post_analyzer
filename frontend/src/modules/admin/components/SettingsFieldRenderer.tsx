import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { formatSettingValue, type SettingsParameterViewModel } from '@modules/admin/mappers';

type SettingsFieldRendererProps = {
  parameters: SettingsParameterViewModel[];
  values: Record<string, unknown>;
  errors?: Record<string, string>;
  readOnly: boolean;
  onChange: (key: string, value: unknown) => void;
};

type SettingsGroup = {
  key: string;
  title: string | null;
  parameters: SettingsParameterViewModel[];
};

const groupTitles: Partial<Record<NonNullable<SettingsParameterViewModel['groupHint']>, string>> = {
  'ingest-window': 'Загрузка постов',
  'comment-schedule': 'Расписание комментариев',
  'comment-throttling': 'Антифлуд и паузы',
  'report-thresholds': 'Пороги запуска',
  'report-length': 'Длина отчёта',
  retention: 'Хранение и архивация',
  'jobs-throughput': 'Пропускная способность',
  'jobs-ai': 'AI-пайплайн',
  'jobs-retention': 'Очистка и ретеншн',
  'api-defaults': 'Значения по умолчанию',
  scheduler: 'Параметры планировщика',
  'discussion-fallback': 'Поиск discussion',
  'comment-reconciliation': 'Сверка комментариев',
  'thresholds-disk': 'Пороги по диску',
  'thresholds-memory': 'Пороги по памяти',
  'thresholds-pending': 'Pending jobs',
  'thresholds-retry': 'Retry jobs',
  'thresholds-database': 'База данных',
  'thresholds-dead-letter': 'Dead-letter',
  'thresholds-ingest': 'Ingest и Telegram',
  'thresholds-backlog': 'Backlog',
  'thresholds-flood': 'FloodWait',
  'thresholds-rpc': 'RPC-ошибки',
  'thresholds-archive': 'Архивация',
  'feature-flags': 'Фичефлаги',
};

const unitLabels: Partial<Record<NonNullable<SettingsParameterViewModel['unit']>, string>> = {
  days: 'дней',
  hours: 'ч',
  seconds: 'сек',
  milliseconds: 'мс',
  percent: '%',
  words: 'слов',
};

function parseFallbackInput(value: string): unknown {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function formatFallbackInput(value: unknown): string {
  if (value === undefined) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function isSmallBoundedInteger(parameter: SettingsParameterViewModel): boolean {
  return parameter.valueMetadata.kind === 'integer' && parameter.valueMetadata.max - parameter.valueMetadata.min <= 100;
}

function getNumberStep(parameter: SettingsParameterViewModel): string {
  if (parameter.valueMetadata.kind === 'float') {
    return parameter.valueMetadata.max <= 1 ? '0.01' : '0.1';
  }

  return '1';
}

function buildGroups(parameters: SettingsParameterViewModel[]): SettingsGroup[] {
  const groups: SettingsGroup[] = [];
  const indexByKey = new Map<string, number>();

  parameters.forEach((parameter) => {
    const key = parameter.groupHint ?? `__ungrouped_${parameter.key}`;
    const existingIndex = indexByKey.get(key);

    if (existingIndex === undefined) {
      indexByKey.set(key, groups.length);
      groups.push({
        key,
        title: parameter.groupHint ? (groupTitles[parameter.groupHint] ?? null) : null,
        parameters: [parameter],
      });
      return;
    }

    groups[existingIndex]!.parameters.push(parameter);
  });

  return groups;
}

export function SettingsFieldRenderer({ parameters, values, errors = {}, readOnly, onChange }: SettingsFieldRendererProps) {
  const { t } = useTranslation();
  const groups = useMemo(() => buildGroups(parameters), [parameters]);

  return (
    <div className="settings-field-renderer">
      {groups.map((group) => (
        <section key={group.key} className="settings-field-group">
          {group.title ? <h4 className="settings-field-group__title">{group.title}</h4> : null}
          <div className="settings-field-group__grid">
            {group.parameters.map((parameter) => {
              const rawValue = values[parameter.key];
              const controlId = `settings-field-${parameter.key}`;
              const helperId = `${controlId}-helper`;
              const metaId = `${controlId}-meta`;
              const errorId = `${controlId}-error`;
              const currentValueLabel = formatSettingValue(rawValue);
              const unitLabel = parameter.unit ? unitLabels[parameter.unit] : null;
              const isBoolean = parameter.valueMetadata.kind === 'boolean';
              const usesSlider = isSmallBoundedInteger(parameter);
              const errorMessage = errors[parameter.key];
              const describedBy = [helperId, metaId, errorMessage ? errorId : null].filter(Boolean).join(' ');

              return (
                <article key={parameter.key} className="settings-field-card">
                  <div className="settings-field-card__header">
                    <div>
                      <label htmlFor={controlId} className="settings-field-card__label">
                        {parameter.label}
                      </label>
                      <div className="settings-field-card__key">{parameter.key}</div>
                    </div>
                    {!parameter.isDocumented ? <span className="settings-parameter-card__badge">{t('admin.settings.fallbackBadge')}</span> : null}
                  </div>

                  {parameter.purpose ? (
                    <p id={helperId} className="dashboard-panel-copy settings-field-card__helper">
                      {parameter.purpose}
                    </p>
                  ) : null}

                  <div className="settings-field-card__control">
                    {isBoolean ? (
                      <label className={`settings-switch ${readOnly ? 'settings-switch--readonly' : ''}`.trim()}>
                        <input
                          id={controlId}
                          type="checkbox"
                          role="switch"
                          checked={Boolean(rawValue)}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errorMessage)}
                          disabled={readOnly}
                          onChange={(event) => onChange(parameter.key, event.target.checked)}
                        />
                        <span className="settings-switch__track" aria-hidden="true">
                          <span className="settings-switch__thumb" />
                        </span>
                        <span className="settings-switch__label">{currentValueLabel}</span>
                      </label>
                    ) : usesSlider ? (
                      <div className="settings-field-card__slider">
                        <input
                          id={controlId}
                          type="range"
                          min={parameter.valueMetadata.kind === 'integer' ? parameter.valueMetadata.min : undefined}
                          max={parameter.valueMetadata.kind === 'integer' ? parameter.valueMetadata.max : undefined}
                          step={getNumberStep(parameter)}
                          value={typeof rawValue === 'number' ? rawValue : parameter.valueMetadata.kind === 'integer' ? parameter.valueMetadata.min : 0}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errorMessage)}
                          disabled={readOnly}
                          onChange={(event) => onChange(parameter.key, Number(event.target.value))}
                        />
                        <output htmlFor={controlId}>{currentValueLabel}</output>
                      </div>
                    ) : parameter.valueMetadata.kind === 'integer' || parameter.valueMetadata.kind === 'float' ? (
                      <div className="settings-field-card__number-input">
                        <input
                          id={controlId}
                          type="number"
                          min={parameter.valueMetadata.min}
                          max={parameter.valueMetadata.max}
                          step={getNumberStep(parameter)}
                          value={typeof rawValue === 'number' ? String(rawValue) : ''}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(errorMessage)}
                          className={errorMessage ? 'dashboard-filter-input--invalid' : ''}
                          disabled={readOnly}
                          onChange={(event) => {
                            const nextValue = event.target.value;
                            onChange(parameter.key, nextValue === '' ? undefined : Number(nextValue));
                          }}
                        />
                        {unitLabel ? <span className="settings-field-card__unit">{unitLabel}</span> : null}
                      </div>
                    ) : (
                      <textarea
                        id={controlId}
                        rows={4}
                        value={formatFallbackInput(rawValue)}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(errorMessage)}
                        className={errorMessage ? 'dashboard-filter-input--invalid' : ''}
                        disabled={readOnly}
                        onChange={(event) => onChange(parameter.key, parseFallbackInput(event.target.value))}
                      />
                    )}
                  </div>

                  {errorMessage ? (
                    <small id={errorId} className="dashboard-filter-field__error settings-field-card__error">
                      {errorMessage}
                    </small>
                  ) : null}

                  <div id={metaId} className="settings-field-card__facts">
                    <div>
                      <span>{t('admin.settings.allowedValuesLabel')}</span>
                      <strong>{parameter.allowedValues}</strong>
                    </div>
                    <div>
                      <span>{t('admin.settings.effectiveValueLabel')}</span>
                      <strong>{currentValueLabel}</strong>
                    </div>
                    {unitLabel ? (
                      <div>
                        <span>Единица</span>
                        <strong>{unitLabel}</strong>
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
