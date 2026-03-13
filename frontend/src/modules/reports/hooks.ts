import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { useAsyncJobAction } from '@shared/jobs/hooks';
import type { ReportType, ReportsFiltersByType } from '@modules/reports/contracts';
import { generatePostReportsByFilter, getReportsList } from '@modules/reports/api';
import { getDefaultReportsFilters, parseReportsFilters, serializeReportsFilters } from '@modules/reports/filters';
import { reportsQueryKeys } from '@modules/reports/query-keys';

export function useReportsFilters<TType extends ReportType>(type: TType) {
  const location = useLocation();
  const navigate = useNavigate();

  const filters = useMemo(() => parseReportsFilters(type, location.search), [location.search, type]);

  const applyFilters = (nextFilters: ReportsFiltersByType[TType]) => {
    const search = serializeReportsFilters(type, nextFilters);
    navigate(
      {
        pathname: location.pathname,
        search: search ? `?${search}` : '',
      },
      { replace: false },
    );
  };

  const resetFilters = () => {
    const defaults = getDefaultReportsFilters(type);
    const search = serializeReportsFilters(type, defaults);
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
    resetFilters,
  };
}

export function useReportsListQuery<TType extends ReportType>(type: TType, filters: ReportsFiltersByType[TType]) {
  const query = serializeReportsFilters(type, filters);

  return useQuery({
    queryKey: reportsQueryKeys.list(type, query),
    queryFn: () => getReportsList(type, filters),
    retry: false,
  });
}

export function useGeneratePostReportsByFilterAction(filters: ReportsFiltersByType['posts']) {
  const queryClient = useQueryClient();

  return useAsyncJobAction({
    actionLabel: 'Generate post reports by filter',
    mutationFn: () => generatePostReportsByFilter(filters),
    onInvalidate: async () => {
      await queryClient.invalidateQueries({ queryKey: reportsQueryKeys.all });
    },
  });
}
