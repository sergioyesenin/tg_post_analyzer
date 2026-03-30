import { useQuery } from '@tanstack/react-query';

import type { PostsDashboardFiltersDto } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import { dashboardQueryKeys } from '@shared/dashboard/query-keys';
import { keepPreviousData } from '@shared/query/placeholder-data';
import { searchPostsByKeyword } from '@modules/keyword-graph/api';
import type { KeywordSearchFilters } from '@modules/keyword-graph/contracts';
import { getPostsDashboard } from '@modules/workspace/posts/api';

function getPostsSnapshotFilters(filters: PostsDashboardFiltersDto): PostsDashboardFiltersDto {
  return {
    ...filters,
    query: '',
  };
}

function getPostsKeywordSearchFilters(filters: PostsDashboardFiltersDto): KeywordSearchFilters {
  return {
    query: filters.query.trim(),
    limit: filters.limit,
    date_from: filters.date_from,
    date_to: filters.date_to,
    channel_ids: filters.channel_ids,
  };
}

export function usePostsDashboardQuery(filters: PostsDashboardFiltersDto) {
  const snapshotFilters = getPostsSnapshotFilters(filters);
  const query = serializeDashboardFilters('posts', snapshotFilters);

  return useQuery({
    queryKey: dashboardQueryKeys.list('posts', query || 'default'),
    queryFn: () => getPostsDashboard(snapshotFilters),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function usePostsKeywordSearchQuery(
  filters: PostsDashboardFiltersDto,
  options?: {
    enabled?: boolean;
  },
) {
  const searchFilters = getPostsKeywordSearchFilters(filters);
  const query = serializeDashboardFilters('posts', {
    ...filters,
    categories: [],
    min_comments: null,
    report_status: [],
    sort_by: 'date',
    sort_order: 'desc',
  });
  const isEnabled = (options?.enabled ?? true) && searchFilters.query.length >= 2;

  return useQuery({
    queryKey: [...dashboardQueryKeys.mode('posts'), 'keyword-search', query || 'default'],
    queryFn: () => searchPostsByKeyword(searchFilters),
    enabled: isEnabled,
    placeholderData: keepPreviousData,
    retry: false,
  });
}
