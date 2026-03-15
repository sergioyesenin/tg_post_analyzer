import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { ReadOnlyNotice } from '@shared/ui/notices/ReadOnlyNotice';
import { canPerformAction } from '@shared/routing/policy';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { mapPostDetailBundleToViewModel } from '@modules/workspace/post-detail/mappers';
import { CommentsBlock } from '@modules/workspace/post-detail/components/CommentsBlock';
import { LinksBlock } from '@modules/workspace/post-detail/components/LinksBlock';
import { ReportBlock } from '@modules/workspace/post-detail/components/ReportBlock';
import { usePostDetailQueries, useRefreshCommentsAction, useUpdateReportAction } from '@modules/workspace/post-detail/hooks';

function ActionPanel({
  title,
  description,
  status,
  jobId,
  resultSummary,
  isFailure,
}: {
  title: string;
  description: string;
  status: string | null;
  jobId?: number | null;
  resultSummary?: string | null;
  isFailure?: boolean;
}) {
  if (!status) {
    return null;
  }

  return (
    <AsyncActionIndicator
      title={title}
      description={description}
      status={status}
      jobId={jobId}
      resultSummary={resultSummary}
      tone={isFailure ? 'danger' : status === 'done' ? 'success' : 'default'}
    />
  );
}

export function PostDetailsPage() {
  const { t } = useTranslation();
  const { postId: postIdParam = '' } = useParams();
  const postId = Number(postIdParam);
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const canRefreshComments = canPerformAction('comments.refresh', roles);
  const canGenerateReport = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(postId) || postId <= 0) {
    return <ErrorState title={t('posts.detail.invalidTitle')} description={t('posts.detail.invalidDescription')} />;
  }

  const { postQuery, commentsQuery, reportQuery, linksQuery } = usePostDetailQueries(postId);
  const refreshCommentsAction = useRefreshCommentsAction(postId);
  const updateReportAction = useUpdateReportAction(postId);

  if (postQuery.isLoading) {
    return <LoadingState title={t('posts.detail.loadingTitle')} description={t('posts.detail.loadingDescription')} />;
  }

  if (postQuery.isError) {
    const error = postQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenState title={t('posts.detail.forbiddenTitle')} description={t('posts.detail.forbiddenDescription')} />;
    }

    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title={t('posts.detail.notFoundTitle')} description={t('posts.detail.notFoundDescription')} />;
    }

    return <ErrorState title={t('posts.detail.errorTitle')} description={t('posts.detail.errorDescription')} />;
  }

  const post = postQuery.data;

  if (!post) {
    return <ErrorState title={t('posts.detail.errorTitle')} description={t('posts.detail.noDataDescription')} />;
  }

  const viewModel = mapPostDetailBundleToViewModel({
    post,
    comments: commentsQuery.data ?? [],
    report: reportQuery.data ?? null,
    links: linksQuery.data ?? { post_id: postId, links: [] },
  });

  return (
    <div className="post-detail-page">
      <header className="post-detail-page__header">
        <div>
          <span className="state-card__eyebrow">{t('posts.detail.eyebrow')}</span>
          <h1>{t('posts.detail.title', { id: viewModel.post.id })}</h1>
          <p>{viewModel.post.text}</p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.post.date}</span>
          <span>{t('posts.detail.commentsCount', { value: viewModel.post.commentsCount })}</span>
          <span>{t('posts.detail.viewsCount', { value: viewModel.post.views })}</span>
          <span>{t('posts.detail.involvementValue', { value: viewModel.post.involvement })}</span>
          <Link className="table-link" to="/dashboard/posts">
            {t('posts.detail.backToDashboard')}
          </Link>
        </div>
      </header>

      {!canRefreshComments || !canGenerateReport ? (
        <ReadOnlyNotice
          title={t('posts.detail.readOnlyTitle')}
          description={t('posts.detail.readOnlyDescription')}
          ariaLabel={t('posts.detail.readOnlyAria')}
        />
      ) : null}

      <div className="post-detail-grid">
        <div className="post-detail-grid__main">
          <CommentsBlock
            comments={viewModel.comments}
            isLoading={commentsQuery.isLoading}
            isError={commentsQuery.isError}
            actionSlot={
              canRefreshComments ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={refreshCommentsAction.isSubmitting || refreshCommentsAction.jobStatus === 'running'}
                  onClick={() => refreshCommentsAction.run(undefined)}
                >
                  {t('posts.detail.refreshComments')}
                </button>
              ) : null
            }
          />

          <ActionPanel
            title={t('posts.detail.commentsJobTitle')}
            description={t('posts.detail.commentsJobDescription')}
            status={refreshCommentsAction.jobStatus}
            jobId={refreshCommentsAction.activeJob?.job_id ?? refreshCommentsAction.terminalState?.jobId}
            resultSummary={refreshCommentsAction.resultSummary}
            isFailure={refreshCommentsAction.terminalState?.status === 'failed'}
          />

          <LinksBlock links={viewModel.links} isLoading={linksQuery.isLoading} isError={linksQuery.isError} />
        </div>

        <aside className="post-detail-grid__side">
          <ReportBlock
            report={viewModel.report}
            isLoading={reportQuery.isLoading}
            isError={reportQuery.isError}
            actionSlot={
              canGenerateReport ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={updateReportAction.isSubmitting || updateReportAction.jobStatus === 'running'}
                  onClick={() => updateReportAction.run(undefined)}
                >
                  {viewModel.report ? t('posts.detail.updateReport') : t('actions.generateReport')}
                </button>
              ) : null
            }
          />

          <ActionPanel
            title={t('posts.detail.reportJobTitle')}
            description={t('posts.detail.reportJobDescription')}
            status={updateReportAction.jobStatus}
            jobId={updateReportAction.activeJob?.job_id ?? updateReportAction.terminalState?.jobId}
            resultSummary={updateReportAction.resultSummary}
            isFailure={updateReportAction.terminalState?.status === 'failed'}
          />
        </aside>
      </div>
    </div>
  );
}
