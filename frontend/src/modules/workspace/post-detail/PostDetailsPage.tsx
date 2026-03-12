import { Link, useParams } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
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
  const { postId: postIdParam = '' } = useParams();
  const postId = Number(postIdParam);
  const { user } = useSession();
  const roles = user?.roles ?? [];
  const canRefreshComments = canPerformAction('comments.refresh', roles);
  const canGenerateReport = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(postId) || postId <= 0) {
    return <ErrorState title="Invalid post id" description="The requested post id is not valid." />;
  }

  const { postQuery, commentsQuery, reportQuery, linksQuery } = usePostDetailQueries(postId);
  const refreshCommentsAction = useRefreshCommentsAction(postId);
  const updateReportAction = useUpdateReportAction(postId);

  if (postQuery.isLoading) {
    return <LoadingState title="Loading post detail" description="Fetching the post detail screen and related blocks." />;
  }

  if (postQuery.isError) {
    const error = postQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return (
        <ForbiddenState
          title="Post detail is restricted"
          description="Your role can open the route, but the backend denied access to this post detail."
        />
      );
    }

    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title="Post not found" description="The requested post does not exist or is no longer available." />;
    }

    return <ErrorState title="Post detail failed to load" description="The main post detail request failed." />;
  }

  const post = postQuery.data;

  if (!post) {
    return <ErrorState title="Post detail failed to load" description="The main post detail request returned no data." />;
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
          <span className="state-card__eyebrow">post detail</span>
          <h1>Post #{viewModel.post.id}</h1>
          <p>{viewModel.post.text}</p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.post.date}</span>
          <span>{viewModel.post.commentsCount} comments</span>
          <span>{viewModel.post.views} views</span>
          <span>{viewModel.post.involvement} involvement</span>
          <Link className="table-link" to="/dashboard/posts">
            Back to posts dashboard
          </Link>
        </div>
      </header>

      {!canRefreshComments || !canGenerateReport ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Read only detail notice">
          <div>
            <span className="dashboard-banner__eyebrow">read only</span>
            <strong>Viewer access has no post mutations</strong>
          </div>
          <p className="dashboard-banner__text">
            Detail data remains visible, but comment refresh and report generation actions are hidden.
          </p>
        </section>
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
                  Refresh comments
                </button>
              ) : null
            }
          />

          <ActionPanel
            title="Comments refresh job"
            description="Async comments refresh runs through the jobs API and invalidates post detail queries after completion."
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
                  {viewModel.report ? 'Update report' : 'Generate report'}
                </button>
              ) : null
            }
          />

          <ActionPanel
            title="Report job"
            description="Report generation uses mutation enqueue, jobs polling and query invalidation on success."
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
