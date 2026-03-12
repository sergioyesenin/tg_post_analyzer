export class AuthApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'AuthApiError';
    this.status = status;
  }
}

export function resolveLoginState(error: unknown) {
  if (error instanceof AuthApiError) {
    if (error.status === 401) {
      return 'invalid_credentials' as const;
    }

    if (error.status === 503) {
      return 'service_unavailable' as const;
    }
  }

  if (typeof error === 'object' && error !== null && 'status' in error) {
    const status = Number(error.status);

    if (status === 401) {
      return 'invalid_credentials' as const;
    }

    if (status === 503) {
      return 'service_unavailable' as const;
    }
  }

  return 'generic_error' as const;
}

export function getLoginErrorMessage(state: 'invalid_credentials' | 'service_unavailable' | 'generic_error') {
  switch (state) {
    case 'invalid_credentials':
      return 'Неверные учетные данные. Проверь логин и пароль.';
    case 'service_unavailable':
      return 'Локальная авторизация сейчас недоступна. Проверь режим auth provider на backend.';
    default:
      return 'Не удалось выполнить вход. Повтори попытку позже.';
  }
}
