export const platformQueryKeys = {
  all: ['platform'] as const,
  monitor: () => [...platformQueryKeys.all, 'monitor', 'full'] as const,
  jobsSummary: () => [...platformQueryKeys.all, 'jobs', 'summary'] as const,
  pendingJobs: (limit: number) => [...platformQueryKeys.all, 'jobs', 'pending', limit] as const,
  deadLetterJobs: (limit: number) => [...platformQueryKeys.all, 'jobs', 'dead-letter', limit] as const,
};
