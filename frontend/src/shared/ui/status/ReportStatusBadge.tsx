import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveReportStatusMeta } from '@shared/ui/status/statusMeta';

type ReportStatusBadgeProps = {
  status: string;
};

export function ReportStatusBadge({ status }: ReportStatusBadgeProps) {
  const meta = resolveReportStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={`Report status: ${meta.label}`} />;
}
