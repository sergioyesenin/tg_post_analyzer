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
  const dashboardQuery = useProcessesDashboardQuery(filters);
  const dashboardData = dashboardQuery.data ?? null;
  const filterOptions = getProcessesDashboardFilterOptions({
    filters,
    dashboardData,
  });
  const viewModel = dashboardData ? mapProcessesDashboardToViewModel(dashboardData) : null;
  const { selectedProcessId, selectProcess } = useSelectedProcessId(dashboardData?.items ?? []);
  const selectedProcess = viewModel?.rows.find((row) => row.processId === selectedProcessId) ?? null;
  const graphQuery = useProcessGraphQuery(selectedProcessId);
  const hasGraphData = graphQuery.data !== undefined;
  const graphViewModel = graphQuery.data ? mapProcessGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const reportAction = useUpdateProcessReportAction(selectedProcessId);
  const tableRows = useMemo(
    () => (viewModel ? mapProcessesRowsToTableRows(viewModel.rows, selectedProcessId, selectProcess, primaryRole) : []),
    [viewModel, selectedProcessId, selectProcess, primaryRole],
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
        feedback={processesViewModel.rows.length === 0 ? emptyUiState.filterBar : null}
        headerSlot={<DashboardGeneratedAt generatedAt={processesViewModel.generatedAt} />}
        onApply={applyFilters}
        onReset={resetFilters}
        onApplySearch={applySearch}
        onResetSearch={resetSearch}
      />

      {dashboardQuery.isFetching ? (
        <QueryActivityNotice
          eyebrow={t('states.loading')}
          title={t('processes.dashboard.refreshingTitle', { defaultValue: 'Дашборд обновляется' })}
          description={t('processes.dashboard.refreshingDescription', { defaultValue: 'Текущий снимок процессов остается на экране до завершения refetch.' })}
        />
      ) : null}

      {dashboardQuery.isError ? (
        <QueryActivityNotice
          eyebrow={t('states.error')}
          title={t('processes.dashboard.refreshErrorTitle', { defaultValue: 'Не удалось обновить дашборд' })}
          description={t('processes.dashboard.refreshErrorDescription', { defaultValue: 'Последний успешный снимок процессов сохранен, чтобы не сбрасывать контекст.' })}
          tone="danger"
        />
      ) : null}

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('processes.dashboard.readOnlyTitle')} description={t('processes.dashboard.readOnlyDescription')} />
      ) : null}

      {processesViewModel.rows.length === 0 ? (
        <EmptyState title={emptyUiState.stateCard.title} description={emptyUiState.stateCard.description} />
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
                tone={reportAction.terminalState?.status === 'failed' ? 'danger' : reportAction.jobStatus === 'done' ? 'success' : 'default'}
              />
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}






