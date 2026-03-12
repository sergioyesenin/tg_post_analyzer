import type {
  DashboardTransportResponse,
  EventGraphResponse,
  ProcessGraphResponse,
} from '@shared/dashboard/contracts';

export type DashboardViewModel<TTransport extends DashboardTransportResponse = DashboardTransportResponse> = {
  transport: TTransport;
  generatedAt: string;
  isPartial: boolean;
  warnings: TTransport['warnings'];
};

export type EventGraphViewModel = {
  transport: EventGraphResponse;
};

export type ProcessGraphViewModel = {
  transport: ProcessGraphResponse;
};

export function mapDashboardResponseToViewModel<TTransport extends DashboardTransportResponse>(
  response: TTransport,
): DashboardViewModel<TTransport> {
  return {
    transport: response,
    generatedAt: response.generated_at,
    isPartial: response.partial,
    warnings: response.warnings,
  };
}

export function mapEventGraphResponseToViewModel(response: EventGraphResponse): EventGraphViewModel {
  return { transport: response };
}

export function mapProcessGraphResponseToViewModel(response: ProcessGraphResponse): ProcessGraphViewModel {
  return { transport: response };
}
