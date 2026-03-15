import { useTranslation } from 'react-i18next';
import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveReportStatusMeta } from '@shared/ui/status/statusMeta';

type ReportStatusBadgeProps = {
  status: string;
};

export function ReportStatusBadge({ status }: ReportStatusBadgeProps) {
  const { t } = useTranslation();
  const meta = resolveReportStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={t('fields.reportStatus') + `: ${meta.label}`} />;
}
