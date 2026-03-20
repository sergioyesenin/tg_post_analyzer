import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createChannelsResponse,
  createCommentsResponse,
  createLinksResponse,
  createPostDetailResponse,
  createPostsDashboardResponse,
  createReportResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

function createAuthApiMock(roles: string[] = ['analyst']) {
  return {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn().mockResolvedValue({
      id: 21,
      username: roles[0],
      email: `${roles[0]}@example.com`,
      fullName: roles[0],
      isActive: true,
      isLocal: true,
      roles,
      createdAt: '2026-03-13T00:00:00Z',
    }),
    refresh: vi.fn(),
  } as never;
}

function renderPostsDashboard(initialEntry = '/dashboard/posts', roles: string[] = ['analyst']) {
  return renderAuthHarness({
    authApi: createAuthApiMock(roles),
    storage: createMemoryTokenStorage({
      accessToken: 'token',
      refreshToken: 'refresh',
      expiresInSeconds: 3600,
    }),
    initialEntry,
  });
}

function installPostsApiMock(options?: {
  dashboard?: ReturnType<typeof createPostsDashboardResponse>;
  onPath?: (path: string) => unknown | Promise<unknown>;
}) {
  const dashboard = options?.dashboard ?? createPostsDashboardResponse();

  return vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
    if (path === '/api/channels/') {
      return createChannelsResponse();
    }

    if (path.startsWith('/api/dashboard/posts')) {
      return dashboard;
    }

    if (options?.onPath) {
      return await options.onPath(path);
    }

    throw new Error(`Unhandled GET path in posts test: ${path}`);
  });
}

