import { apiClient } from '@shared/api/client';
import type {
  KeywordGraphBuildRequest,
  KeywordGraphBuildResponseDto,
  KeywordGraphReportRequest,
  KeywordGraphReportResponseDto,
} from '@modules/keyword-graph/contracts';

export { searchPostsByKeyword } from '@shared/search/api';

export function buildKeywordGraph(payload: KeywordGraphBuildRequest) {
  return apiClient.post<KeywordGraphBuildResponseDto>('/api/keyword/graph/build', payload);
}

export function generateKeywordGraphReport(payload: KeywordGraphReportRequest) {
  return apiClient.post<KeywordGraphReportResponseDto>('/api/keyword/graph/report', payload);
}