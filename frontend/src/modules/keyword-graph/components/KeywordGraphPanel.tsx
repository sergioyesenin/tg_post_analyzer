import { Link } from 'react-router-dom';

import type { KeywordGraphPanelViewModel } from '@modules/keyword-graph/mappers';
import { EmptyState } from '@shared/ui/states/EmptyState';
import { ErrorState } from '@shared/ui/states/ErrorState';
import { LoadingState } from '@shared/ui/states/LoadingState';

type KeywordGraphPanelProps = {
  viewModel: KeywordGraphPanelViewModel | null;
  isLoading: boolean;
  errorMessage: string | null;
  onRefresh: () => void;
};

export function KeywordGraphPanel({ viewModel, isLoading, errorMessage, onRefresh }: KeywordGraphPanelProps) {
  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">keyword graph</span>
          <strong>Graph visualization</strong>
        </div>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          Refresh graph
        </button>
      </div>

      {isLoading ? <LoadingState title="Building keyword graph" description="Resolving nodes and edges for the selected analytical seed set." /> : null}

      {!isLoading && errorMessage ? <ErrorState title="Keyword graph build failed" description={errorMessage} /> : null}

      {!isLoading && !errorMessage && !viewModel ? (
        <EmptyState
          title="Build a graph from selected posts"
          description="Search for posts, select the analytical seed set, then build the graph to inspect node and edge structure."
        />
      ) : null}

      {!isLoading && !errorMessage && viewModel ? (
        <div className="process-graph-panel">
          <article className="process-graph-panel__summary">
            <span className="state-card__eyebrow">graph snapshot</span>
            <strong>{viewModel.nodeCount} nodes and {viewModel.edgeCount} edges</strong>
            <div className="process-graph-panel__summary-meta">
              <span>{viewModel.seedCount} seeds</span>
              <span>{viewModel.excludedCount} excluded</span>
              <span>{viewModel.tookMs} ms</span>
            </div>
            {viewModel.metaEntries.length > 0 ? (
              <div className="process-graph-panel__summary-meta">
                {viewModel.metaEntries.slice(0, 4).map((entry) => (
                  <span key={entry.key}>
                    {entry.key}: {entry.value}
                  </span>
                ))}
              </div>
            ) : null}
          </article>

          <div className="event-graph-legend">
            <span className="event-graph-legend__item">
              <span className="event-graph-legend__swatch event-graph-legend__swatch--root" />
              Seed / explicitly included
            </span>
            <span className="event-graph-legend__item">
              <span className="event-graph-legend__swatch event-graph-legend__swatch--node" />
              Neighbor / related post
            </span>
            <span className="event-graph-legend__item">
              <span className="event-graph-legend__swatch event-graph-legend__swatch--edge" />
              Persisted or transient link
            </span>
          </div>

          <div className="event-graph-panel__nodes">
            {viewModel.nodes.map((node) => (
              <article
                key={node.id}
                className={`event-graph-node ${node.includedBy === 'seed' ? 'event-graph-node--root' : ''}`.trim()}
              >
                <div className="event-graph-node__meta">
                  <strong>Post #{node.postId}</strong>
                  <span>{node.date}</span>
                </div>
                <p>{node.title}</p>
                <div className="event-graph-node__stats">
                  <span>{node.channel}</span>
                  <span>{node.commentsCount} comments</span>
                  <span>{node.views} views</span>
                  <span>{node.involvement} involvement</span>
                  <span>included by {node.includedBy}</span>
                </div>
                <Link className="table-link" to={`/posts/${node.postId}`}>
                  Open post
                </Link>
              </article>
            ))}
          </div>

          {viewModel.edges.length === 0 ? (
            <EmptyState
              title="Graph has no edges"
              description="Nodes were built for the selected seed set, but no links matched the current graph criteria."
            />
          ) : (
            <div className="process-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="process-graph-edge">
                  <strong>
                    {edge.sourcePostId} {'->'} {edge.targetPostId}
                  </strong>
                  <span>
                    {edge.label} | {edge.status} | {edge.source} | score {edge.score}
                  </span>
                  <span>{edge.evidence}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
