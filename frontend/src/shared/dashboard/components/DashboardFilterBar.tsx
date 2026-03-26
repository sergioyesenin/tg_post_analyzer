import { useEffect, useId, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { DashboardMode } from '@shared/dashboard/contracts';
import type { DashboardFilterFeedback } from '@shared/dashboard/filter-feedback';
import type { DashboardFilterOptionsByMode } from '@shared/dashboard/filter-options';
import {
  getDashboardFilterConfig,
  serializeDashboardFilters,
  type DashboardFiltersByMode,
} from '@shared/dashboard/filters';

type ChannelOptionsState = 'ready' | 'loading' | 'error';
type CompactSelectorKey = 'channel_ids' | 'status' | 'report_status';

type DashboardFilterBarProps<TMode extends DashboardMode> = {
  mode: TMode;
  filters: DashboardFiltersByMode[TMode];
  options: DashboardFilterOptionsByMode[TMode];
  onApply: (filters: DashboardFiltersByMode[TMode]) => void;
  onReset: () => void;
  onApplySearch: (query: string) => void;
  onResetSearch: () => void;
  channelOptionsState?: ChannelOptionsState;
  feedback?: DashboardFilterFeedback | null;
  headerSlot?: ReactNode;
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

type FilterValidationErrors = Partial<Record<'date_from' | 'date_to' | 'min_comments', string>>;

type FilterOption<TValue extends string | number> = {
  value: TValue;
  label: string;
  description?: string | null;
};

function buildFiltersFromFormState<TMode extends DashboardMode>(
  mode: TMode,
  currentFilters: DashboardFiltersByMode[TMode],
  formState: FilterFormState,
) {
  const nextFilters = {
    ...currentFilters,
    date_from: formState.date_from || (mode === 'posts' ? '' : null),
    date_to: formState.date_to || (mode === 'posts' ? '' : null),
    limit: Number(formState.limit) || currentFilters.limit,
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

  return nextFilters;
}

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

function FilterField({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="dashboard-filter-field">
      {label ? <span className="dashboard-filter-field__label">{label}</span> : null}
      {children}
    </div>
  );
}

function getOptionLabel<TValue extends string | number>(
  option: FilterOption<TValue>,
  getLabel?: (option: { value: TValue; label: string }) => string,
) {
  return getLabel ? getLabel(option) : option.label;
}

function FilterChipButtons<TValue extends string | number>({
  legend,
  options,
  selectedValues,
  onToggle,
  getLabel,
}: {
  legend: string;
  options: Array<FilterOption<TValue>>;
  selectedValues: TValue[];
  onToggle: (value: TValue) => void;
  getLabel?: (option: { value: TValue; label: string }) => string;
}) {
  return (
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
            <span>{getOptionLabel(option, getLabel)}</span>
            {option.description ? <small>{option.description}</small> : null}
          </button>
        );
      })}
    </div>
  );
}

function FilterChipSection<TValue extends string | number>(props: {
  legend: string;
  options: Array<FilterOption<TValue>>;
  selectedValues: TValue[];
  onToggle: (value: TValue) => void;
  getLabel?: (option: { value: TValue; label: string }) => string;
}) {
  const { legend, ...rest } = props;

  return (
    <fieldset className="dashboard-chip-fieldset">
      <legend className="dashboard-chip-fieldset__legend">{legend}</legend>
      <FilterChipButtons legend={legend} {...rest} />
    </fieldset>
  );
}

