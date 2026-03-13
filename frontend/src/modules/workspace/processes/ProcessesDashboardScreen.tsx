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

export function ProcessesDashboardScreen() {
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
            <h2>Processes workspace</h2>
            <p>Primary source: `/api/dashboard/processes`. Selection stabilizes around process-level hierarchy exploration.</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <LoadingState
          title="Loading processes dashboard"
          description="The dashboard snapshot is being loaded from /api/dashboard/processes."
        />
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
            <h2>Processes workspace</h2>
            <p>Primary source: `/api/dashboard/processes`. Selection stabilizes around process-level hierarchy exploration.</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        {isForbidden ? (
          <ForbiddenState
            title="Processes dashboard is not available for this role"
            description="The route is visible, but the backend denied access to the processes dashboard snapshot."
          />
        ) : (
          <ErrorState
            title="Processes dashboard failed to load"
            description="The snapshot request failed. Retry when the dashboard backend becomes available."
          />
        )}
      </div>
    );
  }

  if (!dashboardQuery.data) {
    return (
      <div className="dashboard-page">
        <section className="dashboard-page__hero">
          <div>
            <h2>Processes workspace</h2>
            <p>Primary source: `/api/dashboard/processes`. Selection stabilizes around process-level hierarchy exploration.</p>
          </div>
        </section>
        <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <ErrorState
          title="Processes dashboard returned no data"
          description="The request finished without a dashboard payload. Retry when the backend snapshot is available."
        />
      </div>
    );
  }

  if (!viewModel) {
    return (
      <div className="dashboard-page">
        <ErrorState
          title="Processes dashboard mapping failed"
          description="The dashboard payload is present, but the UI view model could not be constructed."
        />
      </div>
    );
  }

  const processesViewModel = viewModel;
  const graphPartialHint =
    selectedProcess && (!selectedProcess.graphReady || processesViewModel.isPartial)
      ? 'Partial warnings do not block hierarchy exploration. Nested events and confirmed post context remain visible where available.'
      : null;

  return (
    <div className="dashboard-page dashboard-page--processes">
      <DashboardSystemAlerts warnings={processesViewModel.warnings} partial={processesViewModel.isPartial} />

      <section className="dashboard-page__hero">
        <div>
          <h2>Processes workspace</h2>
          <p>Process mode emphasizes hierarchy: process summary, nested events, and confirmed post context stay synchronized around one selected process.</p>
        </div>
        <DashboardGeneratedAt generatedAt={processesViewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={processesViewModel.summaryCards} />

      <DashboardFilterBar mode="processes" filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice
          title="Viewer access hides process report mutations"
          description="Selection, hierarchy exploration, and event or post navigation remain available while report draft actions stay hidden."
        />
      ) : null}

      {processesViewModel.rows.length === 0 ? (
        <EmptyState
          title="No processes match the current filters"
          description="The dashboard loaded successfully, but the snapshot contains no process rows for these filters."
        />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--workspace">
          <div className="dashboard-page__primary">
            <DashboardTableShell
              title="Processes table"
              description="Process list with stable selection, hierarchy entry points, and process report status."
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
                    {selectedProcess.reportStatus === 'draft' ? 'Update draft report' : 'Generate draft report'}
                  </button>
                ) : null
              }
            />

            {canMutate && selectedProcess && reportAction.jobStatus ? (
              <AsyncActionIndicator
                title="Process report job"
                description="Draft report generation uses jobs polling and invalidates both dashboard rows and selected process hierarchy snapshot."
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
