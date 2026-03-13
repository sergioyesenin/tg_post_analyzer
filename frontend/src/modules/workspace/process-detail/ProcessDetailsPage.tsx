import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { useSession } from '@app/providers/SessionProvider';
import { ProcessDetailPanel } from '@modules/workspace/processes/components/ProcessDetailPanel';
import { ProcessGraphPanel } from '@modules/workspace/processes/components/ProcessGraphPanel';
import {
  useProcessDetailQueries,
  useUpdateProcessDetailReportAction,
} from '@modules/workspace/process-detail/hooks';
import { mapProcessDetailToViewModel } from '@modules/workspace/process-detail/mappers';
import { ApiError } from '@shared/api/client';
import { DashboardSummaryCards } from '@shared/dashboard/components/DashboardSummaryCards';
import { canPerformAction } from '@shared/routing/policy';
import { AsyncActionIndicator } from '@shared/ui/async/AsyncActionIndicator';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { ForbiddenState } from '@shared/ui/states/ForbiddenState';
import { LoadingState } from '@shared/ui/states/LoadingState';

export function ProcessDetailsPage() {
  const { processId: processIdParam = '' } = useParams();
  const processId = Number(processIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, primaryRole } = useSession();
  const roles = user?.roles ?? [];
  const canMutate = canPerformAction('reports.generate', roles);

  if (!Number.isFinite(processId) || processId <= 0) {
    return <ErrorState title="Invalid process id" description="The requested process id is not valid." />;
  }

  const { detailQuery, graphQuery } = useProcessDetailQueries(processId);
  const reportAction = useUpdateProcessDetailReportAction(processId);

  if (detailQuery.isLoading) {
    return <LoadingState title="Loading process detail" description="Fetching the process detail screen and hierarchy context." />;
  }

  if (detailQuery.isError) {
    const error = detailQuery.error;

    if (error instanceof ApiError && error.status === 403) {
      return (
        <ForbiddenState
          title="Process detail is restricted"
          description="Your role can open the route, but the backend denied access to this process detail."
        />
      );
    }

    if (error instanceof ApiError && error.status === 404) {
      return <ErrorState title="Process not found" description="The requested process does not exist or is no longer available." />;
    }

    return <ErrorState title="Process detail failed to load" description="The main process detail request failed." />;
  }

  const detail = detailQuery.data;

  if (!detail) {
    return <ErrorState title="Process detail failed to load" description="The main process detail request returned no data." />;
  }

  const viewModel = mapProcessDetailToViewModel(detail, graphQuery.data ?? null);
  const graphPartialHint =
    graphQuery.isError || !graphQuery.data || graphQuery.data.events.length === detail.events.length
      ? null
      : 'Process detail remains usable even when the hierarchy graph covers only part of the related-event set.';

  const handleBack = () => {
    if (location.key === 'default') {
      navigate('/dashboard/processes');
      return;
    }

    navigate(-1);
  };

  return (
    <div className="post-detail-page">
      <header className="post-detail-page__header">
        <div>
          <span className="state-card__eyebrow">process detail</span>
          <h1>{viewModel.process.title}</h1>
          <p>
            Process detail uses <code>GET /api/processes/{'{id}'}</code> for the canonical entity snapshot and reuses
            the dashboard hierarchy graph endpoint for related event and confirmed post context.
          </p>
        </div>

        <div className="post-detail-page__meta">
          <span>{viewModel.process.startedAt}</span>
          <span>{viewModel.process.eventsCount} related events</span>
          <span>{viewModel.confirmedPostIds.length} confirmed posts</span>
          <span>Created by {viewModel.process.createdBy}</span>
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
            <strong>Viewer access has no process report mutations</strong>
          </div>
          <p className="dashboard-banner__text">
            Detail data, hierarchy exploration, and confirmed navigation remain visible while draft report actions stay hidden.
          </p>
        </section>
      ) : null}

      <div className="post-detail-grid">
        <div className="post-detail-grid__main">
          <ProcessGraphPanel
            selectedTitle={viewModel.process.title}
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
                  <strong>Processes dashboard</strong>
                  <p>Return to the source workspace snapshot for filter-driven hierarchy analysis.</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to="/dashboard/processes">
                    Open dashboard
                  </Link>
                </div>
              </div>

              {viewModel.relatedEvents
                .filter((event) => event.postIds.length > 0)
                .slice(0, 3)
                .map((event) => (
                  <div key={event.eventId} className="detail-list__item">
                    <div>
                      <strong>{event.title}</strong>
                      <p>Confirmed context is available for this related event.</p>
                    </div>
                    <div className="detail-list__actions">
                      <Link className="table-link" to={`/events/${event.eventId}`}>
                        Open event
                      </Link>
                      <Link className="table-link" to={`/posts/${event.postIds[0]}`}>
                        Lead post
                      </Link>
                    </div>
                  </div>
                ))}
            </div>
          </section>
        </div>

        <aside className="post-detail-grid__side">
          <ProcessDetailPanel
            process={viewModel.process}
            graph={viewModel.graph}
            relatedEvents={viewModel.relatedEvents}
            actionSlot={
              canMutate ? (
                <button
                  type="button"
                  className="dashboard-button"
                  disabled={reportAction.isSubmitting || reportAction.jobStatus === 'running'}
                  onClick={() => reportAction.run(undefined)}
                >
                  {viewModel.process.reportStatus === 'draft' ? 'Update draft report' : 'Generate draft report'}
                </button>
              ) : null
            }
          />

          {canMutate && reportAction.jobStatus ? (
            <AsyncActionIndicator
              title="Process report job"
              description="Draft report generation uses the shared jobs flow and invalidates both process detail and hierarchy graph context."
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
