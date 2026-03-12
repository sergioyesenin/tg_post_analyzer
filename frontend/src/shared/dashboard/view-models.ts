import type { DashboardGeneratedAtProps } from '@shared/dashboard/components/DashboardGeneratedAt';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
import type { DashboardTransportResponse } from '@shared/dashboard/contracts';
import type { DashboardFiltersByMode } from '@shared/dashboard/filters';

export type DashboardScreenViewModel = {
  title: string;
  description: string;
  generatedAt: DashboardGeneratedAtProps['generatedAt'];
  isPartial: boolean;
  warnings: DashboardTransportResponse['warnings'];
  filters: DashboardFiltersByMode[keyof DashboardFiltersByMode];
  summaryCards: DashboardSummaryCard[];
  table: {
    title: string;
    description: string;
    columns: DashboardTableColumn[];
    rows: DashboardTableRow[];
  };
  secondaryPanelTitle: string;
  secondaryPanelDescription: string;
};

function formatMetric(value: number | null) {
  if (value === null) {
    return 'n/a';
  }

  return String(value);
}

export function mapDashboardTransportToScreenViewModel(transport: DashboardTransportResponse): DashboardScreenViewModel {
  if (transport.mode === 'posts') {
    return {
      title: 'Posts workspace',
      description: 'Reusable dashboard shell anchored to /api/dashboard/posts contract.',
      generatedAt: transport.generated_at,
      isPartial: transport.partial,
      warnings: transport.warnings,
      filters: transport.filters_applied,
      summaryCards: [
        { id: 'posts_count', label: 'Posts', value: String(transport.summary.posts_count) },
        { id: 'comments', label: 'Comments', value: String(transport.summary.total_comments) },
        { id: 'channels', label: 'Channels', value: String(transport.summary.channels_count) },
        { id: 'ready_reports', label: 'Ready reports', value: String(transport.summary.reports_ready) },
      ],
      table: {
        title: 'Posts table',
        description: 'Foundation shell for table composition and future DataGrid integration.',
        columns: [
          { id: 'channel', label: 'Channel' },
          { id: 'preview', label: 'Preview' },
          { id: 'comments', label: 'Comments' },
          { id: 'report_status', label: 'Report status' },
        ],
        rows: transport.items.map((item) => ({
          id: String(item.post_id),
          href: `/posts/${item.post_id}`,
          cells: {
            channel: item.channel_title ?? item.channel_username ?? String(item.channel_id),
            preview: item.text_preview ?? '—',
            comments: String(item.comments_count),
            report_status: item.report_status,
          },
        })),
      },
      secondaryPanelTitle: 'Selection / details rail',
      secondaryPanelDescription:
        'Stage 2 keeps the right rail reusable for future details, comments and report blocks without binding to a specific API.',
    };
  }

  if (transport.mode === 'events') {
    return {
      title: 'Events workspace',
      description: 'Shell keeps partial data visible and reserves a split panel for graph and detail blocks.',
      generatedAt: transport.generated_at,
      isPartial: transport.partial,
      warnings: transport.warnings,
      filters: transport.filters_applied,
      summaryCards: [
        { id: 'events_count', label: 'Events', value: String(transport.summary.events_count) },
        { id: 'linked_posts', label: 'Linked posts', value: String(transport.summary.total_linked_posts) },
        { id: 'comments', label: 'Comments', value: String(transport.summary.total_comments) },
        { id: 'draft_reports', label: 'Draft reports', value: String(transport.summary.draft_reports) },
      ],
      table: {
        title: 'Events table',
        description: 'Reusable shell for rows, sorting and future detail selection.',
        columns: [
          { id: 'title', label: 'Event' },
          { id: 'status', label: 'Status' },
          { id: 'posts', label: 'Posts' },
          { id: 'report_status', label: 'Report status' },
        ],
        rows: transport.items.map((item) => ({
          id: String(item.event_id),
          href: `/events/${item.event_id}`,
          cells: {
            title: item.title ?? `Event ${item.event_id}`,
            status: item.status,
            posts: String(item.posts_count),
            report_status: item.report_status,
          },
        })),
      },
      secondaryPanelTitle: 'Graph / details foundation',
      secondaryPanelDescription:
        'Split container reserves space for event graph, selected event details and related posts without blocking the table.',
    };
  }

  return {
    title: 'Processes workspace',
    description: 'Processes mode shares shell behavior but isolates its mode-specific graph and details rail.',
    generatedAt: transport.generated_at,
    isPartial: transport.partial,
    warnings: transport.warnings,
    filters: transport.filters_applied,
    summaryCards: [
      { id: 'processes_count', label: 'Processes', value: String(transport.summary.processes_count) },
      { id: 'events', label: 'Events', value: String(transport.summary.total_events) },
      { id: 'comments', label: 'Comments', value: String(transport.summary.total_comments) },
      { id: 'avg_involvement', label: 'Avg involvement', value: formatMetric(transport.summary.avg_involvement) },
    ],
    table: {
      title: 'Processes table',
      description: 'Reusable shell for process rows before graph/detail implementation.',
      columns: [
        { id: 'title', label: 'Process' },
        { id: 'status', label: 'Status' },
        { id: 'events', label: 'Events' },
        { id: 'report_status', label: 'Report status' },
      ],
      rows: transport.items.map((item) => ({
        id: String(item.process_id),
        href: `/processes/${item.process_id}`,
        cells: {
          title: item.title ?? `Process ${item.process_id}`,
          status: item.status,
          events: String(item.events_count),
          report_status: item.report_status,
        },
      })),
    },
    secondaryPanelTitle: 'Process graph / linked events rail',
    secondaryPanelDescription:
      'Shared split layout remains stable while future process graph and linked event blocks are added.',
  };
}
