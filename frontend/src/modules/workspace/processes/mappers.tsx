import { Link } from 'react-router-dom';

import type { UserRole } from '@shared/auth/roles';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { ProcessGraphResponse, ProcessesDashboardItemDto, ProcessesDashboardResponse } from '@shared/dashboard/contracts';
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

export type ProcessDashboardRowViewModel = {
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
  graphReady: boolean;
};

export type ProcessesDashboardViewModel = {
  generatedAt: string;
  isPartial: boolean;
  warnings: ProcessesDashboardResponse['warnings'];
  summaryCards: DashboardSummaryCard[];
  rows: ProcessDashboardRowViewModel[];
};

export const processesDashboardColumns: DashboardTableColumn[] = [
  { id: 'process', label: 'Process' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'events_count', label: 'Events', align: 'right' },
  { id: 'comments_count', label: 'Comments', align: 'right' },
  { id: 'involvement', label: 'Involvement', align: 'right' },
  { id: 'report_status', label: 'Report status' },
  { id: 'actions', label: 'Actions' },
];

export function mapProcessesDashboardToViewModel(response: ProcessesDashboardResponse): ProcessesDashboardViewModel {
  return {
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
    summaryCards: [
      { id: 'processes_count', label: 'Processes', value: String(response.summary.processes_count) },
      { id: 'total_events', label: 'Linked events', value: String(response.summary.total_events) },
      { id: 'comments', label: 'Comments', value: String(response.summary.total_comments) },
      { id: 'avg_involvement', label: 'Avg involvement', value: formatRatio(response.summary.avg_involvement) },
      { id: 'draft_reports', label: 'Draft reports', value: String(response.summary.draft_reports) },
      { id: 'failed_reports', label: 'Failed reports', value: String(response.summary.failed_reports) },
    ],
    rows: response.items.map((item) => mapProcessItemToRow(item)),
  };
}

function mapProcessItemToRow(item: ProcessesDashboardItemDto): ProcessDashboardRowViewModel {
  return {
    processId: item.process_id,
    title: item.title ?? `Process ${item.process_id}`,
    status: item.status,
    startedAt: formatDateTime(item.started_at),
    endedAt: formatDateTime(item.ended_at),
    confidence: formatConfidence(item.confidence),
    commentsCount: String(item.comments_count),
    involvement: formatRatio(item.involvement),
    eventsCount: String(item.events_count),
    eventIds: item.event_ids,
    reportStatus: item.report_status,
    graphReady: item.graph_ready,
  };
}

export function mapProcessesRowsToTableRows(
  rows: ProcessDashboardRowViewModel[],
  selectedProcessId: number | null,
  onSelect: (processId: number) => void,
  role: UserRole | null,
): DashboardTableRow[] {
  return rows.map((row) => {
    const isSelected = row.processId === selectedProcessId;

    return {
      id: String(row.processId),
      isSelected,
      cells: {
        process: (
          <div className="dashboard-table-shell__cell-stack">
            <strong>{row.title}</strong>
            <span>
              {row.status} • confidence {row.confidence}
            </span>
          </div>
        ),
        timeline: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{row.startedAt}</span>
            <span>{row.endedAt === 'n/a' ? 'process still active' : `ended ${row.endedAt}`}</span>
          </div>
        ),
        events_count: row.eventsCount,
        comments_count: row.commentsCount,
        involvement: row.involvement,
        report_status: <ReportStatusBadge status={row.reportStatus} />,
        actions: (
          <div className="dashboard-table-shell__actions">
            <button
              type="button"
              className={`dashboard-button ${isSelected ? 'dashboard-button--ghost' : ''}`.trim()}
              onClick={() => onSelect(row.processId)}
            >
              {isSelected ? 'Selected' : 'Inspect'}
            </button>
            {row.eventIds[0] ? (
              <Link className="table-link" to={`/events/${row.eventIds[0]}`}>
                Lead event
              </Link>
            ) : null}
            {role === 'viewer' ? <span className="table-link table-link--muted">Read only</span> : null}
          </div>
        ),
      },
    };
  });
}

export type ProcessGraphPanelViewModel = {
  summary: {
    processId: number;
    title: string;
    status: string;
    reportStatus: string;
    eventsCount: string;
    postsCount: string;
    commentsCount: string;
    involvement: string;
  };
  events: Array<{
    eventId: number;
    title: string;
    status: string;
    relationType: string;
    direction: string;
    score: string;
    startedAt: string;
    postIds: number[];
  }>;
  nodes: Array<{
    id: string;
    postId: number;
    title: string;
    date: string;
    channel: string;
    eventIds: number[];
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

export function mapProcessGraphToViewModel(response: ProcessGraphResponse): ProcessGraphPanelViewModel {
  const eventIdsByPostId = new Map<number, number[]>();

  Object.entries(response.mapping.event_to_post_ids).forEach(([eventId, postIds]) => {
    postIds.forEach((postId) => {
      const existing = eventIdsByPostId.get(postId) ?? [];
      eventIdsByPostId.set(postId, [...existing, Number(eventId)]);
    });
  });

  return {
    summary: {
      processId: response.summary.process_id,
      title: response.summary.title ?? `Process ${response.summary.process_id}`,
      status: response.summary.status,
      reportStatus: response.summary.report_status,
      eventsCount: String(response.summary.events_count),
      postsCount: String(response.summary.posts_count),
      commentsCount: String(response.summary.comments_count),
      involvement: formatRatio(response.summary.involvement),
    },
    events: response.events.map((event) => ({
      eventId: event.event_id,
      title: event.title ?? `Event ${event.event_id}`,
      status: event.status,
      relationType: event.relation_type,
      direction: event.direction,
      score: event.score === null ? 'n/a' : event.score.toFixed(2),
      startedAt: formatDateTime(event.started_at),
      postIds: event.post_ids,
    })),
    nodes: response.nodes.map((node) => ({
      id: String(node.post_id),
      postId: node.post_id,
      title: node.text_preview ?? `Post #${node.post_id}`,
      date: formatDateTime(node.date),
      channel: node.channel_username ?? `#${node.channel_id}`,
      eventIds: eventIdsByPostId.get(node.post_id) ?? [],
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
