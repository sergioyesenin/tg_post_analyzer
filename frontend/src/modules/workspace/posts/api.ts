import { apiClient } from '@shared/api/client';
import type { PostsDashboardFiltersDto, PostsDashboardResponse } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';

export async function getPostsDashboard(filters: PostsDashboardFiltersDto) {
  const query = serializeDashboardFilters('posts', filters);
  const path = query ? `/api/dashboard/posts?${query}` : '/api/dashboard/posts';

  return apiClient.get<PostsDashboardResponse>(path);
}
