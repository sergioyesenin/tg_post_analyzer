import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();

  return (
    <DetailBlockShell eyebrow={t('posts.report.eyebrow')} title={t('posts.report.title')} actionSlot={actionSlot}>
      {isLoading ? (
        <LoadingState title={t('posts.report.loadingTitle')} description={t('posts.report.loadingDescription')} />
      ) : isError ? (
        <ErrorState title={t('posts.report.errorTitle')} description={t('posts.report.errorDescription')} />
      ) : !report ? (
        <EmptyState title={t('posts.report.emptyTitle')} description={t('posts.report.emptyDescription')} />
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
