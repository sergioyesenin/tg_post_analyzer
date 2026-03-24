import { Link } from 'react-router-dom';

import { i18n } from '@shared/i18n/i18n';
import type { UserRole } from '@shared/auth/roles';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import type { ProcessGraphResponse, ProcessesDashboardItemDto, ProcessesDashboardResponse } from '@shared/dashboard/contracts';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import { formatConfidencePercent, formatNullableRatio, formatUtcDateTime } from '@shared/utils/formatters';

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

export const processesDashboardColumns: DataTableColumn[] = [
  { id: 'process', label: i18n.t('processes.table.process') },
  { id: 'timeline', label: i18n.t('processes.table.timeline') },
  { id: 'events_count', label: i18n.t('processes.table.events'), align: 'right' },
  { id: 'comments_count', label: i18n.t('processes.table.comments'), align: 'right' },
  { id: 'involvement', label: i18n.t('processes.table.involvement'), align: 'right' },
  { id: 'report_status', label: i18n.t('processes.table.reportStatus') },
  { id: 'actions', label: i18n.t('processes.table.actions') },
];

export function mapProcessesDashboardToViewModel(response: ProcessesDashboardResponse): ProcessesDashboardViewModel {
  return {
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
    summaryCards: [
      { id: 'processes_count', label: i18n.t('processes.table.processes'), value: String(response.summary.processes_count) },
      { id: 'total_events', label: i18n.t('processes.table.linkedEvents'), value: String(response.summary.total_events) },
      { id: 'comments', label: i18n.t('processes.table.comments'), value: String(response.summary.total_comments) },
      { id: 'avg_involvement', label: i18n.t('processes.table.avgInvolvement'), value: formatNullableRatio(response.summary.avg_involvement) },
    ],
    rows: response.items.map((item) => mapProcessItemToRow(item)),
  };
}

function mapProcessItemToRow(item: ProcessesDashboardItemDto): ProcessDashboardRowViewModel {
  return {
    processId: item.process_id,
    title: item.title ?? i18n.t('processes.rows.processFallback', { id: item.process_id }),
    status: item.status,
    startedAt: formatUtcDateTime(item.started_at),
    endedAt: formatUtcDateTime(item.ended_at),
    confidence: formatConfidencePercent(item.confidence),
    commentsCount: String(item.comments_count),
    involvement: formatNullableRatio(item.involvement),
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
): DataTableRow[] {
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
              {row.status} | {i18n.t('processes.rows.confidence', { value: row.confidence })}
            </span>
          </div>
        ),
        timeline: (
          <div className="dashboard-table-shell__cell-stack">
            <span>{row.startedAt}</span>
            <span>{row.endedAt === i18n.t('common.na') ? i18n.t('processes.rows.active') : i18n.t('processes.rows.endedAt', { value: row.endedAt })}</span>
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
              {isSelected ? i18n.t('processes.rows.selected') : i18n.t('processes.rows.inspect')}
            </button>
            {row.eventIds[0] ? (
              <Link className="table-link" to={`/events/${row.eventIds[0]}`}>
                {i18n.t('processes.rows.leadEvent')}
              </Link>
            ) : null}
            {role === 'viewer' ? <span className="table-link table-link--muted">{i18n.t('states.readOnly')}</span> : null}
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
      title: response.summary.title ?? i18n.t('processes.rows.processFallback', { id: response.summary.process_id }),
      status: response.summary.status,
      reportStatus: response.summary.report_status,
      eventsCount: String(response.summary.events_count),
      postsCount: String(response.summary.posts_count),
      commentsCount: String(response.summary.comments_count),
      involvement: formatNullableRatio(response.summary.involvement),
    },
    events: response.events.map((event) => ({
      eventId: event.event_id,
      title: event.title ?? i18n.t('reports.rows.eventFallback', { id: event.event_id }),
      status: event.status,
      relationType: event.relation_type,
      direction: event.direction,
      score: event.score === null ? i18n.t('common.na') : event.score.toFixed(2),
      startedAt: formatUtcDateTime(event.started_at),
      postIds: event.post_ids,
    })),
    nodes: response.nodes.map((node) => ({
      id: String(node.post_id),
      postId: node.post_id,
      title: node.text_preview ?? i18n.t('processes.graph.postTitle', { id: node.post_id }),
      date: formatUtcDateTime(node.date),
      channel: node.channel_username ?? i18n.t('reports.rows.channelLabel', { id: node.channel_id }),
      eventIds: eventIdsByPostId.get(node.post_id) ?? [],
      isRoot: node.is_root,
    })),
    edges: response.edges.map((edge) => ({
      id: String(edge.link_id),
      sourcePostId: edge.src_post_id,
      targetPostId: edge.dst_post_id,
      label: edge.link_type,
      status: edge.status,
      score: edge.score === null ? i18n.t('common.na') : edge.score.toFixed(2),
    })),
  };
}

