import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@shared/i18n/i18n';
import { apiClient } from '@shared/api/client';
import { createPostsDashboardResponse } from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthApiMock() {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 1,
      username: 'analyst',
      email: 'analyst@example.com',
      fullName: 'Analyst',
      isActive: true,
      isLocal: true,
      roles: ['analyst'],
      createdAt: '2026-03-13T00:00:00Z',
    }),
    refresh: vi.fn(),
  } as never;
}

describe('i18n', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ru');
    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());
  });

  it('renders Russian by default and switches to English', async () => {
    const user = userEvent.setup();

    renderAuthHarness({
      initialEntry: '/dashboard/posts',
      storage: createMemoryTokenStorage({
        accessToken: 'access',
        refreshToken: 'refresh',
        expiresInSeconds: 3600,
      }),
      authApi: createAuthApiMock(),
    });

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'РћС‚С‡РµС‚С‹' })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'EN' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'EN' }));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    });
  });
});

