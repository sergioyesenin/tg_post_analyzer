type MonitorStatusTone = 'muted' | 'warning' | 'success' | 'danger' | 'info';

const monitorStatusMeta: Record<string, { label: string; tone: MonitorStatusTone }> = {
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

type MonitorStatusBadgeProps = {
  status: string;
};

export function MonitorStatusBadge({ status }: MonitorStatusBadgeProps) {
  const normalized = status.toLowerCase();
  const meta = monitorStatusMeta[normalized] ?? { label: status || 'Unknown', tone: 'muted' as const };

  return <span className={`status-badge status-badge--${meta.tone}`}>{meta.label}</span>;
}
