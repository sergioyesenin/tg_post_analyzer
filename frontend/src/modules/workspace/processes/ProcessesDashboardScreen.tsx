import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
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
import { useTranslation } from 'react-i18next';

export function ProcessesDashboardScreen() {
  const { t } = useTranslation();
  const { filters, applyFilters, resetFilters } = useDashboardFilters('processes');
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const dashboardQuery = useProcessesDashboardQuery(filters);
  const dashboardData = dashboardQuery.data ?? null;
  const viewModel = dashboardData ? mapProcessesDashboardToViewModel(dashboardData) : null;
  const { selectedProcessId, selectProcess } = useSelectedProcessId(dashboardData?.items ?? []);
  const selectedProcess = viewModel?.rows.find((row) => row.processId === selectedProcessId) ?? null;
  const graphQuery = useProcessGraphQuery(selectedProcessId);
  const graphViewModel = graphQuery.data ? mapProcessGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const reportAction = useUpdateProcessReportAction(selectedProcessId);

  if (dashboardQuery.isLoading) {
    return (
      <div className="dashboard-page">
        <section className="dashboard-page__hero">
          <div>
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <LoadingState title={t('processes.dashboard.loadingTitle')} description={t('processes.dashboard.loadingDescription')} />
      </div>
    );
  }

  if (dashboardQuery.isError) {
    const error = dashboardQuery.error;
    const isForbidden = error instanceof ApiError && error.status === 403;

    return (
      <div className="dashboard-page">
        <section className="dashboard-page__hero">
          <div>
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        {isForbidden ? (
          <ForbiddenState title={t('processes.dashboard.forbiddenTitle')} description={t('processes.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('processes.dashboard.errorTitle')} description={t('processes.dashboard.errorDescription')} />
        )}
      </div>
    );
  }

  if (!dashboardQuery.data) {
    return (
      <div className="dashboard-page">
        <section className="dashboard-page__hero">
          <div>
            <h2>{t('processes.dashboard.heroTitle')}</h2>
            <p>{t('processes.dashboard.sourceDescription')}</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <ErrorState title={t('processes.dashboard.noDataTitle')} description={t('processes.dashboard.noDataDescription')} />
      </div>
    );
  }

  if (!viewModel) {
    return (
      <div className="dashboard-page">
        <ErrorState title={t('processes.dashboard.mappingTitle')} description={t('processes.dashboard.mappingDescription')} />
      </div>
    );
  }

  const processesViewModel = viewModel;
  const graphPartialHint =
    selectedProcess && (!selectedProcess.graphReady || processesViewModel.isPartial)
      ? t('processes.dashboard.partialHint')
      : null;

  return (
    <div className="dashboard-page dashboard-page--processes">
      <DashboardSystemAlerts warnings={processesViewModel.warnings} partial={processesViewModel.isPartial} />

      <section className="dashboard-page__hero">
        <div>
          <h2>{t('processes.dashboard.heroTitle')}</h2>
          <p>{t('processes.dashboard.heroDescription')}</p>
        </div>
        <DashboardGeneratedAt generatedAt={processesViewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={processesViewModel.summaryCards} />

      <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('processes.dashboard.readOnlyTitle')} description={t('processes.dashboard.readOnlyDescription')} />
      ) : null}

      {processesViewModel.rows.length === 0 ? (
        <EmptyState title={t('processes.dashboard.emptyTitle')} description={t('processes.dashboard.emptyDescription')} />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--workspace">
          <div className="dashboard-page__primary">
            <DashboardTableShell
              title={t('processes.dashboard.tableTitle')}
              description={t('processes.dashboard.tableDescription')}
              columns={[...processesDashboardColumns]}
              rows={mapProcessesRowsToTableRows(processesViewModel.rows, selectedProcessId, selectProcess, primaryRole)}
            />
          </div>

          <div className="dashboard-page__secondary">
            <ProcessGraphPanel
              selectedTitle={selectedProcess?.title ?? null}
              isLoading={graphQuery.isLoading || graphQuery.isFetching}
              isError={graphQuery.isError}
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
