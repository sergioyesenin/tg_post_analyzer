import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import type { ProcessesDashboardFiltersDto, ProcessesDashboardItemDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { getProcessGraph, getProcessesDashboard, updateProcessReport } from '@modules/workspace/processes/api';

export function useProcessesDashboardQuery(filters: ProcessesDashboardFiltersDto) {
  const query = serializeDashboardFilters('processes', filters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('processes', query || 'default'),
    queryFn: () => getProcessesDashboard(filters),
    retry: false,
  });
}

export function useSelectedProcessId(items: ProcessesDashboardItemDto[]) {
  const [selectedProcessId, setSelectedProcessId] = useState<number | null>(null);

  useEffect(() => {
    if (items.length === 0) {
      setSelectedProcessId(null);
      return;
    }

    setSelectedProcessId((current) => {
      if (current && items.some((item) => item.process_id === current)) {
        return current;
      }

      return null;
    });
  }, [items]);

  return {
    selectedProcessId,
    selectProcess: setSelectedProcessId,
  };
}

export function useProcessGraphQuery(processId: number | null) {
  return useQuery({
    queryKey: processId ? dashboardQueryKeys.graph.process(processId) : [...dashboardQueryKeys.all, 'process-graph', 'idle'],
    queryFn: () => getProcessGraph(processId!),
    enabled: processId !== null,
    retry: false,
  });
}

export function useUpdateProcessReportAction(processId: number | null) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate or update process draft report',
    mutationFn: () => {
      if (processId === null) {
        throw new Error('No process selected for report update');
      }

      return updateProcessReport(processId);
    },
    onInvalidate: async () => {
      if (processId === null) {
        return;
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.mode('processes') }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.graph.process(processId) }),
      ]);
    },
  });
}

