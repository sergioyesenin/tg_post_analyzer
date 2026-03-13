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
    graphReady: boolean | null;
  };
  summaryCards: DashboardSummaryCard[];
  graph: EventGraphPanelViewModel | null;
};

export function mapEventDetailToViewModel(detail: EventDetailDto, graph: EventGraphResponse | null): EventDetailPageViewModel {
  const graphViewModel = graph ? mapEventGraphToViewModel(graph) : null;
  const rootPostId = graphViewModel?.nodes.find((node) => node.isRoot)?.postId ?? null;
  const channelLabels =
    graph && graph.nodes.length > 0
      ? Array.from(
          new Set(
            graph.nodes
              .map((node) => node.channel_username ?? null)
              .filter((value): value is string => Boolean(value)),
          ),
        )
      : [];

  const postsCount = graphViewModel ? graphViewModel.event.postsCount : String(detail.post_ids.length);

  return {
    event: {
      eventId: detail.event.id,
      title: detail.event.title ?? `Event ${detail.event.id}`,
      status: detail.event.status,
      startedAt: formatUtcDateTime(detail.event.started_at),
      endedAt: formatUtcDateTime(detail.event.ended_at),
      confidence: formatConfidencePercent(detail.event.confidence),
      commentsCount: String(detail.event.comments_count),
      involvement: formatNullableRatio(detail.event.involvement),
      postsCount,
      postIds: detail.post_ids,
      rootPostId,
      channels: channelLabels.join(', ') || 'n/a',
      createdBy: detail.event.created_by ?? 'n/a',
      reportStatus: graph?.event.report_status ?? null,
      graphReady: graph ? true : null,
    },
    summaryCards: [
      { id: 'status', label: 'Status', value: detail.event.status },
      { id: 'posts_count', label: 'Linked posts', value: postsCount },
      { id: 'comments_count', label: 'Comments', value: String(detail.event.comments_count) },
      { id: 'involvement', label: 'Involvement', value: formatNullableRatio(detail.event.involvement) },
    ],
    graph: graphViewModel,
  };
}
