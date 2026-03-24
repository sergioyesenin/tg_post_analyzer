import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Position } from 'reactflow';

import { SharedFlowCanvas, type GraphCanvasEdge, type GraphCanvasNode } from '@shared/ui/graph/SharedFlowCanvas';
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

function buildDirectedEdges(viewModel: EventGraphPanelViewModel): GraphCanvasEdge[] {
  return viewModel.edges.map((edge) => {
    const isReverse = edge.direction === 'dst_to_src';

    return {
      id: edge.id,
      source: String(isReverse ? edge.targetPostId : edge.sourcePostId),
      target: String(isReverse ? edge.sourcePostId : edge.targetPostId),
      label: edge.label,
    };
  });
}

function buildOrderedNodes(viewModel: EventGraphPanelViewModel) {
  const rootNode = viewModel.nodes.find((node) => node.isRoot) ?? null;
  const otherNodes = viewModel.nodes.filter((node) => !node.isRoot).sort((left, right) => left.date.localeCompare(right.date));

  return rootNode ? [rootNode, ...otherNodes] : [...viewModel.nodes].sort((left, right) => left.date.localeCompare(right.date));
}

function EventGraphSelectionHeader({ selectedTitle }: { selectedTitle: string | null }) {
  const { t } = useTranslation();

  return (
    <section className={`workspace-selection-context ${selectedTitle ? 'workspace-selection-context--active' : ''}`.trim()}>
      <span className="state-card__eyebrow">{t('events.graph.selectedEvent')}</span>
      <strong>{selectedTitle ?? t('events.graph.noSelectionTitle')}</strong>
      <p>{selectedTitle ? t('events.dashboard.sourceDescription') : t('events.graph.noSelectionDescription')}</p>
    </section>
  );
}

