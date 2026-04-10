import { i18n } from '@shared/i18n/i18n';

export type StatusTone = 'muted' | 'warning' | 'success' | 'danger' | 'info';

export type StatusMeta = {
  label: string;
  tone: StatusTone;
};

const reportStatusMeta: Record<string, StatusMeta> = {
  missing: { label: i18n.t('statusLabels.missing'), tone: 'muted' },
  pending: { label: i18n.t('statusLabels.pending'), tone: 'warning' },
  draft: { label: i18n.t('statusLabels.draft'), tone: 'info' },
  stale: { label: i18n.exists('statusLabels.stale') ? i18n.t('statusLabels.stale') : 'Stale', tone: 'warning' },
  ready: { label: i18n.t('statusLabels.ready'), tone: 'success' },
  failed: { label: i18n.t('statusLabels.failed'), tone: 'danger' },
};

const jobStatusMeta: Record<string, StatusMeta> = {
  pending: { label: i18n.t('statusLabels.pending'), tone: 'warning' },
  running: { label: i18n.t('statusLabels.running'), tone: 'info' },
  building_report: { label: i18n.t('statusLabels.building_report'), tone: 'info' },
  completed: { label: i18n.t('statusLabels.completed'), tone: 'success' },
  blocked: { label: i18n.t('statusLabels.blocked'), tone: 'warning' },
  done: { label: i18n.t('statusLabels.done'), tone: 'success' },
  failed: { label: i18n.t('statusLabels.failed'), tone: 'danger' },
};

const monitorStatusMeta: Record<string, StatusMeta> = {
  ok: { label: i18n.t('statusLabels.ok'), tone: 'success' },
  warning: { label: i18n.t('statusLabels.warning'), tone: 'warning' },
  critical: { label: i18n.t('statusLabels.critical'), tone: 'danger' },
  degraded: { label: i18n.t('statusLabels.degraded'), tone: 'warning' },
  disabled: { label: i18n.t('statusLabels.disabled'), tone: 'muted' },
  late_or_missing: { label: i18n.t('statusLabels.late_or_missing'), tone: 'warning' },
  process_missing: { label: i18n.t('statusLabels.process_missing'), tone: 'danger' },
  process_stale: { label: i18n.t('statusLabels.process_stale'), tone: 'warning' },
  process_stopped: { label: i18n.t('statusLabels.process_stopped'), tone: 'danger' },
  process_unknown: { label: i18n.t('statusLabels.process_unknown'), tone: 'warning' },
  running: { label: i18n.t('statusLabels.running'), tone: 'info' },
};

function normalizeStatus(value: string | null | undefined) {
  return (value ?? '').trim().toLowerCase();
}

function fallbackStatusMeta(status: string | null | undefined): StatusMeta {
  return {
    label: status && status.trim().length > 0 ? status : i18n.t('common.unknown'),
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

