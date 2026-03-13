export const processDetailQueryKeys = {
  all: ['process-detail'] as const,
  detail: (processId: number) => [...processDetailQueryKeys.all, 'detail', processId] as const,
} as const;
