import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import {
  createEventsDashboardResponse,
  createPostsDashboardResponse,
  createProcessesDashboardResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthenticatedUser(roles: string[]) {
  return {
    id: 11,
    username: roles[0],
    email: `${roles[0]}@example.com`,
    fullName: roles[0],
    isActive: true,
    isLocal: true,
    roles,
    createdAt: '2026-03-13T00:00:00Z',
  };
}

function createAuthApiMock(roles: string[]) {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue(createAuthenticatedUser(roles)),
    refresh: vi.fn(),
  } as never;
}

function renderWorkspace(initialEntry: string, roles: string[] = ['analyst']) {
  return renderAuthHarness({
    authApi: createAuthApiMock(roles),
    storage: createMemoryTokenStorage({
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      expiresInSeconds: 3600,
    }),
    initialEntry,
  });
}

describe('Dashboard workspace shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/dashboard/events')) {
        return createEventsDashboardResponse();
      }

      if (path.startsWith('/api/dashboard/processes')) {
        return createProcessesDashboardResponse({
          partial: true,
          warnings: [
            {
              code: 'processes.graph.partial',
              message: 'Process graph snapshot is incomplete.',
              severity: 'warning',
            },
          ],
        });
      }

      return createPostsDashboardResponse();
    });
  });

  it('renders generated_at on all dashboard screens', async () => {
    for (const route of ['/dashboard/posts', '/dashboard/events', '/dashboard/processes']) {
      cleanup();
      renderWorkspace(route);

      await waitFor(() => {
        expect(screen.getByText(/Generated at/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/Mar 13, 2026, 8:45 AM UTC/i)).toBeInTheDocument();
    }
  });

  it('renders warnings and partial state as non-blocking system layers', async () => {
    renderWorkspace('/dashboard/processes');

    await waitFor(() => {
      expect(screen.getByText(/Screen stays usable with partially enriched data/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Snapshot includes non-blocking warnings/i)).toBeInTheDocument();
    expect(screen.getByText(/Process graph snapshot is incomplete/i)).toBeInTheDocument();
  });

  it('computes mode switch links with shared filter preservation only', async () => {
    renderWorkspace('/dashboard/events?date_from=2026-03-01&channel_ids=7&status=active&sort_by=posts_count&sort_order=asc');

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Processes' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'Processes' })).toHaveAttribute(
      'href',
      '/dashboard/processes?date_from=2026-03-01&sort_order=asc',
    );
  });

  it('shows role-aware navigation visibility for viewer', async () => {
    renderWorkspace('/dashboard/posts', ['viewer']);

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Workspace' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Keyword graph' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Channels' })).not.toBeInTheDocument();
  });

  it('applies filter edits back into URL-owned state', async () => {
    const user = userEvent.setup();
    renderWorkspace('/dashboard/posts');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply filters/i })).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/Date from/i));
    await user.type(screen.getByLabelText(/Date from/i), '2026-03-01');
    await user.selectOptions(screen.getByLabelText(/Sort order/i), 'asc');
    await user.click(screen.getByRole('button', { name: /Apply filters/i }));

    expect(screen.getByText('date_from=2026-03-01&sort_order=asc')).toBeInTheDocument();
  });
});
