import { i18n } from '@shared/i18n/i18n';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import { JobStatusInline } from '@shared/ui/status/JobStatusInline';
import { MonitorStatusBadge } from '@shared/ui/status/MonitorStatusBadge';
import { formatNullableNumber, formatUtcDateTime } from '@shared/utils/formatters';
import type { DeadLetterJobDto, JobsSummaryDto, MonitorFullDto, PendingJobDto } from '@modules/platform/contracts';

function formatCount(value: number | null | undefined) {
  return formatNullableNumber(value);
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return i18n.t('common.na');
  }

  return `${value.toFixed(2)}%`;
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return i18n.t('common.na');
  }

  if (value < 60) {
    return `${Math.round(value)}s`;
  }

  const minutes = Math.round(value / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }

  return `${(value / 3600).toFixed(1)}h`;
}

export const pendingJobsColumns: DashboardTableColumn[] = [
  { id: 'job', label: i18n.t('platform.jobs.table.job') },
  { id: 'status', label: i18n.t('platform.jobs.table.status') },
  { id: 'schedule', label: i18n.t('platform.jobs.table.schedule') },
  { id: 'attempts', label: i18n.t('platform.jobs.table.attempts') },
  { id: 'lock', label: i18n.t('platform.jobs.table.lock') },
  { id: 'error', label: i18n.t('platform.jobs.table.error') },
  { id: 'actions', label: i18n.t('platform.jobs.table.actions') },
];

export const deadLetterColumns: DashboardTableColumn[] = [
  { id: 'job', label: i18n.t('platform.jobs.table.deadLetter') },
  { id: 'attempts', label: i18n.t('platform.jobs.table.attempts') },
  { id: 'failed_at', label: i18n.t('platform.jobs.table.failedAt') },
  { id: 'error', label: i18n.t('platform.jobs.table.error') },
  { id: 'actions', label: i18n.t('platform.jobs.table.actions') },
];

export const monitorDependencyColumns: DashboardTableColumn[] = [
  { id: 'dependency', label: i18n.t('platform.monitor.dependenciesTable.dependency') },
  { id: 'status', label: i18n.t('platform.monitor.dependenciesTable.status') },
  { id: 'details', label: i18n.t('platform.monitor.dependenciesTable.details') },
];

export const monitorAlertColumns: DashboardTableColumn[] = [
  { id: 'metric', label: i18n.t('platform.monitor.alertsTable.metric') },
  { id: 'severity', label: i18n.t('platform.monitor.alertsTable.severity') },
  { id: 'current', label: i18n.t('platform.monitor.alertsTable.current') },
  { id: 'threshold', label: i18n.t('platform.monitor.alertsTable.threshold') },
  { id: 'message', label: i18n.t('platform.monitor.alertsTable.message') },
];

export function mapJobsSummaryToCards(summary: JobsSummaryDto, pending: PendingJobDto[], deadLetter: DeadLetterJobDto[]): DashboardSummaryCard[] {
  return [
    { id: 'total', label: i18n.t('platform.jobs.summary.trackedJobs'), value: formatCount(summary.total) },
    { id: 'pending', label: i18n.t('statusLabels.pending'), value: formatCount(summary.by_status.pending ?? 0) },
    { id: 'running', label: i18n.t('statusLabels.running'), value: formatCount(summary.by_status.running ?? 0) },
    { id: 'failed', label: i18n.t('statusLabels.failed'), value: formatCount(summary.by_status.failed ?? 0) },
    { id: 'dead-letter', label: i18n.t('platform.jobs.summary.deadLetter'), value: formatCount(deadLetter.length) },
    { id: 'visible', label: i18n.t('platform.jobs.summary.visibleQueueRows'), value: formatCount(pending.length) },
  ];
}

export function mapPendingJobsToRows(
  jobs: PendingJobDto[],
  onRetry: (jobId: number) => void,
  activeRetryJobId: number | null,
): DashboardTableRow[] {
  return jobs.map((job) => ({
    id: String(job.id),
    cells: {
      job: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{job.type}</strong>
          <span>#{job.id}</span>
        </div>
      ),
      status: <JobStatusInline status={job.status} jobId={job.id} />,
      schedule: (
        <div className="dashboard-table-shell__cell-stack">
          <span>{i18n.t('platform.jobs.rows.runAt', { value: formatUtcDateTime(job.run_at) })}</span>
          <span>{i18n.t('platform.jobs.rows.retryAt', { value: formatUtcDateTime(job.retry_at) })}</span>
        </div>
      ),
      attempts: `${job.attempts}/${job.max_attempts}`,
      lock: job.locked_by ?? i18n.t('platform.jobs.rows.unlocked'),
      error: job.last_error ?? i18n.t('common.na'),
      actions:
        job.status === 'failed' ? (
          <button
            type="button"
            className="dashboard-button dashboard-button--ghost"
            disabled={activeRetryJobId === job.id}
            onClick={() => onRetry(job.id)}
          >
            {i18n.t('platform.jobs.actions.retryFailedJob')}
          </button>
        ) : (
          i18n.t('common.na')
        ),
    },
  }));
}

