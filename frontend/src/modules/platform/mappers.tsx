import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import { JobStatusInline } from '@shared/ui/status/JobStatusInline';
import { MonitorStatusBadge } from '@shared/ui/status/MonitorStatusBadge';
import type { DeadLetterJobDto, JobsSummaryDto, MonitorFullDto, PendingJobDto } from '@modules/platform/contracts';

function formatDateTime(value: string | null) {
  if (!value) {
    return 'n/a';
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatCount(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return 'n/a';
  }

  return new Intl.NumberFormat('en-US').format(value);
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return 'n/a';
  }

  return `${value.toFixed(2)}%`;
}

function formatSeconds(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return 'n/a';
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
  { id: 'job', label: 'Job' },
  { id: 'status', label: 'Status' },
  { id: 'schedule', label: 'Run / Retry' },
  { id: 'attempts', label: 'Attempts' },
  { id: 'lock', label: 'Lock' },
  { id: 'error', label: 'Last error' },
  { id: 'actions', label: 'Actions' },
];

export const deadLetterColumns: DashboardTableColumn[] = [
  { id: 'job', label: 'Dead letter' },
  { id: 'attempts', label: 'Attempts' },
  { id: 'failed_at', label: 'Failed at' },
  { id: 'error', label: 'Last error' },
  { id: 'actions', label: 'Actions' },
];

export const monitorDependencyColumns: DashboardTableColumn[] = [
  { id: 'dependency', label: 'Dependency' },
  { id: 'status', label: 'Status' },
  { id: 'details', label: 'Details' },
];

export const monitorAlertColumns: DashboardTableColumn[] = [
  { id: 'metric', label: 'Metric' },
  { id: 'severity', label: 'Severity' },
  { id: 'current', label: 'Current' },
  { id: 'threshold', label: 'Threshold' },
  { id: 'message', label: 'Message' },
];

export function mapJobsSummaryToCards(summary: JobsSummaryDto, pending: PendingJobDto[], deadLetter: DeadLetterJobDto[]): DashboardSummaryCard[] {
  return [
    { id: 'total', label: 'Tracked jobs', value: formatCount(summary.total) },
    { id: 'pending', label: 'Pending', value: formatCount(summary.by_status.pending ?? 0) },
    { id: 'running', label: 'Running', value: formatCount(summary.by_status.running ?? 0) },
    { id: 'failed', label: 'Failed', value: formatCount(summary.by_status.failed ?? 0) },
    { id: 'dead-letter', label: 'Dead-letter', value: formatCount(deadLetter.length) },
    { id: 'visible', label: 'Visible queue rows', value: formatCount(pending.length) },
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
          <span>Run: {formatDateTime(job.run_at)}</span>
          <span>Retry: {formatDateTime(job.retry_at)}</span>
        </div>
      ),
      attempts: `${job.attempts}/${job.max_attempts}`,
      lock: job.locked_by ?? 'unlocked',
      error: job.last_error ?? 'n/a',
      actions:
        job.status === 'failed' ? (
          <button
            type="button"
            className="dashboard-button dashboard-button--ghost"
            disabled={activeRetryJobId === job.id}
            onClick={() => onRetry(job.id)}
          >
            Retry failed job
          </button>
        ) : (
          'n/a'
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
          <span>Dead-letter #{row.id}</span>
          <span>Source job: {row.source_job_id ?? 'n/a'}</span>
        </div>
      ),
      attempts: `${row.attempts}/${row.max_attempts}`,
      failed_at: formatDateTime(row.failed_at),
      error: row.last_error ?? 'n/a',
      actions: (
        <button
          type="button"
          className="dashboard-button dashboard-button--ghost"
          disabled={activeRetryId === row.id}
          onClick={() => onRetry(row.id)}
        >
          Retry dead letter
        </button>
      ),
    },
  }));
}

export function mapMonitorSummaryCards(monitor: MonitorFullDto): DashboardSummaryCard[] {
  return [
    { id: 'health', label: 'Health', value: monitor.health.status },
    { id: 'alerts', label: 'Alerts', value: formatCount(monitor.alerts.alerts_count) },
    { id: 'jobs-total', label: 'Jobs tracked', value: formatCount(monitor.jobs.total) },
    { id: 'dead-letter', label: 'Dead-letter', value: formatCount(monitor.jobs.dead_letter_count) },
    { id: 'posts-24h', label: 'Posts 24h', value: formatCount(monitor.activity_24h.posts_last_hours) },
    { id: 'comments-24h', label: 'Comments 24h', value: formatCount(monitor.activity_24h.comments_last_hours) },
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
          <span>Heartbeat: {formatDateTime(dependency.last_heartbeat_at ?? null)}</span>
          <span>Next run: {formatDateTime(dependency.next_expected_run_at ?? null)}</span>
          <span>Latency: {dependency.latency_ms ?? 'n/a'} ms</span>
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
      current: alert.current === null ? 'n/a' : String(alert.current),
      threshold: alert.threshold === null ? 'n/a' : String(alert.threshold),
      message: alert.message,
    },
  }));
}

export function mapMonitorOverview(monitor: MonitorFullDto) {
  return {
    snapshotAt: formatDateTime(monitor.health.time_utc),
    overview: [
      {
        id: 'overall-health',
        label: 'Overall health',
        value: <MonitorStatusBadge status={monitor.health.status} />,
      },
      {
        id: 'alerts-status',
        label: 'Alerts status',
        value: <MonitorStatusBadge status={monitor.alerts.status} />,
      },
      {
        id: 'scheduler',
        label: 'Scheduler',
        value: <MonitorStatusBadge status={monitor.scheduler.status} />,
      },
      {
        id: 'pending-lag',
        label: 'Pending lag',
        value: formatSeconds(monitor.jobs.pending_lag_seconds),
      },
      {
        id: 'retry-lag',
        label: 'Retry lag',
        value: formatSeconds(monitor.jobs.retry_lag_seconds),
      },
      {
        id: 'db-size',
        label: 'Database size',
        value: monitor.database.pretty ?? 'n/a',
      },
      {
        id: 'disk',
        label: 'Disk used',
        value: formatPercent(monitor.system.disk.used_percent),
      },
      {
        id: 'memory',
        label: 'Memory used',
        value: formatPercent(monitor.system.memory.used_percent),
      },
      {
        id: 'backlog',
        label: 'Backlog delta 1h',
        value: formatCount(monitor.pipeline.backlog.delta_1h),
      },
    ],
  };
}
