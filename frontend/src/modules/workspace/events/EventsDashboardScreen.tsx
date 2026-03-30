import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
import { getDashboardEmptyFeedback, getDashboardErrorFilterFeedback } from '@shared/dashboard/filter-feedback';
import { getEventsDashboardFilterOptions } from '@shared/dashboard/filter-options';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import {
  getDashboardSearchAvailabilityFeedback,
  getDashboardSearchDisabledReason,
  isDashboardSearchAllowedForRole,
} from '@shared/dashboard/search-availability';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { QueryActivityNotice, ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { useSession } from '@app/providers/SessionProvider';
import { useChannelsQuery } from '@modules/admin/hooks';
import { EventDetailPanel } from '@modules/workspace/events/components/EventDetailPanel';
import { EventGraphPanel } from '@modules/workspace/events/components/EventGraphPanel';
import {
  useEventGraphQuery,
  useEventsDashboardQuery,
  useEventsKeywordSearchQuery,
  useSelectedEventId,
  useUpdateEventReportAction,
} from '@modules/workspace/events/hooks';
import {
  eventsDashboardColumns,
  mapEventGraphToViewModel,
  mapEventsDashboardToViewModel,
  mapEventsRowsToTableRows,
} from '@modules/workspace/events/mappers';

export function EventsDashboardScreen() {
  const { t } = useTranslation();
  const { filters, applyFilters, resetFilters, applySearch, resetSearch } = useDashboardFilters('events');
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const isSearchAllowed = isDashboardSearchAllowedForRole(primaryRole);
  const searchDisabledReason = getDashboardSearchDisabledReason(primaryRole, t);
  const dashboardQuery = useEventsDashboardQuery(filters);
  const keywordSearchQuery = useEventsKeywordSearchQuery(filters, { enabled: isSearchAllowed });
  const channelsQuery = useChannelsQuery();
  const dashboardData = dashboardQuery.data ?? null;
  const filterOptions = getEventsDashboardFilterOptions({
    filters,
    dashboardData,
    channels: channelsQuery.data,
  });
  const normalizedSearchQuery = filters.query.trim();
  const channelOptionsState = channelsQuery.isLoading ? 'loading' : channelsQuery.isError ? 'error' : 'ready';
  const viewModel = dashboardData ? mapEventsDashboardToViewModel(dashboardData) : null;
  const isKeywordSearchActive = normalizedSearchQuery.length >= 2;
  const matchedPostIds = useMemo(() => {
    if (!keywordSearchQuery.data || normalizedSearchQuery.length < 2) {
      return null;
    }

    if (keywordSearchQuery.data.query.trim() !== normalizedSearchQuery) {
      return null;
    }

    return new Set(keywordSearchQuery.data.items.map((item) => item.post_id));
  }, [keywordSearchQuery.data, normalizedSearchQuery]);
  const filteredDashboardItems = useMemo(() => {
    if (!dashboardData) {
      return [];
    }

    if (!matchedPostIds) {
      return dashboardData.items;
    }

    return dashboardData.items.filter((item) => item.post_ids.some((postId) => matchedPostIds.has(postId)));
  }, [dashboardData, matchedPostIds]);
  const filteredRows = useMemo(() => {
    if (!viewModel) {
      return [];
    }

    if (!matchedPostIds) {
      return viewModel.rows;
    }

    return viewModel.rows.filter((row) => row.postIds.some((postId) => matchedPostIds.has(postId)));
  }, [viewModel, matchedPostIds]);
  const hasKeywordFilteredRows = isKeywordSearchActive && matchedPostIds !== null;
  const visibleRows = hasKeywordFilteredRows ? filteredRows : viewModel?.rows ?? [];
  const visibleDashboardItems = hasKeywordFilteredRows ? filteredDashboardItems : dashboardData?.items ?? [];
  const { selectedEventId, selectEvent } = useSelectedEventId(visibleDashboardItems);
  const selectedEvent = visibleRows.find((row) => row.eventId === selectedEventId) ?? null;
  const graphQuery = useEventGraphQuery(selectedEventId);
  const hasGraphData = graphQuery.data !== undefined;
  const graphViewModel = graphQuery.data ? mapEventGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const keywordSearchAvailabilityFeedback = getDashboardSearchAvailabilityFeedback(keywordSearchQuery.error, t);
  const reportAction = useUpdateEventReportAction(selectedEventId);
  const tableRows = useMemo(
    () => mapEventsRowsToTableRows(visibleRows, selectedEventId, selectEvent, primaryRole),
    [visibleRows, selectedEventId, selectEvent, primaryRole],
  );

  if (dashboardQuery.isLoading && !dashboardData) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <section className="dashboard-page__hero dashboard-page__hero--analytics">
          <div>
            <h2>{t('events.dashboard.heroTitle')}</h2>
            <p>{t('events.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="events"
          filters={filters}
          options={filterOptions}
          channelOptionsState={channelOptionsState}
          onApply={applyFilters}
          onReset={resetFilters}
          onApplySearch={applySearch}
          onResetSearch={resetSearch}
          searchDisabled={!isSearchAllowed}
          searchDisabledReason={searchDisabledReason}
          searchFeedback={keywordSearchAvailabilityFeedback}
        />
        <LoadingState title={t('events.dashboard.loadingTitle')} description={t('events.dashboard.loadingDescription')} />
      </div>
    );
  }

  if (dashboardQuery.isError && !dashboardData) {
    const error = dashboardQuery.error;
    const isForbidden = error instanceof ApiError && error.status === 403;

    return (
      <div className="dashboard-page dashboard-page--analytics">
        <section className="dashboard-page__hero dashboard-page__hero--analytics">
          <div>
            <h2>{t('events.dashboard.heroTitle')}</h2>
            <p>{t('events.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="events"
          filters={filters}
          options={filterOptions}
          channelOptionsState={channelOptionsState}
          feedback={getDashboardErrorFilterFeedback(t)}
          onApply={applyFilters}
          onReset={resetFilters}
          onApplySearch={applySearch}
          onResetSearch={resetSearch}
          searchDisabled={!isSearchAllowed}
          searchDisabledReason={searchDisabledReason}
          searchFeedback={keywordSearchAvailabilityFeedback}
        />
        {isForbidden ? (
          <ForbiddenState title={t('events.dashboard.forbiddenTitle')} description={t('events.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('events.dashboard.errorTitle')} description={t('events.dashboard.errorDescription')} />
        )}
      </div>
    );
  }

  if (!dashboardData) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <section className="dashboard-page__hero dashboard-page__hero--analytics">
          <div>
            <h2>{t('events.dashboard.heroTitle')}</h2>
            <p>{t('events.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="events"
          filters={filters}
          options={filterOptions}
          channelOptionsState={channelOptionsState}
          feedback={getDashboardErrorFilterFeedback(t)}
          onApply={applyFilters}
          onReset={resetFilters}
          onApplySearch={applySearch}
          onResetSearch={resetSearch}
          searchDisabled={!isSearchAllowed}
          searchDisabledReason={searchDisabledReason}
          searchFeedback={keywordSearchAvailabilityFeedback}
        />
        <ErrorState title={t('events.dashboard.noDataTitle')} description={t('events.dashboard.noDataDescription')} />
      </div>
    );
  }

  if (!viewModel) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <ErrorState title={t('events.dashboard.mappingTitle')} description={t('events.dashboard.mappingDescription')} />
      </div>
    );
  }

  const eventsViewModel = viewModel;
  const graphPartialHint = selectedEvent && (!selectedEvent.graphReady || eventsViewModel.isPartial) ? t('events.dashboard.partialHint') : null;
  const emptyUiState = getDashboardEmptyFeedback('events', filters, t);
  const keywordMappedEmptyState = {
    filterBar: {
      tone: 'warning' as const,
      title: t('events.dashboard.keywordSearch.emptyFeedbackTitle', {
        defaultValue: 'По этому запросу событий в текущей выборке нет',
      }),
      description: t('events.dashboard.keywordSearch.emptyFeedbackDescription', {
        defaultValue: 'Поиск нашел связанные материалы, но среди текущих событий совпадений нет. Уточните запрос или расширьте фильтры.',
      }),
    },
    stateCard: {
      title: t('events.dashboard.keywordSearch.emptyStateTitle', {
        defaultValue: 'По этому запросу событий в текущей выборке нет',
      }),
      description: t('events.dashboard.keywordSearch.emptyStateDescription', {
        defaultValue: 'Совпадения по запросу есть, но среди текущих событий они не отобразились. Попробуйте другой запрос или более широкий диапазон фильтров.',
      }),
    },
  };
  const emptyFeedback = hasKeywordFilteredRows && eventsViewModel.rows.length > 0 ? keywordMappedEmptyState : emptyUiState;

  return (
    <div className="dashboard-page dashboard-page--analytics">
      <DashboardSystemAlerts warnings={eventsViewModel.warnings} partial={eventsViewModel.isPartial} />

      <section className="dashboard-page__hero dashboard-page__hero--analytics">
        <div>
          <h2>{t('events.dashboard.heroTitle')}</h2>
          <p>{t('events.dashboard.heroDescription')}</p>
        </div>
      </section>

      <DashboardSummaryCards cards={eventsViewModel.summaryCards} />

      <DashboardFilterBar
        mode="events"
        filters={filters}
        options={filterOptions}
        channelOptionsState={channelOptionsState}
        feedback={visibleRows.length === 0 ? emptyFeedback.filterBar : null}
        headerSlot={<DashboardGeneratedAt generatedAt={viewModel.generatedAt} />}
        onApply={applyFilters}
        onReset={resetFilters}
        onApplySearch={applySearch}
        onResetSearch={resetSearch}
        searchDisabled={!isSearchAllowed}
        searchDisabledReason={searchDisabledReason}
        searchFeedback={keywordSearchAvailabilityFeedback}
      />

      {dashboardQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('events.dashboard.refreshingTitle', { defaultValue: 'Дашборд обновляется' })}
          description={t('events.dashboard.refreshingDescription', { defaultValue: 'Текущий снимок остается на экране, пока загружаются обновленные данные.' })}
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('events.dashboard.keywordSearch.loadingTitle', { defaultValue: 'Ищем события по найденным материалам' })}
          description={t('events.dashboard.keywordSearch.loadingDescription', { defaultValue: 'Текущая таблица и выбранный контекст остаются на экране, пока обновляются результаты поиска.' })}
        />
      ) : null}

      {dashboardQuery.isError ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('events.dashboard.refreshErrorTitle', { defaultValue: 'Не удалось обновить данные' })}
          description={t('events.dashboard.refreshErrorDescription', { defaultValue: 'Показываем последнюю доступную версию экрана, чтобы вы могли продолжить анализ.' })}
          tone="danger"
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isError && !keywordSearchAvailabilityFeedback ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('events.dashboard.keywordSearch.errorTitle', { defaultValue: 'Не удалось применить поиск к событиям' })}
          description={t('events.dashboard.keywordSearch.errorDescription', { defaultValue: 'Показываем текущую выборку и выбранное событие без изменений. Повторите попытку или скорректируйте запрос.' })}
          tone="danger"
        />
      ) : null}

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('events.dashboard.readOnlyTitle')} description={t('events.dashboard.readOnlyDescription')} />
      ) : null}

      {visibleRows.length === 0 ? (
        <EmptyState title={emptyFeedback.stateCard.title} description={emptyFeedback.stateCard.description} />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--workspace">
          <div className="dashboard-page__primary">
            <AnalyticsTable
              title={t('events.dashboard.tableTitle')}
              description={t('events.dashboard.tableDescription')}
              columns={eventsDashboardColumns}
              rows={tableRows}
            />
          </div>

          <div className="dashboard-page__secondary">
            <EventGraphPanel
              selectedTitle={selectedEvent?.title ?? null}
              isLoading={graphQuery.isLoading && !hasGraphData}
              isRefreshing={graphQuery.isFetching && hasGraphData}
              isError={graphQuery.isError && !hasGraphData}
              showErrorNotice={graphQuery.isError && hasGraphData}
              viewModel={graphViewModel}
              hasSelection={selectedEvent !== null}
              partialHint={graphPartialHint}
              onRefresh={() => {
                void graphQuery.refetch();
              }}
            />

            <EventDetailPanel
              event={selectedEvent}
              graph={graphViewModel}
              actionSlot={
                canMutate && selectedEvent ? (
                  <button
                    type="button"
                    className="dashboard-button"
                    disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                    onClick={() => reportAction.run(undefined)}
                  >
                    {selectedEvent.reportStatus === 'draft' ? t('actions.updateDraftReport') : t('actions.generateDraftReport')}
                  </button>
                ) : null
              }
            />

            {canMutate && selectedEvent && reportAction.jobStatus ? (
              <AsyncActionIndicator
                title={t('events.rows.reportJobTitle')}
                description={t('events.rows.reportJobDescription')}
                status={reportAction.jobStatus}
                jobId={reportAction.activeJob?.job_id ?? reportAction.terminalState?.jobId}
                resultSummary={reportAction.resultSummary}
                tone={reportAction.terminalState?.status === 'failed' ? 'danger' : reportAction.jobStatus === 'done' ? 'success' : 'default'}
              />
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}



