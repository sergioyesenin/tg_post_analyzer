import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { SharedFlowCanvas, type GraphCanvasEdge, type GraphCanvasNode } from '@shared/ui/graph/SharedFlowCanvas';
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
  const { t } = useTranslation();
  const [resetSignal, setResetSignal] = useState(0);

  const orderedEvents = useMemo(() => {
    if (!viewModel) {
      return [];
    }

    return [...viewModel.events].sort((left, right) => left.startedAt.localeCompare(right.startedAt));
  }, [viewModel]);

  const flowNodes = useMemo<GraphCanvasNode[]>(() => {
    const eventSpacing = 320;
    const eventStartX = 80;

    return orderedEvents.map((event, index) => ({
      id: `event-${event.eventId}`,
      label: event.title,
      meta: `${event.status} | ${event.startedAt}`,
      tone: 'event' as const,
      href: `/events/${event.eventId}`,
      position: { x: eventStartX + index * eventSpacing, y: 120 },
    }));
  }, [orderedEvents]);

  const flowEdges = useMemo<GraphCanvasEdge[]>(() => {
    if (orderedEvents.length < 2) {
      return [];
    }

    return orderedEvents.slice(1).map((event, index) => {
      const previousEvent = orderedEvents[index];
      const isReverse = event.direction === 'dst_to_src';

      return {
        id: `process-event-sequence-${previousEvent.eventId}-${event.eventId}`,
        source: isReverse ? `event-${event.eventId}` : `event-${previousEvent.eventId}`,
        target: isReverse ? `event-${previousEvent.eventId}` : `event-${event.eventId}`,
        label: event.relationType,
      };
    });
  }, [orderedEvents]);

  if (!hasSelection) {
    return (
      <section className="detail-block detail-block--process">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{t('processes.graph.eyebrow')}</span>
            <strong>{t('processes.graph.title')}</strong>
          </div>
        </div>
        <EmptyState title={t('processes.graph.noSelectionTitle')} description={t('processes.graph.noSelectionDescription')} />
      </section>
    );
  }

  return (
    <section className="detail-block detail-block--process">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{t('processes.graph.eyebrow')}</span>
          <strong>{t('processes.graph.title')}</strong>
        </div>
      </div>

      <ProcessGraphToolbar
        title={selectedTitle ?? t('processes.graph.selectedProcess')}
        eventCount={viewModel?.events.length ?? 0}
        postCount={viewModel?.nodes.length ?? 0}
        isLoading={isLoading}
        onRefresh={onRefresh}
        onResetView={() => setResetSignal((value) => value + 1)}
      />

      <ProcessGraphLegend />

      {partialHint ? (
        <section className="dashboard-banner dashboard-banner--partial" aria-label={t('processes.graph.partialAria')}>
          <div>
            <span className="dashboard-banner__eyebrow">{t('processes.graph.partialEyebrow')}</span>
            <strong>{t('processes.graph.partialTitle')}</strong>
          </div>
          <p className="dashboard-banner__text">{partialHint}</p>
        </section>
      ) : null}

      {isLoading ? <LoadingState title={t('processes.graph.loadingTitle')} description={t('processes.graph.loadingDescription')} /> : null}

      {!isLoading && isError ? <ErrorState title={t('processes.graph.errorTitle')} description={t('processes.graph.errorDescription')} /> : null}

      {!isLoading && !isError && viewModel && viewModel.events.length === 0 && viewModel.nodes.length === 0 ? (
        <EmptyState title={t('processes.graph.noHierarchyTitle')} description={t('processes.graph.noHierarchyDescription')} />
      ) : null}

      {!isLoading && !isError && viewModel && (viewModel.events.length > 0 || viewModel.nodes.length > 0) ? (
        <div className="process-graph-panel">
          <article className="graph-panel-summary graph-panel-summary--process">
            <div className="graph-panel-summary__header">
              <div>
                <span className="state-card__eyebrow">{t('processes.graph.processLayerEyebrow')}</span>
                <strong>{viewModel.summary.title}</strong>
              </div>
            </div>
            <div className="graph-panel-summary__meta">
              <span>{viewModel.summary.status}</span>
              <span>{t('processes.graph.eventsCount', { value: viewModel.summary.eventsCount })}</span>
              <span>{t('processes.graph.postsCount', { value: viewModel.summary.postsCount })}</span>
              <span>{t('processes.graph.commentsCount', { value: viewModel.summary.commentsCount })}</span>
              <span>{t('processes.detail.involvement')}: {viewModel.summary.involvement}</span>
            </div>
          </article>

          {orderedEvents.length > 0 ? (
            <div className="graph-panel-section">
              <div className="graph-panel-section__header">
                <div>
                  <span className="state-card__eyebrow">{t('processes.graph.title')}</span>
                  <strong>{selectedTitle ?? t('processes.graph.selectedProcess')}</strong>
                </div>
              </div>
              <SharedFlowCanvas
                ariaLabel={t('processes.graph.title')}
                nodes={flowNodes}
                edges={flowEdges}
                height={300}
                resetSignal={resetSignal}
                showMiniMap={false}
                showEdgeLabels
              />
            </div>
          ) : null}

          <div className="graph-panel-section">
            <div className="graph-panel-section__header">
              <div>
                <span className="state-card__eyebrow">{t('processes.detail.relatedEyebrow')}</span>
                <strong>{t('processes.detail.linkedEvents', { count: viewModel.events.length })}</strong>
              </div>
            </div>
            <div className="process-graph-panel__events">
              {viewModel.events.map((event) => (
                <article key={event.eventId} className="process-graph-event-card">
                  <div className="process-graph-event-card__header">
                    <div>
                      <span className="state-card__eyebrow">{t('processes.graph.nestedEventEyebrow')}</span>
                      <strong>{event.title}</strong>
                    </div>
                    <Link className="table-link" to={`/events/${event.eventId}`}>{t('processes.graph.openEvent')}</Link>
                  </div>
                  <div className="process-graph-event-card__meta">
                    <span>{event.status}</span>
                    <span>{event.startedAt}</span>
                    <span>{event.relationType}</span>
                    <span>{t('processes.graph.score', { value: event.score })}</span>
                  </div>
                  <div className="process-graph-event-card__posts">
                    {event.postIds.length === 0 ? (
                      <span className="table-link table-link--muted">{t('processes.graph.noConfirmedPosts')}</span>
                    ) : (
                      event.postIds.map((postId) => (
                        <Link key={postId} className="table-link" to={`/posts/${postId}`}>
                          {t('processes.graph.postTitle', { id: postId })}
                        </Link>
                      ))
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="graph-panel-section">
            <div className="graph-panel-section__header">
              <div>
                <span className="state-card__eyebrow">{t('processes.graph.eyebrow')}</span>
                <strong>{t('processes.graph.title')}</strong>
              </div>
            </div>
            {viewModel.edges.length === 0 ? (
              <section className="graph-panel-empty-state" aria-label={t('processes.graph.noEdgesTitle')}>
                <div>
                  <span className="state-card__eyebrow">{t('processes.graph.eyebrow')}</span>
                  <strong>{t('processes.graph.noEdgesTitle')}</strong>
                </div>
                <p>{t('processes.graph.noEdgesDescription')}</p>
              </section>
            ) : (
              <div className="process-graph-panel__edges">
                {viewModel.edges.map((edge) => (
                  <div key={edge.id} className="process-graph-edge">
                    <strong>
                      {edge.sourcePostId} {'->'} {edge.targetPostId}
                    </strong>
                    <span>{edge.label}</span>
                    <div className="graph-panel-meta-list">
                      <span>{edge.status}</span>
                      <span>{t('processes.graph.score', { value: edge.score })}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

