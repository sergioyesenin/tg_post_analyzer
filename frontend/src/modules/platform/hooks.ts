import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getDeadLetterJobs,
  getJobsSummary,
  getMonitorFull,
  getPendingJobs,
  retryDeadLetterJob,
  retryFailedJob,
} from '@modules/platform/api';
import type { JobsFilters } from '@modules/platform/contracts';
import { platformQueryKeys } from '@modules/platform/query-keys';
import { parseQueryParams, serializeQueryParams } from '@shared/utils/queryParams';

function parseLimit(search: string) {
  const params = parseQueryParams(search);
  const raw = Array.isArray(params.limit) ? params.limit[0] : params.limit;
  const parsed = raw ? Number(raw) : NaN;

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 100;
  }

  return Math.min(parsed, 200);
}

export function useJobsFilters() {
  const location = useLocation();
  const navigate = useNavigate();

  const filters = useMemo<JobsFilters>(() => ({ limit: parseLimit(location.search) }), [location.search]);

  const applyFilters = (nextFilters: JobsFilters) => {
    const search = serializeQueryParams({ limit: nextFilters.limit });
    navigate(
      {
        pathname: location.pathname,
        search: search ? `?${search}` : '',
      },
      { replace: false },
    );
  };

  return {
    filters,
    applyFilters,
  };
}

export function useMonitorFullQuery() {
  return useQuery({
    queryKey: platformQueryKeys.monitor(),
    queryFn: getMonitorFull,
    retry: false,
  });
}

export function useJobsSummaryQuery() {
  return useQuery({
    queryKey: platformQueryKeys.jobsSummary(),
    queryFn: getJobsSummary,
    retry: false,
  });
}

export function usePendingJobsQuery(filters: JobsFilters) {
  return useQuery({
    queryKey: platformQueryKeys.pendingJobs(filters.limit),
    queryFn: () => getPendingJobs(filters),
    retry: false,
  });
}

export function useDeadLetterJobsQuery(filters: JobsFilters) {
  return useQuery({
    queryKey: platformQueryKeys.deadLetterJobs(filters.limit),
    queryFn: () => getDeadLetterJobs(filters),
    retry: false,
  });
}

export function useJobsRetryMutations() {
  const queryClient = useQueryClient();

  const invalidateJobs = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: platformQueryKeys.jobsSummary() }),
      queryClient.invalidateQueries({ queryKey: [...platformQueryKeys.all, 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: platformQueryKeys.monitor() }),
    ]);
  };

  return {
    retryFailed: useMutation({
      mutationFn: retryFailedJob,
      onSuccess: async () => {
        await invalidateJobs();
      },
    }),
    retryDeadLetter: useMutation({
      mutationFn: retryDeadLetterJob,
      onSuccess: async () => {
        await invalidateJobs();
      },
    }),
  };
}
