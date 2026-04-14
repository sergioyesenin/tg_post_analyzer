import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
import { getDashboardEmptyFeedback, getDashboardErrorFilterFeedback } from '@shared/dashboard/filter-feedback';
import { getProcessesDashboardFilterOptions } from '@shared/dashboard/filter-options';
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
import { ProcessDetailPanel } from '@modules/workspace/processes/components/ProcessDetailPanel';
import { ProcessGraphPanel } from '@modules/workspace/processes/components/ProcessGraphPanel';
import {
  useProcessGraphQuery,
  useProcessesDashboardQuery,
  useProcessesKeywordSearchQuery,
  useSelectedProcessId,
  useUpdateProcessReportAction,
} from '@modules/workspace/processes/hooks';
import {
  mapProcessGraphToViewModel,
  mapProcessesDashboardToViewModel,
  mapProcessesRowsToTableRows,
  processesDashboardColumns,
} from '@modules/workspace/processes/mappers';

export function ProcessesDashboardScreen() {
  const { t } = useTranslation();
  const { filters, applyFilters, resetFilters, applySearch, resetSearch } = useDashboardFilters('processes');
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const isSearchAllowed = isDashboardSearchAllowedForRole(primaryRole);
  const searchDisabledReason = getDashboardSearchDisabledReason(primaryRole, t);
  const dashboardQuery = useProcessesDashboardQuery(filters);
  const keywordSearchQuery = useProcessesKeywordSearchQuery(filters, { enabled: isSearchAllowed });
  const keywordSearchAvailabilityFeedback = getDashboardSearchAvailabilityFeedback(keywordSearchQuery.error, t);
  const dashboardData = dashboardQuery.data ?? null;
  const filterOptions = getProcessesDashboardFilterOptions({
    filters,
    dashboardData,
  });
  const viewModel = dashboardData ? mapProcessesDashboardToViewModel(dashboardData) : null;
  const isKeywordSearchActive = filters.query.trim().length >= 2;
  const matchedPostIds = useMemo(() => {
    if (!keywordSearchQuery.data) {
      return null;
    }

    return new Set(keywordSearchQuery.data.items.map((item) => item.post_id));
  }, [keywordSearchQuery.data]);
  const filteredDashboardItems = useMemo(() => {
    if (!dashboardData) {
      return [];
    }

    if (!matchedPostIds) {
      return dashboardData.items;
    }

    return dashboardData.items.filter((item) => (item.post_ids ?? []).some((postId) => matchedPostIds.has(postId)));
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
  const { selectedProcessId, selectProcess } = useSelectedProcessId(visibleDashboardItems);
  const selectedProcess = visibleRows.find((row) => row.processId === selectedProcessId) ?? null;
  const graphQuery = useProcessGraphQuery(selectedProcessId);
  const hasGraphData = graphQuery.data !== undefined;
  const graphViewModel = graphQuery.data ? mapProcessGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const reportAction = useUpdateProcessReportAction(selectedProcessId);
  const tableRows = useMemo(
    () => mapProcessesRowsToTableRows(visibleRows, selectedProcessId, selectProcess, primaryRole),
    [visibleRows, selectedProcessId, selectProcess, primaryRole],
  );

  if (dashboardQuery.isLoading && !dashboardData) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <section className="dashboard-page__hero dashboard-page__hero--analytics">
          <div>
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="processes"
          filters={filters}
          options={filterOptions}
          onApply={applyFilters}
          onReset={resetFilters}
          onApplySearch={applySearch}
          onResetSearch={resetSearch}
          searchDisabled={!isSearchAllowed}
          searchDisabledReason={searchDisabledReason}
          searchFeedback={keywordSearchAvailabilityFeedback}
        />
        <LoadingState title={t('processes.dashboard.loadingTitle')} description={t('processes.dashboard.loadingDescription')} />
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
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="processes"
          filters={filters}
          options={filterOptions}
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
          <ForbiddenState title={t('processes.dashboard.forbiddenTitle')} description={t('processes.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('processes.dashboard.errorTitle')} description={t('processes.dashboard.errorDescription')} />
        )}
      </div>
    );
  }

  if (!dashboardData) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <section className="dashboard-page__hero dashboard-page__hero--analytics">
          <div>
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar
          mode="processes"
          filters={filters}
          options={filterOptions}
          feedback={getDashboardErrorFilterFeedback(t)}
          onApply={applyFilters}
          onReset={resetFilters}
          onApplySearch={applySearch}
          onResetSearch={resetSearch}
          searchDisabled={!isSearchAllowed}
          searchDisabledReason={searchDisabledReason}
          searchFeedback={keywordSearchAvailabilityFeedback}
        />
        <ErrorState title={t('processes.dashboard.noDataTitle')} description={t('processes.dashboard.noDataDescription')} />
      </div>
    );
  }

  if (!viewModel) {
    return (
      <div className="dashboard-page dashboard-page--analytics">
        <ErrorState title={t('processes.dashboard.mappingTitle')} description={t('processes.dashboard.mappingDescription')} />
      </div>
    );
  }

  const processesViewModel = viewModel;
  const graphPartialHint =
    selectedProcess && (!selectedProcess.graphReady || processesViewModel.isPartial)
      ? t('processes.dashboard.partialHint')
      : null;
  const emptyUiState = getDashboardEmptyFeedback('processes', filters, t);
  const keywordSearchResultCount = keywordSearchQuery.data?.items.length ?? null;
  const isKeywordSearchEmpty = isKeywordSearchActive && keywordSearchQuery.isSuccess && keywordSearchResultCount === 0;
  const isKeywordMappedEmpty =
    isKeywordSearchActive && keywordSearchQuery.isSuccess && (keywordSearchResultCount ?? 0) > 0 && visibleRows.length === 0;
  const keywordSearchEmptyState = {
    stateCard: {
      title: t('processes.dashboard.keywordSearch.emptySearchTitle', {
        defaultValue: 'По этому запросу процессы не найдены',
      }),
      description: t('processes.dashboard.keywordSearch.emptySearchDescription', {
        defaultValue: 'Поиск не нашел материалов по этому запросу. Уточните формулировку или расширьте диапазон фильтров.',
      }),
    },
  };
  const keywordMappedEmptyState = {
    stateCard: {
      title: t('processes.dashboard.keywordSearch.emptyStateTitle', {
        defaultValue: 'По этому запросу процессов в текущей выборке нет',
      }),
      description: t('processes.dashboard.keywordSearch.emptyStateDescription', {
        defaultValue: 'Совпадения по запросу есть, но среди текущих процессов они не отобразились. Попробуйте другой запрос или более широкий диапазон фильтров.',
      }),
    },
  };
  const emptyFeedback = isKeywordSearchEmpty
    ? keywordSearchEmptyState
    : isKeywordMappedEmpty
      ? keywordMappedEmptyState
      : emptyUiState;
  const filterFeedback = visibleRows.length === 0 && !isKeywordSearchActive ? emptyUiState.filterBar : null;

  return (
    <div className="dashboard-page dashboard-page--analytics dashboard-page--processes">
      <DashboardSystemAlerts warnings={processesViewModel.warnings} partial={processesViewModel.isPartial} />

      <section className="dashboard-page__hero dashboard-page__hero--analytics">
        <div>
          <h2>{t('processes.dashboard.heroTitle')}</h2>
          <p>{t('processes.dashboard.heroDescription')}</p>
        </div>
      </section>

      <DashboardSummaryCards cards={processesViewModel.summaryCards} />

      <DashboardFilterBar
        mode="processes"
        filters={filters}
        options={filterOptions}
        feedback={filterFeedback}
        headerSlot={<DashboardGeneratedAt generatedAt={processesViewModel.generatedAt} />}
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
          title={t('processes.dashboard.refreshingTitle', { defaultValue: 'Данные обновляются' })}
          description={t('processes.dashboard.refreshingDescription', { defaultValue: 'Текущая выборка процессов остается на экране, пока загружаются обновленные данные.' })}
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('processes.dashboard.keywordSearch.loadingTitle', { defaultValue: 'Ищем процессы по найденным материалам' })}
          description={t('processes.dashboard.keywordSearch.loadingDescription', { defaultValue: 'Текущая таблица и выбранный контекст остаются на экране, пока обновляются результаты поиска.' })}
        />
      ) : null}

      {dashboardQuery.isError ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('processes.dashboard.refreshErrorTitle', { defaultValue: 'Не удалось обновить данные' })}
          description={t('processes.dashboard.refreshErrorDescription', { defaultValue: 'Показываем последнюю доступную версию экрана, чтобы вы могли продолжить анализ.' })}
          tone="danger"
        />
      ) : null}

      {isKeywordSearchActive && keywordSearchQuery.isError && !keywordSearchAvailabilityFeedback ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('processes.dashboard.keywordSearch.errorTitle', { defaultValue: 'Не удалось применить поиск к процессам' })}
          description={t('processes.dashboard.keywordSearch.errorDescription', { defaultValue: 'Показываем текущую выборку и выбранный процесс без изменений. Повторите попытку или скорректируйте запрос.' })}
          tone="danger"
        />
      ) : null}

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('processes.dashboard.readOnlyTitle')} description={t('processes.dashboard.readOnlyDescription')} />
      ) : null}

      {visibleRows.length === 0 ? (
        <EmptyState title={emptyFeedback.stateCard.title} description={emptyFeedback.stateCard.description} />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--workspace">
          <div className="dashboard-page__primary">
            <AnalyticsTable
              title={t('processes.dashboard.tableTitle')}
              description={t('processes.dashboard.tableDescription')}
              columns={processesDashboardColumns}
              rows={tableRows}
            />
          </div>

          <div className="dashboard-page__secondary">
            <ProcessGraphPanel
              selectedTitle={selectedProcess?.title ?? null}
              isLoading={graphQuery.isLoading && !hasGraphData}
              isRefreshing={graphQuery.isFetching && hasGraphData}
              isError={graphQuery.isError && !hasGraphData}
              showErrorNotice={graphQuery.isError && hasGraphData}
              viewModel={graphViewModel}
              hasSelection={selectedProcess !== null}
              partialHint={graphPartialHint}
              onRefresh={() => {
                void graphQuery.refetch();
              }}
            />

            <ProcessDetailPanel
              process={selectedProcess}
              graph={graphViewModel}
              actionSlot={
                canMutate && selectedProcess ? (
                  <button
                    type="button"
                    className="dashboard-button"
                    disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                    onClick={() => reportAction.run(undefined)}
                  >
                    {selectedProcess.reportStatus === 'draft' ? t('actions.updateDraftReport') : t('actions.generateDraftReport')}
                  </button>
                ) : null
              }
            />

            {canMutate && selectedProcess && reportAction.jobStatus ? (
              <AsyncActionIndicator
                title={t('processes.rows.reportJobTitle')}
                description={t('processes.rows.reportJobDescription')}
                status={reportAction.jobStatus}
                jobId={reportAction.activeJob?.job_id ?? reportAction.terminalState?.jobId}
                resultSummary={reportAction.resultSummary}
                tone={reportAction.terminalState?.status === 'failed' ? 'danger' : reportAction.jobStatus === 'done' || reportAction.jobStatus === 'completed' ? 'success' : 'default'}
              />
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}
