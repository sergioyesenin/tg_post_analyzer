import { i18n } from '@shared/i18n/i18n';
import { classifyErrorKind } from '@shared/errors/error-policy';

export class AuthApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'AuthApiError';
    this.status = status;
  }
}

export function resolveLoginState(error: unknown) {
  const kind = classifyErrorKind(error, 'login');

  if (kind === 'invalid_credentials' || kind === 'service_unavailable') {
    return kind;
  }

  return 'generic_error' as const;
}

export function getLoginErrorMessage(state: 'invalid_credentials' | 'service_unavailable' | 'generic_error') {
  switch (state) {
    case 'invalid_credentials':
      return i18n.t('auth.login.errors.invalidCredentials', {
        defaultValue: 'Invalid credentials. Check the username and password and try again.',
      });
    case 'service_unavailable':
      return i18n.t('auth.login.errors.serviceUnavailable', {
        defaultValue: 'Authentication service is unavailable. Check backend auth mode and try again later.',
      });
    default:
      return i18n.t('auth.login.errors.generic', {
        defaultValue: 'Login failed. Try again later.',
      });
  }
}
