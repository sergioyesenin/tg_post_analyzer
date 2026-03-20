import type { DashboardGeneratedAtProps } from '@shared/dashboard/components/DashboardGeneratedAt';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import type { DashboardTransportResponse } from '@shared/dashboard/contracts';
import type { DashboardFiltersByMode } from '@shared/dashboard/filters';
import { i18n } from '@shared/i18n/i18n';

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
    columns: DataTableColumn[];
    rows: DataTableRow[];
  };
  secondaryPanelTitle: string;
  secondaryPanelDescription: string;
};

function formatMetric(value: number | null) {
  if (value === null) {
    return i18n.t('common.na');
  }

  return String(value);
}

export function mapDashboardTransportToScreenViewModel(transport: DashboardTransportResponse): DashboardScreenViewModel {
  if (transport.mode === 'posts') {
    return {
      title: i18n.t('dashboard.foundation.posts.title'),
      description: i18n.t('dashboard.foundation.posts.description'),
      generatedAt: transport.generated_at,
      isPartial: transport.partial,
      warnings: transport.warnings,
      filters: transport.filters_applied,
      summaryCards: [
        { id: 'posts_count', label: i18n.t('navigation.posts'), value: String(transport.summary.posts_count) },
        { id: 'comments', label: i18n.t('dashboard.foundation.metrics.comments'), value: String(transport.summary.total_comments) },
        { id: 'channels', label: i18n.t('navigation.channels'), value: String(transport.summary.channels_count) },
        { id: 'ready_reports', label: i18n.t('dashboard.foundation.metrics.readyReports'), value: String(transport.summary.reports_ready) },
      ],
      table: {
        title: i18n.t('dashboard.foundation.posts.tableTitle'),
        description: i18n.t('dashboard.foundation.posts.tableDescription'),
        columns: [
          { id: 'channel', label: i18n.t('dashboard.foundation.columns.channel') },
          { id: 'preview', label: i18n.t('dashboard.foundation.columns.preview') },
          { id: 'comments', label: i18n.t('dashboard.foundation.metrics.comments') },
          { id: 'report_status', label: i18n.t('fields.reportStatus') },
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
      secondaryPanelTitle: i18n.t('dashboard.foundation.posts.secondaryTitle'),
      secondaryPanelDescription: i18n.t('dashboard.foundation.posts.secondaryDescription'),
    };
  }

  if (transport.mode === 'events') {
    return {
      title: i18n.t('dashboard.foundation.events.title'),
      description: i18n.t('dashboard.foundation.events.description'),
      generatedAt: transport.generated_at,
      isPartial: transport.partial,
      warnings: transport.warnings,
      filters: transport.filters_applied,
      summaryCards: [
        { id: 'events_count', label: i18n.t('navigation.events'), value: String(transport.summary.events_count) },
        { id: 'linked_posts', label: i18n.t('dashboard.foundation.metrics.linkedPosts'), value: String(transport.summary.total_linked_posts) },
        { id: 'comments', label: i18n.t('dashboard.foundation.metrics.comments'), value: String(transport.summary.total_comments) },
        { id: 'draft_reports', label: i18n.t('dashboard.foundation.metrics.draftReports'), value: String(transport.summary.draft_reports) },
      ],
      table: {
        title: i18n.t('dashboard.foundation.events.tableTitle'),
        description: i18n.t('dashboard.foundation.events.tableDescription'),
        columns: [
          { id: 'title', label: i18n.t('navigation.events') },
          { id: 'status', label: i18n.t('fields.status') },
          { id: 'posts', label: i18n.t('navigation.posts') },
          { id: 'report_status', label: i18n.t('fields.reportStatus') },
        ],
        rows: transport.items.map((item) => ({
          id: String(item.event_id),
          href: `/events/${item.event_id}`,
          cells: {
            title: item.title ?? i18n.t('dashboard.foundation.events.fallbackTitle', { id: item.event_id }),
            status: item.status,
            posts: String(item.posts_count),
            report_status: item.report_status,
          },
        })),
      },
      secondaryPanelTitle: i18n.t('dashboard.foundation.events.secondaryTitle'),
      secondaryPanelDescription: i18n.t('dashboard.foundation.events.secondaryDescription'),
    };
  }

  return {
    title: i18n.t('dashboard.foundation.processes.title'),
    description: i18n.t('dashboard.foundation.processes.description'),
    generatedAt: transport.generated_at,
    isPartial: transport.partial,
    warnings: transport.warnings,
    filters: transport.filters_applied,
    summaryCards: [
      { id: 'processes_count', label: i18n.t('navigation.processes'), value: String(transport.summary.processes_count) },
      { id: 'events', label: i18n.t('navigation.events'), value: String(transport.summary.total_events) },
      { id: 'comments', label: i18n.t('dashboard.foundation.metrics.comments'), value: String(transport.summary.total_comments) },
      { id: 'avg_involvement', label: i18n.t('dashboard.foundation.metrics.avgInvolvement'), value: formatMetric(transport.summary.avg_involvement) },
    ],
    table: {
      title: i18n.t('dashboard.foundation.processes.tableTitle'),
      description: i18n.t('dashboard.foundation.processes.tableDescription'),
      columns: [
        { id: 'title', label: i18n.t('navigation.processes') },
        { id: 'status', label: i18n.t('fields.status') },
        { id: 'events', label: i18n.t('navigation.events') },
        { id: 'report_status', label: i18n.t('fields.reportStatus') },
      ],
      rows: transport.items.map((item) => ({
        id: String(item.process_id),
        href: `/processes/${item.process_id}`,
        cells: {
          title: item.title ?? i18n.t('dashboard.foundation.processes.fallbackTitle', { id: item.process_id }),
          status: item.status,
          events: String(item.events_count),
          report_status: item.report_status,
        },
      })),
    },
    secondaryPanelTitle: i18n.t('dashboard.foundation.processes.secondaryTitle'),
    secondaryPanelDescription: i18n.t('dashboard.foundation.processes.secondaryDescription'),
  };
}


