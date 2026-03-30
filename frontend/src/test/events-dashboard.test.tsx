import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createChannelsResponse,
  createEventGraphResponse,
  createEventsDashboardResponse,
  createKeywordSearchResponse,
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

function installEventsKeywordSearchApiMock(response = createKeywordSearchResponse()) {
  return vi.spyOn(apiClient, 'post').mockImplementation(async (path: string, body?: unknown) => {
    if (path === '/api/keyword/search/posts') {
      return response;
    }

    throw new Error(`Unhandled POST path in events test: ${path} body=${JSON.stringify(body)}`);
  });
}
function installEventsKeywordSearchApiErrorMock(status: number) {
  return vi.spyOn(apiClient, 'post').mockImplementation(async (path: string) => {
    if (path === '/api/keyword/search/posts') {
      throw new ApiError(`Keyword search failed with status ${status}`, status);
    }

    throw new Error(`Unhandled POST path in events test: ${path}`);
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

    expect(screen.getAllByText(ru('\\u0421\\u043e\\u0431\\u044b\\u0442\\u0438\\u0435 \\u043d\\u0435 \\u0432\\u044b\\u0431\\u0440\\u0430\\u043d\\u043e')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0412\\u044b\\u0431\\u0435\\u0440\\u0438\\u0442\\u0435 \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u0435 \\u0432 \\u0442\\u0430\\u0431\\u043b\\u0438\\u0446\\u0435, \\u0447\\u0442\\u043e\\u0431\\u044b \\u043e\\u0442\\u043a\\u0440\\u044b\\u0442\\u044c \\u0435\\u0434\\u0438\\u043d\\u043e\\u0435 \\u0440\\u0430\\u0431\\u043e\\u0447\\u0435\\u0435 \\u043f\\u0440\\u043e\\u0441\\u0442\\u0440\\u0430\\u043d\\u0441\\u0442\\u0432\\u043e \\u0441\\u043f\\u0438\\u0441\\u043a\\u0430, \\u0433\\u0440\\u0430\\u0444\\u0430 \\u0438 \\u043f\\u0430\\u043d\\u0435\\u043b\\u0438 \\u0434\\u0435\\u0442\\u0430\\u043b\\u0435\\u0439.')).length).toBeGreaterThan(0);
    expect(getSpy).not.toHaveBeenCalledWith('/api/dashboard/events/81/graph');

    await selectEvent(0);

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0422\\u0430\\u0431\\u043b\\u0438\\u0446\\u0430, \\u0433\\u0440\\u0430\\u0444 \\u0438 \\u043f\\u0440\\u0430\\u0432\\u0430\\u044f \\u043f\\u0430\\u043d\\u0435\\u043b\\u044c \\u0441\\u0435\\u0439\\u0447\\u0430\\u0441 \\u0441\\u0438\\u043d\\u0445\\u0440\\u043e\\u043d\\u0438\\u0437\\u0438\\u0440\\u043e\\u0432\\u0430\\u043d\\u044b \\u0432\\u043e\\u043a\\u0440\\u0443\\u0433 \\u044d\\u0442\\u043e\\u0433\\u043e \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u044f.')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\u0441\u0432\u044f\u0437\u0430\u043d\u043d\u044b\u0435 \u043f\u043e\u0441\u0442\u044b'), { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: ru('\u0412\u044b\u0431\u0440\u0430\u043d\u043e') })).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelector('.dashboard-table-shell__row--selected')).not.toBeNull();
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


  it('renders keyword search controls for events, calls search endpoint, and filters rows by matched post ids', async () => {
    const user = userEvent.setup();
    const getSpy = installEventsApiMock();
    const postSpy = installEventsKeywordSearchApiMock(createKeywordSearchResponse({ total: 1, items: [createKeywordSearchResponse().items[0]] }));

    renderWorkspace('/dashboard/events?date_from=2026-03-01&date_to=2026-03-10&channel_ids=7');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeDisabled();
    });
    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441'));
    fireEvent.change(searchInput, { target: { value: 'a' } });
    expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeDisabled();

    const snapshotCallsBeforeSubmit = getSpy.mock.calls.length;
    fireEvent.change(searchInput, { target: { value: 'policy shift' } });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeEnabled();
    });

    await user.click(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith('/api/keyword/search/posts', {
        query: 'policy shift',
        limit: 25,
        date_from: '2026-03-01T00:00:00Z',
        date_to: '2026-03-10T23:59:59Z',
        channel_ids: [7],
      });
    });

    expect(getSpy).toHaveBeenCalledTimes(snapshotCallsBeforeSubmit);
    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
      expect(screen.queryByText(/Official response cascade/i)).not.toBeInTheDocument();
    });
  });

  it('shows mapped empty state when keyword search finds posts but no events intersect the current snapshot', async () => {
    installEventsApiMock();
    installEventsKeywordSearchApiMock(
      createKeywordSearchResponse({
        query: 'policy',
        normalized_query: 'policy',
        lemmas: ['policy'],
        total: 1,
        items: [
          {
            post_id: 999999,
            channel_id: 77,
            channel_username: 'signal_watch',
            date: '2026-03-12T10:10:00Z',
            text_preview: 'No mapped event row',
            comments_count: 5,
            views: 100,
            involvement: 0.05,
            rank: 0.99,
            matched_lemmas: ['policy'],
          },
        ],
      }),
    );

    renderWorkspace('/dashboard/events?query=policy');

    await waitFor(() => {
      expect(screen.queryByText(/Загрузка дашборда событий/i)).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.queryByText(/Election coverage spike/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Official response cascade/i)).not.toBeInTheDocument();
      expect(screen.getAllByText(/По текущему запросу события не найдены в этой выборке/i).length).toBeGreaterThan(0);
      expect(
        screen.getByText(
          /Поиск по постам вернул совпадения, но они не сматчились ни с одним событием в текущем snapshot/i,
        ),
      ).toBeInTheDocument();
    });
  });

  it('shows forbidden search message when backend returns 403 for keyword search', async () => {
    installEventsApiMock();
    installEventsKeywordSearchApiErrorMock(403);

    renderWorkspace('/dashboard/events?query=policy');

    await waitFor(() => {
      expect(screen.getByText(/Поиск недоступен для вашей роли/i)).toBeInTheDocument();
    });
  });

  it('restores event keyword query from URL and clears it with reset search', async () => {
    const user = userEvent.setup();
    const getSpy = installEventsApiMock();
    const postSpy = installEventsKeywordSearchApiMock(createKeywordSearchResponse({ total: 1, items: [createKeywordSearchResponse().items[0]] }));

    renderWorkspace('/dashboard/events?query=policy%20shift');
    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue('policy shift')).toBeInTheDocument();
      expect(screen.queryByText(/Official response cascade/i)).not.toBeInTheDocument();
    });

    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events');
    expect(postSpy).toHaveBeenCalledWith('/api/keyword/search/posts', {
      query: 'policy shift',
      limit: 25,
      date_from: null,
      date_to: null,
      channel_ids: [],
    });

    await user.click(screen.getByRole('button', { name: /\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u043e\u0438\u0441\u043a/i }));
    await waitFor(() => {
      expect((screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441')) as HTMLInputElement).value).toBe('');
      expect(screen.getAllByText(/Official response cascade/i).length).toBeGreaterThan(0);
    });
  });

  it('keeps selection and right rail scoped to the filtered event rows', async () => {
    const user = userEvent.setup();
    installEventsApiMock();
    installEventsKeywordSearchApiMock(createKeywordSearchResponse({ total: 1, items: [createKeywordSearchResponse().items[0]] }));

    renderWorkspace('/dashboard/events');

    await waitFor(() => {
      expect(screen.getAllByText(/Election coverage spike/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[1]);

    await waitFor(() => {
      expect(screen.getAllByText(/Official statement root post/i).length).toBeGreaterThan(0);
    });

    fireEvent.change(screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441')), { target: { value: 'policy shift' } });
    await user.click(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i }));

    await waitFor(() => {
      expect(screen.queryByText(/Official response cascade/i)).not.toBeInTheDocument();
      expect(screen.getAllByText(ru('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u043e\u0431\u044b\u0442\u0438\u0435 \u0434\u043b\u044f \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0430 \u0433\u0440\u0430\u0444\u0430')).length).toBeGreaterThan(0);
      expect(screen.queryByText(/Official statement root post/i)).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') }));

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
      expect(screen.queryByText(/Official response cascade/i)).not.toBeInTheDocument();
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
      expect(screen.getByText(ru('\\u0417\\u0430\\u0433\\u0440\\u0443\\u0437\\u043a\\u0430 \\u0433\\u0440\\u0430\\u0444\\u0430 \\u0441\\u043e\\u0431\\u044b\\u0442\\u0438\\u044f'))).toBeInTheDocument();
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
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: ru('\\u041e\\u0431\\u043d\\u043e\\u0432\\u0438\\u0442\\u044c \\u0433\\u0440\\u0430\\u0444') })).toBeDisabled();
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
    expect(screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441'))).toBeDisabled();
    expect(screen.getByRole('button', { name: /^\u041d\u0430\u0439\u0442\u0438$/i })).toBeDisabled();
    expect(screen.getByText(/\u041f\u043e\u0438\u0441\u043a \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0434\u043b\u044f \u0432\u0430\u0448\u0435\u0439 \u0440\u043e\u043b\u0438/i)).toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c') })[0]);

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });
  });
});



















