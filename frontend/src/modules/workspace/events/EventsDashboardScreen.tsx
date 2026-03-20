import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@shared/api/client';
import { DashboardFilterBar } from '@shared/dashboard/components/DashboardFilterBar';
import { DashboardGeneratedAt } from '@shared/dashboard/components/DashboardGeneratedAt';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { DashboardSystemAlerts } from '@shared/dashboard/components/DashboardSystemAlerts';
import { AnalyticsTable } from '@shared/dashboard/components/DashboardTableShell';
import { getEventsDashboardFilterOptions } from '@shared/dashboard/filter-options';
import { useDashboardFilters } from '@shared/dashboard/hooks';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
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
  const { filters, applyFilters, resetFilters } = useDashboardFilters('events');
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const dashboardQuery = useEventsDashboardQuery(filters);
  const channelsQuery = useChannelsQuery();
  const dashboardData = dashboardQuery.data ?? null;
  const filterOptions = getEventsDashboardFilterOptions({
    filters,
    dashboardData,
    channels: channelsQuery.data,
  });
  const channelOptionsState = channelsQuery.isLoading ? 'loading' : channelsQuery.isError ? 'error' : 'ready';
  const viewModel = dashboardData ? mapEventsDashboardToViewModel(dashboardData) : null;
  const { selectedEventId, selectEvent } = useSelectedEventId(dashboardData?.items ?? []);
  const selectedEvent = viewModel?.rows.find((row) => row.eventId === selectedEventId) ?? null;
  const graphQuery = useEventGraphQuery(selectedEventId);
  const graphViewModel = graphQuery.data ? mapEventGraphToViewModel(graphQuery.data) : null;
  const canMutate = canPerformAction('reports.generate', roles);
  const reportAction = useUpdateEventReportAction(selectedEventId);
  const tableRows = useMemo(
    () => (viewModel ? mapEventsRowsToTableRows(viewModel.rows, selectedEventId, selectEvent, primaryRole) : []),
    [viewModel, selectedEventId, selectEvent, primaryRole],
  );

  if (dashboardQuery.isLoading) {
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
        />
        <LoadingState title={t('events.dashboard.loadingTitle')} description={t('events.dashboard.loadingDescription')} />
      </div>
    );
  }

  if (dashboardQuery.isError) {
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
          onApply={applyFilters}
          onReset={resetFilters}
        />
        {isForbidden ? (
          <ForbiddenState title={t('events.dashboard.forbiddenTitle')} description={t('events.dashboard.forbiddenDescription')} />
        ) : (
          <ErrorState title={t('events.dashboard.errorTitle')} description={t('events.dashboard.errorDescription')} />
        )}
      </div>
    );
  }

  if (!dashboardQuery.data) {
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

  return (
    <div className="dashboard-page dashboard-page--analytics">
      <DashboardSystemAlerts warnings={eventsViewModel.warnings} partial={eventsViewModel.isPartial} />

      <section className="dashboard-page__hero dashboard-page__hero--analytics">
        <div>
          <h2>{t('events.dashboard.heroTitle')}</h2>
          <p>{t('events.dashboard.heroDescription')}</p>
        </div>
        <DashboardGeneratedAt generatedAt={viewModel.generatedAt} />
      </section>

      <DashboardSummaryCards cards={eventsViewModel.summaryCards} />

      <DashboardFilterBar
        mode="events"
        filters={filters}
        options={filterOptions}
        channelOptionsState={channelOptionsState}
        onApply={applyFilters}
        onReset={resetFilters}
      />

      {primaryRole === 'viewer' ? (
        <ReadOnlyNotice title={t('events.dashboard.readOnlyTitle')} description={t('events.dashboard.readOnlyDescription')} />
      ) : null}

      {eventsViewModel.rows.length === 0 ? (
        <EmptyState title={t('events.dashboard.emptyTitle')} description={t('events.dashboard.emptyDescription')} />
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
              isLoading={graphQuery.isLoading || graphQuery.isFetching}
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





