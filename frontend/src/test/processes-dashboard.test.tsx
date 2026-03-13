import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createJobResultResponse,
  createJobStatusResponse,
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

function renderWorkspace(initialEntry = '/dashboard/processes', roles: string[] = ['analyst']) {
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

function installProcessesApiMock(options?: {
  dashboard?: ReturnType<typeof createProcessesDashboardResponse>;
  graph?: ReturnType<typeof createProcessGraphResponse>;
  secondaryGraph?: ReturnType<typeof createProcessGraphResponse>;
  jobStatus?: ReturnType<typeof createJobStatusResponse>;
  jobResult?: ReturnType<typeof createJobResultResponse>;
}) {
  const dashboard = options?.dashboard ?? createProcessesDashboardResponse();
  const graph = options?.graph ?? createProcessGraphResponse();
  const secondaryGraph =
    options?.secondaryGraph ??
    createProcessGraphResponse({
      summary: {
        process_id: 202,
        title: 'Cleanup response cycle',
        status: 'cooling',
        started_at: '2026-03-08T10:30:00Z',
        ended_at: '2026-03-10T18:00:00Z',
        confidence: 0.71,
        report_status: 'ready',
        events_count: 1,
        posts_count: 1,
        comments_count: 220,
        involvement: 0.29,
      },
      events: [
        {
          event_id: 91,
          title: 'Cleanup bulletin',
          status: 'cooling',
          started_at: '2026-03-09T09:00:00Z',
          ended_at: '2026-03-09T18:00:00Z',
          confidence: 0.68,
          relation_type: 'closure',
          direction: 'src_to_dst',
          score: 0.63,
          post_ids: [5100],
        },
      ],
      nodes: [
        {
          post_id: 5100,
          channel_id: 28,
          channel_username: 'cleanup_watch',
          date: '2026-03-09T09:10:00Z',
          text_preview: 'Cleanup bulletin root post.',
          comments_count: 120,
          views: 6700,
          involvement: 0.29,
          is_root: true,
        },
      ],
      edges: [],
      mapping: {
        process_id: 202,
        event_to_post_ids: {
          91: [5100],
        },
      },
    });
  const jobStatus = options?.jobStatus ?? createJobStatusResponse({ type: 'build_process_report' });
  const jobResult = options?.jobResult ?? createJobResultResponse({ status: 'draft', process_id: 201, report_id: 44 });

  return vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
    if (path.startsWith('/api/dashboard/processes?') || path === '/api/dashboard/processes') {
      return dashboard;
    }

    if (path === '/api/dashboard/processes/201/graph') {
      return graph;
    }

    if (path === '/api/dashboard/processes/202/graph') {
      return secondaryGraph;
    }

    if (path === '/api/jobs/501') {
      return jobStatus;
    }

    if (path === '/api/jobs/501/result') {
      return jobResult;
    }

    throw new Error(`Unhandled GET path in processes test: ${path}`);
  });
}

