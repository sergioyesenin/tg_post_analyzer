import { apiClient } from '@shared/api/client';
import type { KeywordSearchFilters, KeywordSearchResponseDto } from '@shared/search/contracts';

export function searchPostsByKeyword(filters: KeywordSearchFilters) {
  return apiClient.post<KeywordSearchResponseDto>('/api/keyword/search/posts', {
    query: filters.query,
    limit: filters.limit,
    date_from: filters.date_from ? `${filters.date_from}T00:00:00Z` : null,
    date_to: filters.date_to ? `${filters.date_to}T23:59:59Z` : null,
    channel_ids: filters.channel_ids,
  });
}