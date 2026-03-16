import { Link } from 'react-router-dom';

import { i18n } from '@shared/i18n/i18n';
import type { UserRole } from '@shared/auth/roles';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { EventGraphResponse, EventsDashboardItemDto, EventsDashboardResponse } from '@shared/dashboard/contracts';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import { formatConfidencePercent, formatNullableRatio, formatUtcDateTime } from '@shared/utils/formatters';

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
  { id: 'event', label: i18n.t('events.table.event') },
  { id: 'status', label: i18n.t('events.table.status') },
  { id: 'started_at', label: i18n.t('events.table.startedAt') },
  { id: 'posts_count', label: i18n.t('events.table.posts'), align: 'right' },
  { id: 'comments_count', label: i18n.t('events.table.comments'), align: 'right' },
  { id: 'involvement', label: i18n.t('events.table.involvement'), align: 'right' },
  { id: 'report_status', label: i18n.t('events.table.reportStatus') },
  { id: 'actions', label: i18n.t('events.table.actions') },
];

export function mapEventsDashboardToViewModel(response: EventsDashboardResponse): EventsDashboardViewModel {
  return {
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
    summaryCards: [
      { id: 'events_count', label: i18n.t('events.table.events'), value: String(response.summary.events_count) },
      { id: 'linked_posts', label: i18n.t('events.table.linkedPosts'), value: String(response.summary.total_linked_posts) },
      { id: 'comments', label: i18n.t('events.table.comments'), value: String(response.summary.total_comments) },
      { id: 'avg_involvement', label: i18n.t('events.table.avgInvolvement'), value: formatNullableRatio(response.summary.avg_involvement) },
      { id: 'draft_reports', label: i18n.t('events.table.draftReports'), value: String(response.summary.draft_reports) },
      { id: 'ready_reports', label: i18n.t('events.table.readyReports'), value: String(response.summary.ready_reports) },
    ],
    rows: response.items.map((item) => mapEventItemToRow(item)),
  };
}

function mapEventItemToRow(item: EventsDashboardItemDto): EventDashboardRowViewModel {
  return {
    eventId: item.event_id,
    title: item.title ?? i18n.t('events.rows.eventFallback', { id: item.event_id }),
    status: item.status,
    startedAt: formatUtcDateTime(item.started_at),
    endedAt: formatUtcDateTime(item.ended_at),
    confidence: formatConfidencePercent(item.confidence),
    commentsCount: String(item.comments_count),
    involvement: formatNullableRatio(item.involvement),
    postsCount: String(item.posts_count),
    postIds: item.post_ids,
    rootPostId: item.root_post_id,
    channels: item.channels.map((channel) => channel.channel_username ?? i18n.t('events.rows.channelFallback', { id: channel.channel_id })).join(', ') || i18n.t('common.na'),
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
            <span>{i18n.t('events.rows.confidence', { value: row.confidence })}</span>
          </div>
        ),
        started_at: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{row.startedAt}</span>
            <span>{row.endedAt === i18n.t('common.na') ? i18n.t('events.rows.openEvent') : i18n.t('events.rows.endedAt', { value: row.endedAt })}</span>
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
              {isSelected ? i18n.t('events.rows.selected') : i18n.t('events.rows.inspect')}
            </button>
            <Link className="table-link" to={`/events/${row.eventId}`}>
              {i18n.t('events.rows.eventDetail')}
            </Link>
            {row.rootPostId ? (
              <Link className="table-link" to={`/posts/${row.rootPostId}`}>
                {i18n.t('events.rows.rootPost')}
              </Link>
            ) : null}
            {role === 'viewer' ? <span className="table-link table-link--muted">{i18n.t('states.readOnly')}</span> : null}
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
    direction: string;
  }>;
};

export function mapEventGraphToViewModel(response: EventGraphResponse): EventGraphPanelViewModel {
  return {
    event: {
      title: response.event.title ?? i18n.t('events.rows.eventFallback', { id: response.event.event_id }),
      status: response.event.status,
      reportStatus: response.event.report_status,
      postsCount: String(response.event.posts_count),
      commentsCount: String(response.event.comments_count),
      involvement: formatNullableRatio(response.event.involvement),
    },
    nodes: response.nodes.map((node) => ({
      id: String(node.post_id),
      postId: node.post_id,
      title: node.text_preview ?? i18n.t('reports.rows.postLabel', { id: node.post_id }),
      date: formatUtcDateTime(node.date),
      commentsCount: String(node.comments_count),
      views: node.views === null ? i18n.t('common.na') : String(node.views),
      involvement: formatNullableRatio(node.involvement),
      isRoot: node.is_root,
    })),
    edges: response.edges.map((edge) => ({
      id: String(edge.link_id),
      sourcePostId: edge.src_post_id,
      targetPostId: edge.dst_post_id,
      label: edge.link_type,
      status: edge.status,
      score: edge.score === null ? i18n.t('common.na') : edge.score.toFixed(2),
      direction: edge.direction,
    })),
  };
}
