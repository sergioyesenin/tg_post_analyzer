type JobStatusTone = 'muted' | 'warning' | 'success' | 'danger' | 'info';

const jobStatusMeta: Record<string, { label: string; tone: JobStatusTone }> = {
  pending: { label: 'Pending', tone: 'warning' },
  running: { label: 'Running', tone: 'info' },
  done: { label: 'Done', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

type JobStatusInlineProps = {
  status: string;
  jobId?: number | null;
};

export function JobStatusInline({ status, jobId }: JobStatusInlineProps) {
  const normalized = status.toLowerCase();
  const meta = jobStatusMeta[normalized] ?? { label: status || 'Unknown', tone: 'muted' as const };

  return (
    <span className={`status-badge status-badge--${meta.tone}`}>
      {meta.label}
      {jobId ? ` #${jobId}` : ''}
    </span>
  );
}
