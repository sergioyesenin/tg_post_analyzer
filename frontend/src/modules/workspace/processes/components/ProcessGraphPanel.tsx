import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

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
          <article className="process-graph-panel__summary">
            <span className="state-card__eyebrow">{t('processes.graph.processLayerEyebrow')}</span>
            <strong>{viewModel.summary.title}</strong>
            <div className="process-graph-panel__summary-meta">
              <span>{viewModel.summary.status}</span>
              <span>{t('processes.graph.eventsCount', { value: viewModel.summary.eventsCount })}</span>
              <span>{t('processes.graph.postsCount', { value: viewModel.summary.postsCount })}</span>
              <span>{t('processes.graph.commentsCount', { value: viewModel.summary.commentsCount })}</span>
            </div>
          </article>

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
                  <span>{event.direction}</span>
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

          {viewModel.edges.length === 0 ? (
            <EmptyState title={t('processes.graph.noEdgesTitle')} description={t('processes.graph.noEdgesDescription')} />
          ) : (
            <div className="process-graph-panel__edges">
              {viewModel.edges.map((edge) => (
                <div key={edge.id} className="process-graph-edge">
                  <strong>
                    {edge.sourcePostId} {'->'} {edge.targetPostId}
                  </strong>
                  <span>
                    {edge.label} | {edge.status} | {t('processes.graph.score', { value: edge.score })}
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
