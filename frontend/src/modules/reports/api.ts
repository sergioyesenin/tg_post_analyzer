import { apiClient } from '@shared/api/client';
import { serializeReportsFilters } from '@modules/reports/filters';
import type {
  PostReportBatchMutationResponse,
  ReportType,
  ReportsExportResponseByType,
  ReportsFiltersByType,
  ReportsListResponseByType,
} from '@modules/reports/contracts';

export async function getReportsList<TType extends ReportType>(type: TType, filters: ReportsFiltersByType[TType]) {
  const query = serializeReportsFilters(type, filters);
  const path = query ? `/api/reports/${type}/list?${query}` : `/api/reports/${type}/list`;

  return apiClient.get<ReportsListResponseByType[TType]>(path);
}

export function buildReportsExportHref<TType extends ReportType>(
  type: TType,
  filters: ReportsFiltersByType[TType],
  format: 'json' | 'csv',
) {
  const query = serializeReportsFilters(type, filters);
  const suffix = query ? `${query}&format=${format}` : `format=${format}`;
  return `/api/reports/${type}/export?${suffix}`;
}

export async function getReportsExportPreview<TType extends ReportType>(type: TType, filters: ReportsFiltersByType[TType]) {
  const query = serializeReportsFilters(type, filters);
  const suffix = query ? `${query}&format=json` : 'format=json';
  return apiClient.get<ReportsExportResponseByType[TType]>(`/api/reports/${type}/export?${suffix}`);
}

export async function generatePostReportsByFilter(filters: ReportsFiltersByType['posts']) {
  const query = serializeReportsFilters('posts', filters);
  const path = query ? `/api/reports/posts/generate-by-filter?${query}` : '/api/reports/posts/generate-by-filter';

  return apiClient.post<PostReportBatchMutationResponse>(path);
}
