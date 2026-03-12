import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { PartialDataNotice } from '@shared/dashboard/components/PartialDataNotice';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardTableShell } from '@shared/dashboard/components/DashboardTableShell';
import { DashboardWarningsBanner } from '@shared/dashboard/components/DashboardWarningsBanner';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { useSession } from '@app/providers/SessionProvider';
import { EventDetailPanel } from '@modules/workspace/events/components/EventDetailPanel';
import { EventGraphPanel } from '@modules/workspace/events/components/EventGraphPanel';
import {
  useEventGraphQuery,
  useEventsDashboardQuery,
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
  const { filters, applyFilters, resetFilters } = useDashboardFilters('events');
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const dashboardQuery = useEventsDashboardQuery(filters);
  const dashboardData = dashboardQuery.data ?? null;
  const viewModel = dashboardData ? mapEventsDashboardToViewModel(dashboardData) : null;
  const { selectedEventId, selectEvent } = useSelectedEventId(dashboardData?.items ?? []);
  const selectedEvent = viewModel?.rows.find((row) => row.eventId === selectedEventId) ?? null;
  const graphQuery = useEventGraphQuery(selectedEventId);
  const graphViewModel = graphQuery.data ? mapEventGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const reportAction = useUpdateEventReportAction(selectedEventId);

  if (dashboardQuery.isLoading) {
    return (
      <div className="dashboard-page">
        <section className="dashboard-page__hero">
          <div>
            <h2>Events workspace</h2>
            <p>Primary source: `/api/dashboard/events`. Selection auto-stabilizes against the current snapshot.</p>
          </div>
        </section>
        <DashboardFilterBar mode="events" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <LoadingState
          title="Loading events dashboard"
          description="The dashboard snapshot is being loaded from /api/dashboard/events."
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
            <h2>Events workspace</h2>
            <p>Primary source: `/api/dashboard/events`. Selection auto-stabilizes against the current snapshot.</p>
          </div>
        </section>
        <DashboardFilterBar mode="events" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        {isForbidden ? (
          <ForbiddenState
            title="Events dashboard is not available for this role"
            description="The route is visible, but the backend denied access to the events dashboard snapshot."
          />
        ) : (
          <ErrorState
            title="Events dashboard failed to load"
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
            <h2>Events workspace</h2>
            <p>Primary source: `/api/dashboard/events`. Selection auto-stabilizes against the current snapshot.</p>
          </div>
        </section>
        <DashboardFilterBar mode="events" filters={filters} onApply={applyFilters} onReset={resetFilters} />
        <ErrorState
          title="Events dashboard returned no data"
          description="The request finished without a dashboard payload. Retry when the backend snapshot is available."
        />
      </div>
    );
  }

  if (!viewModel) {
    return (
      <div className="dashboard-page">
        <ErrorState
          title="Events dashboard mapping failed"
          description="The dashboard payload is present, but the UI view model could not be constructed."
        />
      </div>
    );
  }

  const eventsViewModel = viewModel;

  const graphPartialHint =
    selectedEvent && (!selectedEvent.graphReady || eventsViewModel.isPartial)
      ? 'Warnings and partial state do not block graph exploration. Related posts and selected-event metadata stay visible.'
      : null;

  return (
    <div className="dashboard-page">
      <div className="dashboard-page__system-layer">
        <DashboardWarningsBanner warnings={eventsViewModel.warnings} />
        <PartialDataNotice partial={eventsViewModel.isPartial} />
      </div>

      <section className="dashboard-page__hero">
        <div>
          <h2>Events workspace</h2>
          <p>List, graph, and selected-event detail panel stay synchronized around `/api/dashboard/events` and graph-by-selection.</p>
        </div>
        <DashboardGeneratedAt generatedAt={viewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={eventsViewModel.summaryCards} />

      <DashboardFilterBar mode="events" filters={filters} onApply={applyFilters} onReset={resetFilters} />

      {primaryRole === 'viewer' ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Read only notice">
          <div>
            <span className="dashboard-banner__eyebrow">read only</span>
            <strong>Viewer access hides event report mutations</strong>
          </div>
          <p className="dashboard-banner__text">
            Selection, graph exploration, and related posts remain available while report draft actions stay hidden.
          </p>
        </section>
      ) : null}

      {eventsViewModel.rows.length === 0 ? (
        <EmptyState
          title="No events match the current filters"
          description="The dashboard loaded successfully, but the snapshot contains no event rows for these filters."
        />
      ) : (
        <section className="dashboard-page__content dashboard-page__content--workspace">
          <div className="dashboard-page__primary">
            <DashboardTableShell
              title="Events table"
              description="Dense event list with stable selection, report status, and root-post entry points."
              columns={[...eventsDashboardColumns]}
              rows={mapEventsRowsToTableRows(eventsViewModel.rows, selectedEventId, selectEvent, primaryRole)}
            />
          </div>

          <div className="dashboard-page__secondary">
            <EventGraphPanel
              selectedTitle={selectedEvent?.title ?? null}
              isLoading={graphQuery.isLoading}
              isError={graphQuery.isError}
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
                    {selectedEvent.reportStatus === 'draft' ? 'Update draft report' : 'Generate draft report'}
                  </button>
                ) : null
              }
            />

            {canMutate && selectedEvent && reportAction.jobStatus ? (
              <AsyncActionIndicator
                title="Event report job"
                description="Draft report generation uses jobs polling and invalidates both dashboard rows and selected graph snapshot."
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
