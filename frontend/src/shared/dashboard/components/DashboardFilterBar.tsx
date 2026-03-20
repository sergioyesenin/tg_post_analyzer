import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import type { DashboardFilterOptionsByMode } from '@shared/dashboard/filter-options';
import {
  getDashboardFilterConfig,
  serializeDashboardFilters,
  type DashboardFiltersByMode,
} from '@shared/dashboard/filters';

type ChannelOptionsState = 'ready' | 'loading' | 'error';

type DashboardFilterBarProps<TMode extends DashboardMode> = {
  mode: TMode;
  filters: DashboardFiltersByMode[TMode];
  options: DashboardFilterOptionsByMode[TMode];
  onApply: (filters: DashboardFiltersByMode[TMode]) => void;
  onReset: () => void;
  channelOptionsState?: ChannelOptionsState;
};

type FilterFormState = {
  date_from: string;
  date_to: string;
  limit: string;
  min_comments: string;
  sort_by: string;
  sort_order: string;
  channel_ids: number[];
  categories: string[];
  status: string[];
  report_status: string[];
};

function buildFormState<TMode extends DashboardMode>(filters: DashboardFiltersByMode[TMode]): FilterFormState {
  return {
    date_from: String(filters.date_from ?? ''),
    date_to: String(filters.date_to ?? ''),
    limit: String(filters.limit ?? ''),
    min_comments: filters.min_comments === null ? '' : String(filters.min_comments),
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
    channel_ids: 'channel_ids' in filters ? [...filters.channel_ids] : [],
    categories: 'categories' in filters ? [...filters.categories] : [],
    status: 'status' in filters ? [...filters.status] : [],
    report_status: 'report_status' in filters ? [...filters.report_status] : [],
  };
}

function toggleArrayValue<TValue extends string | number>(currentValues: TValue[], value: TValue) {
  return currentValues.includes(value) ? currentValues.filter((item) => item !== value) : [...currentValues, value];
}

function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="dashboard-filter-field">
      <span className="dashboard-filter-field__label">{label}</span>
      {children}
    </div>
  );
}

