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

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

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
      expect(screen.getByText(ru('\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0434\u0435\u0442\u0430\u043b\u0435\u0439 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430'))).toBeInTheDocument();
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
    expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435') }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: ru('\u0412\u0435\u0434\u0443\u0449\u0438\u0439 \u043f\u043e\u0441\u0442') }).length).toBeGreaterThan(0);
  });

  it('renders limited process report status and mapped stage topics', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/processes/201') {
        return createProcessDetailResponse({
          latest_report: {
            id: 802,
            status: 'limited',
            version: 6,
            report_text: 'Process report text.',
            report_json: {
              summary: 'Сводка по процессу с ограничениями.',
              stage_analysis: [{ main_topics: ['эскалация', 'реакция'] }],
            },
            created_at: '2026-03-13T08:45:00Z',
          },
        });
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse({
          summary: {
            ...createProcessGraphResponse().summary,
            report_status: 'limited',
          },
        });
      }

      throw new Error(`Unhandled GET path in limited process detail test: ${path}`);
    });

    renderProcessDetail();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByLabelText(/Статус отчета: Ограничен/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Сводка по процессу с ограничениями/i)).toBeInTheDocument();
    expect(screen.getByText(/эскалация, реакция/i)).toBeInTheDocument();
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
      expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435') }).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435') })[0]!);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Election coverage spike/i })).toBeInTheDocument();
    });

    cleanup();
    renderProcessDetail('/processes/201');

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: ru('\u0412\u0435\u0434\u0443\u0449\u0438\u0439 \u043f\u043e\u0441\u0442') }).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('link', { name: ru('\u0412\u0435\u0434\u0443\u0449\u0438\u0439 \u043f\u043e\u0441\u0442') })[0]!);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: ru('\\u041f\\u043e\\u0441\\u0442 #4012') })).toBeInTheDocument();
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
      expect(screen.getByText(ru('\\u0414\\u0435\\u0442\\u0430\\u043b\\u0438 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441\\u0430 \\u043d\\u0435\\u0434\\u043e\\u0441\\u0442\\u0443\\u043f\\u043d\\u044b'))).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u041f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d'))).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0433\u0440\u0430\u0444 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430'))).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') })).not.toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u0430 \u043f\u043e \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0443'))).toBeInTheDocument();
      expect(screen.getByText(/report_id: 44/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(ru('\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a')).length).toBeGreaterThan(0);
    });
  });
});


