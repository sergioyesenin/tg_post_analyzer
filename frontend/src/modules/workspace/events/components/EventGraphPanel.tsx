import { useTranslation } from 'react-i18next';

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

export function EventGraphPanel({ selectedTitle, isLoading, isError, viewModel, hasSelection, partialHint, onRefresh }: EventGraphPanelProps) {
  const { t } = useTranslation();

  if (!hasSelection) {
    return (
      <section className="detail-block">
        <div className="detail-block__header"><div><span className="state-card__eyebrow">{t('events.graph.eyebrow')}</span><strong>{t('events.graph.title')}</strong></div></div>
        <EmptyState title={t('events.graph.noSelectionTitle')} description={t('events.graph.noSelectionDescription')} />
      </section>
    );
  }

  return (
    <section className="detail-block">
      <div className="detail-block__header"><div><span className="state-card__eyebrow">{t('events.graph.eyebrow')}</span><strong>{t('events.graph.title')}</strong></div></div>
      <EventGraphToolbar title={selectedTitle ?? t('events.graph.selectedEvent')} nodeCount={viewModel?.nodes.length ?? 0} edgeCount={viewModel?.edges.length ?? 0} isLoading={isLoading} onRefresh={onRefresh} />
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
          <div className="event-graph-panel__nodes">
            {viewModel.nodes.map((node) => (
              <article key={node.id} className={`event-graph-node ${node.isRoot ? 'event-graph-node--root' : ''}`.trim()}>
                <div className="event-graph-node__meta">
                  <strong>{node.isRoot ? t('events.graph.rootNode') : t('events.graph.linkedNode')} #{node.postId}</strong>
                  <span>{node.date}</span>
                </div>
                <p>{node.title}</p>
                <div className="event-graph-node__stats">
                  <span>{t('events.graph.comments', { value: node.commentsCount })}</span>
                  <span>{t('events.graph.views', { value: node.views })}</span>
                  <span>{t('events.graph.involvement', { value: node.involvement })}</span>
                </div>
              </article>
            ))}
          </div>

          {viewModel.edges.length === 0 ? (
            <EmptyState title={t('events.graph.noEdgesTitle')} description={t('events.graph.noEdgesDescription')} />
          ) : (
            <div className="event-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="event-graph-edge">
                  <strong>{edge.sourcePostId} {'->'} {edge.targetPostId}</strong>
                  <span>{edge.label} | {edge.status} | {t('events.graph.score', { value: edge.score })}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
