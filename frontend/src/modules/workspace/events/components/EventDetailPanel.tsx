import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import type { EventGraphPanelViewModel } from '@modules/workspace/events/mappers';

type EventDetailPanelProps = {
  event: {
    eventId: number;
    title: string;
    status: string;
    startedAt: string;
    endedAt: string;
    confidence: string;
    commentsCount: string;
    involvement: string;
    postsCount: string;
    postIds: number[];
    rootPostId: number | null;
    channels: string;
    reportStatus: string | null;
    graphReady: boolean | null;
    createdBy?: string;
  } | null;
  graph: EventGraphPanelViewModel | null;
  actionSlot?: ReactNode;
};

function EventDetailSelectionHeader({ title }: { title: string | null }) {
  const { t } = useTranslation();

  return (
    <section className={`workspace-selection-context ${title ? 'workspace-selection-context--active' : ''}`.trim()}>
      <span className="state-card__eyebrow">{t('events.detail.selectedTitle')}</span>
      <strong>{title ?? t('events.graph.noSelectionTitle')}</strong>
      <p>{title ? t('events.dashboard.sourceDescription') : t('events.detail.emptyDescription')}</p>
    </section>
  );
}

export function EventDetailPanel({ event, graph, actionSlot }: EventDetailPanelProps) {
  const { t } = useTranslation();

  if (!event) {
    return (
      <section className="detail-block">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{t('events.detail.eyebrow')}</span>
            <strong>{t('events.detail.selectedTitle')}</strong>
          </div>
        </div>
        <EventDetailSelectionHeader title={null} />
 
      </section>
    );
  }

  const relatedPosts =
    graph?.nodes.map((node) => ({
      postId: node.postId,
      label: node.title,
      isRoot: node.isRoot,
    })) ??
    event.postIds.map((postId) => ({
      postId,
      label: t('events.detail.postTitle', { id: postId }),
      isRoot: event.rootPostId === postId,
    }));

  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{t('events.detail.eyebrow')}</span>
          <strong>{event.title}</strong>
        </div>
        {actionSlot}
      </div>

      <div className="event-detail-panel">
        <EventDetailSelectionHeader title={event.title} />

        <div className="event-detail-panel__summary">
          <div><span>{t('events.detail.status')}</span><strong>{event.status}</strong></div>
          <div><span>{t('events.detail.started')}</span><strong>{event.startedAt}</strong></div>
          <div><span>{t('events.detail.ended')}</span><strong>{event.endedAt}</strong></div>
          <div><span>{t('events.detail.confidence')}</span><strong>{event.confidence}</strong></div>
          <div><span>{t('events.detail.comments')}</span><strong>{event.commentsCount}</strong></div>
          <div><span>{t('events.detail.involvement')}</span><strong>{event.involvement}</strong></div>
          <div><span>{t('events.detail.posts')}</span><strong>{event.postsCount}</strong></div>
          <div><span>{t('events.detail.channels')}</span><strong>{event.channels}</strong></div>
          {'createdBy' in event ? <div><span>{t('events.detail.createdBy')}</span><strong>{event.createdBy}</strong></div> : null}
        </div>

        <div className="event-detail-panel__report">
          <div className="event-detail-panel__report-header">
            <span className="state-card__eyebrow">{t('events.detail.reportEyebrow')}</span>
            {graph?.event.reportStatus ?? event.reportStatus ? (
              <ReportStatusBadge status={graph?.event.reportStatus ?? event.reportStatus ?? ''} />
            ) : (
              <span className="table-link table-link--muted">{t('events.detail.reportPending')}</span>
            )}
          </div>
          <p className="dashboard-panel-copy">{t('events.detail.reportDescription')}</p>
        </div>

        <div className="event-detail-panel__posts">
          <div className="event-detail-panel__posts-header">
            <span className="state-card__eyebrow">{t('events.detail.relatedEyebrow')}</span>
            <strong>{t('events.detail.linkedPosts', { count: relatedPosts.length })}</strong>
          </div>
          <div className="detail-list">
            {relatedPosts.map((post) => (
              <div key={post.postId} className="detail-list__item">
                <div>
                  <strong>{post.isRoot ? t('events.detail.rootPostTitle', { id: post.postId }) : t('events.detail.postTitle', { id: post.postId })}</strong>
                  <p>{post.label}</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to={`/posts/${post.postId}`}>{t('events.detail.openPost')}</Link>
                </div>
              </div>
            ))}
          </div>
        </div>

        {event.graphReady === false ? (
          <section className="dashboard-banner dashboard-banner--partial" aria-label={t('events.detail.graphReadyAria')}>
            <div>
              <span className="dashboard-banner__eyebrow">{t('events.detail.graphReadyEyebrow')}</span>
              <strong>{t('events.detail.graphReadyTitle')}</strong>
            </div>
            <p className="dashboard-banner__text">{t('events.detail.graphReadyDescription')}</p>
          </section>
        ) : null}
      </div>
    </section>
  );
}
