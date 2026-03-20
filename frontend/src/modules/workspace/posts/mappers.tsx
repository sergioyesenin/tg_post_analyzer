import { Link } from 'react-router-dom';

import { i18n } from '@shared/i18n/i18n';
import type { PostsDashboardResponse } from '@shared/dashboard/contracts';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DataTableColumn, DataTableRow } from '@shared/tables/types';
import { ReportStatusBadge } from '@shared/ui/status/ReportStatusBadge';
import type { UserRole } from '@shared/auth/roles';
import { buildPostDetailHref } from '@modules/workspace/posts/links';

export type PostsDashboardRowViewModel = {
  id: string;
  postId: number;
  detailHref: string;
  commentsHref: string;
  reportHref: string;
  channel: string;
  date: string;
  preview: string;
  commentsCount: string;
  views: string;
  involvement: string;
  linksCount: string;
  reportStatus: string;
  readOnly: boolean;
};

export type PostsDashboardViewModel = {
  generatedAt: string;
  isPartial: boolean;
  warnings: PostsDashboardResponse['warnings'];
  summaryCards: DashboardSummaryCard[];
  rows: PostsDashboardRowViewModel[];
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(i18n.language === 'ru' ? 'ru' : 'en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatNullableNumber(value: number | null) {
  return value === null ? i18n.t('common.na') : new Intl.NumberFormat(i18n.language === 'ru' ? 'ru' : 'en').format(value);
}

function formatNullableRatio(value: number | null) {
  return value === null ? i18n.t('common.na') : value.toFixed(2);
}

function formatChannelLabel(
  channelTitle: string | null,
  channelUsername: string | null,
  channelId: number,
  channelCategory: string | null,
) {
  const base = channelTitle ?? channelUsername ?? i18n.t('posts.rows.channelFallback', { id: channelId });
  return channelCategory ? `${base} | ${channelCategory}` : base;
}

export function mapPostsDashboardToViewModel(
  response: PostsDashboardResponse,
  role: UserRole | null,
): PostsDashboardViewModel {
  return {
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
    summaryCards: [
      { id: 'posts', label: i18n.t('posts.table.posts'), value: String(response.summary.posts_count) },
      { id: 'comments', label: i18n.t('posts.table.comments'), value: String(response.summary.total_comments) },
      { id: 'channels', label: i18n.t('posts.table.channels'), value: String(response.summary.channels_count) },
      { id: 'avg_involvement', label: i18n.t('posts.table.avgInvolvement'), value: formatNullableRatio(response.summary.avg_involvement) },
      { id: 'reports_ready', label: i18n.t('posts.table.readyReports'), value: String(response.summary.reports_ready) },
      { id: 'reports_pending', label: i18n.t('posts.table.pendingReports'), value: String(response.summary.reports_pending) },
    ],
    rows: response.items.map((item) => ({
      id: String(item.post_id),
      postId: item.post_id,
      detailHref: buildPostDetailHref(item.post_id),
      commentsHref: buildPostDetailHref(item.post_id, 'comments'),
      reportHref: buildPostDetailHref(item.post_id, 'report'),
      channel: formatChannelLabel(
        item.channel_title,
        item.channel_username,
        item.channel_id,
        item.channel_category,
      ),
      date: formatDate(item.date),
      preview: item.text_preview ?? i18n.t('posts.rows.noPreview'),
      commentsCount: new Intl.NumberFormat(i18n.language === 'ru' ? 'ru' : 'en').format(item.comments_count),
      views: formatNullableNumber(item.views),
      involvement: formatNullableRatio(item.involvement),
      linksCount: formatNullableNumber(item.links_count),
      reportStatus: item.report_status,
      readOnly: role === 'viewer',
    })),
  };
}

export const postsDashboardColumns: readonly DataTableColumn[] = [
  { id: 'date', label: i18n.t('posts.table.date') },
  { id: 'channel', label: i18n.t('posts.table.channel') },
  { id: 'preview', label: i18n.t('posts.table.preview') },
  { id: 'comments', label: i18n.t('posts.table.comments') },
  { id: 'views', label: i18n.t('posts.table.views') },
  { id: 'involvement', label: i18n.t('posts.table.involvement') },
  { id: 'links', label: i18n.t('posts.table.links') },
  { id: 'report_status', label: i18n.t('posts.table.reportStatus') },
  { id: 'actions', label: i18n.t('posts.table.actions') },
] as const;

export function mapPostsRowsToTableRows(rows: PostsDashboardRowViewModel[]): DataTableRow[] {
  return rows.map((row) => ({
    id: row.id,
    href: row.detailHref,
    cells: {
      date: row.date,
      channel: row.channel,
      preview: row.preview,
      comments: row.commentsCount,
      views: row.views,
      involvement: row.involvement,
      links: row.linksCount,
      report_status: <ReportStatusBadge status={row.reportStatus} />,
      actions: (
        <div className="table-action-group">
          <Link className="table-link" to={row.detailHref}>
            {i18n.t('posts.rows.openPost')}
          </Link>
          {!row.readOnly ? (
            <>
              <Link className="table-link" to={row.commentsHref}>
                {i18n.t('posts.rows.comments')}
              </Link>
              <Link className="table-link" to={row.reportHref}>
                {i18n.t('posts.rows.report')}
              </Link>
            </>
          ) : null}
        </div>
      ),
    },
  }));
}

