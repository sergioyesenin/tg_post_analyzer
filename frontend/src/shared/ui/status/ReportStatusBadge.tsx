type ReportStatus = 'missing' | 'pending' | 'draft' | 'ready' | 'failed';

const reportStatusMeta: Record<ReportStatus, { label: string; tone: string }> = {
  missing: { label: 'Missing', tone: 'muted' },
  pending: { label: 'Pending', tone: 'warning' },
  draft: { label: 'Draft', tone: 'info' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

type ReportStatusBadgeProps = {
  status: string;
};

export function ReportStatusBadge({ status }: ReportStatusBadgeProps) {
  const normalized = status.toLowerCase() as ReportStatus;
  const meta = reportStatusMeta[normalized] ?? {
    label: status || 'Unknown',
    tone: 'muted',
  };

  return <span className={`status-badge status-badge--${meta.tone}`}>{meta.label}</span>;
}
