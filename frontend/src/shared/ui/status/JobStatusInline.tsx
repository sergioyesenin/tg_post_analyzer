import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveJobStatusMeta } from '@shared/ui/status/statusMeta';

type JobStatusInlineProps = {
  status: string;
  jobId?: number | null;
};

export function JobStatusInline({ status, jobId }: JobStatusInlineProps) {
  const meta = resolveJobStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={`Job status: ${meta.label}`} suffix={jobId ? ` #${jobId}` : null} />;
}
