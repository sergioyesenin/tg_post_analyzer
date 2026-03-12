export type DashboardMode = 'posts' | 'events' | 'processes';

export type DashboardWarning = {
  code: string;
  message: string;
  severity: 'info' | 'warning' | 'error';
};

export type PartialDashboardState = {
  partial: boolean;
  warnings: DashboardWarning[];
};

export type DashboardEnvelope<TSummary, TItem, TMeta, TFilters = Record<string, unknown>> =
  PartialDashboardState & {
    mode: DashboardMode;
    generated_at: string;
    filters_applied: TFilters;
    summary: TSummary;
    items: TItem[];
    meta: TMeta;
  };
