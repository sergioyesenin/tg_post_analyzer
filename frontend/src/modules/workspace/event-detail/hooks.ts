import { useQueries, useQueryClient } from '@tanstack/react-query';

import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { getEventDetail, getEventGraph, updateEventReport } from '@modules/workspace/event-detail/api';
import { eventDetailQueryKeys } from '@modules/workspace/event-detail/query-keys';

export function useEventDetailQueries(eventId: number) {
  const [detailQuery, graphQuery] = useQueries({
    queries: [
      {
        queryKey: eventDetailQueryKeys.detail(eventId),
        queryFn: () => getEventDetail(eventId),
        retry: false,
      },
      {
        queryKey: dashboardQueryKeys.graph.event(eventId),
        queryFn: () => getEventGraph(eventId),
        retry: false,
      },
    ],
  });

  return {
    detailQuery,
    graphQuery,
  };
}

export function useUpdateEventDetailReportAction(eventId: number) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate or update event draft report',
    mutationFn: () => updateEventReport(eventId),
    onInvalidate: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: eventDetailQueryKeys.detail(eventId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.graph.event(eventId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('events') }),
      ]);
    },
  });
}
