import type { DashboardMode } from '@shared/dashboard/contracts';

export const dashboardQueryKeys = {
  all: ['dashboard'] as const,
  mode: (mode: DashboardMode) => [...dashboardQueryKeys.all, mode] as const,
  list: (mode: DashboardMode, query: string) => [...dashboardQueryKeys.mode(mode), 'list', query] as const,
  graph: {
    event: (eventId: number) => [...dashboardQueryKeys.all, 'event-graph', eventId] as const,
    process: (processId: number) => [...dashboardQueryKeys.all, 'process-graph', processId] as const,
  },
} as const;

export const dashboardQueryKeyConventions = {
  namespace: 'dashboard',
  listSegment: 'list',
  graphSegments: {
    event: 'event-graph',
    process: 'process-graph',
  },
} as const;
