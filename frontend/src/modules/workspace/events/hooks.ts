import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import type { EventsDashboardFiltersDto, EventsDashboardItemDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { getEventGraph, getEventsDashboard, updateEventReport } from '@modules/workspace/events/api';

export function useEventsDashboardQuery(filters: EventsDashboardFiltersDto) {
  const query = serializeDashboardFilters('events', filters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('events', query || 'default'),
    queryFn: () => getEventsDashboard(filters),
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

      return items[0]?.event_id ?? null;
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
  });
}