export function EventGraphPanel({ selectedTitle, isLoading, isError, viewModel, hasSelection, partialHint, onRefresh }: EventGraphPanelProps) {
  const [resetSignal, setResetSignal] = useState(0);
  const { t } = useTranslation();

  const orderedNodes = useMemo(() => (viewModel ? buildOrderedNodes(viewModel) : []), [viewModel]);

  const flowNodes = useMemo<GraphCanvasNode[]>(() => {
    const startX = 80;
    const spacingX = 320;

    return orderedNodes.map((node, index) => ({
      id: node.id,
      label: `#${node.postId}`,
      meta: `${node.date} | ${t('events.graph.comments', { value: node.commentsCount })}`,
      tone: node.isRoot ? 'root' : 'linked',
      href: `/posts/${node.postId}`,
      position: { x: startX + index * spacingX, y: 120 },
    }));
  }, [orderedNodes, t]);

  const flowEdges = useMemo<GraphCanvasEdge[]>(() => (viewModel ? buildDirectedEdges(viewModel) : []), [viewModel]);

  if (!hasSelection) {
    return (
      <section className="detail-block">
        <div className="detail-block__header"><div><span className="state-card__eyebrow">{t('events.graph.eyebrow')}</span><strong>{t('events.graph.title')}</strong></div></div>
        <EventGraphSelectionHeader selectedTitle={null} />
        <EmptyState title={t('events.graph.noSelectionTitle')} description={t('events.graph.noSelectionDescription')} />
      </section>
    );
  }

  return (
    <section className="detail-block">
      <div className="detail-block__header"><div><span className="state-card__eyebrow">{t('events.graph.eyebrow')}</span><strong>{t('events.graph.title')}</strong></div></div>
      <EventGraphSelectionHeader selectedTitle={selectedTitle} />
      <EventGraphToolbar title={selectedTitle ?? t('events.graph.selectedEvent')} nodeCount={viewModel?.nodes.length ?? 0} edgeCount={viewModel?.edges.length ?? 0} isLoading={isLoading} onRefresh={onRefresh} onResetView={() => setResetSignal((value) => value + 1)} />
      <EventGraphLegend />

      {partialHint ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label={t('events.graph.partialAria')}>
          <div><span className="dashboard-banner__eyebrow">{t('events.graph.partialEyebrow')}</span><strong>{t('events.graph.partialTitle')}</strong></div>
          <p className="dashboard-banner__text">{partialHint}</p>
        </section>
      ) : null}

      {isLoading ? <LoadingState title={t('events.graph.loadingTitle')} description={t('events.graph.loadingDescription')} /> : null}
      {!isLoading && isError ? <ErrorState title={t('events.graph.errorTitle')} description={t('events.graph.errorDescription')} /> : null}
      {!isLoading && !isError && viewModel && viewModel.nodes.length === 0 ? <EmptyState title={t('events.graph.noNodesTitle')} description={t('events.graph.noNodesDescription')} /> : null}

      {!isLoading && !isError && viewModel && viewModel.nodes.length > 0 ? (
        <div className="event-graph-panel">
          <article className="graph-panel-summary graph-panel-summary--event">
            <div className="graph-panel-summary__header">
              <div>
                <span className="state-card__eyebrow">{t('events.graph.toolbarEyebrow')}</span>
                <strong>{viewModel.event.title}</strong>
              </div>
            </div>
            <div className="graph-panel-summary__meta">
              <span>{viewModel.event.status}</span>
              <span>{t('events.graph.nodes', { value: viewModel.nodes.length })}</span>
              <span>{t('events.graph.edges', { value: viewModel.edges.length })}</span>
              <span>{t('events.graph.comments', { value: viewModel.event.commentsCount })}</span>
              <span>{t('events.graph.involvement', { value: viewModel.event.involvement })}</span>
            </div>
          </article>

          <div className="graph-panel-section">
            <div className="graph-panel-section__header">
              <div>
                <span className="state-card__eyebrow">{t('events.graph.title')}</span>
                <strong>{selectedTitle ?? t('events.graph.selectedEvent')}</strong>
              </div>
            </div>
            <SharedFlowCanvas
              ariaLabel={t('events.graph.title')}
              nodes={flowNodes}
              edges={flowEdges}
              height={300}
              resetSignal={resetSignal}
              showMiniMap={false}
              showEdgeLabels={false}
              sourcePosition={Position.Bottom}
              targetPosition={Position.Bottom}
            />
          </div>

          <div className="graph-panel-section">
            <div className="graph-panel-section__header">
              <div>
                <span className="state-card__eyebrow">{t('events.detail.relatedEyebrow')}</span>
                <strong>{t('events.detail.linkedPosts', { count: orderedNodes.length })}</strong>
              </div>
            </div>
            <div className="event-graph-panel__nodes">
              {orderedNodes.map((node) => (
                <article key={node.id} className={`event-graph-node ${node.isRoot ? 'event-graph-node--root' : ''}`.trim()}>
                  <div className="event-graph-node__meta">
                    <span>{node.isRoot ? t('events.graph.rootNode') : t('events.graph.linkedNode')}</span>
                    <span>{node.date}</span>
                  </div>
                  <strong className="event-graph-node__title">{node.isRoot ? t('events.detail.rootPostTitle', { id: node.postId }) : t('events.detail.postTitle', { id: node.postId })}</strong>
                  <p>{node.title}</p>
                  <div className="event-graph-node__stats">
                    <span>{t('events.graph.comments', { value: node.commentsCount })}</span>
                    <span>{t('events.graph.views', { value: node.views })}</span>
                    <span>{t('events.graph.involvement', { value: node.involvement })}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="graph-panel-section">
            <div className="graph-panel-section__header">
              <div>
                <span className="state-card__eyebrow">{t('events.graph.edges', { value: viewModel.edges.length })}</span>
                <strong>{t('events.graph.title')}</strong>
              </div>
            </div>
            {viewModel.edges.length === 0 ? (
              <section className="graph-panel-empty-state" aria-label={t('events.graph.noEdgesTitle')}>
                <div>
                  <span className="state-card__eyebrow">{t('events.graph.edges', { value: 0 })}</span>
                  <strong>{t('events.graph.noEdgesTitle')}</strong>
                </div>
                <p>{t('events.graph.noEdgesDescription')}</p>
              </section>
            ) : (
              <div className="event-graph-panel__edges">
                {viewModel.edges.map((edge) => {
                  const directionLabel = edge.direction === 'dst_to_src'
                    ? `${edge.targetPostId} -> ${edge.sourcePostId}`
                    : `${edge.sourcePostId} -> ${edge.targetPostId}`;

                  return (
                    <div key={edge.id} className="event-graph-edge">
                      <strong>{directionLabel}</strong>
                      <span>{edge.label}</span>
                      <div className="graph-panel-meta-list">
                        <span>{edge.status}</span>
                        <span>{t('events.graph.score', { value: edge.score })}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