describe('Processes dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders processes dashboard summary, table, hierarchy graph, and detail panel', async () => {
    installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(/Linked events/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Process hierarchy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: /Open event/i }).length).toBeGreaterThan(0);
    expect(screen.getByText(/process -> event -> post/i)).toBeInTheDocument();
  });

  it('keeps selection stable and loads the graph for the selected process', async () => {
    const user = userEvent.setup();
    const getSpy = installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: /Inspect/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Cleanup bulletin/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes/202/graph');
  });

  it('renders related events and confirmed event/post navigation from graph data', async () => {
    installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /Open event/i }).length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.queryByText(/Loading process graph/i)).not.toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /Post #4012/i })).toBeInTheDocument();
  });

  it('runs the process report action flow and renders the async job result', async () => {
    const user = userEvent.setup();
    let dashboardVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/dashboard/processes') {
        dashboardVersion += 1;

        return createProcessesDashboardResponse({
          items: [
            {
              ...createProcessesDashboardResponse().items[0],
              report_status: dashboardVersion > 1 ? 'draft' : 'missing',
            },
            createProcessesDashboardResponse().items[1],
          ],
        });
      }

      if (path === '/api/dashboard/processes/201/graph') {
        return createProcessGraphResponse({
          summary: {
            ...createProcessGraphResponse().summary,
            report_status: dashboardVersion > 1 ? 'draft' : 'missing',
          },
        });
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_process_report', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'draft', process_id: 201, report_id: 44 });
      }

      throw new Error(`Unhandled GET path in process report flow test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_process_report' }),
    );

    renderWorkspace();

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

  it('renders warnings and partial state as non-blocking layers for process hierarchy exploration', async () => {
    installProcessesApiMock({
      dashboard: createProcessesDashboardResponse({
        partial: true,
        warnings: [
          {
            code: 'processes.graph.partial',
            message: 'Process hierarchy enrichment is partially unavailable for some processes.',
            severity: 'warning',
          },
        ],
        items: [
          {
            ...createProcessesDashboardResponse().items[0],
            graph_ready: false,
          },
          createProcessesDashboardResponse().items[1],
        ],
      }),
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getByText(/Process hierarchy enrichment is partially unavailable/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Screen stays usable with partially enriched data/i)).toBeInTheDocument();
    expect(screen.getByText(/Process hierarchy is partially available/i)).toBeInTheDocument();
  });

  it('renders no-edges and empty graph states without breaking the detail rail', async () => {
    const user = userEvent.setup();

    installProcessesApiMock({
      graph: createProcessGraphResponse({ events: [], nodes: [], edges: [], mapping: { process_id: 201, event_to_post_ids: {} } }),
      secondaryGraph: createProcessGraphResponse({
        summary: {
          process_id: 202,
          title: 'Cleanup response cycle',
          status: 'cooling',
          started_at: '2026-03-08T10:30:00Z',
          ended_at: '2026-03-10T18:00:00Z',
          confidence: 0.71,
          report_status: 'ready',
          events_count: 1,
          posts_count: 1,
          comments_count: 220,
          involvement: 0.29,
        },
        events: [
          {
            event_id: 91,
            title: 'Cleanup bulletin',
            status: 'cooling',
            started_at: '2026-03-09T09:00:00Z',
            ended_at: '2026-03-09T18:00:00Z',
            confidence: 0.68,
            relation_type: 'closure',
            direction: 'src_to_dst',
            score: 0.63,
            post_ids: [5100],
          },
        ],
        nodes: [
          {
            post_id: 5100,
            channel_id: 28,
            channel_username: 'cleanup_watch',
            date: '2026-03-09T09:10:00Z',
            text_preview: 'Cleanup bulletin root post.',
            comments_count: 120,
            views: 6700,
            involvement: 0.29,
            is_root: true,
          },
        ],
        edges: [],
        mapping: {
          process_id: 202,
          event_to_post_ids: {
            91: [5100],
          },
        },
      }),
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getByText(/No process hierarchy is available/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Inspect/i }));

    await waitFor(() => {
      expect(screen.getByText(/Process graph has no post-link edges/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Cleanup bulletin/i).length).toBeGreaterThan(0);
  });

  it('renders forbidden graph state without breaking the selected process detail rail', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/dashboard/processes') {
        return createProcessesDashboardResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        throw new ApiError('Graph failed', 500);
      }

      throw new Error(`Unhandled GET path in process graph error test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getByText(/Process graph failed to load/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/related events/i)).toBeInTheDocument();
  });

  it('shows hierarchy loading feedback during manual graph refresh', async () => {
    const user = userEvent.setup();
    let graphRequests = 0;
    let resolveRefresh: ((value: ReturnType<typeof createProcessGraphResponse>) => void) | undefined;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/dashboard/processes') {
        return createProcessesDashboardResponse();
      }

      if (path === '/api/dashboard/processes/201/graph') {
        graphRequests += 1;

        if (graphRequests === 1) {
          return createProcessGraphResponse();
        }

        return await new Promise<ReturnType<typeof createProcessGraphResponse>>((resolve) => {
          resolveRefresh = resolve;
        });
      }

      throw new Error(`Unhandled GET path in process graph refresh test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: /Reload graph/i }));

    await waitFor(() => {
      expect(screen.getByText(/Loading process graph/i)).toBeInTheDocument();
    });

    resolveRefresh?.(
      createProcessGraphResponse({
        events: [
          {
            event_id: 95,
            title: 'Refreshed process event',
            status: 'active',
            started_at: '2026-03-10T10:00:00Z',
            ended_at: null,
            confidence: 0.77,
            relation_type: 'trigger',
            direction: 'src_to_dst',
            score: 0.71,
            post_ids: [9999],
          },
        ],
        nodes: [
          {
            post_id: 9999,
            channel_id: 28,
            channel_username: 'cleanup_watch',
            date: '2026-03-10T10:05:00Z',
            text_preview: 'Refreshed process hierarchy snapshot.',
            comments_count: 40,
            views: 3200,
            involvement: 0.17,
            is_root: true,
          },
        ],
        edges: [],
        mapping: {
          process_id: 201,
          event_to_post_ids: {
            95: [9999],
          },
        },
      }),
    );

    await waitFor(() => {
      expect(screen.getAllByText(/Refreshed process event/i).length).toBeGreaterThan(0);
    });
  });
});
