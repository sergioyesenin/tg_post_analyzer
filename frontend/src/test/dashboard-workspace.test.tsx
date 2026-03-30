import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@shared/api/client';
import {
  createChannelsResponse,
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
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

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
        expect(screen.getByText(/РЎС„РѕСЂРјРёСЂРѕРІР°РЅРѕ/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/13 РјР°СЂ. 2026 Рі., 08:45 UTC/i)).toBeInTheDocument();
    }
  });

  it('renders warnings and partial state as non-blocking system layers', async () => {
    renderWorkspace('/dashboard/processes');

    await waitFor(() => {
      expect(screen.getByText(/Р­РєСЂР°РЅ РѕСЃС‚Р°РµС‚СЃСЏ РґРѕСЃС‚СѓРїРЅС‹Рј РїСЂРё С‡Р°СЃС‚РёС‡РЅРѕ РѕР±РѕРіР°С‰РµРЅРЅС‹С… РґР°РЅРЅС‹С…/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/РЎРЅРёРјРѕРє СЃРѕРґРµСЂР¶РёС‚ РЅРµР±Р»РѕРєРёСЂСѓСЋС‰РёРµ РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёСЏ/i)).toBeInTheDocument();
    expect(screen.getByText(/Process graph snapshot is incomplete/i)).toBeInTheDocument();
  });

  it('computes mode switch links with shared filter preservation only', async () => {
    renderWorkspace('/dashboard/events?query=policy%20shift&date_from=2026-03-01&channel_ids=7&status=active&sort_by=posts_count&sort_order=asc');

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'РџСЂРѕС†РµСЃСЃС‹' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'РџСЂРѕС†РµСЃСЃС‹' })).toHaveAttribute(
      'href',
      '/dashboard/processes?query=policy+shift&date_from=2026-03-01&sort_order=asc',
    );
  });

  it('shows role-aware navigation visibility for viewer', async () => {
    renderWorkspace('/dashboard/posts', ['viewer']);

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Р Р°Р±РѕС‡РµРµ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ' })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'РћС‚С‡РµС‚С‹' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Р“СЂР°С„ РєР»СЋС‡РµРІС‹С… СЃР»РѕРІ' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'РљР°РЅР°Р»С‹' })).not.toBeInTheDocument();
  });

  it('renders a compact analytics session block without email and keeps logout available', async () => {
    renderWorkspace('/dashboard/posts', ['admin', 'analyst']);

    await waitFor(() => {
      expect(document.querySelector('.app-session-chip__row--secondary .app-session-chip__action')).not.toBeNull();
    });

    expect(screen.queryByText('admin@example.com')).not.toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText('admin / analyst')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^ru$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^en$/i })).toBeInTheDocument();
  });

  it('applies filter edits back into URL-owned state', async () => {
    const user = userEvent.setup();
    renderWorkspace('/dashboard/posts');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /РџСЂРёРјРµРЅРёС‚СЊ С„РёР»СЊС‚СЂС‹/i })).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/Р”Р°С‚Р° РѕС‚/i));
    await user.type(screen.getByLabelText(/Р”Р°С‚Р° РѕС‚/i), '2026-03-01');
    await user.selectOptions(screen.getByLabelText(/РџРѕСЂСЏРґРѕРє/i), 'asc');
    await user.click(screen.getByRole('button', { name: /РџСЂРёРјРµРЅРёС‚СЊ С„РёР»СЊС‚СЂС‹/i }));

    await waitFor(() => {
      expect(screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/dashboard/posts?date_from=2026-03-01&sort_order=asc')).toBeDefined();
    });
  });
});





