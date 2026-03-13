import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createDeadLetterJobsResponse,
  createJobsSummaryResponse,
  createMonitorFullResponse,
  createPendingJobsResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthenticatedUser(roles: string[]) {
  return {
    id: 21,
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

function renderProtected(initialEntry: string, roles: string[] = ['admin']) {
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

describe('Monitor and jobs modules', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('protects admin-only monitor and jobs routes', async () => {
    renderProtected('/monitor', ['analyst']);

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });

    cleanup();

    renderProtected('/jobs', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });
  });

  it('renders monitor overview with status system and alerts', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/monitor/full') {
        return createMonitorFullResponse();
      }

      throw new Error(`Unhandled GET path in monitor test: ${path}`);
    });

    renderProtected('/monitor');

    await waitFor(() => {
      expect(screen.getByText(/Admin-only monitor snapshot/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Snapshot at/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Critical/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/Telegram pipeline/i)[0]).toBeInTheDocument();
    expect(screen.getByText(/Retry lag is above threshold/i)).toBeInTheDocument();
  });

  it('renders jobs tables, status badges, and retry flows', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/jobs/summary') {
        return createJobsSummaryResponse();
      }

      if (path === '/api/jobs/pending?limit=100') {
        return createPendingJobsResponse();
      }

      if (path === '/api/jobs/dead-letter?limit=100') {
        return createDeadLetterJobsResponse();
      }

      throw new Error(`Unhandled GET path in jobs test: ${path}`);
    });

    const postSpy = vi.spyOn(apiClient, 'post').mockImplementation(async (path: string) => {
      if (path === '/api/jobs/failed/12/retry') {
        return { status: 'queued', job_id: 12, type: 'build_event_report' };
      }

      if (path === '/api/jobs/dead-letter/91/retry') {
        return { status: 'queued', dead_letter_id: 91, source_job_id: 12, new_job_id: 120, type: 'build_process_report' };
      }

      throw new Error(`Unhandled POST path in jobs test: ${path}`);
    });

    renderProtected('/jobs');

    await waitFor(() => {
      expect(screen.getByText(/Admin-only queue inspection/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Retry failed job/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry dead letter/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Retry failed job/i }));
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith('/api/jobs/failed/12/retry');
    });

    await user.click(screen.getByRole('button', { name: /Retry dead letter/i }));
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith('/api/jobs/dead-letter/91/retry');
    });
  });

  it('renders empty jobs states when queues are empty', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/jobs/summary') {
        return createJobsSummaryResponse({ total: 0, by_status: {} });
      }

      if (path === '/api/jobs/pending?limit=100') {
        return [];
      }

      if (path === '/api/jobs/dead-letter?limit=100') {
        return [];
      }

      throw new Error(`Unhandled GET path in jobs empty test: ${path}`);
    });

    renderProtected('/jobs');

    await waitFor(() => {
      expect(screen.getByText(/No pending jobs/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/No dead-letter jobs/i)).toBeInTheDocument();
  });

  it('renders forbidden backend states for monitor and jobs', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/monitor/full' || path === '/api/jobs/summary') {
        throw new ApiError('Forbidden', 403);
      }

      if (path === '/api/jobs/pending?limit=100' || path === '/api/jobs/dead-letter?limit=100') {
        throw new ApiError('Forbidden', 403);
      }

      throw new Error(`Unhandled GET path in forbidden state test: ${path}`);
    });

    renderProtected('/monitor');

    await waitFor(() => {
      expect(screen.getByText(/Monitor module is restricted/i)).toBeInTheDocument();
    });

    cleanup();

    renderProtected('/jobs');

    await waitFor(() => {
      expect(screen.getByText(/Jobs module is restricted/i)).toBeInTheDocument();
    });
  });
});
