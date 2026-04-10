import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import type { EventsDashboardFiltersDto, EventsDashboardItemDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { keepPreviousData } from '@shared/query/placeholder-data';
import { searchPostsByKeyword } from '@modules/keyword-graph/api';
import type { KeywordSearchFilters } from '@modules/keyword-graph/contracts';
import { getEventGraph, getEventsDashboard, updateEventReport } from '@modules/workspace/events/api';

function getEventsSnapshotFilters(filters: EventsDashboardFiltersDto): EventsDashboardFiltersDto {
  return {
    ...filters,
    query: '',
  };
}

function getEventsKeywordSearchFilters(filters: EventsDashboardFiltersDto): KeywordSearchFilters {
  return {
    query: filters.query.trim(),
    limit: filters.limit,
    date_from: filters.date_from ?? '',
    date_to: filters.date_to ?? '',
    channel_ids: filters.channel_ids,
  };
}

export function useEventsDashboardQuery(filters: EventsDashboardFiltersDto) {
  const snapshotFilters = getEventsSnapshotFilters(filters);
  const query = serializeDashboardFilters('events', snapshotFilters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('events', query || 'default'),
    queryFn: () => getEventsDashboard(snapshotFilters),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useEventsKeywordSearchQuery(
  filters: EventsDashboardFiltersDto,
  options?: {
    enabled?: boolean;
  },
) {
  const searchFilters = getEventsKeywordSearchFilters(filters);
  const query = serializeDashboardFilters('events', {
    ...filters,
    categories: [],
    min_comments: null,
    sort_by: 'started_at',
    sort_order: 'desc',
    status: [],
  });
  const isEnabled = (options?.enabled ?? true) && searchFilters.query.length >= 2;

  return useQuery({
    queryKey: [...dashboardQueryKeys.mode('events'), 'keyword-search', query || 'default'],
    queryFn: () => searchPostsByKeyword(searchFilters),
    enabled: isEnabled,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useSelectedEventId(items: EventsDashboardItemDto[]) {
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);

  useEffect(() => {
    if (items.length === 0) {
      setSelectedEventId(null);
      return;
    }

    setSelectedEventId((current) => {
      if (current && items.some((item) => item.event_id === current)) {
        return current;
      }

      return null;
    });
  }, [items]);

  return {
    selectedEventId,
    selectEvent: setSelectedEventId,
  };
}

export function useEventGraphQuery(eventId: number | null) {
  return useQuery({
    queryKey: eventId ? dashboardQueryKeys.graph.event(eventId) : [...dashboardQueryKeys.all, 'event-graph', 'idle'],
    queryFn: () => getEventGraph(eventId!),
    enabled: eventId !== null,
    retry: false,
  });
}

export function useUpdateEventReportAction(eventId: number | null) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate or update event draft report',
    mutationFn: () => {
      if (eventId === null) {
        throw new Error('No event selected for report update');
      }

      return updateEventReport(eventId);
    },
    onInvalidate: async () => {
      if (eventId === null) {
        return;
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('events') }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.graph.event(eventId) }),
      ]);
    },
    progress: { mode: 'report-build', entityType: 'event', entityId: eventId },
  });
}
