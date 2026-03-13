import type { ReportType } from '@modules/reports/contracts';

export const reportsQueryKeys = {
  all: ['reports'] as const,
  list: <TType extends ReportType>(type: TType, query: string) => [...reportsQueryKeys.all, type, 'list', query || 'default'] as const,
} as const;
