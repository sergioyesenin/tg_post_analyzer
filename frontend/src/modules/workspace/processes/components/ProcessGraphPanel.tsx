import { Link } from 'react-router-dom';

import { ErrorState } from '@shared/ui/states/ErrorState';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import type { ProcessGraphPanelViewModel } from '@modules/workspace/processes/mappers';
import { ProcessGraphLegend } from '@modules/workspace/processes/components/ProcessGraphLegend';
import { ProcessGraphToolbar } from '@modules/workspace/processes/components/ProcessGraphToolbar';

type ProcessGraphPanelProps = {
  selectedTitle: string | null;
  isLoading: boolean;
  isError: boolean;
  viewModel: ProcessGraphPanelViewModel | null;
  hasSelection: boolean;
  partialHint: string | null;
  onRefresh: () => void;
};

export function ProcessGraphPanel({
  selectedTitle,
  isLoading,
  isError,
  viewModel,
  hasSelection,
  partialHint,
  onRefresh,
}: ProcessGraphPanelProps) {
  if (!hasSelection) {
    return (
      <section className="detail-block detail-block--process">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">hierarchy graph</span>
            <strong>Process hierarchy</strong>
          </div>
        </div>
        <EmptyState
          title="Select a process to inspect its hierarchy"
          description="The hierarchy area stays mounted and waits for a stable process selection from the processes table."
        />
      </section>
    );
  }

  return (
    <section className="detail-block detail-block--process">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">hierarchy graph</span>
          <strong>Process hierarchy</strong>
        </div>
      </div>

      <ProcessGraphToolbar
        title={selectedTitle ?? 'Selected process'}
        eventCount={viewModel?.events.length ?? 0}
        postCount={viewModel?.nodes.length ?? 0}
        isLoading={isLoading}
        onRefresh={onRefresh}
      />

      <ProcessGraphLegend />

      {partialHint ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Process graph partial notice">
          <div>
            <span className="dashboard-banner__eyebrow">partial hierarchy</span>
            <strong>Process hierarchy is partially available</strong>
          </div>
          <p className="dashboard-banner__text">{partialHint}</p>
        </section>
      ) : null}

      {isLoading ? (
        <LoadingState
          title="Loading process graph"
          description="Fetching /api/dashboard/processes/{process_id}/graph for the selected process."
        />
      ) : null}

      {!isLoading && isError ? (
        <ErrorState
          title="Process graph failed to load"
          description="The selected process remains visible in the detail panel, but hierarchy data could not be loaded."
        />
      ) : null}

      {!isLoading && !isError && viewModel && viewModel.events.length === 0 && viewModel.nodes.length === 0 ? (
        <EmptyState
          title="No process hierarchy is available"
          description="The selected process has no nested events or context posts in the current graph snapshot."
        />
      ) : null}

      {!isLoading && !isError && viewModel && (viewModel.events.length > 0 || viewModel.nodes.length > 0) ? (
        <div className="process-graph-panel">
          <article className="process-graph-panel__summary">
            <span className="state-card__eyebrow">process layer</span>
            <strong>{viewModel.summary.title}</strong>
            <div className="process-graph-panel__summary-meta">
              <span>{viewModel.summary.status}</span>
              <span>{viewModel.summary.eventsCount} events</span>
              <span>{viewModel.summary.postsCount} posts</span>
              <span>{viewModel.summary.commentsCount} comments</span>
            </div>
          </article>

          <div className="process-graph-panel__events">
            {viewModel.events.map((event) => (
              <article key={event.eventId} className="process-graph-event-card">
                <div className="process-graph-event-card__header">
                  <div>
                    <span className="state-card__eyebrow">nested event</span>
                    <strong>{event.title}</strong>
                  </div>
                  <Link className="table-link" to={`/events/${event.eventId}`}>
                    Open event
                  </Link>
                </div>
                <div className="process-graph-event-card__meta">
                  <span>{event.status}</span>
                  <span>{event.startedAt}</span>
                  <span>{event.relationType}</span>
                  <span>{event.direction}</span>
                  <span>score {event.score}</span>
                </div>
                <div className="process-graph-event-card__posts">
                  {event.postIds.length === 0 ? (
                    <span className="table-link table-link--muted">No confirmed posts</span>
                  ) : (
                    event.postIds.map((postId) => (
                      <Link key={postId} className="table-link" to={`/posts/${postId}`}>
                        Post #{postId}
                      </Link>
                    ))
                  )}
                </div>
              </article>
            ))}
          </div>

          {viewModel.edges.length === 0 ? (
            <EmptyState
              title="Process graph has no post-link edges"
              description="Hierarchy data is present, but no post-to-post link edges are available in the current process graph snapshot."
            />
          ) : (
            <div className="process-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="process-graph-edge">
                  <strong>
                    {edge.sourcePostId} {'->'} {edge.targetPostId}
                  </strong>
                  <span>
                    {edge.label} | {edge.status} | score {edge.score}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
