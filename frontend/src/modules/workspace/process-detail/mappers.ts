import type { DashboardSummaryCard } from '@shared/dashboard/components/DashboardSummaryCards';
import type { ProcessGraphResponse } from '@shared/dashboard/contracts';
import {
  mapProcessGraphToViewModel,
  type ProcessGraphPanelViewModel,
} from '@modules/workspace/processes/mappers';
import type { ProcessDetailDto } from '@modules/workspace/process-detail/contracts';

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
      title: graphEvent?.title ?? `Event ${event.event_id}`,
      status: graphEvent?.status ?? event.status,
      relationType: graphEvent?.relationType ?? event.relation_type,
      direction: graphEvent?.direction ?? event.direction,
      score: graphEvent?.score ?? (event.score === null ? 'n/a' : event.score.toFixed(2)),
      startedAt: graphEvent?.startedAt ?? 'n/a',
      postIds: graphEvent?.postIds ?? [],
    };
  });

  const confirmedPostIds = Array.from(new Set(relatedEvents.flatMap((event) => event.postIds)));

  return {
    process: {
      processId: detail.process.id,
      title: detail.process.title ?? `Process ${detail.process.id}`,
      status: detail.process.status,
      startedAt: formatDateTime(detail.process.started_at),
      endedAt: formatDateTime(detail.process.ended_at),
      confidence: formatConfidence(detail.process.confidence),
      commentsCount: String(detail.process.comments_count),
      involvement: formatRatio(detail.process.involvement),
      eventsCount: String(detail.events.length),
      eventIds: detail.events.map((event) => event.event_id),
      createdBy: detail.process.created_by ?? 'n/a',
      reportStatus: graph?.summary.report_status ?? 'missing',
      graphReady: graph ? true : null,
    },
    summaryCards: [
      { id: 'status', label: 'Status', value: detail.process.status },
      { id: 'events_count', label: 'Related events', value: String(detail.events.length) },
      { id: 'comments_count', label: 'Comments', value: String(detail.process.comments_count) },
      { id: 'involvement', label: 'Involvement', value: formatRatio(detail.process.involvement) },
    ],
    relatedEvents,
    confirmedPostIds,
    graph: graphViewModel,
  };
}
