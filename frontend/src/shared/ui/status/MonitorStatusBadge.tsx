import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveMonitorStatusMeta } from '@shared/ui/status/statusMeta';

type MonitorStatusBadgeProps = {
  status: string;
};

export function MonitorStatusBadge({ status }: MonitorStatusBadgeProps) {
  const meta = resolveMonitorStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={`Monitor status: ${meta.label}`} />;
}
