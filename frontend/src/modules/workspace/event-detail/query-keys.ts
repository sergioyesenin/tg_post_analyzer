export const eventDetailQueryKeys = {
  all: ['event-detail'] as const,
  detail: (eventId: number) => [...eventDetailQueryKeys.all, 'detail', eventId] as const,
} as const;
