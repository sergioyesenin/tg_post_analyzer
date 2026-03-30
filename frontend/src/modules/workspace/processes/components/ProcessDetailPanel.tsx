import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import type { ProcessGraphPanelViewModel } from '@modules/workspace/processes/mappers';

export type ProcessDetailPanelProcess = {
  processId: number;
  title: string;
  status: string;
  startedAt: string;
  endedAt: string;
  confidence: string;
  commentsCount: string;
  involvement: string;
  eventsCount: string;
  eventIds: number[];
  reportStatus: string;
  reportSummary?: string | null;
  reportTopics?: string[];
  graphReady: boolean | null;
};

export type ProcessDetailPanelRelatedEvent = {
  eventId: number;
  title: string;
  relationType: string;
  postIds: number[];
};

type ProcessDetailPanelProps = {
  process: ProcessDetailPanelProcess | null;
  graph: ProcessGraphPanelViewModel | null;
  relatedEvents?: ProcessDetailPanelRelatedEvent[];
  actionSlot?: ReactNode;
};

function ProcessDetailSelectionHeader({ title }: { title: string | null }) {
  const { t } = useTranslation();

  return (
    <section className={`workspace-selection-context ${title ? 'workspace-selection-context--active' : ''}`.trim()}>
      <span className="state-card__eyebrow">{t('processes.detail.selectedTitle')}</span>
      <strong>{title ?? t('processes.graph.noSelectionTitle')}</strong>
      <p>{title ? t('processes.dashboard.sourceDescription') : t('processes.detail.emptyDescription')}</p>
    </section>
  );
}

export function ProcessDetailPanel({ process, graph, relatedEvents, actionSlot }: ProcessDetailPanelProps) {
  const { t } = useTranslation();

  if (!process) {
    return (
      <section className="detail-block detail-block--process">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">{t('processes.detail.eyebrow')}</span>
            <strong>{t('processes.detail.selectedTitle')}</strong>
          </div>
        </div>
        <ProcessDetailSelectionHeader title={null} />
      </section>
    );
  }

  const mergedRelatedEvents =
    relatedEvents ??
    graph?.events.map((event) => ({
      eventId: event.eventId,
      title: event.title,
      relationType: event.relationType,
      postIds: event.postIds,
    })) ??
    process.eventIds.map((eventId) => ({
      eventId,
      title: t('processes.detail.fallbackEvent', { id: eventId }),
      relationType: t('processes.detail.fallbackRelation'),
      postIds: [],
    }));

  return (
    <section className="detail-block detail-block--process">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">{t('processes.detail.eyebrow')}</span>
          <strong>{process.title}</strong>
        </div>
        {actionSlot}
      </div>

      <div className="process-detail-panel">
        <ProcessDetailSelectionHeader title={process.title} />

        <div className="process-detail-panel__summary">
          <div><span>{t('processes.detail.status')}</span><strong>{process.status}</strong></div>
          <div><span>{t('processes.detail.started')}</span><strong>{process.startedAt}</strong></div>
          <div><span>{t('processes.detail.ended')}</span><strong>{process.endedAt}</strong></div>
          <div><span>{t('processes.detail.confidence')}</span><strong>{process.confidence}</strong></div>
          <div><span>{t('processes.detail.events')}</span><strong>{process.eventsCount}</strong></div>
          <div><span>{t('processes.detail.comments')}</span><strong>{process.commentsCount}</strong></div>
          <div><span>{t('processes.detail.involvement')}</span><strong>{process.involvement}</strong></div>
          <div><span>{t('processes.detail.hierarchyLayer')}</span><strong>{t('processes.detail.hierarchyValue')}</strong></div>
        </div>

        <div className="process-detail-panel__report">
          <div className="process-detail-panel__report-header">
            <span className="state-card__eyebrow">{t('processes.detail.reportEyebrow')}</span>
            <ReportStatusBadge status={graph?.summary.reportStatus ?? process.reportStatus} />
          </div>
          <p className="dashboard-panel-copy">{process.reportSummary ?? t('processes.detail.reportDescription')}</p>
          {(process.reportTopics ?? []).length > 0 ? (
            <p className="dashboard-panel-copy">{t('processes.detail.reportTopicsInline', { defaultValue: 'Темы: {{topics}}', topics: (process.reportTopics ?? []).join(', ') })}</p>
          ) : null}
        </div>

        <div className="process-detail-panel__events">
          <div className="process-detail-panel__events-header">
            <span className="state-card__eyebrow">{t('processes.detail.relatedEyebrow')}</span>
            <strong>{t('processes.detail.linkedEvents', { count: mergedRelatedEvents.length })}</strong>
          </div>
          <div className="detail-list">
            {mergedRelatedEvents.map((event) => (
              <div key={event.eventId} className="detail-list__item">
                <div>
                  <strong>{event.title}</strong>
                  <p>
                    {event.relationType}
                    {event.postIds.length > 0 ? ` | ${t('processes.detail.confirmedPosts', { count: event.postIds.length })}` : ''}
                  </p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to={`/events/${event.eventId}`}>{t('processes.detail.openEvent')}</Link>
                  {event.postIds[0] ? (
                    <Link className="table-link" to={`/posts/${event.postIds[0]}`}>{t('processes.detail.leadPost')}</Link>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>

        {process.graphReady === false ? (
          <section className="dashboard-banner dashboard-banner--partial" aria-label={t('processes.detail.readinessAria')}>
            <div>
              <span className="dashboard-banner__eyebrow">{t('processes.detail.readinessEyebrow')}</span>
              <strong>{t('processes.detail.readinessTitle')}</strong>
            </div>
            <p className="dashboard-banner__text">{t('processes.detail.readinessDescription')}</p>
          </section>
        ) : null}
      </div>
    </section>
  );
}
