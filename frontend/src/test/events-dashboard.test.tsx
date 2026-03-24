import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createChannelsResponse,
  createEventGraphResponse,
  createEventsDashboardResponse,
  createJobResultResponse,
  createJobStatusResponse,
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

function renderWorkspace(initialEntry = '/dashboard/events', roles: string[] = ['analyst']) {
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

async function selectEvent(index = 0) {
  const user = userEvent.setup();
  await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[index]);
  return user;
}

function installEventsApiMock(options?: {
  dashboard?: ReturnType<typeof createEventsDashboardResponse>;
  graph?: ReturnType<typeof createEventGraphResponse>;
  secondaryGraph?: ReturnType<typeof createEventGraphResponse>;
  jobStatus?: ReturnType<typeof createJobStatusResponse>;
  jobResult?: ReturnType<typeof createJobResultResponse>;
}) {
  const dashboard = options?.dashboard ?? createEventsDashboardResponse();
  const graph = options?.graph ?? createEventGraphResponse();
  const secondaryGraph =
    options?.secondaryGraph ??
    createEventGraphResponse({
      event: {
        event_id: 82,
        title: 'Official response cascade',
        status: 'cooling',
        started_at: '2026-03-11T14:00:00Z',
        ended_at: '2026-03-12T02:30:00Z',
        confidence: 0.73,
        report_status: 'ready',
        posts_count: 2,
        comments_count: 301,
        involvement: 0.35,
      },
      nodes: [
        {
          post_id: 4100,
          channel_id: 22,
          channel_username: 'gov_updates',
          date: '2026-03-11T14:05:00Z',
          text_preview: 'Official statement root post.',
          comments_count: 190,
          views: 20100,
          involvement: 0.41,
          is_root: true,
        },
      ],
      edges: [],
    });
  const jobStatus = options?.jobStatus ?? createJobStatusResponse({ type: 'build_event_report' });
  const jobResult = options?.jobResult ?? createJobResultResponse({ status: 'draft', event_id: 81, report_id: 23 });

  return vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
    if (path === '/api/channels/') {
      return createChannelsResponse();
    }
    if (path.startsWith('/api/dashboard/events?') || path === '/api/dashboard/events') {
      return dashboard;
    }
    if (path === '/api/dashboard/events/81/graph') {
      return graph;
    }
    if (path === '/api/dashboard/events/82/graph') {
      return secondaryGraph;
    }
    if (path === '/api/jobs/501') {
      return jobStatus;
    }
    if (path === '/api/jobs/501/result') {
      return jobResult;
    }
    throw new Error(`Unhandled GET path in events test: ${path}`);
  });
}

