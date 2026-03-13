import { Link } from 'react-router-dom';

import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import { formatUtcDateTime } from '@shared/utils/formatters';
import type {
  EventReportListItemDto,
  PostReportListItemDto,
  ProcessReportListItemDto,
  ReportType,
  ReportsListResponseByType,
} from '@modules/reports/contracts';

export const reportsColumnsByType: Record<ReportType, DashboardTableColumn[]> = {
  posts: [
    { id: 'entity', label: 'Post' },
    { id: 'context', label: 'Context' },
    { id: 'status', label: 'Status' },
    { id: 'created_at', label: 'Created' },
    { id: 'actions', label: 'Actions' },
  ],
  events: [
    { id: 'entity', label: 'Event' },
    { id: 'version', label: 'Version' },
    { id: 'status', label: 'Status' },
    { id: 'created_at', label: 'Created' },
    { id: 'actions', label: 'Actions' },
  ],
  processes: [
    { id: 'entity', label: 'Process' },
    { id: 'version', label: 'Version' },
    { id: 'status', label: 'Status' },
    { id: 'created_at', label: 'Created' },
    { id: 'actions', label: 'Actions' },
  ],
};

function mapPostRow(item: PostReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>Post #{item.post_id}</strong>
          <span>{formatUtcDateTime(item.post_date)}</span>
        </div>
      ),
      context: (
        <div className="dashboard-table-shell__cell-stack">
          <span>{item.channel_username ? `@${item.channel_username}` : `Channel #${item.channel_id}`}</span>
          <span>{item.channel_category ?? 'n/a'}</span>
        </div>
      ),
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/posts/${item.post_id}`}>
            Open post
          </Link>
        </div>
      ),
    },
  };
}

function mapEventRow(item: EventReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{item.event_title ?? `Event ${item.event_id}`}</strong>
          <span>Event #{item.event_id}</span>
        </div>
      ),
      version: item.version ?? 'n/a',
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/events/${item.event_id}`}>
            Open event
          </Link>
        </div>
      ),
    },
  };
}

function mapProcessRow(item: ProcessReportListItemDto): DashboardTableRow {
  return {
    id: String(item.report_id),
    cells: {
      entity: (
        <div className="dashboard-table-shell__cell-stack">
          <strong>{item.process_title ?? `Process ${item.process_id}`}</strong>
          <span>Process #{item.process_id}</span>
        </div>
      ),
      version: item.version ?? 'n/a',
      status: <ReportStatusBadge status={item.status} />,
      created_at: formatUtcDateTime(item.created_at),
      actions: (
        <div className="dashboard-table-shell__actions">
          <Link className="table-link" to={`/processes/${item.process_id}`}>
            Open process
          </Link>
        </div>
      ),
    },
  };
}

export function mapReportsRowsToTableRows<TType extends ReportType>(
  type: TType,
  items: ReportsListResponseByType[TType],
): DashboardTableRow[] {
  if (type === 'posts') {
    return (items as ReportsListResponseByType['posts']).map(mapPostRow);
  }

  if (type === 'events') {
    return (items as ReportsListResponseByType['events']).map(mapEventRow);
  }

  return (items as ReportsListResponseByType['processes']).map(mapProcessRow);
}

export const reportsCopyByType: Record<ReportType, { title: string; description: string; emptyTitle: string; emptyDescription: string }> = {
  posts: {
    title: 'Post reports',
    description: 'Post report catalog stays filterable by channel/date and supports batch draft generation for supported roles.',
    emptyTitle: 'No post reports match the current filters',
    emptyDescription: 'The report list loaded successfully, but no post reports matched the current filter set.',
  },
  events: {
    title: 'Event reports',
    description: 'Event report catalog focuses on generated drafts and ready reports for event-level review.',
    emptyTitle: 'No event reports match the current filters',
    emptyDescription: 'The report list loaded successfully, but no event reports matched the current filter set.',
  },
  processes: {
    title: 'Process reports',
    description: 'Process report catalog keeps process-level report versions and direct navigation to process detail available.',
    emptyTitle: 'No process reports match the current filters',
    emptyDescription: 'The report list loaded successfully, but no process reports matched the current filter set.',
  },
};
