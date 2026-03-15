import { useTranslation } from 'react-i18next';
import { StatusBadge } from '@shared/ui/status/StatusBadge';
import { resolveJobStatusMeta } from '@shared/ui/status/statusMeta';

type JobStatusInlineProps = {
  status: string;
  jobId?: number | null;
};

export function JobStatusInline({ status, jobId }: JobStatusInlineProps) {
  const { t } = useTranslation();
  const meta = resolveJobStatusMeta(status);
  return <StatusBadge meta={meta} ariaLabel={t('navigation.jobs') + `: ${meta.label}`} suffix={jobId ? ` #${jobId}` : null} />;
}
