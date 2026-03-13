import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import { EventDetailPanel } from '@modules/workspace/events/components/EventDetailPanel';
import { EventGraphPanel } from '@modules/workspace/events/components/EventGraphPanel';
import { useEventDetailQueries, useUpdateEventDetailReportAction } from '@modules/workspace/event-detail/hooks';
import { mapEventDetailToViewModel } from '@modules/workspace/event-detail/mappers';

export function EventDetailsPage() {
  const { eventId: eventIdParam = '' } = useParams();
  const eventId = Number(eventIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const canMutate = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(eventId) || eventId <= 0) {
    return <ErrorState title="Invalid event id" description="The requested event id is not valid." />;
  }

  const { detailQuery, graphQuery } = useEventDetailQueries(eventId);
  const reportAction = useUpdateEventDetailReportAction(eventId);

  if (detailQuery.isLoading) {
    return <LoadingState title="Loading event detail" description="Fetching the event detail screen and graph context." />;
  }

  if (detailQuery.isError) {
    const error = detailQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return (
        <ForbiddenState
          title="Event detail is restricted"
          description="Your role can open the route, but the backend denied access to this event detail."
        />
      );
    }

    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title="Event not found" description="The requested event does not exist or is no longer available." />;
    }

    return <ErrorState title="Event detail failed to load" description="The main event detail request failed." />;
  }

  const detail = detailQuery.data;

  if (!detail) {
    return <ErrorState title="Event detail failed to load" description="The main event detail request returned no data." />;
  }

  const viewModel = mapEventDetailToViewModel(detail, graphQuery.data ?? null);
  const graphPartialHint = graphQuery.isError
    ? null
    : 'Full detail reuses the dashboard graph endpoint directly, so graph exploration stays limited to one additional request.';

  const handleBack = () => {
    if (location.key === 'default') {
      navigate('/dashboard/events');
      return;
    }

    navigate(-1);
  };

  return (
    <div className="post-detail-page">
      <header className="post-detail-page__header">
        <div>
          <span className="state-card__eyebrow">event detail</span>
          <h1>{viewModel.event.title}</h1>
          <p>
            Event detail uses <code>GET /api/events/{'{id}'}</code> for the canonical entity snapshot and reuses the
            dashboard graph endpoint only for graph/report context.
          </p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.event.startedAt}</span>
          <span>{viewModel.event.commentsCount} comments</span>
          <span>{viewModel.event.postsCount} linked posts</span>
          <span>Created by {viewModel.event.createdBy}</span>
          <button type="button" className="dashboard-button dashboard-button--ghost" onClick={handleBack}>
            Back
          </button>
        </div>
      </header>

      <DashboardSummaryCards cards={viewModel.summaryCards} />

      {primaryRole === 'viewer' ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Read only detail notice">
          <div>
            <span className="dashboard-banner__eyebrow">read only</span>
            <strong>Viewer access has no event report mutations</strong>
          </div>
          <p className="dashboard-banner__text">
            Detail data, graph exploration, and related post links remain visible while draft report actions stay hidden.
          </p>
        </section>
      ) : null}

      <div className="post-detail-grid">
        <div className="post-detail-grid__main">
          <EventGraphPanel
            selectedTitle={viewModel.event.title}
            isLoading={graphQuery.isLoading}
            isError={graphQuery.isError}
            viewModel={viewModel.graph}
            hasSelection
            partialHint={graphPartialHint}
            onRefresh={() => {
              void graphQuery.refetch();
            }}
          />

          <section className="detail-block">
            <div className="detail-block__header">
              <div>
                <span className="state-card__eyebrow">context links</span>
                <strong>Related context</strong>
              </div>
            </div>

            <div className="detail-list">
              <div className="detail-list__item">
                <div>
                  <strong>Events dashboard</strong>
                  <p>Return to the source workspace snapshot for filter-driven analysis.</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to="/dashboard/events">
                    Open dashboard
                  </Link>
                </div>
              </div>

              {viewModel.event.rootPostId ? (
                <div className="detail-list__item">
                  <div>
                    <strong>Root post #{viewModel.event.rootPostId}</strong>
                    <p>Root context is confirmed from the dashboard graph payload.</p>
                  </div>
                  <div className="detail-list__actions">
                    <Link className="table-link" to={`/posts/${viewModel.event.rootPostId}`}>
                      Open root post
                    </Link>
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <aside className="post-detail-grid__side">
          <EventDetailPanel
            event={viewModel.event}
            graph={viewModel.graph}
            actionSlot={
              canMutate ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                  onClick={() => reportAction.run(undefined)}
                >
                  {viewModel.event.reportStatus === 'draft' ? 'Update draft report' : 'Generate draft report'}
                </button>
              ) : null
            }
          />

          {canMutate && reportAction.jobStatus ? (
            <AsyncActionIndicator
              title="Event report job"
              description="Draft report generation uses the shared jobs flow and invalidates both event detail and graph context."
              status={reportAction.jobStatus}
              jobId={reportAction.activeJob?.job_id ?? reportAction.terminalState?.jobId}
              resultSummary={reportAction.resultSummary}
              tone={reportAction.terminalState?.status === 'failed' ? 'danger' : reportAction.jobStatus === 'done' ? 'success' : 'default'}
            />
          ) : null}
        </aside>
      </div>
    </div>
  );
}
