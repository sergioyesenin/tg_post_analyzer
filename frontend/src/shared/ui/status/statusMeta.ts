export type StatusTone = 'muted' | 'warning' | 'success' | 'danger' | 'info';

export type StatusMeta = {
  label: string;
  tone: StatusTone;
};

const reportStatusMeta: Record<string, StatusMeta> = {
  missing: { label: 'Missing', tone: 'muted' },
  pending: { label: 'Pending', tone: 'warning' },
  draft: { label: 'Draft', tone: 'info' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

const jobStatusMeta: Record<string, StatusMeta> = {
  pending: { label: 'Pending', tone: 'warning' },
  running: { label: 'Running', tone: 'info' },
  done: { label: 'Done', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

const monitorStatusMeta: Record<string, StatusMeta> = {
  ok: { label: 'OK', tone: 'success' },
  warning: { label: 'Warning', tone: 'warning' },
  critical: { label: 'Critical', tone: 'danger' },
  degraded: { label: 'Degraded', tone: 'warning' },
  disabled: { label: 'Disabled', tone: 'muted' },
  late_or_missing: { label: 'Late or missing', tone: 'warning' },
  process_missing: { label: 'Process missing', tone: 'danger' },
  process_stale: { label: 'Process stale', tone: 'warning' },
  process_stopped: { label: 'Process stopped', tone: 'danger' },
  process_unknown: { label: 'Process unknown', tone: 'warning' },
  running: { label: 'Running', tone: 'info' },
};

function normalizeStatus(value: string | null | undefined) {
  return (value ?? '').trim().toLowerCase();
}

function fallbackStatusMeta(status: string | null | undefined): StatusMeta {
  return {
    label: status && status.trim().length > 0 ? status : 'Unknown',
    tone: 'muted',
  };
}

export function resolveReportStatusMeta(status: string | null | undefined) {
  return reportStatusMeta[normalizeStatus(status)] ?? fallbackStatusMeta(status);
}

export function resolveJobStatusMeta(status: string | null | undefined) {
  return jobStatusMeta[normalizeStatus(status)] ?? fallbackStatusMeta(status);
}

export function resolveMonitorStatusMeta(status: string | null | undefined) {
  return monitorStatusMeta[normalizeStatus(status)] ?? fallbackStatusMeta(status);
}
