import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createCommentsResponse,
  createLinksResponse,
  createPostDetailResponse,
  createPostsDashboardResponse,
  createReportResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

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

describe('Posts dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('parses query params into API request URL', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());

    renderPostsDashboard(
      '/dashboard/posts?date_from=2026-03-01&date_to=2026-03-10&channel_ids=7&categories=media&report_status=ready&sort_by=views&sort_order=asc',
    );

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        '/api/dashboard/posts?date_from=2026-03-01&date_to=2026-03-10&channel_ids=7&categories=media&report_status=ready&sort_by=views&sort_order=asc',
      );
    });
  });

  it('renders posts dashboard data, summary cards, and report status badges', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Dense list from \/api\/dashboard\/posts items/i)).toBeInTheDocument();
    });

    expect(screen.getByText('537')).toBeInTheDocument();
    expect(screen.getByText(/Signal Watch/i)).toBeInTheDocument();
    expect(screen.getByText(/media/i)).toBeInTheDocument();
    expect(screen.getByText(/Top post preview for posts dashboard rendering/i)).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('renders loading state while snapshot request is pending', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(() => new Promise(() => undefined) as never);

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Loading posts dashboard/i)).toBeInTheDocument();
    });
  });

  it('renders empty state for successful response without items', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(
      createPostsDashboardResponse({
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
    );

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/No posts match the current filters/i)).toBeInTheDocument();
    });
  });

  it('renders error state for failed requests', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce(new ApiError('Failed', 500));

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Posts dashboard failed to load/i)).toBeInTheDocument();
    });
  });

  it('renders forbidden state for 403 response', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce(new ApiError('Forbidden', 403));

    renderPostsDashboard('/dashboard/posts?limit=10');

    await waitFor(() => {
      expect(screen.getByText(/Posts dashboard is not available for this role/i)).toBeInTheDocument();
    });
  });

  it('renders partial state and warnings banner without treating snapshot as hard error', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(
      createPostsDashboardResponse({
        partial: true,
        warnings: [
          {
            code: 'posts.comments.pending',
            message: 'Comments enrichment is incomplete, but the list remains usable.',
            severity: 'warning',
          },
        ],
      }),
    );

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Snapshot includes non-blocking warnings/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Comments enrichment is incomplete/i)).toBeInTheDocument();
    expect(screen.getByText(/Screen stays usable with partially enriched data/i)).toBeInTheDocument();
  });

  it('navigates to post detail entry point from table actions', async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/dashboard/posts')) {
        return createPostsDashboardResponse();
      }

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
    });

    renderPostsDashboard();

    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: 'Open post' })[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('link', { name: 'Open post' })[0]);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Post #4012/i })).toBeInTheDocument();
    });
  });

  it('hides mutation entry points for viewer while keeping detail navigation', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(createPostsDashboardResponse());

    renderPostsDashboard('/dashboard/posts', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Viewer access hides mutation entry points/i)).toBeInTheDocument();
    });

    expect(screen.getAllByRole('link', { name: 'Open post' })).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Comments' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Report' })).not.toBeInTheDocument();
  });
});
