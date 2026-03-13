import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createChannelsResponse,
  createEffectiveSettingsResponse,
  createSettingsResponse,
  createUsersResponse,
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

function renderAdmin(initialEntry: string, roles: string[] = ['admin']) {
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

describe('Admin modules', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('protects admin-only routes and keeps viewer/analyst restrictions in place', async () => {
    renderAdmin('/channels', ['analyst']);

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });

    cleanup();

    renderAdmin('/users', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });
  });

  it('renders channels CRUD UI and runs basic admin flows', async () => {
    const user = userEvent.setup();
    let channelsVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        channelsVersion += 1;
        return createChannelsResponse(
          channelsVersion > 1
            ? [
                {
                  ...createChannelsResponse()[0],
                  title: 'Updated Signal Watch',
                  is_active: false,
                },
              ]
            : createChannelsResponse(),
        );
      }

      throw new Error(`Unhandled GET path in channels test: ${path}`);
    });

    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue('OK: saved channel id=3 username=@new_channel title=None');
    const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      ...createChannelsResponse()[0],
      title: 'Updated Signal Watch',
    });
    const putSpy = vi.spyOn(apiClient, 'put').mockResolvedValue({
      ...createChannelsResponse()[0],
      is_active: true,
    });
    const deleteSpy = vi.spyOn(apiClient, 'delete').mockResolvedValue({
      status: 'deleted',
      channel_id: 1,
      username: 'signal_watch',
    });

    renderAdmin('/channels');

    await waitFor(() => {
      expect(screen.getByText(/Signal Watch/i)).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/@channel_name/i), '@new_channel');
    await user.click(screen.getByRole('button', { name: /Add channel/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith('/api/channels/add', { username: '@new_channel' });
    });

    const titleInput = screen.getByDisplayValue(/Signal Watch/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated Signal Watch');
    await user.click(screen.getByRole('button', { name: /Save channel/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('/api/channels/1', {
        title: 'Updated Signal Watch',
        category: 'media',
        is_active: false,
      });
    });

    await user.click(screen.getByRole('button', { name: /Activate/i }));

    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledWith('/api/channels/1/active?is_active=true');
    });

    await user.click(screen.getByRole('button', { name: /Delete/i }));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('/api/channels/1');
    });
  });

  it('renders users management and runs role and active update flows', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/auth/users') {
        return createUsersResponse();
      }

      throw new Error(`Unhandled GET path in users test: ${path}`);
    });

    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      id: 3,
      username: 'new_user',
      email: 'new@example.com',
      full_name: 'New User',
      is_active: true,
      is_local: true,
      roles: ['viewer'],
      created_at: '2026-03-13T08:45:00Z',
    });
    const putSpy = vi.spyOn(apiClient, 'put').mockImplementation(async (path: string, body?: unknown) => {
      if (path === '/api/auth/users/1/roles') {
        return {
          ...createUsersResponse()[0],
          roles: (body as { roles: string[] }).roles,
        };
      }

      if (path === '/api/auth/users/1/active?active=false') {
        return {
          ...createUsersResponse()[0],
          is_active: false,
        };
      }

      throw new Error(`Unhandled PUT path in users test: ${path}`);
    });

    renderAdmin('/users');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Create user/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Username/i), 'new_user');
    await user.type(screen.getByLabelText(/Password/i), 'password123');
    await user.type(screen.getByLabelText(/Email/i), 'new@example.com');
    await user.type(screen.getByLabelText(/Full name/i), 'New User');
    await user.click(screen.getAllByRole('checkbox', { name: /viewer/i })[0]!);
    await user.click(screen.getByRole('button', { name: /Create user/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalled();
    });

    await user.click(screen.getAllByRole('checkbox', { name: /^viewer$/i })[1]!);
    await user.click(screen.getByRole('button', { name: /Save roles/i }));

    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledWith(
        '/api/auth/users/1/roles',
        expect.objectContaining({ roles: expect.arrayContaining(['admin', 'viewer']) }),
      );
    });

    await user.click(screen.getByRole('button', { name: /Deactivate/i }));

    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledWith('/api/auth/users/1/active?active=false');
    });
  });

  it('enforces settings read-write boundaries between analyst and admin', async () => {
    const analystGetSpy = vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/settings/effective') {
        return createEffectiveSettingsResponse();
      }

      throw new Error(`Unhandled GET path in analyst settings test: ${path}`);
    });

    renderAdmin('/settings', ['analyst']);

    await waitFor(() => {
      expect(screen.getByText(/Analyst access is limited to effective settings/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /Save setting/i })).not.toBeInTheDocument();
    expect(analystGetSpy).not.toHaveBeenCalledWith('/api/settings/');

    cleanup();
    vi.restoreAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/settings/effective') {
        return createEffectiveSettingsResponse();
      }

      if (path === '/api/settings/') {
        return createSettingsResponse();
      }

      throw new Error(`Unhandled GET path in admin settings test: ${path}`);
    });

    const putSpy = vi.spyOn(apiClient, 'put').mockResolvedValue(createSettingsResponse()[0]);

    renderAdmin('/settings', ['admin']);

    await waitFor(() => {
      expect(screen.getByText(/Jobs configuration/i)).toBeInTheDocument();
    });

    const settingsUser = userEvent.setup();
    const jsonField = screen.getByDisplayValue(/"ai_poll_seconds": 30/i);
    await settingsUser.clear(jsonField);
    await settingsUser.paste('{"ai_poll_seconds":60,"ai_scheduler_limit":20}');
    await settingsUser.click(screen.getByRole('button', { name: /Save setting/i }));

    await waitFor(() => {
      expect(putSpy).toHaveBeenCalledWith('/api/settings/jobs', {
        description: 'Jobs configuration',
        value_json: {
          ai_poll_seconds: 60,
          ai_scheduler_limit: 20,
        },
      });
    });
  });

  it('renders forbidden backend state for settings when analyst access is denied', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/settings/effective') {
        throw new ApiError('Forbidden', 403);
      }

      throw new Error(`Unhandled GET path in settings forbidden test: ${path}`);
    });

    renderAdmin('/settings', ['analyst']);

    await waitFor(() => {
      expect(screen.getByText(/Settings module is restricted/i)).toBeInTheDocument();
    });
  });
});
