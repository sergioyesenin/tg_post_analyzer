import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

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

export function EventDetailPanel({ event, graph, actionSlot }: EventDetailPanelProps) {
  if (!event) {
    return (
      <section className="detail-block">
        <div className="detail-block__header">
          <div>
            <span className="state-card__eyebrow">detail panel</span>
            <strong>Selected event</strong>
          </div>
        </div>
        <p className="dashboard-panel-copy">Select an event row to keep the detail panel and graph synchronized.</p>
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
      label: `Post #${postId}`,
      isRoot: event.rootPostId === postId,
    }));

  return (
    <section className="detail-block">
      <div className="detail-block__header">
        <div>
          <span className="state-card__eyebrow">detail panel</span>
          <strong>{event.title}</strong>
        </div>
        {actionSlot}
      </div>

      <div className="event-detail-panel">
        <div className="event-detail-panel__summary">
          <div>
            <span>Status</span>
            <strong>{event.status}</strong>
          </div>
          <div>
            <span>Started</span>
            <strong>{event.startedAt}</strong>
          </div>
          <div>
            <span>Ended</span>
            <strong>{event.endedAt}</strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>{event.confidence}</strong>
          </div>
          <div>
            <span>Comments</span>
            <strong>{event.commentsCount}</strong>
          </div>
          <div>
            <span>Involvement</span>
            <strong>{event.involvement}</strong>
          </div>
          <div>
            <span>Posts</span>
            <strong>{event.postsCount}</strong>
          </div>
          <div>
            <span>Channels</span>
            <strong>{event.channels}</strong>
          </div>
          {'createdBy' in event ? (
            <div>
              <span>Created by</span>
              <strong>{event.createdBy}</strong>
            </div>
          ) : null}
        </div>

        <div className="event-detail-panel__report">
          <div className="event-detail-panel__report-header">
            <span className="state-card__eyebrow">event report</span>
            {graph?.event.reportStatus ?? event.reportStatus ? (
              <ReportStatusBadge status={graph?.event.reportStatus ?? event.reportStatus ?? ''} />
            ) : (
              <span className="table-link table-link--muted">Report status becomes available with graph context</span>
            )}
          </div>
          <p className="dashboard-panel-copy">
            Draft report action runs async and refreshes both the events dashboard row and selected event graph snapshot.
          </p>
        </div>

        <div className="event-detail-panel__posts">
          <div className="event-detail-panel__posts-header">
            <span className="state-card__eyebrow">related posts</span>
            <strong>{relatedPosts.length} linked posts</strong>
          </div>
          <div className="detail-list">
            {relatedPosts.map((post) => (
              <div key={post.postId} className="detail-list__item">
                <div>
                  <strong>{post.isRoot ? `Root post #${post.postId}` : `Post #${post.postId}`}</strong>
                  <p>{post.label}</p>
                </div>
                <div className="detail-list__actions">
                  <Link className="table-link" to={`/posts/${post.postId}`}>
                    Open post
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>

        {event.graphReady === false ? (
          <section className="dashboard-banner dashboard-banner--partial" aria-label="Graph readiness notice">
            <div>
              <span className="dashboard-banner__eyebrow">graph readiness</span>
              <strong>Graph enrichment is still catching up</strong>
            </div>
            <p className="dashboard-banner__text">
              Selection stays stable and related posts remain explorable even while graph enrichment is incomplete.
            </p>
          </section>
        ) : null}
      </div>
    </section>
  );
}
