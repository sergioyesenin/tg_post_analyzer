import { apiClient } from '@shared/api/client';
import type {
  KeywordGraphBuildRequest,
  KeywordGraphBuildResponseDto,
  KeywordGraphReportRequest,
  KeywordGraphReportResponseDto,
  KeywordSearchFilters,
  KeywordSearchResponseDto,
} from '@modules/keyword-graph/contracts';

export function searchPostsByKeyword(filters: KeywordSearchFilters) {
  return apiClient.post<KeywordSearchResponseDto>('/api/keyword/search/posts', {
    query: filters.query,
    limit: filters.limit,
    date_from: filters.date_from ? `${filters.date_from}T00:00:00Z` : null,
    date_to: filters.date_to ? `${filters.date_to}T23:59:59Z` : null,
    channel_ids: filters.channel_ids,
  });
}

export function buildKeywordGraph(payload: KeywordGraphBuildRequest) {
  return apiClient.post<KeywordGraphBuildResponseDto>('/api/keyword/graph/build', payload);
}

export function generateKeywordGraphReport(payload: KeywordGraphReportRequest) {
  return apiClient.post<KeywordGraphReportResponseDto>('/api/keyword/graph/report', payload);
}
