import { useTranslation } from 'react-i18next';
import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveMonitorStatusMeta } from '@shared/ui/status/statusMeta';

type MonitorStatusBadgeProps = {
  status: string;
};

export function MonitorStatusBadge({ status }: MonitorStatusBadgeProps) {
  const { t } = useTranslation();
  const meta = resolveMonitorStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={t('navigation.monitor') + `: ${meta.label}`} />;
}
