import { useQueries, useQueryClient } from '@tanstack/react-query';

import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { getProcessDetail, getProcessGraph, updateProcessReport } from '@modules/workspace/process-detail/api';
import { processDetailQueryKeys } from '@modules/workspace/process-detail/query-keys';

export function useProcessDetailQueries(processId: number) {
  const [detailQuery, graphQuery] = useQueries({
    queries: [
      {
        queryKey: processDetailQueryKeys.detail(processId),
        queryFn: () => getProcessDetail(processId),
        retry: false,
      },
      {
        queryKey: dashboardQueryKeys.graph.process(processId),
        queryFn: () => getProcessGraph(processId),
        retry: false,
      },
    ],
  });

  return {
    detailQuery,
    graphQuery,
  };
}

export function useUpdateProcessDetailReportAction(processId: number) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate or update process draft report',
    mutationFn: () => updateProcessReport(processId),
    onInvalidate: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: processDetailQueryKeys.detail(processId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.graph.process(processId) }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('processes') }),
      ]);
    },
  });
}