describe('Posts dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('parses query params into API request URL', async () => {
    const getSpy = installPostsApiMock();

    renderPostsDashboard(
      '/dashboard/posts?date_from=2026-03-01&date_to=2026-03-10&channel_ids=7&categories=media&report_status=ready&sort_by=views&sort_order=asc',
    );

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        '/api/dashboard/posts?date_from=2026-03-01&date_to=2026-03-10&channel_ids=7&categories=media&report_status=ready&sort_by=views&sort_order=asc',
      );
    });
  });

  it('applies productized filters through supported controls and resets them', async () => {
    const user = userEvent.setup();
    const getSpy = installPostsApiMock();

    renderPostsDashboard('/dashboard/posts?unsupported=raw');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Signal Watch/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Signal Watch/i }));
    await user.click(screen.getByRole('button', { name: ru('\u0413\u043e\u0442\u043e\u0432') }));
    await user.click(screen.getByRole('button', { name: ru('\u041f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c \u0444\u0438\u043b\u044c\u0442\u0440\u044b') }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/posts?channel_ids=1&report_status=ready');
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u0444\u0438\u043b\u044c\u0442\u0440\u044b') }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/dashboard/posts');
    });
  });

  it('renders posts dashboard data, summary cards, and report status badges', async () => {
    installPostsApiMock();

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(ru('\u041f\u043b\u043e\u0442\u043d\u044b\u0439 \u0441\u043f\u0438\u0441\u043e\u043a \u044d\u043b\u0435\u043c\u0435\u043d\u0442\u043e\u0432 /api/dashboard/posts'), { exact: false })).toBeInTheDocument();
    });

    expect(screen.getByText('537')).toBeInTheDocument();
    expect(screen.getAllByText(/Signal Watch/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/media/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Top post preview for posts dashboard rendering/i)).toBeInTheDocument();
    expect(screen.getAllByText(ru('\\u0413\\u043e\\u0442\\u043e\\u0432')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(ru('\\u0412 \\u043e\\u0436\\u0438\\u0434\\u0430\\u043d\\u0438\\u0438')).length).toBeGreaterThan(0);
  });

  it('renders loading state while snapshot request is pending', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation((path: string) => {
      if (path === '/api/channels/') {
        return Promise.resolve(createChannelsResponse()) as never;
      }

      return new Promise(() => undefined) as never;
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(ru('\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0434\u0430\u0448\u0431\u043e\u0440\u0434\u0430 \u043f\u043e\u0441\u0442\u043e\u0432'))).toBeInTheDocument();
    });
  });

  it('renders empty state for successful response without items', async () => {
    installPostsApiMock({
      dashboard: createPostsDashboardResponse({
        summary: {
          posts_count: 0,
          total_comments: 0,
          avg_involvement: null,
          channels_count: 0,
          reports_ready: 0,
          reports_missing: 0,
          reports_pending: 0,
          reports_failed: 0,
        },
        items: [],
      }),
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435\u0442 \u043f\u043e\u0441\u0442\u043e\u0432, \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0445 \u043f\u043e\u0434 \u0442\u0435\u043a\u0443\u0449\u0438\u0435 \u0444\u0438\u043b\u044c\u0442\u0440\u044b'))).toBeInTheDocument();
    });
  });

  it('renders error state for failed requests', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new ApiError('Failed', 500);
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0434\u0430\u0448\u0431\u043e\u0440\u0434 \u043f\u043e\u0441\u0442\u043e\u0432'))).toBeInTheDocument();
    });
  });

  it('renders forbidden state for 403 response', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new ApiError('Forbidden', 403);
    });

    renderPostsDashboard('/dashboard/posts?limit=10');

    await waitFor(() => {
      expect(screen.getByText(ru('\u0414\u0430\u0448\u0431\u043e\u0440\u0434 \u043f\u043e\u0441\u0442\u043e\u0432 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0440\u043e\u043b\u0438'))).toBeInTheDocument();
    });
  });

  it('renders partial state and warnings banner without treating snapshot as hard error', async () => {
    installPostsApiMock({
      dashboard: createPostsDashboardResponse({
        partial: true,
        warnings: [
          {
            code: 'posts.comments.pending',
            message: 'Comments enrichment is incomplete, but the list remains usable.',
            severity: 'warning',
          },
        ],
      }),
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(ru('\u0421\u043d\u0438\u043c\u043e\u043a \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043d\u0435\u0431\u043b\u043e\u043a\u0438\u0440\u0443\u044e\u0449\u0438\u0435 \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u044f'), { exact: false })).toBeInTheDocument();
    });

    expect(screen.getByText(/Comments enrichment is incomplete/i)).toBeInTheDocument();
    expect(screen.getByText(ru('\u042d\u043a\u0440\u0430\u043d \u043e\u0441\u0442\u0430\u0435\u0442\u0441\u044f \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u043c \u043f\u0440\u0438 \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e \u043e\u0431\u043e\u0433\u0430\u0449\u0435\u043d\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445'))).toBeInTheDocument();
  });

  it('navigates to post detail entry point from table actions', async () => {
    const user = userEvent.setup();

    installPostsApiMock({
      onPath: async (path) => {
        if (path === '/api/posts/4012') {
          return createPostDetailResponse({ id: 4012 });
        }

        if (path === '/api/posts/4012/comments') {
          return createCommentsResponse();
        }

        if (path === '/api/reports/post/4012') {
          return createReportResponse({ post_id: 4012 });
        }

        if (path === '/api/posts/4012/links') {
          return createLinksResponse();
        }

        throw new Error(`Unhandled GET path in test: ${path}`);
      },
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u0442') })[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u0442') })[0]);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: ru('\u041f\u043e\u0441\u0442 #4012') })).toBeInTheDocument();
    });
  });

  it('hides mutation entry points for viewer while keeping detail navigation', async () => {
    installPostsApiMock();

    renderPostsDashboard('/dashboard/posts', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(ru('\u0414\u043b\u044f viewer \u0441\u043a\u0440\u044b\u0442\u044b \u0442\u043e\u0447\u043a\u0438 \u0432\u0445\u043e\u0434\u0430 \u0432 \u043c\u0443\u0442\u0430\u0446\u0438\u0438'))).toBeInTheDocument();
    });

    expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u0442') })).toHaveLength(2);
    expect(screen.queryByRole('link', { name: ru('\u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438') })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: ru('\u041e\u0442\u0447\u0435\u0442') })).not.toBeInTheDocument();
  });
});




