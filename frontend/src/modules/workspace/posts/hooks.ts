import { useQuery } from '@tanstack/react-query';

import type { PostsDashboardFiltersDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { keepPreviousData } from '@shared/query/placeholder-data';
import { getPostsDashboard } from '@modules/workspace/posts/api';

export function usePostsDashboardQuery(filters: PostsDashboardFiltersDto) {
  const query = serializeDashboardFilters('posts', filters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('posts', query || 'default'),
    queryFn: () => getPostsDashboard(filters),
    placeholderData: keepPreviousData,
    retry: false,
  });
}
