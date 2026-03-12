import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createEventGraphResponse,
  createEventsDashboardResponse,
  createJobResultResponse,
  createJobStatusResponse,
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

  it('renders events dashboard summary, table, graph area, and detail panel', async () => {
    installEventsApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Linked posts/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Draft report action runs async/i)).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Open post/i }).length).toBeGreaterThan(0);
  });

  it('keeps selection stable and loads the graph for the selected event', async () => {
    const user = userEvent.setup();
    const getSpy = installEventsApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: /Inspect/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events/82/graph');
    expect(screen.getAllByText(/Official response cascade/i).length).toBeGreaterThan(0);
  });

  it('renders graph loading state for the selected event', async () => {
    let resolveGraph: ((value: ReturnType<typeof createEventGraphResponse>) => void) | undefined;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
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
      expect(screen.getByText(/Loading event graph/i)).toBeInTheDocument();
    });

    if (resolveGraph) {
      resolveGraph(createEventGraphResponse());
    }
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
      expect(screen.getByText(/No graph nodes are available/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Inspect/i }));

    await waitFor(() => {
      expect(screen.getByText(/Graph has no edges/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
  });

  it('renders graph error state while keeping selected event details visible', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
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
      expect(screen.getByText(/Event graph failed to load/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Draft report action runs async/i)).toBeInTheDocument();
  });

  it('runs the event report action flow and renders the async job result', async () => {
    const user = userEvent.setup();
    let dashboardVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
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
      expect(screen.getByRole('button', { name: /Generate draft report/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Generate draft report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Event report job/i)).toBeInTheDocument();
      expect(screen.getByText(/report_id: 23/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(/Draft/i).length).toBeGreaterThan(0);
    });
  });

  it('renders warnings and partial state as non-blocking layers for events exploration', async () => {
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

    expect(screen.getByText(/Screen stays usable with partially enriched data/i)).toBeInTheDocument();
    expect(screen.getByText(/Graph data is partially available/i)).toBeInTheDocument();
  });

  it('hides event report mutation for viewer while keeping selection and graph visible', async () => {
    installEventsApiMock();

    renderWorkspace('/dashboard/events', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Viewer access hides event report mutations/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /Generate draft report/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Update draft report/i })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });
  });
});
