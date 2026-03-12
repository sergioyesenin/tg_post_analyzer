import { ErrorState } from '@shared/ui/states/ErrorState';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { LoadingState } from '@shared/ui/states/LoadingState';
import type { EventGraphPanelViewModel } from '@modules/workspace/events/mappers';
import { EventGraphLegend } from '@modules/workspace/events/components/EventGraphLegend';
import { EventGraphToolbar } from '@modules/workspace/events/components/EventGraphToolbar';

type EventGraphPanelProps = {
  selectedTitle: string | null;
  isLoading: boolean;
  isError: boolean;
  viewModel: EventGraphPanelViewModel | null;
  hasSelection: boolean;
  partialHint: string | null;
  onRefresh: () => void;
};

export function EventGraphPanel({
  selectedTitle,
  isLoading,
  isError,
  viewModel,
  hasSelection,
  partialHint,
  onRefresh,
}: EventGraphPanelProps) {
  if (!hasSelection) {
    return (
      <section className="detail-block">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">graph</span>
            <strong>Event graph</strong>
          </div>
        </div>
        <EmptyState
          title="Select an event to inspect its graph"
          description="The graph area stays mounted and waits for a stable event selection from the events table."
        />
      </section>
    );
  }

  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">graph</span>
          <strong>Event graph</strong>
        </div>
      </div>

      <EventGraphToolbar
        title={selectedTitle ?? 'Selected event'}
        nodeCount={viewModel?.nodes.length ?? 0}
        edgeCount={viewModel?.edges.length ?? 0}
        isLoading={isLoading}
        onRefresh={onRefresh}
      />

      <EventGraphLegend />

      {partialHint ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label="Graph partial notice">
          <div>
            <span className="dashboard-banner__eyebrow">partial graph</span>
            <strong>Graph data is partially available</strong>
          </div>
          <p className="dashboard-banner__text">{partialHint}</p>
        </section>
      ) : null}

      {isLoading ? (
        <LoadingState title="Loading event graph" description="Fetching /api/dashboard/events/{event_id}/graph for the selected event." />
      ) : null}

      {!isLoading && isError ? (
        <ErrorState
          title="Event graph failed to load"
          description="The selected event remains visible in the detail panel, but graph data could not be loaded."
        />
      ) : null}

      {!isLoading && !isError && viewModel && viewModel.nodes.length === 0 ? (
        <EmptyState
          title="No graph nodes are available"
          description="The selected event has no graph nodes in the current snapshot."
        />
      ) : null}

      {!isLoading && !isError && viewModel && viewModel.nodes.length > 0 ? (
        <div className="event-graph-panel">
          <div className="event-graph-panel__nodes">
            {viewModel.nodes.map((node) => (
              <article
                key={node.id}
                className={`event-graph-node ${node.isRoot ? 'event-graph-node--root' : ''}`.trim()}
              >
                <div className="event-graph-node__meta">
                  <strong>{node.isRoot ? 'Root' : 'Linked'} post #{node.postId}</strong>
                  <span>{node.date}</span>
                </div>
                <p>{node.title}</p>
                <div className="event-graph-node__stats">
                  <span>{node.commentsCount} comments</span>
                  <span>{node.views} views</span>
                  <span>{node.involvement} involvement</span>
                </div>
              </article>
            ))}
          </div>

          {viewModel.edges.length === 0 ? (
            <EmptyState
              title="Graph has no edges"
              description="Nodes are available for exploration, but link edges are absent in the current graph snapshot."
            />
          ) : (
            <div className="event-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="event-graph-edge">
                  <strong>
                    {edge.sourcePostId} {'->'} {edge.targetPostId}
                  </strong>
                  <span>
                    {edge.label} • {edge.status} • score {edge.score}
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
