import { apiClient } from '@shared/api/client';
import type { ProcessGraphResponse, ProcessesDashboardFiltersDto, ProcessesDashboardResponse } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export async function getProcessesDashboard(filters: ProcessesDashboardFiltersDto) {
  const query = serializeDashboardFilters('processes', filters);
  const path = query ? `/api/dashboard/processes?${query}` : '/api/dashboard/processes';

  return apiClient.get<ProcessesDashboardResponse>(path);
}

export async function getProcessGraph(processId: number) {
  return apiClient.get<ProcessGraphResponse>(`/api/dashboard/processes/${processId}/graph`);
}

export async function updateProcessReport(processId: number) {
  return apiClient.post<AcceptedJobResponse>(`/api/reports/processes/${processId}/update`);
}
