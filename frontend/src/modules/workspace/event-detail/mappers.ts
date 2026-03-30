import { i18n } from '@shared/i18n/i18n';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { EventGraphResponse } from '@shared/dashboard/contracts';
import { mapEventGraphToViewModel, type EventGraphPanelViewModel } from '@modules/workspace/events/mappers';
import type { EventDetailDto } from '@modules/workspace/event-detail/contracts';
import { formatConfidencePercent, formatNullableRatio, formatUtcDateTime } from '@shared/utils/formatters';

export type EventDetailPageViewModel = {
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
    createdBy: string;
    reportStatus: string | null;
    reportSummary: string | null;
    reportTopics: string[];
    graphReady: boolean | null;
  };
  summaryCards: DashboardSummaryCard[];
  graph: EventGraphPanelViewModel | null;
};

function readEventReportSummary(detail: EventDetailDto): string | null {
  const summary = detail.latest_report?.report_json?.summary;
  return typeof summary === 'string' && summary.trim() ? summary : null;
}

function readEventReportTopics(detail: EventDetailDto): string[] {
  const topics = detail.latest_report?.report_json?.cross_post_topics;
  if (!Array.isArray(topics)) {
    return [];
  }
  return topics
    .map((topic) => (typeof topic === 'object' && topic && 'name' in topic ? String((topic as { name?: unknown }).name ?? '').trim() : ''))
    .filter((topic) => Boolean(topic))
    .slice(0, 4);
}

export function mapEventDetailToViewModel(detail: EventDetailDto, graph: EventGraphResponse | null): EventDetailPageViewModel {
  const graphViewModel = graph ? mapEventGraphToViewModel(graph) : null;
  const rootPostId = graphViewModel?.nodes.find((node) => node.isRoot)?.postId ?? detail.root_post_id ?? null;
  const channelLabels = graph && graph.nodes.length > 0
    ? Array.from(new Set(graph.nodes.map((node) => node.channel_username ?? null).filter((value): value is string => Boolean(value))))
    : detail.channels;
  const postsCount = graphViewModel ? graphViewModel.event.postsCount : String(detail.post_ids.length);

  return {
    event: {
      eventId: detail.event.id,
      title: detail.event.title ?? i18n.t('events.rows.eventFallback', { id: detail.event.id }),
      status: detail.event.status,
      startedAt: formatUtcDateTime(detail.event.started_at),
      endedAt: formatUtcDateTime(detail.event.ended_at),
      confidence: formatConfidencePercent(detail.event.confidence),
      commentsCount: String(detail.event.comments_count),
      involvement: formatNullableRatio(detail.event.involvement),
      postsCount,
      postIds: detail.post_ids,
      rootPostId,
      channels: channelLabels.join(', ') || i18n.t('common.na'),
      createdBy: detail.event.created_by ?? i18n.t('common.na'),
      reportStatus: graph?.event.report_status ?? detail.latest_report?.status ?? null,
      reportSummary: readEventReportSummary(detail),
      reportTopics: readEventReportTopics(detail),
      graphReady: graph ? true : null,
    },
    summaryCards: [
      { id: 'status', label: i18n.t('events.detail.status'), value: detail.event.status },
      { id: 'posts_count', label: i18n.t('events.table.linkedPosts'), value: postsCount },
      { id: 'comments_count', label: i18n.t('events.table.comments'), value: String(detail.event.comments_count) },
      { id: 'involvement', label: i18n.t('events.table.involvement'), value: formatNullableRatio(detail.event.involvement) },
    ],
    graph: graphViewModel,
  };
}
