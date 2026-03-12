import type { ReactNode } from 'react';

import { DetailBlockShell } from '@modules/workspace/post-detail/components/DetailBlockShell';
import type { ReportViewModel } from '@modules/workspace/post-detail/mappers';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type ReportBlockProps = {
  report: ReportViewModel | null;
  isLoading: boolean;
  isError: boolean;
  actionSlot?: ReactNode;
};

export function ReportBlock({ report, isLoading, isError, actionSlot }: ReportBlockProps) {
  return (
    <DetailBlockShell eyebrow="report" title="Report" actionSlot={actionSlot}>
      {isLoading ? (
        <LoadingState title="Loading report" description="Fetching the current report state for this post." />
      ) : isError ? (
        <ErrorState title="Report failed to load" description="Report data could not be loaded for this post." />
      ) : !report ? (
        <EmptyState title="Report is missing" description="No report exists yet for this post." />
      ) : (
        <div className="report-block">
          <div className="report-block__meta">
            <ReportStatusBadge status={report.status} />
            <span>{report.createdAt}</span>
          </div>
          <pre className="report-block__content">{report.content}</pre>
        </div>
      )}
    </DetailBlockShell>
  );
}
