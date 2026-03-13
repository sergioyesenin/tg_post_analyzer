import { apiClient } from '@shared/api/client';
import { getEventGraph, updateEventReport } from '@modules/workspace/events/api';
import type { EventDetailDto } from '@modules/workspace/event-detail/contracts';

export async function getEventDetail(eventId: number) {
  return apiClient.get<EventDetailDto>(`/api/events/${eventId}`);
}

export { getEventGraph, updateEventReport };
