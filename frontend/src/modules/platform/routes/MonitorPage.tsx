import { AdminDataGrid } from '@modules/admin/components/AdminDataGrid';
import { useMonitorFullQuery } from '@modules/platform/hooks';
import {
  mapMonitorAlertRows,
  mapMonitorDependencyRows,
  mapMonitorOverview,
  mapMonitorSummaryCards,
  monitorAlertColumns,
  monitorDependencyColumns,
} from '@modules/platform/mappers';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function MonitorPage() {
  const monitorQuery = useMonitorFullQuery();

  if (monitorQuery.isLoading) {
    return <LoadingState title="Loading monitor overview" description="Fetching the full system monitor snapshot." />;
  }

  if (monitorQuery.isError) {
    const error = monitorQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title="Monitor module is restricted" description="Monitor visibility is limited to admin users." />;
    }

    return <ErrorState title="Monitor overview failed to load" description="The full monitor snapshot request failed." />;
  }

  const monitor = monitorQuery.data;

  if (!monitor) {
    return <EmptyState title="Monitor snapshot is empty" description="The monitor endpoint returned no overview payload." />;
  }

  const summaryCards = mapMonitorSummaryCards(monitor);
  const overview = mapMonitorOverview(monitor);
  const dependencyRows = mapMonitorDependencyRows(monitor);
  const alertRows = mapMonitorAlertRows(monitor);

  return (
    <div className="dashboard-page">
      <section className="dashboard-page__hero">
        <div>
          <span className="state-card__eyebrow">monitor</span>
          <h2>Monitor overview</h2>
          <p>
            Admin-only monitor snapshot built from <code>GET /api/monitor/full</code> without assuming unsupported
            specialized tabs.
          </p>
        </div>
        <div className="dashboard-page__meta">
          <span>Snapshot at {overview.snapshotAt}</span>
          <span>Timezone {monitor.scheduler.timezone}</span>
        </div>
      </section>

      <DashboardSummaryCards cards={summaryCards} />

      <section className="dashboard-page__content dashboard-page__content--workspace">
        <div className="dashboard-page__primary">
          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">status system</span>
                <strong>Overview</strong>
              </div>
            </div>

            <div className="detail-list">
              {overview.overview.map((item) => (
                <div key={item.id} className="detail-list__item">
                  <div>
                    <strong>{item.label}</strong>
                  </div>
                  <div className="detail-list__actions">{item.value}</div>
                </div>
              ))}
            </div>
          </section>

          <AdminDataGrid
            title="Dependencies"
            description="Database and runtime dependencies with current monitor status."
            columns={monitorDependencyColumns}
            rows={dependencyRows}
          />
        </div>

        <div className="dashboard-page__secondary">
          {alertRows.length > 0 ? (
            <AdminDataGrid
              title="Active alerts"
              description="Threshold-driven warning and critical alerts from the monitor snapshot."
              columns={monitorAlertColumns}
              rows={alertRows}
            />
          ) : (
            <EmptyState title="No active alerts" description="The monitor snapshot currently has no warning or critical alerts." />
          )}

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">pipeline</span>
                <strong>Runtime and backlog</strong>
              </div>
            </div>

            <div className="detail-list">
              <div className="detail-list__item">
                <div>
                  <strong>Telegram pipeline</strong>
                  <p>Status from runtime heartbeat and health snapshot.</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.runtime.telegram_pipeline.status}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>AI pipeline</strong>
                  <p>Status from runtime heartbeat and health snapshot.</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.runtime.ai_pipeline.status}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>Collect comments flood rate</strong>
                  <p>Recent FloodWait ratio within the monitor window.</p>
                </div>
                <div className="detail-list__actions">{monitor.pipeline.collect_comments.flood_rate}</div>
              </div>
              <div className="detail-list__item">
                <div>
                  <strong>Archive lag</strong>
                  <p>Lag for retention archive processing.</p>
                </div>
                <div className="detail-list__actions">
                  {monitor.pipeline.archive.archive_lag_seconds === null ? 'n/a' : `${Math.round(monitor.pipeline.archive.archive_lag_seconds)}s`}
                </div>
              </div>
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}
