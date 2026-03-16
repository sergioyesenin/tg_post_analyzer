import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import type { KeywordGraphPanelViewModel } from '@modules/keyword-graph/mappers';
import { SharedFlowCanvas, type GraphCanvasEdge, type GraphCanvasNode } from '@shared/ui/graph/SharedFlowCanvas';
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
  const { t } = useTranslation();

  const flowNodes = useMemo<GraphCanvasNode[]>(() => {
    if (!viewModel) {
      return [];
    }

    return viewModel.nodes.map((node, index) => ({
      id: `post-${node.postId}`,
      label: `#${node.postId}`,
      meta: `${node.channel} | ${t('keywordGraph.rows.comments', { value: node.commentsCount })}`,
      tone: node.includedBy === 'seed' ? 'seed' : 'neighbor',
      href: `/posts/${node.postId}`,
      position: { x: index * 220, y: node.includedBy === 'seed' ? 40 : 190 },
    }));
  }, [t, viewModel]);

  const flowEdges = useMemo<GraphCanvasEdge[]>(() => {
    if (!viewModel) {
      return [];
    }

    return viewModel.edges.map((edge) => ({
      id: edge.id,
      source: `post-${edge.sourcePostId}`,
      target: `post-${edge.targetPostId}`,
      label: edge.label,
    }));
  }, [viewModel]);

  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{t('keywordGraph.panel.eyebrow')}</span>
          <strong>{t('keywordGraph.panel.title')}</strong>
        </div>
        <button type="button" className="dashboard-button dashboard-button--ghost" onClick={onRefresh} disabled={isLoading}>
          {t('keywordGraph.panel.refresh')}
        </button>
      </div>

      {isLoading ? <LoadingState title={t('keywordGraph.panel.loadingTitle')} description={t('keywordGraph.panel.loadingDescription')} /> : null}

      {!isLoading && errorMessage ? <ErrorState title={t('keywordGraph.panel.errorTitle')} description={errorMessage} /> : null}

      {!isLoading && !errorMessage && !viewModel ? (
        <EmptyState
          title={t('keywordGraph.panel.emptyTitle')}
          description={t('keywordGraph.panel.emptyDescription')}
        />
      ) : null}

      {!isLoading && !errorMessage && viewModel ? (
        <div className="process-graph-panel">
          <SharedFlowCanvas ariaLabel={t('keywordGraph.panel.title')} nodes={flowNodes} edges={flowEdges} />

          <article className="process-graph-panel__summary">
            <span className="state-card__eyebrow">{t('keywordGraph.panel.snapshotEyebrow')}</span>
            <strong>{t('keywordGraph.panel.graphSummary', { nodes: viewModel.nodeCount, edges: viewModel.edgeCount })}</strong>
            <div className="process-graph-panel__summary-meta">
              <span>{t('keywordGraph.panel.seeds', { value: viewModel.seedCount })}</span>
              <span>{t('keywordGraph.panel.excluded', { value: viewModel.excludedCount })}</span>
              <span>{t('keywordGraph.panel.tookMs', { value: viewModel.tookMs })}</span>
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
              {t('keywordGraph.panel.legend.seed')}
            </span>
            <span className="event-graph-legend__item">
              <span className="event-graph-legend__swatch event-graph-legend__swatch--node" />
              {t('keywordGraph.panel.legend.neighbor')}
            </span>
            <span className="event-graph-legend__item">
              <span className="event-graph-legend__swatch event-graph-legend__swatch--edge" />
              {t('keywordGraph.panel.legend.edge')}
            </span>
          </div>

          <div className="event-graph-panel__nodes">
            {viewModel.nodes.map((node) => (
              <article
                key={node.id}
                className={`event-graph-node ${node.includedBy === 'seed' ? 'event-graph-node--root' : ''}`.trim()}
              >
                <div className="event-graph-node__meta">
                  <strong>{t('keywordGraph.rows.postLabel', { id: node.postId })}</strong>
                  <span>{node.date}</span>
                </div>
                <p>{node.title}</p>
                <div className="event-graph-node__stats">
                  <span>{node.channel}</span>
                  <span>{t('keywordGraph.rows.comments', { value: node.commentsCount })}</span>
                  <span>{t('keywordGraph.rows.views', { value: node.views })}</span>
                  <span>{t('keywordGraph.rows.involvement', { value: node.involvement })}</span>
                  <span>{t('keywordGraph.panel.includedBy', { value: node.includedBy })}</span>
                </div>
                <Link className="table-link" to={`/posts/${node.postId}`}>
                  {t('keywordGraph.rows.openPost')}
                </Link>
              </article>
            ))}
          </div>

          {viewModel.edges.length === 0 ? (
            <EmptyState
              title={t('keywordGraph.panel.noEdgesTitle')}
              description={t('keywordGraph.panel.noEdgesDescription')}
            />
          ) : (
            <div className="process-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="process-graph-edge">
                  <strong>
                    {edge.sourcePostId} {'->'} {edge.targetPostId}
                  </strong>
                  <span>
                    {edge.label} | {edge.status} | {edge.source} | {t('keywordGraph.panel.score', { value: edge.score })}
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