describe('Events dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders explicit no-selection state first and synchronizes graph/detail after selection', async () => {
    const getSpy = installEventsApiMock();
    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(ru('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u043e\u0431\u044b\u0442\u0438\u0435 \u0434\u043b\u044f \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0430 \u0433\u0440\u0430\u0444\u0430')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0442\u0440\u043e\u043a\u0443 \u0441\u043e\u0431\u044b\u0442\u0438\u044f, \u0447\u0442\u043e\u0431\u044b \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u0430\u043d\u0435\u043b\u044c \u0434\u0435\u0442\u0430\u043b\u0435\u0439 \u0438 \u0433\u0440\u0430\u0444.')).length).toBeGreaterThan(0);
    expect(getSpy).not.toHaveBeenCalledWith('/api/dashboard/events/81/graph');

    await selectEvent(0);

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\u0441\u0432\u044f\u0437\u0430\u043d\u043d\u044b\u0435 \u043f\u043e\u0441\u0442\u044b'), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: ru('\u0412\u044b\u0431\u0440\u0430\u043d\u043e') })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(ru('\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0441 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u043c \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0430\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u043d\u043e'), { exact: false })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u0442') }).length).toBeGreaterThan(0);
  });

  it('applies supported event filters from product controls', async () => {
    const user = userEvent.setup();
    const getSpy = installEventsApiMock();

    renderWorkspace('/dashboard/events?unsupported=raw');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /\u041a\u0430\u043d\u0430\u043b\u044b/i })).toBeEnabled();
    });

    await user.click(screen.getByRole('button', { name: /\u041a\u0430\u043d\u0430\u043b\u044b/i }));
    await user.click(screen.getAllByRole('button', { name: /Signal Watch/i }).find((button) => button.className.includes('dashboard-filter-chip')) as HTMLButtonElement);
    await user.click(screen.getByRole('button', { name: /\u0421\u0442\u0430\u0442\u0443\u0441/i }));
    await user.click(screen.getAllByRole('button', { name: /active/i }).find((button) => button.className.includes('dashboard-filter-chip')) as HTMLButtonElement);
    await user.click(screen.getByRole('button', { name: ru('\\u041f\\u0440\\u0438\\u043c\\u0435\\u043d\\u0438\\u0442\\u044c \\u0444\\u0438\\u043b\\u044c\\u0442\\u0440\\u044b') }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events?status=active&channel_ids=1');
    });
  });

  it('keeps selection stable and loads the graph for the selected event', async () => {
    const getSpy = installEventsApiMock();
    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await selectEvent(1);

    await waitFor(() => {
      expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events/82/graph');
    expect(screen.getAllByText(/Official response cascade/i).length).toBeGreaterThan(0);
  });

  it('preserves the selected event across dashboard refetch when the row still exists', async () => {
    const user = userEvent.setup();
    let dashboardVersion = 0;

    const getSpy = vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      if (path === '/api/dashboard/events') {
        dashboardVersion += 1;
        return createEventsDashboardResponse({
          items: [
            createEventsDashboardResponse().items[0],
            {
              ...createEventsDashboardResponse().items[1],
              title: dashboardVersion > 1 ? 'Official response cascade' : createEventsDashboardResponse().items[1].title,
            },
          ],
        });
      }

      if (path === '/api/dashboard/events/82/graph') {
        return createEventGraphResponse({
          event: {
            event_id: 82,
            title: 'Official response cascade',
            status: 'cooling',
            started_at: '2026-03-11T14:00:00Z',
            ended_at: '2026-03-12T02:30:00Z',
            confidence: 0.73,
            report_status: 'ready',
            posts_count: 2,
            comments_count: 301,
            involvement: 0.35,
          },
          nodes: [
            {
              post_id: 4100,
              channel_id: 22,
              channel_username: 'gov_updates',
              date: '2026-03-11T14:05:00Z',
              text_preview: 'Official statement root post.',
              comments_count: 190,
              views: 20100,
              involvement: 0.41,
              is_root: true,
            },
          ],
          edges: [],
        });
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse();
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_event_report', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'draft', event_id: 82, report_id: 77 });
      }

      throw new Error(`Unhandled GET path in selection refetch test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(createAcceptedJobResponse({ job_id: 501, job_type: 'build_event_report' }));

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[1]);

    await waitFor(() => {
      expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') }));

    await waitFor(() => {
      expect(screen.getByText(/report_id: 77/i)).toBeInTheDocument();
    });

    expect(getSpy.mock.calls.filter(([path]) => path === '/api/dashboard/events').length).toBeGreaterThan(1);
    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events/82/graph');
    expect(screen.getByRole('button', { name: ru('\u0412\u044b\u0431\u0440\u0430\u043d\u043e') })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText(/Official response cascade/i).length).toBeGreaterThan(0);
  });

  it('renders graph loading state for the selected event', async () => {
    let resolveGraph: ((value: ReturnType<typeof createEventGraphResponse>) => void) | undefined;
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      if (path === '/api/dashboard/events') {
        return createEventsDashboardResponse();
      }

      if (path === '/api/dashboard/events/81/graph') {
        return await new Promise<ReturnType<typeof createEventGraphResponse>>((resolve) => {
          resolveGraph = resolve;
        });
      }

      throw new Error(`Unhandled GET path in loading test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0433\u0440\u0430\u0444\u0430 \u0441\u043e\u0431\u044b\u0442\u0438\u044f'))).toBeInTheDocument();
    });

    resolveGraph?.(createEventGraphResponse());
  });

  it('renders graph empty and no-edges states without breaking the detail rail', async () => {
    installEventsApiMock({
      graph: createEventGraphResponse({ nodes: [] }),
      secondaryGraph: createEventGraphResponse({
        event: {
          event_id: 82,
          title: 'Official response cascade',
          status: 'cooling',
          started_at: '2026-03-11T14:00:00Z',
          ended_at: '2026-03-12T02:30:00Z',
          confidence: 0.73,
          report_status: 'ready',
          posts_count: 2,
          comments_count: 301,
          involvement: 0.35,
        },
        nodes: [
          {
            post_id: 4100,
            channel_id: 22,
            channel_username: 'gov_updates',
            date: '2026-03-11T14:05:00Z',
            text_preview: 'Official statement root post.',
            comments_count: 190,
            views: 20100,
            involvement: 0.41,
            is_root: true,
          },
        ],
        edges: [],
      }),
    });
    const user = userEvent.setup();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0412 \u0433\u0440\u0430\u0444\u0435 \u043d\u0435\u0442 \u0443\u0437\u043b\u043e\u0432'))).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[1]);
    await user.click(screen.getAllByRole('button', { name: ru('\\u041e\\u0442\\u043a\\u0440\\u044b\\u0442\\u044c') })[0]);
    await waitFor(() => {
      expect(screen.getByText(ru('\u0412 \u0433\u0440\u0430\u0444\u0435 \u043d\u0435\u0442 \u0440\u0435\u0431\u0435\u0440'))).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
  });

  it('renders graph error state while keeping selected event details visible', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      if (path === '/api/dashboard/events') {
        return createEventsDashboardResponse();
      }

      if (path === '/api/dashboard/events/81/graph') {
        throw new ApiError('Graph failed', 500);
      }

      throw new Error(`Unhandled GET path in graph error test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0433\u0440\u0430\u0444 \u0441\u043e\u0431\u044b\u0442\u0438\u044f'))).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    expect(screen.getByText(ru('\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0441 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u043c \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0430\u0441\u0438\u043d\u0445\u0440\u043e\u043d\u043d\u043e'), { exact: false })).toBeInTheDocument();
  });

  it('runs the event report action flow and renders the async job result', async () => {
    const user = userEvent.setup();
    let dashboardVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      if (path === '/api/dashboard/events') {
        dashboardVersion += 1;

        return createEventsDashboardResponse({
          items: [
            {
              ...createEventsDashboardResponse().items[0],
              report_status: dashboardVersion > 1 ? 'draft' : 'missing',
            },
            createEventsDashboardResponse().items[1],
          ],
        });
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse({
          event: {
            ...createEventGraphResponse().event,
            report_status: dashboardVersion > 1 ? 'draft' : 'missing',
          },
        });
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_event_report', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'draft', event_id: 81, report_id: 23 });
      }

      throw new Error(`Unhandled GET path in report flow test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_event_report' }),
    );

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0434\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u0430 \u043f\u043e \u0441\u043e\u0431\u044b\u0442\u0438\u044e'))).toBeInTheDocument();
      expect(screen.getByText(/report_id: 23/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(ru('\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a')).length).toBeGreaterThan(0);
    });
  });

  it('renders warnings and partial state as non-blocking layers for events exploration', async () => {
    const user = userEvent.setup();

    installEventsApiMock({
      dashboard: createEventsDashboardResponse({
        partial: true,
        warnings: [
          {
            code: 'events.graph.partial',
            message: 'Graph enrichment is partially unavailable for some events.',
            severity: 'warning',
          },
        ],
        items: [
          {
            ...createEventsDashboardResponse().items[0],
            graph_ready: false,
          },
          createEventsDashboardResponse().items[1],
        ],
      }),
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getByText(/Graph enrichment is partially unavailable/i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getByText(ru('\u042d\u043a\u0440\u0430\u043d \u043e\u0441\u0442\u0430\u0435\u0442\u0441\u044f \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u043c \u043f\u0440\u0438 \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e \u043e\u0431\u043e\u0433\u0430\u0449\u0435\u043d\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445'))).toBeInTheDocument();
      expect(screen.getByText(ru('\u0414\u0430\u043d\u043d\u044b\u0435 \u0433\u0440\u0430\u0444\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e'))).toBeInTheDocument();
    });
  });

  it('shows graph loading feedback during manual graph refresh', async () => {
    const user = userEvent.setup();
    let graphRequests = 0;
    let resolveRefresh: ((value: ReturnType<typeof createEventGraphResponse>) => void) | undefined;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      if (path === '/api/dashboard/events') {
        return createEventsDashboardResponse();
      }

      if (path === '/api/dashboard/events/81/graph') {
        graphRequests += 1;
        if (graphRequests === 1) {
          return createEventGraphResponse();
        }
        return await new Promise<ReturnType<typeof createEventGraphResponse>>((resolve) => {
          resolveRefresh = resolve;
        });
      }

      throw new Error(`Unhandled GET path in graph refresh test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0433\u0440\u0430\u0444') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0433\u0440\u0430\u0444\u0430 \u0441\u043e\u0431\u044b\u0442\u0438\u044f'))).toBeInTheDocument();
    });

    resolveRefresh?.(
      createEventGraphResponse({
        nodes: [
          {
            post_id: 7777,
            channel_id: 77,
            channel_username: 'signal_watch',
            date: '2026-03-12T11:30:00Z',
            text_preview: 'Refreshed graph snapshot.',
            comments_count: 99,
            views: 1234,
            involvement: 0.21,
            is_root: true,
          },
        ],
        edges: [],
      }),
    );

    await waitFor(() => {
      expect(screen.getAllByText(/Refreshed graph snapshot/i).length).toBeGreaterThan(0);
    });
  });

  it('hides event report mutation for viewer while keeping selection and graph visible', async () => {
    const user = userEvent.setup();
    installEventsApiMock();
    renderWorkspace('/dashboard/events', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0414\u043b\u044f viewer \u0441\u043a\u0440\u044b\u0442\u044b \u043c\u0443\u0442\u0430\u0446\u0438\u0438 \u043e\u0442\u0447\u0435\u0442\u043e\u0432 \u043f\u043e \u0441\u043e\u0431\u044b\u0442\u0438\u044f\u043c'))).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u043e\u0442\u0447\u0435\u0442\u0430') })).not.toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });
  });
});



