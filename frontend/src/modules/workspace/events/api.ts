import { apiClient } from '@shared/api/client';
import type { EventGraphResponse, EventsDashboardFiltersDto, EventsDashboardResponse } from '@shared/dashboard/contracts';
import { serializeDashboardFilters } from '@shared/dashboard/filters';
import type { AcceptedJobResponse } from '@shared/jobs/contracts';

export async function getEventsDashboard(filters: EventsDashboardFiltersDto) {
  const query = serializeDashboardFilters('events', filters);
  const path = query ? `/api/dashboard/events?${query}` : '/api/dashboard/events';

  return apiClient.get<EventsDashboardResponse>(path);
}

export async function getEventGraph(eventId: number) {
  return apiClient.get<EventGraphResponse>(`/api/dashboard/events/${eventId}/graph`);
}

export async function updateEventReport(eventId: number) {
  return apiClient.post<AcceptedJobResponse>(`/api/reports/events/${eventId}/update`);
}
