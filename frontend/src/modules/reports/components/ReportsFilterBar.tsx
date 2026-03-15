import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';
import { serializeReportsFilters } from '@modules/reports/filters';

type ReportsFilterBarProps<TType extends ReportType> = {
  type: TType;
  filters: ReportsFiltersByType[TType];
  onApply: (filters: ReportsFiltersByType[TType]) => void;
  onReset: () => void;
};

function formatArrayInput(value: readonly string[] | readonly number[]) {
  return value.join(', ');
}

export function ReportsFilterBar<TType extends ReportType>({ type, filters, onApply, onReset }: ReportsFilterBarProps<TType>) {
  const { t } = useTranslation();
  const buildFormState = () => ({
    date_from: String(filters.date_from ?? ''),
    date_to: String(filters.date_to ?? ''),
    limit: String(filters.limit ?? ''),
    offset: String(filters.offset ?? ''),
    min_comments: 'min_comments' in filters ? (filters.min_comments === null ? '' : String(filters.min_comments)) : '',
    channel_ids: 'channel_ids' in filters ? formatArrayInput(filters.channel_ids) : '',
    categories: 'categories' in filters ? formatArrayInput(filters.categories) : '',
    event_id: 'event_id' in filters ? (filters.event_id === null ? '' : String(filters.event_id)) : '',
    process_id: 'process_id' in filters ? (filters.process_id === null ? '' : String(filters.process_id)) : '',
  });

  const [formState, setFormState] = useState(buildFormState);
  const previewQuery = useMemo(() => serializeReportsFilters(type, filters), [filters, type]);

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
    const common = {
      ...filters,
      date_from: formState.date_from,
      date_to: formState.date_to,
      limit: Number(formState.limit) || filters.limit,
      offset: Number(formState.offset) || 0,
    };

    if (type === 'posts') {
      onApply({
        ...common,
        channel_ids: formState.channel_ids
          .split(',')
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isFinite(value)),
        categories: formState.categories
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        min_comments: formState.min_comments ? Number(formState.min_comments) : null,
      } as ReportsFiltersByType[TType]);
      return;
    }

    if (type === 'events') {
      onApply({
        ...common,
        event_id: formState.event_id ? Number(formState.event_id) : null,
      } as ReportsFiltersByType[TType]);
      return;
    }

    onApply({
      ...common,
      process_id: formState.process_id ? Number(formState.process_id) : null,
    } as ReportsFiltersByType[TType]);
  };

  return (
    <section className="dashboard-filter-bar" aria-label={t('reports.filters.ariaLabel', { defaultValue: 'Фильтры отчетов' })}>
      <div className="dashboard-filter-bar__header">
        <div>
          <span className="state-card__eyebrow">{t('states.filters')}</span>
          <strong>{t('reports.filters.title', { defaultValue: 'Фильтры отчетов в URL' })}</strong>
        </div>
        <code>{previewQuery || t('reports.filters.defaultQuery', { defaultValue: 'фильтры отчетов по умолчанию' })}</code>
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
          <span>{t('reports.fields.offset', { defaultValue: 'Смещение' })}</span>
          <input type="number" min="0" value={formState.offset} onChange={(event) => updateField('offset', event.target.value)} />
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
        {'min_comments' in filters ? (
          <label>
            <span>{t('fields.minComments')}</span>
            <input type="number" min="0" value={formState.min_comments} onChange={(event) => updateField('min_comments', event.target.value)} />
          </label>
        ) : null}
        {'event_id' in filters ? (
          <label>
            <span>{t('reports.fields.eventId', { defaultValue: 'ID события' })}</span>
            <input type="number" min="1" value={formState.event_id} onChange={(event) => updateField('event_id', event.target.value)} />
          </label>
        ) : null}
        {'process_id' in filters ? (
          <label>
            <span>{t('reports.fields.processId', { defaultValue: 'ID процесса' })}</span>
            <input type="number" min="1" value={formState.process_id} onChange={(event) => updateField('process_id', event.target.value)} />
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
