import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import { AuthApiError } from '@shared/auth/auth-errors';
import type { SessionTokens } from '@shared/auth/session-types';
import { createPostsDashboardResponse } from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthApiMock() {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockRejectedValue(new AuthApiError('Unauthorized', 401)),
    refresh: vi.fn(),
  };
}

type AuthApiMock = ReturnType<typeof createAuthApiMock>;

describe('Login flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());
  });

  it('logs in successfully and redirects into the workspace', async () => {
    const user = userEvent.setup();
    const authApi: AuthApiMock = createAuthApiMock();

    authApi.login.mockResolvedValue({
      tokens: {
        accessToken: 'access-1',
        expiresInSeconds: 3600,
      } satisfies SessionTokens,
      roles: ['analyst'],
    });
    authApi.me.mockResolvedValue({
      id: 7,
      username: 'analyst',
      email: 'analyst@example.com',
      fullName: 'Analyst',
      isActive: true,
      isLocal: true,
      roles: ['analyst'],
      createdAt: '2026-03-13T00:00:00Z',
    });

    renderAuthHarness({
      initialEntry: '/login',
      storage: createMemoryTokenStorage(),
      authApi,
    });

    await user.type(screen.getByLabelText(/Имя пользователя/i), 'analyst');
    await user.type(screen.getByLabelText(/Пароль/i), 'AnalystPass123!');
    await user.click(screen.getByRole('button', { name: /Войти/i }));

    await waitFor(() => {
      expect(screen.getByText(/Дашборд: Посты/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/analyst@example.com/i)).toBeInTheDocument();
  });

  it('renders invalid credentials state on 401', async () => {
    const user = userEvent.setup();
    const authApi: AuthApiMock = createAuthApiMock();
    authApi.login.mockRejectedValue(new AuthApiError('Invalid credentials', 401));

    renderAuthHarness({
      initialEntry: '/login',
      storage: createMemoryTokenStorage(),
      authApi,
    });

    await user.type(screen.getByLabelText(/Имя пользователя/i), 'bad-user');
    await user.type(screen.getByLabelText(/Пароль/i), 'bad-password');
    await user.click(screen.getByRole('button', { name: /Войти/i }));

    await waitFor(() => {
      expect(screen.getByText(/Неверные учетные данные/i)).toBeInTheDocument();
    });
  });

  it('renders service unavailable state on 503', async () => {
    const user = userEvent.setup();
    const authApi: AuthApiMock = createAuthApiMock();
    authApi.login.mockRejectedValue(new AuthApiError('Local auth disabled', 503));

    renderAuthHarness({
      initialEntry: '/login',
      storage: createMemoryTokenStorage(),
      authApi,
    });

    await user.type(screen.getByLabelText(/Имя пользователя/i), 'admin');
    await user.type(screen.getByLabelText(/Пароль/i), 'AdminPass123!');
    await user.click(screen.getByRole('button', { name: /Войти/i }));

    await waitFor(() => {
      expect(screen.getByText(/Сервис аутентификации недоступен/i)).toBeInTheDocument();
    });
  });
});


