import { i18n } from '@shared/i18n/i18n';
import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { ProcessGraphResponse } from '@shared/dashboard/contracts';
import {
  mapProcessGraphToViewModel,
  type ProcessGraphPanelViewModel,
} from '@modules/workspace/processes/mappers';
import type { ProcessDetailDto } from '@modules/workspace/process-detail/contracts';
import { formatConfidencePercent, formatNullableRatio, formatUtcDateTime } from '@shared/utils/formatters';

export type ProcessDetailPageViewModel = {
  process: {
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
    createdBy: string;
    reportStatus: string;
    graphReady: boolean | null;
  };
  summaryCards: DashboardSummaryCard[];
  relatedEvents: Array<{
    eventId: number;
    title: string;
    status: string;
    relationType: string;
    direction: string;
    score: string;
    startedAt: string;
    postIds: number[];
  }>;
  confirmedPostIds: number[];
  graph: ProcessGraphPanelViewModel | null;
};

export function mapProcessDetailToViewModel(
  detail: ProcessDetailDto,
  graph: ProcessGraphResponse | null,
): ProcessDetailPageViewModel {
  const graphViewModel = graph ? mapProcessGraphToViewModel(graph) : null;
  const graphEventsById = new Map(graphViewModel?.events.map((event) => [event.eventId, event]) ?? []);

  const relatedEvents = detail.events.map((event) => {
    const graphEvent = graphEventsById.get(event.event_id);

    return {
      eventId: event.event_id,
      title: graphEvent?.title ?? i18n.t('processes.detail.fallbackEvent', { id: event.event_id }),
      status: graphEvent?.status ?? event.status,
      relationType: graphEvent?.relationType ?? event.relation_type,
      direction: graphEvent?.direction ?? event.direction,
      score: graphEvent?.score ?? (event.score === null ? i18n.t('common.na') : event.score.toFixed(2)),
      startedAt: graphEvent?.startedAt ?? i18n.t('common.na'),
      postIds: graphEvent?.postIds ?? [],
    };
  });

  const confirmedPostIds = Array.from(new Set(relatedEvents.flatMap((event) => event.postIds)));

  return {
    process: {
      processId: detail.process.id,
      title: detail.process.title ?? i18n.t('processes.rows.processFallback', { id: detail.process.id }),
      status: detail.process.status,
      startedAt: formatUtcDateTime(detail.process.started_at),
      endedAt: formatUtcDateTime(detail.process.ended_at),
      confidence: formatConfidencePercent(detail.process.confidence),
      commentsCount: String(detail.process.comments_count),
      involvement: formatNullableRatio(detail.process.involvement),
      eventsCount: String(detail.events.length),
      eventIds: detail.events.map((event) => event.event_id),
      createdBy: detail.process.created_by ?? i18n.t('common.na'),
      reportStatus: graph?.summary.report_status ?? 'missing',
      graphReady: graph ? true : null,
    },
    summaryCards: [
      { id: 'status', label: i18n.t('processes.detail.status'), value: detail.process.status },
      { id: 'events_count', label: i18n.t('processes.detail.events'), value: String(detail.events.length) },
      { id: 'comments_count', label: i18n.t('processes.table.comments'), value: String(detail.process.comments_count) },
      { id: 'involvement', label: i18n.t('processes.table.involvement'), value: formatNullableRatio(detail.process.involvement) },
    ],
    relatedEvents,
    confirmedPostIds,
    graph: graphViewModel,
  };
}
