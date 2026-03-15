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

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

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
      expect(screen.getByText(ru('\u041c\u0430\u0440\u0448\u0440\u0443\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d'))).toBeInTheDocument();
    });

    cleanup();

    renderProtected('/jobs', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(ru('\u041c\u0430\u0440\u0448\u0440\u0443\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d'))).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u0421\u043d\u0438\u043c\u043e\u043a \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433\u0430 \u0434\u043b\u044f admin, \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d\u043d\u044b\u0439 \u043d\u0430 GET /api/monitor/full \u0431\u0435\u0437 \u043f\u0440\u0435\u0434\u043f\u043e\u043b\u043e\u0436\u0435\u043d\u0438\u0439 \u043e \u043d\u0435\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0445 \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0432\u043a\u043b\u0430\u0434\u043a\u0430\u0445.'))).toBeInTheDocument();
    });

    expect(screen.getByText(/\u0421\u043d\u0438\u043c\u043e\u043a \u043d\u0430/u)).toBeInTheDocument();
    expect(screen.getAllByText(ru('\\u041a\\u0440\\u0438\\u0442\\u0438\\u0447\\u043d\\u043e'))[0]).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440 \u043e\u0447\u0435\u0440\u0435\u0434\u0438 \u0434\u043b\u044f admin \u0441 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043d\u044b\u043c\u0438 retry-\u0441\u0446\u0435\u043d\u0430\u0440\u0438\u044f\u043c\u0438 \u0434\u043b\u044f failed jobs \u0438 dead-letter rows.'))).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: ru('\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c failed job') })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: ru('\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c dead letter') })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: ru('\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c failed job') }));
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith('/api/jobs/failed/12/retry');
    });

    await user.click(screen.getByRole('button', { name: ru('\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c dead letter') }));
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
      expect(screen.getByText(ru('\u041d\u0435\u0442 \u043e\u0436\u0438\u0434\u0430\u044e\u0449\u0438\u0445 \u0437\u0430\u0434\u0430\u043d\u0438\u0439'))).toBeInTheDocument();
    });

    expect(screen.getByText(ru('\u041d\u0435\u0442 dead-letter \u0437\u0430\u0434\u0430\u043d\u0438\u0439'))).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u041c\u043e\u0434\u0443\u043b\u044c \u043c\u043e\u043d\u0438\u0442\u043e\u0440\u0438\u043d\u0433\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d'))).toBeInTheDocument();
    });

    cleanup();

    renderProtected('/jobs');

    await waitFor(() => {
      expect(screen.getByText(ru('\u041c\u043e\u0434\u0443\u043b\u044c \u0437\u0430\u0434\u0430\u043d\u0438\u0439 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d'))).toBeInTheDocument();
    });
  });
});

