import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import {
  getDashboardFilterConfig,
  serializeDashboardFilters,
  type DashboardFiltersByMode,
} from '@shared/dashboard/filters';

type DashboardFilterBarProps<TMode extends DashboardMode> = {
  mode: TMode;
  filters: DashboardFiltersByMode[TMode];
  onApply: (filters: DashboardFiltersByMode[TMode]) => void;
  onReset: () => void;
};

function formatArrayInput(value: readonly string[] | readonly number[]) {
  return value.join(', ');
}

export function DashboardFilterBar<TMode extends DashboardMode>({
  mode,
  filters,
  onApply,
  onReset,
}: DashboardFilterBarProps<TMode>) {
  const { t } = useTranslation();
  const config = getDashboardFilterConfig(mode);
  const buildFormState = () => ({
    date_from: String(filters.date_from ?? ''),
    date_to: String(filters.date_to ?? ''),
    limit: String(filters.limit ?? ''),
    min_comments: filters.min_comments === null ? '' : String(filters.min_comments),
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
    channel_ids: 'channel_ids' in filters ? formatArrayInput(filters.channel_ids) : '',
    categories: 'categories' in filters ? formatArrayInput(filters.categories) : '',
    status: 'status' in filters ? formatArrayInput(filters.status) : '',
    report_status: 'report_status' in filters ? formatArrayInput(filters.report_status) : '',
  });
  const [formState, setFormState] = useState(buildFormState);

  const previewQuery = useMemo(() => serializeDashboardFilters(mode, filters), [filters, mode]);

  useEffect(() => {
    setFormState(buildFormState());
  }, [filters]);

  const updateField = (name: string, value: string) => {
    setFormState((current) => ({
      ...current,
      [name]: value,
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
      nextFilters.channel_ids = formState.channel_ids
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
    }

    if ('categories' in nextFilters) {
      nextFilters.categories = formState.categories
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
    }

    if ('status' in nextFilters) {
      nextFilters.status = formState.status
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
    }

    if ('report_status' in nextFilters) {
      nextFilters.report_status = formState.report_status
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
    }

    onApply(nextFilters);
  };

  return (
    <section className="dashboard-filter-bar" aria-label={t('dashboard.filters.ariaLabel', { defaultValue: 'Dashboard filters' })}>
      <div className="dashboard-filter-bar__header">
        <div>
          <span className="state-card__eyebrow">{t('states.filters')}</span>
          <strong>{t('dashboard.filters.title', { defaultValue: 'URL-driven filter state' })}</strong>
        </div>
        <code>{previewQuery || t('common.defaultDashboardFilters')}</code>
      </div>

      <div className="dashboard-filter-grid">
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
          <input type="number" min="1" value={formState.limit} onChange={(event) => updateField('limit', event.target.value)} />
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
        {'channel_ids' in filters ? (
          <label>
            <span>{t('fields.channelIds')}</span>
            <input value={formState.channel_ids} onChange={(event) => updateField('channel_ids', event.target.value)} />
          </label>
        ) : null}
        {'categories' in filters ? (
          <label>
            <span>{t('fields.categories')}</span>
            <input value={formState.categories} onChange={(event) => updateField('categories', event.target.value)} />
          </label>
        ) : null}
        {'status' in filters ? (
          <label>
            <span>{t('fields.status')}</span>
            <input value={formState.status} onChange={(event) => updateField('status', event.target.value)} />
          </label>
        ) : null}
        {'report_status' in filters ? (
          <label>
            <span>{t('fields.reportStatus')}</span>
            <input value={formState.report_status} onChange={(event) => updateField('report_status', event.target.value)} />
          </label>
        ) : null}
      </div>

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