function FilterSelector({
  label,
  selectorId,
  summary,
  isOpen,
  disabled = false,
  note,
  clearDisabled = true,
  onToggle,
  onClear,
  children,
}: {
  label: string;
  selectorId: string;
  summary: string;
  isOpen: boolean;
  disabled?: boolean;
  note?: string | null;
  clearDisabled?: boolean;
  onToggle: () => void;
  onClear: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();

  return (
    <FilterField label={label}>
      <div className={`dashboard-filter-selector ${isOpen ? 'dashboard-filter-selector--open' : ''}`.trim()}>
        <button
          type="button"
          className="dashboard-filter-selector__trigger"
          aria-expanded={isOpen}
          aria-controls={selectorId}
          aria-label={`${label}: ${summary}`}
          disabled={disabled}
          onClick={onToggle}
        >
          <span className="dashboard-filter-selector__summary">{summary}</span>
          <span className="dashboard-filter-selector__icon" aria-hidden="true">
            v
          </span>
        </button>

        {isOpen ? (
          <div id={selectorId} className="dashboard-filter-selector__panel" role="region" aria-label={label}>
            <div className="dashboard-filter-selector__panel-header">
              <strong>{label}</strong>
              <button
                type="button"
                className="dashboard-filter-selector__clear"
                disabled={clearDisabled}
                onClick={onClear}
              >
                {t('dashboard.filters.selector.clear', { defaultValue: 'Clear' })}
              </button>
            </div>
            {children}
          </div>
        ) : null}
      </div>
      {note ? <p className="dashboard-filter-field__note">{note}</p> : null}
    </FilterField>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) {
    return null;
  }

  return <small className="dashboard-filter-field__error">{message}</small>;
}

function validateFormState(formState: FilterFormState, t: ReturnType<typeof useTranslation>['t']): FilterValidationErrors {
  const errors: FilterValidationErrors = {};
  const dateRangeMessage = t('dashboard.filters.validation.dateRange', {
    defaultValue: 'Date from must be earlier than or equal to date to.',
  });

  if (formState.date_from && formState.date_to && formState.date_from > formState.date_to) {
    errors.date_from = dateRangeMessage;
    errors.date_to = dateRangeMessage;
  }

  if (formState.min_comments) {
    const isInteger = /^\d+$/.test(formState.min_comments.trim());
    if (!isInteger) {
      errors.min_comments = t('dashboard.filters.validation.minComments', {
        defaultValue: 'Min comments must be a whole number greater than or equal to 0.',
      });
    }
  }

  return errors;
}

function buildSelectionSummary<TValue extends string | number>(params: {
  selectedValues: TValue[];
  options: Array<FilterOption<TValue>>;
  getLabel?: (option: { value: TValue; label: string }) => string;
  allText: string;
}) {
  const { selectedValues, options, getLabel, allText } = params;

  if (selectedValues.length === 0) {
    return allText;
  }

  const optionByValue = new Map(options.map((option) => [option.value, getOptionLabel(option, getLabel)]));
  const labels = selectedValues.map((value) => optionByValue.get(value) ?? String(value));

  if (labels.length === 1) {
    return labels[0];
  }

  return `${labels[0]} +${labels.length - 1}`;
}

export function DashboardFilterBar<TMode extends DashboardMode>({
  mode,
  filters,
  options,
  onApply,
  onReset,
  onApplySearch,
  onResetSearch,
  channelOptionsState = 'ready',
  feedback = null,
  headerSlot = null,
}: DashboardFilterBarProps<TMode>) {
  const { t } = useTranslation();
  const config = getDashboardFilterConfig(mode);
  const selectorIdBase = useId();
  const [formState, setFormState] = useState(() => buildFormState(filters));
  const [searchDraft, setSearchDraft] = useState(() => filters.query);
  const [openSelector, setOpenSelector] = useState<CompactSelectorKey | null>(null);

  const validationErrors = useMemo(() => validateFormState(formState, t), [formState, t]);
  const hasValidationErrors = Object.keys(validationErrors).length > 0;
  const appliedQuery = useMemo(() => serializeDashboardFilters(mode, filters), [filters, mode]);
  const pendingFilters = useMemo(() => buildFiltersFromFormState(mode, filters, formState), [filters, formState, mode]);
  const previewQuery = useMemo(() => serializeDashboardFilters(mode, pendingFilters), [mode, pendingFilters]);
  const isDirty = useMemo(() => appliedQuery !== previewQuery, [appliedQuery, previewQuery]);
  const actionHint = isDirty ? t('dashboard.filters.pendingChanges') : t('dashboard.filters.resetHint');
  const isApplyDisabled = hasValidationErrors || !isDirty;
  const isResetDisabled = !isDirty;
  const allSelectedText = t('dashboard.filters.summary.all', { defaultValue: 'All' });
  const normalizedSearchDraft = searchDraft.trim();
  const appliedSearchQuery = filters.query.trim();
  const isSearchSubmitDisabled = normalizedSearchDraft.length < 2;
  const isSearchResetDisabled = normalizedSearchDraft.length === 0 && appliedSearchQuery.length === 0;

  useEffect(() => {
    setFormState(buildFormState(filters));
    setSearchDraft(filters.query);
    setOpenSelector(null);
  }, [appliedQuery, filters.query]);

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

  const clearListField = <TKey extends 'channel_ids' | 'categories' | 'status' | 'report_status'>(field: TKey) => {
    setFormState((current) => ({
      ...current,
      [field]: [],
    }));
  };

  const handleApply = () => {
    if (isApplyDisabled) {
      return;
    }

    setOpenSelector(null);
    onApply(pendingFilters);
  };

  const handleReset = () => {
    if (isResetDisabled) {
      return;
    }

    setOpenSelector(null);
    setFormState(buildFormState(getDashboardFilterConfig(mode).defaults));
    onReset();
  };

  const handleSearchSubmit = () => {
    if (isSearchSubmitDisabled) {
      return;
    }

    onApplySearch(normalizedSearchDraft);
  };

  const handleSearchReset = () => {
    if (isSearchResetDisabled) {
      return;
    }

    setSearchDraft('');

    if (appliedSearchQuery.length > 0) {
      onResetSearch();
    }
  };

  const translateStatusOption = (option: { value: string; label: string }) =>
    t(`statusLabels.${option.value}`, { defaultValue: option.label });

  const channelSelectorNote =
    channelOptionsState === 'loading'
      ? t('keywordGraph.channels.loading')
      : channelOptionsState === 'error'
        ? t('keywordGraph.channels.error')
        : 'channel_ids' in options && options.channel_ids.length === 0
          ? t('keywordGraph.channels.empty', { defaultValue: 'No channels are available for filtering.' })
          : null;
  const isChannelSelectorDisabled = Boolean(channelSelectorNote);

  const channelSummary =
    channelSelectorNote ??
    ('channel_ids' in options
      ? buildSelectionSummary({
          selectedValues: formState.channel_ids,
          options: options.channel_ids,
          allText: allSelectedText,
        })
      : allSelectedText);

  const statusSummary =
    'status' in options
      ? buildSelectionSummary({
          selectedValues: formState.status,
          options: options.status,
          getLabel: translateStatusOption,
          allText: allSelectedText,
        })
      : allSelectedText;

  const reportStatusSummary =
    'report_status' in options
      ? buildSelectionSummary({
          selectedValues: formState.report_status,
          options: options.report_status,
          getLabel: translateStatusOption,
          allText: allSelectedText,
        })
      : allSelectedText;

  return (
    <section className="dashboard-filter-bar" aria-label={t('dashboard.filters.ariaLabel', { defaultValue: 'Dashboard filters' })}>
      <div className="dashboard-filter-bar__header">
        <div className="dashboard-filter-bar__title">
          <span className="state-card__eyebrow">{t('states.filters')}</span>
          <strong>{t('dashboard.filters.title', { defaultValue: 'URL-driven filter state' })}</strong>
        </div>
        {headerSlot ? <div className="dashboard-filter-bar__header-slot">{headerSlot}</div> : null}
      </div>

      <section className="dashboard-search-block" aria-label={t('dashboard.search.ariaLabel', { defaultValue: 'Keyword search' })}>
        <div className="dashboard-search-block__header">
          <div className="dashboard-search-block__title">
            <span className="state-card__eyebrow">{t('states.search')}</span>
            <strong>{t('dashboard.search.title', { defaultValue: 'Keyword search' })}</strong>
          </div>
          <p>{t('dashboard.search.description', { defaultValue: 'The query is stored in the URL and applies only after explicit submit.' })}</p>
        </div>

        <div className="dashboard-search-block__form">
          <label className="dashboard-search-block__field" htmlFor={`${selectorIdBase}-query`}>
            <span>{t('fields.query')}</span>
            <input
              id={`${selectorIdBase}-query`}
              type="search"
              value={searchDraft}
              placeholder={t('dashboard.search.placeholder', { defaultValue: 'Enter a topic or keyword phrase' })}
              onChange={(event) => setSearchDraft(event.target.value)}
            />
          </label>

          <div className="dashboard-search-block__actions">
            <button
              type="button"
              className="dashboard-button dashboard-button--ghost"
              onClick={handleSearchReset}
              disabled={isSearchResetDisabled}
            >
              {t('actions.resetSearch', { defaultValue: '—бросить поиск' })}
            </button>
            <button type="button" className="dashboard-button" onClick={handleSearchSubmit} disabled={isSearchSubmitDisabled}>
              {t('dashboard.search.submit', { defaultValue: '\u041d\u0430\u0439\u0442\u0438' })}
            </button>
          </div>
        </div>
      </section>

      <div className="dashboard-filter-grid dashboard-filter-grid--foundation">
        <label className={validationErrors.date_from ? 'dashboard-filter-grid__field--invalid' : ''}>
          <span>{t('fields.dateFrom')}</span>
          <input
            type="date"
            value={formState.date_from}
            aria-invalid={Boolean(validationErrors.date_from)}
            className={validationErrors.date_from ? 'dashboard-filter-input--invalid' : ''}
            onChange={(event) => updateField('date_from', event.target.value)}
          />
          <FieldError message={validationErrors.date_from} />
        </label>
        <label className={validationErrors.date_to ? 'dashboard-filter-grid__field--invalid' : ''}>
          <span>{t('fields.dateTo')}</span>
          <input
            type="date"
            value={formState.date_to}
            aria-invalid={Boolean(validationErrors.date_to)}
            className={validationErrors.date_to ? 'dashboard-filter-input--invalid' : ''}
            onChange={(event) => updateField('date_to', event.target.value)}
          />
          <FieldError message={validationErrors.date_to} />
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
        <label className={validationErrors.min_comments ? 'dashboard-filter-grid__field--invalid' : ''}>
          <span>{t('fields.minComments')}</span>
          <input
            type="number"
            min="0"
            step="1"
            value={formState.min_comments}
            aria-invalid={Boolean(validationErrors.min_comments)}
            className={validationErrors.min_comments ? 'dashboard-filter-input--invalid' : ''}
            onChange={(event) => updateField('min_comments', event.target.value)}
          />
          <FieldError message={validationErrors.min_comments} />
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

        {'channel_ids' in options ? (
          <FilterSelector
            label={t('fields.channels', { defaultValue: t('fields.channelIds') })}
            selectorId={`${selectorIdBase}-channels`}
            summary={channelSummary}
            isOpen={openSelector === 'channel_ids'}
            disabled={isChannelSelectorDisabled}
            note={channelSelectorNote}
            clearDisabled={formState.channel_ids.length === 0}
            onToggle={() => setOpenSelector((current) => (current === 'channel_ids' ? null : 'channel_ids'))}
            onClear={() => clearListField('channel_ids')}
          >
            {'channel_ids' in options ? (
              <FilterChipButtons
                legend={t('fields.channels', { defaultValue: t('fields.channelIds') })}
                options={options.channel_ids}
                selectedValues={formState.channel_ids}
                onToggle={(value) => toggleListField('channel_ids', value)}
              />
            ) : null}
          </FilterSelector>
        ) : null}

        {'status' in options && options.status.length > 0 ? (
          <FilterSelector
            label={t('fields.status')}
            selectorId={`${selectorIdBase}-status`}
            summary={statusSummary}
            isOpen={openSelector === 'status'}
            clearDisabled={formState.status.length === 0}
            onToggle={() => setOpenSelector((current) => (current === 'status' ? null : 'status'))}
            onClear={() => clearListField('status')}
          >
            <FilterChipButtons
              legend={t('fields.status')}
              options={options.status}
              selectedValues={formState.status}
              onToggle={(value) => toggleListField('status', value)}
              getLabel={translateStatusOption}
            />
          </FilterSelector>
        ) : null}

        {'report_status' in options && options.report_status.length > 0 ? (
          <FilterSelector
            label={t('fields.reportStatus')}
            selectorId={`${selectorIdBase}-report-status`}
            summary={reportStatusSummary}
            isOpen={openSelector === 'report_status'}
            clearDisabled={formState.report_status.length === 0}
            onToggle={() => setOpenSelector((current) => (current === 'report_status' ? null : 'report_status'))}
            onClear={() => clearListField('report_status')}
          >
            <FilterChipButtons
              legend={t('fields.reportStatus')}
              options={options.report_status}
              selectedValues={formState.report_status}
              onToggle={(value) => toggleListField('report_status', value)}
              getLabel={translateStatusOption}
            />
          </FilterSelector>
        ) : null}
      </div>

      {'categories' in options && options.categories.length > 0 ? (
        <FilterField>
          <FilterChipSection
            legend={t('fields.categories')}
            options={options.categories}
            selectedValues={formState.categories}
            onToggle={(value) => toggleListField('categories', value)}
          />
        </FilterField>
      ) : null}

      {feedback ? (
        <div className={`dashboard-filter-feedback dashboard-filter-feedback--${feedback.tone}`.trim()} role="status" aria-live="polite">
          <strong>{feedback.title}</strong>
          <p>{feedback.description}</p>
        </div>
      ) : null}

      <div className="dashboard-filter-bar__actions">
        <p className="dashboard-filter-bar__action-note">{actionHint}</p>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={handleReset} disabled={isResetDisabled}>
          {t('actions.resetFilters')}
        </button>
        <button type="button" className="dashboard-button" onClick={handleApply} disabled={isApplyDisabled}>
          {t('actions.applyFilters')}
        </button>
      </div>
    </section>
  );
}





















