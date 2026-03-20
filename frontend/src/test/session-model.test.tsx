import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import type { AuthApiContract } from '@shared/auth/auth-api';
import { AuthApiError } from '@shared/auth/auth-errors';
import type { SessionTokens } from '@shared/auth/session-types';
import { createPostsDashboardResponse } from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

function createAuthApiMock(overrides: Partial<AuthApiContract> = {}): AuthApiContract {
  return {
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue({ status: 'ok', refresh_revoked: true }),
    me: vi.fn().mockRejectedValue(new AuthApiError('Unauthorized', 401)),
    refresh: vi.fn().mockRejectedValue(new AuthApiError('Unauthorized', 401)),
    ...overrides,
  };
}

describe('Session model', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());
  });

  it('bootstraps an authenticated session via refresh cookie flow when no token is preloaded', async () => {
    const authApi = createAuthApiMock({
      refresh: vi.fn().mockResolvedValue({
        tokens: {
          accessToken: 'refreshed-access',
          expiresInSeconds: 3600,
        } satisfies SessionTokens,
        roles: ['analyst'],
      }),
      me: vi.fn().mockResolvedValue({
        id: 7,
        username: 'analyst',
        email: 'analyst@example.com',
        fullName: 'Analyst',
        isActive: true,
        isLocal: true,
        roles: ['analyst'],
        createdAt: '2026-03-13T00:00:00Z',
      }),
    });

    renderAuthHarness({
      initialEntry: '/dashboard/posts',
      storage: createMemoryTokenStorage(),
      authApi,
    });

    await waitFor(() => {
      expect(screen.getByText(/analyst@example.com/i)).toBeInTheDocument();
    });

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
  });

  it('logs out, clears local access state, and returns to the login screen', async () => {
    const user = userEvent.setup();
    const authApi = createAuthApiMock({
      me: vi.fn().mockResolvedValue({
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        fullName: 'Admin',
        isActive: true,
        isLocal: true,
        roles: ['admin'],
        createdAt: '2026-03-13T00:00:00Z',
      }),
    });

    renderAuthHarness({
      initialEntry: '/dashboard/posts',
      storage: createMemoryTokenStorage({
        accessToken: 'admin-access',
        expiresInSeconds: 3600,
      }),
      authApi,
    });

    await waitFor(() => {
      expect(screen.getByText(/admin@example.com/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\\u0412\\u044b\\u0439\\u0442\\u0438') }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: ru('\\u0412\\u0445\\u043e\\u0434 \\u0432 \\u0430\\u043d\\u0430\\u043b\\u0438\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u043e\\u0435 \\u0440\\u0430\\u0431\\u043e\\u0447\\u0435\\u0435 \\u043f\\u0440\\u043e\\u0441\\u0442\\u0440\\u0430\\u043d\\u0441\\u0442\\u0432\\u043e') })).toBeInTheDocument();
    });

    expect(authApi.logout).toHaveBeenCalledTimes(1);
  });
});

