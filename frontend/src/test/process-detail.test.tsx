import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createJobResultResponse,
  createJobStatusResponse,
  createProcessDetailResponse,
  createProcessGraphResponse,
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

function renderProcessDetail(initialEntry = '/processes/201', roles: string[] = ['analyst']) {
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

describe('Process detail', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state before the detail payload resolves', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return await new Promise<ReturnType<typeof createProcessDetailResponse>>(() => undefined);
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse();
      }

      throw new Error(`Unhandled GET path in process detail loading test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getByText(/Loading process detail/i)).toBeInTheDocument();
    });
  });

  it('renders process detail and reuses the dashboard graph endpoint', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return createProcessDetailResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse();
      }

      throw new Error(`Unhandled GET path in process detail graph integration test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/processes/201');
    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes/201/graph');
    expect(screen.getAllByRole('link', { name: /Open event/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: /Lead post/i }).length).toBeGreaterThan(0);
  });

  it('navigates to related event and post context when confirmed', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return createProcessDetailResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse();
      }

      if (path === '/api/events/81') {
        return {
          event: {
            id: 81,
            title: 'Election coverage spike',
            status: 'active',
            started_at: '2026-03-12T06:30:00Z',
            ended_at: null,
            confidence: 0.88,
            created_by: 'analyst.bot',
            comments_count: 310,
            involvement: 0.57,
          },
          post_ids: [4012, 3975],
        };
      }

      if (path === '/api/dashboard/events/81/graph') {
        return {
          event: {
            event_id: 81,
            title: 'Election coverage spike',
            status: 'active',
            started_at: '2026-03-12T06:30:00Z',
            ended_at: null,
            confidence: 0.88,
            comments_count: 310,
            involvement: 0.57,
            posts_count: 2,
            root_post_id: 4012,
            report_status: 'draft',
            channels: [{ channel_id: 77, channel_username: 'signal_watch' }],
          },
          nodes: [
            {
              post_id: 4012,
              channel_id: 77,
              channel_username: 'signal_watch',
              date: '2026-03-12T06:45:00Z',
              text_preview: 'Root post drives the event graph.',
              comments_count: 170,
              views: 14300,
              involvement: 0.62,
              is_root: true,
            },
          ],
          edges: [],
        };
      }

      if (path === '/api/posts/4012') {
        return {
          id: 4012,
          channel_id: 77,
          text: 'Root post detail body.',
          date: '2026-03-12T06:45:00Z',
          comments_count: 170,
          views: 14300,
          involvement: 0.62,
        };
      }

      if (path === '/api/posts/4012/comments') {
        return [];
      }

      if (path === '/api/posts/4012/report') {
        return null;
      }

      if (path === '/api/posts/4012/links') {
        return { post_id: 4012, links: [] };
      }

      throw new Error(`Unhandled GET path in process detail navigation test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /Open event/i }).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('link', { name: /Open event/i })[0]!);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Election coverage spike/i })).toBeInTheDocument();
    });

    cleanup();
    renderProcessDetail('/processes/201');

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /Lead post/i }).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('link', { name: /Lead post/i })[0]!);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Post #4012/i })).toBeInTheDocument();
    });
  });

  it('renders forbidden and not found states from the main detail request', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        throw new ApiError('Forbidden', 403);
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse();
      }

      throw new Error(`Unhandled GET path in process detail forbidden test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getByText(/Process detail is restricted/i)).toBeInTheDocument();
    });

    vi.restoreAllMocks();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        throw new ApiError('Not found', 404);
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse();
      }

      throw new Error(`Unhandled GET path in process detail not found test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getByText(/Process not found/i)).toBeInTheDocument();
    });
  });

  it('keeps detail content visible when the hierarchy graph fails and hides mutations for viewers', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return createProcessDetailResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        throw new ApiError('Graph failed', 500);
      }

      throw new Error(`Unhandled GET path in process detail graph failure test: ${path}`);
    });

    renderProcessDetail('/processes/201', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Process graph failed to load/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Viewer access has no process report mutations/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Generate draft report/i })).not.toBeInTheDocument();
  });

  it('runs the process report action flow and invalidates process detail data', async () => {
    const user = userEvent.setup();
    let graphVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return createProcessDetailResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        graphVersion += 1;

        return createProcessGraphResponse({
          summary: {
            ...createProcessGraphResponse().summary,
            report_status: graphVersion > 1 ? 'draft' : 'missing',
          },
        });
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_process_report', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'draft', process_id: 201, report_id: 44 });
      }

      if (path === '/api/dashboard/processes') {
        return createProcessesDashboardResponse();
      }

      throw new Error(`Unhandled GET path in process detail report flow test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_process_report' }),
    );

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Generate draft report/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Generate draft report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Process report job/i)).toBeInTheDocument();
      expect(screen.getByText(/report_id: 44/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(/Draft/i).length).toBeGreaterThan(0);
    });
  });
});
