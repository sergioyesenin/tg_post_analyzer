import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

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

export function ProcessDetailPanel({ process, graph, relatedEvents, actionSlot }: ProcessDetailPanelProps) {
  if (!process) {
    return (
      <section className="detail-block detail-block--process">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">detail panel</span>
            <strong>Selected process</strong>
          </div>
        </div>
        <p className="dashboard-panel-copy">Select a process row to keep the detail panel and hierarchy graph synchronized.</p>
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
      title: `Event ${eventId}`,
      relationType: 'confirmed relation',
      postIds: [],
    }));

  return (
    <section className="detail-block detail-block--process">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">detail panel</span>
          <strong>{process.title}</strong>
        </div>
        {actionSlot}
      </div>

      <div className="process-detail-panel">
        <div className="process-detail-panel__summary">
          <div>
            <span>Status</span>
            <strong>{process.status}</strong>
          </div>
          <div>
            <span>Started</span>
            <strong>{process.startedAt}</strong>
          </div>
          <div>
            <span>Ended</span>
            <strong>{process.endedAt}</strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>{process.confidence}</strong>
          </div>
          <div>
            <span>Events</span>
            <strong>{process.eventsCount}</strong>
          </div>
          <div>
            <span>Comments</span>
            <strong>{process.commentsCount}</strong>
          </div>
          <div>
            <span>Involvement</span>
            <strong>{process.involvement}</strong>
          </div>
          <div>
            <span>Hierarchy layer</span>
            <strong>process {'->'} event {'->'} post</strong>
          </div>
        </div>

        <div className="process-detail-panel__report">
          <div className="process-detail-panel__report-header">
            <span className="state-card__eyebrow">process report</span>
            <ReportStatusBadge status={graph?.summary.reportStatus ?? process.reportStatus} />
          </div>
          <p className="dashboard-panel-copy">
            Draft report action runs async and refreshes both the processes dashboard row and selected process hierarchy snapshot.
          </p>
        </div>

        <div className="process-detail-panel__events">
          <div className="process-detail-panel__events-header">
            <span className="state-card__eyebrow">related events</span>
            <strong>{mergedRelatedEvents.length} linked events</strong>
          </div>
          <div className="detail-list">
            {mergedRelatedEvents.map((event) => (
              <div key={event.eventId} className="detail-list__item">
                <div>
                  <strong>{event.title}</strong>
                  <p>
                    {event.relationType}
                    {event.postIds.length > 0 ? ` | ${event.postIds.length} confirmed posts` : ''}
                  </p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to={`/events/${event.eventId}`}>
                    Open event
                  </Link>
                  {event.postIds[0] ? (
                    <Link className="table-link" to={`/posts/${event.postIds[0]}`}>
                      Lead post
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>

        {process.graphReady === false ? (
          <section className="dashboard-banner dashboard-banner--partial" aria-label="Hierarchy readiness notice">
            <div>
              <span className="dashboard-banner__eyebrow">hierarchy readiness</span>
              <strong>Nested events are still catching up</strong>
            </div>
            <p className="dashboard-banner__text">
              The selected process remains explorable even while the hierarchy graph is only partially enriched.
            </p>
          </section>
        ) : null}
      </div>
    </section>
  );
}