function FilterChipGroup<TValue extends string | number>({
  legend,
  options,
  selectedValues,
  onToggle,
  getLabel,
}: {
  legend: string;
  options: Array<{ value: TValue; label: string; description?: string | null }>;
  selectedValues: TValue[];
  onToggle: (value: TValue) => void;
  getLabel?: (option: { value: TValue; label: string }) => string;
}) {
  return (
    <fieldset className="dashboard-chip-fieldset">
      <legend className="dashboard-chip-fieldset__legend">{legend}</legend>
      <div className="dashboard-chip-group" role="group" aria-label={legend}>
        {options.map((option) => {
          const isSelected = selectedValues.includes(option.value);

          return (
            <button
              key={String(option.value)}
              type="button"
              className={`dashboard-filter-chip ${isSelected ? 'dashboard-filter-chip--selected' : ''}`.trim()}
              aria-pressed={isSelected}
              onClick={() => onToggle(option.value)}
              title={option.description ?? undefined}
            >
              <span>{getLabel ? getLabel(option) : option.label}</span>
              {option.description ? <small>{option.description}</small> : null}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function DashboardFilterBar<TMode extends DashboardMode>({
  mode,
  filters,
  options,
  onApply,
  onReset,
  channelOptionsState = 'ready',
}: DashboardFilterBarProps<TMode>) {
  const { t } = useTranslation();
  const config = getDashboardFilterConfig(mode);
  const [formState, setFormState] = useState(() => buildFormState(filters));

  const previewQuery = useMemo(() => serializeDashboardFilters(mode, filters), [filters, mode]);

  useEffect(() => {
    setFormState(buildFormState(filters));
  }, [filters]);

  const updateField = (name: keyof FilterFormState, value: string) => {
    setFormState((current) => ({
      ...current,
      [name]: value,
    }));
  };

  const toggleListField = <TKey extends 'channel_ids' | 'categories' | 'status' | 'report_status'>(field: TKey, value: FilterFormState[TKey][number]) => {
    setFormState((current) => ({
      ...current,
      [field]: toggleArrayValue(current[field] as Array<string | number>, value),
    }));
  };

  const handleApply = () => {
    const nextFilters = {
      ...filters,
      date_from: formState.date_from || (mode === 'posts' ? '' : null),
      date_to: formState.date_to || (mode === 'posts' ? '' : null),
      limit: Number(formState.limit) || filters.limit,
      min_comments: formState.min_comments ? Number(formState.min_comments) : null,
      sort_by: formState.sort_by,
      sort_order: formState.sort_order,
    } as DashboardFiltersByMode[TMode];

    if ('channel_ids' in nextFilters) {
      nextFilters.channel_ids = [...formState.channel_ids];
    }

    if ('categories' in nextFilters) {
      nextFilters.categories = [...formState.categories];
    }

    if ('status' in nextFilters) {
      nextFilters.status = [...formState.status];
    }

    if ('report_status' in nextFilters) {
      nextFilters.report_status = [...formState.report_status];
    }

    onApply(nextFilters);
  };

  const renderChannelState = () => {
    if (channelOptionsState === 'loading') {
      return <p className="dashboard-filter-field__note">{t('keywordGraph.channels.loading')}</p>;
    }

    if (channelOptionsState === 'error') {
      return <p className="dashboard-filter-field__note">{t('keywordGraph.channels.error')}</p>;
    }

    if ('channel_ids' in options && options.channel_ids.length === 0) {
      return (
        <p className="dashboard-filter-field__note">
          {t('keywordGraph.channels.empty', { defaultValue: 'No channels are available for filtering.' })}
        </p>
      );
    }

    return null;
  };

  const translateStatusOption = (option: { value: string; label: string }) =>
    t(`statusLabels.${option.value}`, { defaultValue: option.label });

  return (
    <section className="dashboard-filter-bar" aria-label={t('dashboard.filters.ariaLabel', { defaultValue: 'Dashboard filters' })}>
      <div className="dashboard-filter-bar__header">
        <div>
          <span className="state-card__eyebrow">{t('states.filters')}</span>
          <strong>{t('dashboard.filters.title', { defaultValue: 'URL-driven filter state' })}</strong>
        </div>
        <code>{previewQuery || t('common.defaultDashboardFilters')}</code>
      </div>

      <div className="dashboard-filter-grid dashboard-filter-grid--foundation">
        <label>
          <span>{t('fields.dateFrom')}</span>
          <input type="date" value={formState.date_from} onChange={(event) => updateField('date_from', event.target.value)} />
        </label>
        <label>
          <span>{t('fields.dateTo')}</span>
          <input type="date" value={formState.date_to} onChange={(event) => updateField('date_to', event.target.value)} />
        </label>
        <label>
          <span>{t('fields.limit')}</span>
          <select value={formState.limit} onChange={(event) => updateField('limit', event.target.value)}>
            {[25, 50, 100, 250].map((limit) => (
              <option key={limit} value={String(limit)}>
                {limit}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t('fields.minComments')}</span>
          <input
            type="number"
            min="0"
            value={formState.min_comments}
            onChange={(event) => updateField('min_comments', event.target.value)}
          />
        </label>
        <label>
          <span>{t('fields.sortBy')}</span>
          <select value={formState.sort_by} onChange={(event) => updateField('sort_by', event.target.value)}>
            {config.sortOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{t('fields.sortOrder')}</span>
          <select value={formState.sort_order} onChange={(event) => updateField('sort_order', event.target.value)}>
            <option value="desc">{t('common.desc')}</option>
            <option value="asc">{t('common.asc')}</option>
          </select>
        </label>
      </div>

      {'channel_ids' in options ? (
        <FilterField label={t('fields.channels', { defaultValue: t('fields.channelIds') })}>
          {renderChannelState() ?? (
            <FilterChipGroup
              legend={t('fields.channels', { defaultValue: t('fields.channelIds') })}
              options={options.channel_ids}
              selectedValues={formState.channel_ids}
              onToggle={(value) => toggleListField('channel_ids', value)}
            />
          )}
        </FilterField>
      ) : null}

      {'categories' in options && options.categories.length > 0 ? (
        <FilterField label={t('fields.categories')}>
          <FilterChipGroup
            legend={t('fields.categories')}
            options={options.categories}
            selectedValues={formState.categories}
            onToggle={(value) => toggleListField('categories', value)}
          />
        </FilterField>
      ) : null}

      {'status' in options && options.status.length > 0 ? (
        <FilterField label={t('fields.status')}>
          <FilterChipGroup
            legend={t('fields.status')}
            options={options.status}
            selectedValues={formState.status}
            onToggle={(value) => toggleListField('status', value)}
            getLabel={translateStatusOption}
          />
        </FilterField>
      ) : null}

      {'report_status' in options && options.report_status.length > 0 ? (
        <FilterField label={t('fields.reportStatus')}>
          <FilterChipGroup
            legend={t('fields.reportStatus')}
            options={options.report_status}
            selectedValues={formState.report_status}
            onToggle={(value) => toggleListField('report_status', value)}
            getLabel={translateStatusOption}
          />
        </FilterField>
      ) : null}

      <div className="dashboard-filter-bar__actions">
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onReset}>
          {t('actions.resetFilters')}
        </button>
        <button type="button" className="dashboard-button" onClick={handleApply}>
          {t('actions.applyFilters')}
        </button>
      </div>
    </section>
  );
}

