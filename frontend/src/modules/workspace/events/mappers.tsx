import { Link } from 'react-router-dom';

import type { UserRole } from '@shared/auth/roles';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { EventGraphResponse, EventsDashboardItemDto, EventsDashboardResponse } from '@shared/dashboard/contracts';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';

function formatDateTime(value: string | null) {
  if (!value) {
    return 'n/a';
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatRatio(value: number | null) {
  if (value === null) {
    return 'n/a';
  }

  return value.toFixed(2);
}

function formatConfidence(value: number | null) {
  if (value === null) {
    return 'n/a';
  }

  return `${Math.round(value * 100)}%`;
}

type EventDashboardRowViewModel = {
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
  reportStatus: string;
  graphReady: boolean;
};

export type EventsDashboardViewModel = {
  generatedAt: string;
  isPartial: boolean;
  warnings: EventsDashboardResponse['warnings'];
  summaryCards: DashboardSummaryCard[];
  rows: EventDashboardRowViewModel[];
};

export const eventsDashboardColumns: DashboardTableColumn[] = [
  { id: 'event', label: 'Event' },
  { id: 'status', label: 'Status' },
  { id: 'started_at', label: 'Started at' },
  { id: 'posts_count', label: 'Posts', align: 'right' },
  { id: 'comments_count', label: 'Comments', align: 'right' },
  { id: 'involvement', label: 'Involvement', align: 'right' },
  { id: 'report_status', label: 'Report status' },
  { id: 'actions', label: 'Actions' },
];

export function mapEventsDashboardToViewModel(response: EventsDashboardResponse): EventsDashboardViewModel {
  return {
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
    summaryCards: [
      { id: 'events_count', label: 'Events', value: String(response.summary.events_count) },
      { id: 'linked_posts', label: 'Linked posts', value: String(response.summary.total_linked_posts) },
      { id: 'comments', label: 'Comments', value: String(response.summary.total_comments) },
      { id: 'avg_involvement', label: 'Avg involvement', value: formatRatio(response.summary.avg_involvement) },
      { id: 'draft_reports', label: 'Draft reports', value: String(response.summary.draft_reports) },
      { id: 'ready_reports', label: 'Ready reports', value: String(response.summary.ready_reports) },
    ],
    rows: response.items.map((item) => mapEventItemToRow(item)),
  };
}

function mapEventItemToRow(item: EventsDashboardItemDto): EventDashboardRowViewModel {
  return {
    eventId: item.event_id,
    title: item.title ?? `Event ${item.event_id}`,
    status: item.status,
    startedAt: formatDateTime(item.started_at),
    endedAt: formatDateTime(item.ended_at),
    confidence: formatConfidence(item.confidence),
    commentsCount: String(item.comments_count),
    involvement: formatRatio(item.involvement),
    postsCount: String(item.posts_count),
    postIds: item.post_ids,
    rootPostId: item.root_post_id,
    channels: item.channels.map((channel) => channel.channel_username ?? `#${channel.channel_id}`).join(', ') || 'n/a',
    reportStatus: item.report_status,
    graphReady: item.graph_ready,
  };
}

export function mapEventsRowsToTableRows(
  rows: EventDashboardRowViewModel[],
  selectedEventId: number | null,
  onSelect: (eventId: number) => void,
  role: UserRole | null,
): DashboardTableRow[] {
  return rows.map((row) => {
    const isSelected = row.eventId === selectedEventId;

    return {
      id: String(row.eventId),
      isSelected,
      cells: {
        event: (
          <div className="dashboard-table-shell__cell-stack">
            <strong>{row.title}</strong>
            <span>{row.channels}</span>
          </div>
        ),
        status: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{row.status}</span>
            <span>confidence {row.confidence}</span>
          </div>
        ),
        started_at: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{row.startedAt}</span>
            <span>{row.endedAt === 'n/a' ? 'open event' : `ended ${row.endedAt}`}</span>
          </div>
        ),
        posts_count: row.postsCount,
        comments_count: row.commentsCount,
        involvement: row.involvement,
        report_status: <ReportStatusBadge status={row.reportStatus} />,
        actions: (
          <div className="dashboard-table-shell__actions">
            <button
              type="button"
              className={`dashboard-button ${isSelected ? 'dashboard-button--ghost' : ''}`.trim()}
              onClick={() => onSelect(row.eventId)}
            >
              {isSelected ? 'Selected' : 'Inspect'}
            </button>
            {row.rootPostId ? (
              <Link className="table-link" to={`/posts/${row.rootPostId}`}>
                Root post
              </Link>
            ) : null}
            {role === 'viewer' ? <span className="table-link table-link--muted">Read only</span> : null}
          </div>
        ),
      },
    };
  });
}

export type EventGraphPanelViewModel = {
  event: {
    title: string;
    status: string;
    reportStatus: string;
    postsCount: string;
    commentsCount: string;
    involvement: string;
  };
  nodes: Array<{
    id: string;
    postId: number;
    title: string;
    date: string;
    commentsCount: string;
    views: string;
    involvement: string;
    isRoot: boolean;
  }>;
  edges: Array<{
    id: string;
    sourcePostId: number;
    targetPostId: number;
    label: string;
    status: string;
    score: string;
  }>;
};

export function mapEventGraphToViewModel(response: EventGraphResponse): EventGraphPanelViewModel {
  return {
    event: {
      title: response.event.title ?? `Event ${response.event.event_id}`,
      status: response.event.status,
      reportStatus: response.event.report_status,
      postsCount: String(response.event.posts_count),
      commentsCount: String(response.event.comments_count),
      involvement: formatRatio(response.event.involvement),
    },
    nodes: response.nodes.map((node) => ({
      id: String(node.post_id),
      postId: node.post_id,
      title: node.text_preview ?? `Post #${node.post_id}`,
      date: formatDateTime(node.date),
      commentsCount: String(node.comments_count),
      views: node.views === null ? 'n/a' : String(node.views),
      involvement: formatRatio(node.involvement),
      isRoot: node.is_root,
    })),
    edges: response.edges.map((edge) => ({
      id: String(edge.link_id),
      sourcePostId: edge.src_post_id,
      targetPostId: edge.dst_post_id,
      label: edge.link_type,
      status: edge.status,
      score: edge.score === null ? 'n/a' : edge.score.toFixed(2),
    })),
  };
}
