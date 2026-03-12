import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthApiError } from '@shared/auth/auth-errors';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

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
  });

  it('redirects guest users from protected routes to /login', async () => {
    renderAuthHarness({
      authApi: createAuthApiMock(),
      initialEntry: '/dashboard/posts',
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Sign in to the analytics workspace/i })).toBeInTheDocument();
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
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('link', { name: /Channels/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Keyword graph/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Hidden navigation and direct route access use the same policy source/i)).toBeInTheDocument();
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
      expect(screen.getByText(/Keyword graph placeholder/i)).toBeInTheDocument();
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
      expect(screen.getByText(/Posts dashboard foundation/i)).toBeInTheDocument();
    });
  });
});
