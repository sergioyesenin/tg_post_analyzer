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
        expect(screen.getByText(/Сформировано/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/13 мар. 2026 г., 08:45 UTC/i)).toBeInTheDocument();
    }
  });

  it('renders warnings and partial state as non-blocking system layers', async () => {
    renderWorkspace('/dashboard/processes');

    await waitFor(() => {
      expect(screen.getByText(/Экран остается доступным при частично обогащенных данных/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Снимок содержит неблокирующие предупреждения/i)).toBeInTheDocument();
    expect(screen.getByText(/Process graph snapshot is incomplete/i)).toBeInTheDocument();
  });

  it('computes mode switch links with shared filter preservation only', async () => {
    renderWorkspace('/dashboard/events?date_from=2026-03-01&channel_ids=7&status=active&sort_by=posts_count&sort_order=asc');

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Процессы' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'Процессы' })).toHaveAttribute(
      'href',
      '/dashboard/processes?date_from=2026-03-01&sort_order=asc',
    );
  });

  it('shows role-aware navigation visibility for viewer', async () => {
    renderWorkspace('/dashboard/posts', ['viewer']);

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Рабочее пространство' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'Отчеты' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Граф ключевых слов' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Каналы' })).not.toBeInTheDocument();
  });

  it('applies filter edits back into URL-owned state', async () => {
    const user = userEvent.setup();
    renderWorkspace('/dashboard/posts');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Применить фильтры/i })).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/Дата от/i));
    await user.type(screen.getByLabelText(/Дата от/i), '2026-03-01');
    await user.selectOptions(screen.getByLabelText(/Порядок/i), 'asc');
    await user.click(screen.getByRole('button', { name: /Применить фильтры/i }));

    expect(screen.getByText('date_from=2026-03-01&sort_order=asc')).toBeInTheDocument();
  });
});