export function mapDeadLetterRows(
  rows: DeadLetterJobDto[],
  onRetry: (deadLetterId: number) => void,
  activeRetryId: number | null,
): DashboardTableRow[] {
  return rows.map((row) => ({
    id: String(row.id),
    cells: {
      job: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{row.type}</strong>
          <span>{i18n.t('platform.jobs.rows.deadLetterId', { id: row.id })}</span>
          <span>{i18n.t('platform.jobs.rows.sourceJob', { id: row.source_job_id ?? i18n.t('common.na') })}</span>
        </div>
      ),
      attempts: `${row.attempts}/${row.max_attempts}`,
      failed_at: formatUtcDateTime(row.failed_at),
      error: row.last_error ?? i18n.t('common.na'),
      actions: (
        <button
          type="button"
          className="dashboard-button dashboard-button--ghost"
          disabled={activeRetryId === row.id}
          onClick={() => onRetry(row.id)}
        >
          {i18n.t('platform.jobs.actions.retryDeadLetter')}
        </button>
      ),
    },
  }));
}

export function mapMonitorSummaryCards(monitor: MonitorFullDto): DashboardSummaryCard[] {
  return [
    { id: 'health', label: i18n.t('platform.monitor.summary.health'), value: monitor.health.status },
    { id: 'alerts', label: i18n.t('platform.monitor.summary.alerts'), value: formatCount(monitor.alerts.alerts_count) },
    { id: 'jobs-total', label: i18n.t('platform.monitor.summary.jobsTracked'), value: formatCount(monitor.jobs.total) },
    { id: 'dead-letter', label: i18n.t('platform.monitor.summary.deadLetter'), value: formatCount(monitor.jobs.dead_letter_count) },
    { id: 'posts-24h', label: i18n.t('platform.monitor.summary.posts24h'), value: formatCount(monitor.activity_24h.posts_last_hours) },
    { id: 'comments-24h', label: i18n.t('platform.monitor.summary.comments24h'), value: formatCount(monitor.activity_24h.comments_last_hours) },
  ];
}

export function mapMonitorDependencyRows(monitor: MonitorFullDto): DashboardTableRow[] {
  return Object.entries(monitor.health.dependencies).map(([key, dependency]) => ({
    id: key,
    cells: {
      dependency: key,
      status: <MonitorStatusBadge status={dependency.status ?? (dependency.ok ? 'ok' : 'degraded')} />,
      details: (
        <div className="dashboard-table-shell__cell-stack">
          <span>{i18n.t('platform.monitor.rows.heartbeat', { value: formatUtcDateTime(dependency.last_heartbeat_at ?? null) })}</span>
          <span>{i18n.t('platform.monitor.rows.nextRun', { value: formatUtcDateTime(dependency.next_expected_run_at ?? null) })}</span>
          <span>{i18n.t('platform.monitor.rows.latency', { value: dependency.latency_ms ?? i18n.t('common.na') })}</span>
        </div>
      ),
    },
  }));
}

export function mapMonitorAlertRows(monitor: MonitorFullDto): DashboardTableRow[] {
  return monitor.alerts.alerts.map((alert, index) => ({
    id: `${alert.metric}-${index}`,
    cells: {
      metric: alert.metric,
      severity: <MonitorStatusBadge status={alert.severity} />,
      current: alert.current === null ? i18n.t('common.na') : String(alert.current),
      threshold: alert.threshold === null ? i18n.t('common.na') : String(alert.threshold),
      message: alert.message,
    },
  }));
}

export function mapMonitorOverview(monitor: MonitorFullDto) {
  return {
    snapshotAt: formatUtcDateTime(monitor.health.time_utc),
    overview: [
      {
        id: 'overall-health',
        label: i18n.t('platform.monitor.overview.overallHealth'),
        value: <MonitorStatusBadge status={monitor.health.status} />,
      },
      {
        id: 'alerts-status',
        label: i18n.t('platform.monitor.overview.alertsStatus'),
        value: <MonitorStatusBadge status={monitor.alerts.status} />,
      },
      {
        id: 'scheduler',
        label: i18n.t('platform.monitor.overview.scheduler'),
        value: <MonitorStatusBadge status={monitor.scheduler.status} />,
      },
      {
        id: 'pending-lag',
        label: i18n.t('platform.monitor.overview.pendingLag'),
        value: formatSeconds(monitor.jobs.pending_lag_seconds),
      },
      {
        id: 'retry-lag',
        label: i18n.t('platform.monitor.overview.retryLag'),
        value: formatSeconds(monitor.jobs.retry_lag_seconds),
      },
      {
        id: 'db-size',
        label: i18n.t('platform.monitor.overview.databaseSize'),
        value: monitor.database.pretty ?? i18n.t('common.na'),
      },
      {
        id: 'disk',
        label: i18n.t('platform.monitor.overview.diskUsed'),
        value: formatPercent(monitor.system.disk.used_percent),
      },
      {
        id: 'memory',
        label: i18n.t('platform.monitor.overview.memoryUsed'),
        value: formatPercent(monitor.system.memory.used_percent),
      },
      {
        id: 'backlog',
        label: i18n.t('platform.monitor.overview.backlogDelta'),
        value: formatCount(monitor.pipeline.backlog.delta_1h),
      },
    ],
  };
}
