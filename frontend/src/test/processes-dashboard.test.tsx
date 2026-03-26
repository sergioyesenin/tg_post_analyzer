import { fireEvent, screen, waitFor } from '@testing-library/react';
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
async function selectProcess(index: number) {
  const user = userEvent.setup();
  const buttons = screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') });
  await user.click(buttons[index] as HTMLButtonElement);
}

describe('Processes dashboard', () => {
  it('applies supported process filters from product controls', async () => {
    const user = userEvent.setup();
    const getSpy = installProcessesApiMock();

    renderWorkspace('/dashboard/processes?unsupported=raw');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /\u0421\u0442\u0430\u0442\u0443\u0441/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /\u0421\u0442\u0430\u0442\u0443\u0441/i }));
    await user.click(screen.getAllByRole('button', { name: /active/i }).find((button) => button.className.includes('dashboard-filter-chip')) as HTMLButtonElement);
    await user.click(screen.getByRole('button', { name: ru('\\u041f\\u0440\\u0438\\u043c\\u0435\\u043d\\u0438\\u0442\\u044c \\u0444\\u0438\\u043b\\u044c\\u0442\\u0440\\u044b') }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes?status=active');
    });
  });

  it('renders keyword search controls for processes and applies query only after submit', async () => {
    const user = userEvent.setup();
    const getSpy = installProcessesApiMock();

    renderWorkspace('/dashboard/processes');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeDisabled();
    });
    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441'));
    fireEvent.change(searchInput, { target: { value: 'pr' } });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeEnabled();
    });

    const callsBeforeSubmit = getSpy.mock.calls.length;
    expect(getSpy).toHaveBeenCalledTimes(callsBeforeSubmit);

    await user.click(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes?query=pr');
    });
  });

  it('restores process keyword query from URL and clears it with reset search', async () => {
    const user = userEvent.setup();
    const getSpy = installProcessesApiMock();

    renderWorkspace('/dashboard/processes?query=policy%20shift');

    await waitFor(() => {
      expect(screen.getByDisplayValue('policy shift')).toBeInTheDocument();
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes?query=policy+shift');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u043e\u0438\u0441\u043a/i })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: /\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u043e\u0438\u0441\u043a/i }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes');
    });
  });
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders processes dashboard summary, table, hierarchy graph, and detail panel', async () => {
    const getSpy = installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(ru('\\u0418\\u0435\\u0440\\u0430\\u0440\\u0445\\u0438\\u044f \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441\\u0430')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441 \\u0434\\u043b\\u044f \\u043f\\u0440\\u043e\\u0441\\u043c\\u043e\\u0442\\u0440\\u0430 \\u0438\\u0435\\u0440\\u0430\\u0440\\u0445\\u0438\\u0438')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u0441\\u0442\\u0440\\u043e\\u043a\\u0443 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441\\u0430, \\u0447\\u0442\\u043e\\u0431\\u044b \\u0441\\u0438\\u043d\\u0445\\u0440\\u043e\\u043d\\u0438\\u0437\\u0438\\u0440\\u043e\\u0432\\u0430\\u0442\\u044c \\u043f\\u0430\\u043d\\u0435\\u043b\\u044c \\u0434\\u0435\\u0442\\u0430\\u043b\\u0435\\u0439 \\u0438 \\u0433\\u0440\\u0430\\u0444 \\u0438\\u0435\\u0440\\u0430\\u0440\\u0445\\u0438\\u0438.')).length).toBeGreaterThan(0);
    expect(getSpy).not.toHaveBeenCalledWith('/api/dashboard/processes/201/graph');
  });

  it('renders explicit no-selection state first and synchronizes hierarchy and detail after selection', async () => {
    const getSpy = installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441 \\u0434\\u043b\\u044f \\u043f\\u0440\\u043e\\u0441\\u043c\\u043e\\u0442\\u0440\\u0430 \\u0438\\u0435\\u0440\\u0430\\u0440\\u0445\\u0438\\u0438')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u0441\\u0442\\u0440\\u043e\\u043a\\u0443 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441\\u0430, \\u0447\\u0442\\u043e\\u0431\\u044b \\u0441\\u0438\\u043d\\u0445\\u0440\\u043e\\u043d\\u0438\\u0437\\u0438\\u0440\\u043e\\u0432\\u0430\\u0442\\u044c \\u043f\\u0430\\u043d\\u0435\\u043b\\u044c \\u0434\\u0435\\u0442\\u0430\\u043b\\u0435\\u0439 \\u0438 \\u0433\\u0440\\u0430\\u0444 \\u0438\\u0435\\u0440\\u0430\\u0440\\u0445\\u0438\\u0438.')).length).toBeGreaterThan(0);
    expect(getSpy).not.toHaveBeenCalledWith('/api/dashboard/processes/201/graph');

    await selectProcess(0);

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    expect(screen.getByRole('button', { name: ru('\\u0412\\u044b\\u0431\\u0440\\u0430\\u043d\\u043e') })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0440\\u0430\\u043d\\u043d\\u044b\\u0439 \\u043f\\u0440\\u043e\\u0446\\u0435\\u0441\\u0441')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0421\\u0432\\u044f\\u0437\\u0430\\u043d\\u043d\\u044b\\u0435 \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u044f'), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: ru('\\u041e\\u0442\\u043a\\u0440\\u044b\\u0442\\u044c \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u0435') }).length).toBeGreaterThan(0);
  });

  it('keeps selection stable and loads the graph for the selected process', async () => {
    const getSpy = installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(1);

    await waitFor(() => {
      expect(screen.getAllByText(/Cleanup bulletin/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/processes/202/graph');
  });

  it('preserves the selected process across dashboard refetch when the row still exists', async () => {
    const user = userEvent.setup();
    let dashboardVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/dashboard/processes') {
        dashboardVersion += 1;

        return createProcessesDashboardResponse({
          items: [
            createProcessesDashboardResponse().items[0],
            {
              ...createProcessesDashboardResponse().items[1],
              title: dashboardVersion > 1 ? 'Cleanup response cycle' : createProcessesDashboardResponse().items[1].title,
            },
          ],
        });
      }

      if (path === '/api/dashboard/processes/202/graph') {
        return createProcessGraphResponse({
          summary: {
            ...createProcessGraphResponse().summary,
            process_id: 202,
            title: 'Cleanup response cycle',
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
      }

      throw new Error(`Unhandled GET path in selection refetch process test: ${path}`);
    });

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(1);

    await waitFor(() => {
      expect(screen.getAllByText(/Cleanup bulletin/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: ru('\\u041f\\u0440\\u0438\\u043c\\u0435\\u043d\\u0438\\u0442\\u044c \\u0444\\u0438\\u043b\\u044c\\u0442\\u0440\\u044b') }));

    await waitFor(() => {
      expect(screen.getAllByText(/Cleanup response cycle/i).length).toBeGreaterThan(0);
    });

    expect(screen.getByRole('button', { name: ru('\\u0412\\u044b\\u0431\\u0440\\u0430\\u043d\\u043e') })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByText(/Cleanup bulletin/i).length).toBeGreaterThan(0);
  });

  it('renders related events and confirmed event/post navigation from graph data', async () => {
    installProcessesApiMock();

    renderWorkspace();

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(0);

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0441\u043e\u0431\u044b\u0442\u0438\u0435') }).length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.queryByText(ru('\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0433\u0440\u0430\u0444\u0430 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430'))).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole('link', { name: ru('\u041f\u043e\u0441\u0442 #4012') })).toBeInTheDocument();
    });
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
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(0);

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

    await selectProcess(0);

    expect(screen.getByText(ru('\u042d\u043a\u0440\u0430\u043d \u043e\u0441\u0442\u0430\u0435\u0442\u0441\u044f \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u043c \u043f\u0440\u0438 \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e \u043e\u0431\u043e\u0433\u0430\u0449\u0435\u043d\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445'))).toBeInTheDocument();
    expect(screen.getByText(ru('\u0418\u0435\u0440\u0430\u0440\u0445\u0438\u044f \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e'))).toBeInTheDocument();
  });

  it('renders no-edges and empty graph states without breaking the detail rail', async () => {

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
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(0);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0418\u0435\u0440\u0430\u0440\u0445\u0438\u044f \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430'))).toBeInTheDocument();
    });

    await selectProcess(0);

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
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(0);

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0433\u0440\u0430\u0444 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430'))).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0441\\u0432\\u044f\\u0437\\u0430\\u043d\\u043d\\u044b\\u0435 \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u044f'), { exact: false }).length).toBeGreaterThan(0);
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
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
    });

    await selectProcess(0);

    await user.click(screen.getByRole('button', { name: ru('\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0433\u0440\u0430\u0444') }));

    await waitFor(() => {
      expect(screen.getAllByText(/Narrative escalation chain/i).length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: ru('\\u041e\\u0431\\u043d\\u043e\\u0432\\u0438\\u0442\\u044c \\u0433\\u0440\\u0430\\u0444') })).toBeDisabled();
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





