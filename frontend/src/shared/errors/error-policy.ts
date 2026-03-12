import { ApiError } from '@shared/api/client';

export type AppErrorKind =
  | 'invalid_credentials'
  | 'service_unavailable'
  | 'refresh_failed'
  | 'unauthorized'
  | 'forbidden'
  | 'request_failed'
  | 'partial_data';

export type ErrorSurface = 'redirect' | 'forbidden' | 'inline' | 'non_blocking';
export type ErrorContext = 'login' | 'session_bootstrap' | 'refresh' | 'protected_route' | 'dashboard_block';

export type ErrorPolicyDecision = {
  kind: AppErrorKind;
  surface: ErrorSurface;
  blocking: boolean;
};

function getStatus(error: unknown) {
  if (error instanceof ApiError) {
    return error.status;
  }

  if (typeof error === 'object' && error !== null && 'status' in error) {
    return Number(error.status);
  }

  return null;
}

export function classifyErrorKind(error: unknown, context: ErrorContext): AppErrorKind {
  const status = getStatus(error);

  if (context === 'refresh') {
    return 'refresh_failed';
  }

  if (status === 401) {
    return context === 'login' ? 'invalid_credentials' : 'unauthorized';
  }

  if (status === 403) {
    return 'forbidden';
  }

  if (status === 503) {
    return 'service_unavailable';
  }

  return 'request_failed';
}

export function resolveErrorPolicy(error: unknown, context: ErrorContext): ErrorPolicyDecision {
  const kind = classifyErrorKind(error, context);

  switch (kind) {
    case 'invalid_credentials':
      return { kind, surface: 'inline', blocking: true };
    case 'service_unavailable':
      return { kind, surface: 'inline', blocking: true };
    case 'refresh_failed':
    case 'unauthorized':
      return { kind, surface: 'redirect', blocking: true };
    case 'forbidden':
      return { kind, surface: 'forbidden', blocking: true };
    case 'partial_data':
      return { kind, surface: 'non_blocking', blocking: false };
    default:
      return { kind, surface: 'inline', blocking: true };
  }
}

export function getErrorPolicySummary() {
  return {
    invalid_credentials: resolveErrorPolicy({ status: 401 }, 'login'),
    service_unavailable: resolveErrorPolicy({ status: 503 }, 'login'),
    refresh_failed: resolveErrorPolicy({ status: 401 }, 'refresh'),
    unauthorized: resolveErrorPolicy({ status: 401 }, 'protected_route'),
    forbidden: resolveErrorPolicy({ status: 403 }, 'protected_route'),
    generic_request_failure: resolveErrorPolicy({ status: 500 }, 'dashboard_block'),
    partial_data: {
      kind: 'partial_data' as const,
      surface: 'non_blocking' as const,
      blocking: false,
    },
  };
}
