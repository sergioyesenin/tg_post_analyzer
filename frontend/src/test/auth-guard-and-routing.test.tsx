import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import { AuthApiError } from '@shared/auth/auth-errors';
import { createChannelsResponse, createPostsDashboardResponse } from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

function createAuthApiMock(overrides: Record<string, unknown> = {}) {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockRejectedValue(new AuthApiError('Unauthorized', 401)),
    refresh: vi.fn(),
    ...overrides,
  } as never;
}

describe('Auth guard and RBAC routing', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/dashboard/posts') {
        return createPostsDashboardResponse();
      }

      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new Error(`Unhandled GET path in auth guard test: ${path}`);
    });
  });

  it('redirects guest users from protected routes to /login', async () => {
    renderAuthHarness({
      authApi: createAuthApiMock(),
      initialEntry: '/dashboard/posts',
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: ru('\\u0412\\u0445\\u043e\\u0434 \\u0432 \\u0430\\u043d\\u0430\\u043b\\u0438\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u043e\\u0435 \\u0440\\u0430\\u0431\\u043e\\u0447\\u0435\\u0435 \\u043f\\u0440\\u043e\\u0441\\u0442\\u0440\\u0430\\u043d\\u0441\\u0442\\u0432\\u043e') })).toBeInTheDocument();
    });
  });

  it('shows forbidden state for authenticated viewer on admin-only route', async () => {
    renderAuthHarness({
      authApi: createAuthApiMock({
        me: vi.fn().mockResolvedValue({
          id: 2,
          username: 'viewer',
          email: 'viewer@example.com',
          fullName: null,
          isActive: true,
          isLocal: true,
          roles: ['viewer'],
          createdAt: '2026-03-13T00:00:00Z',
        }),
      }),
      storage: createMemoryTokenStorage({
        accessToken: 'viewer-access',
        refreshToken: 'viewer-refresh',
        expiresInSeconds: 3600,
      }),
      initialEntry: '/channels',
    });

    await waitFor(() => {
      expect(screen.getByText(ru('\\u041c\\u0430\\u0440\\u0448\\u0440\\u0443\\u0442 \\u043d\\u0435\\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u0435\\u043d'))).toBeInTheDocument();
    });

    expect(screen.queryByRole('link', { name: ru('\\u041a\\u0430\\u043d\\u0430\\u043b\\u044b') })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: ru('\\u0413\\u0440\\u0430\\u0444 \\u043a\\u043b\\u044e\\u0447\\u0435\\u0432\\u044b\\u0445 \\u0441\\u043b\\u043e\\u0432') })).not.toBeInTheDocument();
    expect(screen.getByText(/\/channels/)).toBeInTheDocument();
  });

  it('allows analyst to open analyst-level routes', async () => {
    renderAuthHarness({
      authApi: createAuthApiMock({
        me: vi.fn().mockResolvedValue({
          id: 3,
          username: 'analyst',
          email: 'analyst@example.com',
          fullName: 'Analyst',
          isActive: true,
          isLocal: true,
          roles: ['analyst'],
          createdAt: '2026-03-13T00:00:00Z',
        }),
      }),
      storage: createMemoryTokenStorage({
        accessToken: 'analyst-access',
        refreshToken: 'analyst-refresh',
        expiresInSeconds: 3600,
      }),
      initialEntry: '/keyword-graph',
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: ru('\\u0413\\u0440\\u0430\\u0444 \\u043a\\u043b\\u044e\\u0447\\u0435\\u0432\\u044b\\u0445 \\u0441\\u043b\\u043e\\u0432') })).toBeInTheDocument();
    });
  });

  it('redirects authenticated users away from /login into the workspace', async () => {
    renderAuthHarness({
      authApi: createAuthApiMock({
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
      }),
      storage: createMemoryTokenStorage({
        accessToken: 'admin-access',
        refreshToken: 'admin-refresh',
        expiresInSeconds: 3600,
      }),
      initialEntry: '/login',
    });

    await waitFor(() => {
      expect(screen.getByText(ru('\\u0420\\u0430\\u0431\\u043e\\u0447\\u0435\\u0435 \\u043f\\u0440\\u043e\\u0441\\u0442\\u0440\\u0430\\u043d\\u0441\\u0442\\u0432\\u043e \\u043f\\u043e\\u0441\\u0442\\u043e\\u0432'))).toBeInTheDocument();
    });
  });
});

