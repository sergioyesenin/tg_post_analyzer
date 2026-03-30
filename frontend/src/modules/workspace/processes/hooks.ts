import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import type { ProcessesDashboardFiltersDto, ProcessesDashboardItemDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { useAsyncJobAction } from '@shared/jobs/hooks';
import { keepPreviousData } from '@shared/query/placeholder-data';
import { searchPostsByKeyword } from '@modules/keyword-graph/api';
import type { KeywordSearchFilters } from '@modules/keyword-graph/contracts';
import { getProcessGraph, getProcessesDashboard, updateProcessReport } from '@modules/workspace/processes/api';

function getProcessesSnapshotFilters(filters: ProcessesDashboardFiltersDto): ProcessesDashboardFiltersDto {
  return {
    ...filters,
    query: '',
  };
}

function getProcessesKeywordSearchFilters(filters: ProcessesDashboardFiltersDto): KeywordSearchFilters {
  return {
    query: filters.query.trim(),
    limit: filters.limit,
    date_from: filters.date_from ?? '',
    date_to: filters.date_to ?? '',
    channel_ids: [],
  };
}

export function useProcessesDashboardQuery(filters: ProcessesDashboardFiltersDto) {
  const snapshotFilters = getProcessesSnapshotFilters(filters);
  const query = serializeDashboardFilters('processes', snapshotFilters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('processes', query || 'default'),
    queryFn: () => getProcessesDashboard(snapshotFilters),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useProcessesKeywordSearchQuery(
  filters: ProcessesDashboardFiltersDto,
  options?: {
    enabled?: boolean;
  },
) {
  const searchFilters = getProcessesKeywordSearchFilters(filters);
  const query = serializeDashboardFilters('processes', {
    ...filters,
    min_comments: null,
    sort_by: 'started_at',
    sort_order: 'desc',
    status: [],
  });
  const isEnabled = (options?.enabled ?? true) && searchFilters.query.length >= 2;

  return useQuery({
    queryKey: [...dashboardQueryKeys.mode('processes'), 'keyword-search', query || 'default'],
    queryFn: () => searchPostsByKeyword(searchFilters),
    enabled: isEnabled,
    placeholderData: keepPreviousData,
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
