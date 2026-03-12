import { Link } from 'react-router-dom';

import type { PostsDashboardResponse } from '@shared/dashboard/contracts';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { DashboardTableColumn, DashboardTableRow } from '@shared/dashboard/components/DashboardTableShell';
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
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value));
}

function formatNullableNumber(value: number | null) {
  return value === null ? '—' : new Intl.NumberFormat('en').format(value);
}

function formatNullableRatio(value: number | null) {
  return value === null ? '—' : value.toFixed(2);
}

function formatChannelLabel(
  channelTitle: string | null,
  channelUsername: string | null,
  channelId: number,
  channelCategory: string | null,
) {
  const base = channelTitle ?? channelUsername ?? `Channel ${channelId}`;
  return channelCategory ? `${base} · ${channelCategory}` : base;
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
      { id: 'posts', label: 'Posts', value: String(response.summary.posts_count) },
      { id: 'comments', label: 'Comments', value: String(response.summary.total_comments) },
      { id: 'channels', label: 'Channels', value: String(response.summary.channels_count) },
      { id: 'avg_involvement', label: 'Avg involvement', value: formatNullableRatio(response.summary.avg_involvement) },
      { id: 'reports_ready', label: 'Ready reports', value: String(response.summary.reports_ready) },
      { id: 'reports_pending', label: 'Pending reports', value: String(response.summary.reports_pending) },
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
      preview: item.text_preview ?? 'No preview available',
      commentsCount: new Intl.NumberFormat('en').format(item.comments_count),
      views: formatNullableNumber(item.views),
      involvement: formatNullableRatio(item.involvement),
      linksCount: formatNullableNumber(item.links_count),
      reportStatus: item.report_status,
      readOnly: role === 'viewer',
    })),
  };
}

export const postsDashboardColumns: readonly DashboardTableColumn[] = [
  { id: 'date', label: 'Date' },
  { id: 'channel', label: 'Channel' },
  { id: 'preview', label: 'Preview' },
  { id: 'comments', label: 'Comments' },
  { id: 'views', label: 'Views' },
  { id: 'involvement', label: 'Involvement' },
  { id: 'links', label: 'Links' },
  { id: 'report_status', label: 'Report status' },
  { id: 'actions', label: 'Actions' },
] as const;

export function mapPostsRowsToTableRows(rows: PostsDashboardRowViewModel[]): DashboardTableRow[] {
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
            Open post
          </Link>
          {!row.readOnly ? (
            <>
              <Link className="table-link" to={row.commentsHref}>
                Comments
              </Link>
              <Link className="table-link" to={row.reportHref}>
                Report
              </Link>
            </>
          ) : null}
        </div>
      ),
    },
  }));
}
