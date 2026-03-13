import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createEventDetailResponse,
  createEventGraphResponse,
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

function renderEventDetail(initialEntry = '/events/81', roles: string[] = ['analyst']) {
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

describe('Event detail', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state before the detail payload resolves', async () => {
    let resolveDetail: ((value: ReturnType<typeof createEventDetailResponse>) => void) | undefined;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/events/81') {
        return await new Promise<ReturnType<typeof createEventDetailResponse>>((resolve) => {
          resolveDetail = resolve;
        });
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse();
      }

      throw new Error(`Unhandled GET path in event detail loading test: ${path}`);
    });

    renderEventDetail();

    await waitFor(() => {
      expect(screen.getByText(/Loading event detail/i)).toBeInTheDocument();
    });

    resolveDetail?.(createEventDetailResponse());

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Election coverage spike/i })).toBeInTheDocument();
    });
  });

  it('renders event not found state when the main detail request returns 404', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/events/81') {
        throw new ApiError('Not found', 404);
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse();
      }

      throw new Error(`Unhandled GET path in event detail 404 test: ${path}`);
    });

    renderEventDetail();

    await waitFor(() => {
      expect(screen.getByText(/Event not found/i)).toBeInTheDocument();
    });
  });

  it('reuses the dashboard graph endpoint for graph and report context', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/events/81') {
        return createEventDetailResponse();
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse();
      }

      throw new Error(`Unhandled GET path in graph integration test: ${path}`);
    });
    renderEventDetail();

    await waitFor(() => {
      expect(screen.getAllByText(/Root post drives the event graph/i).length).toBeGreaterThan(0);
    });

    expect(getSpy).toHaveBeenCalledWith('/api/events/81');
    expect(getSpy).toHaveBeenCalledWith('/api/dashboard/events/81/graph');
    expect(screen.getAllByText(/Draft/i).length).toBeGreaterThan(0);
  });

  it('navigates back to events dashboard from direct event detail entry', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/events/81') {
        return createEventDetailResponse();
      }

      if (path === '/api/dashboard/events/81/graph') {
        return createEventGraphResponse();
      }

      if (path === '/api/dashboard/events') {
        return {
          mode: 'events',
          generated_at: '2026-03-13T08:45:00Z',
          partial: false,
          warnings: [],
          filters_applied: {
            date_from: null,
            date_to: null,
            limit: 25,
            status: [],
            channel_ids: [],
            categories: [],
            min_comments: null,
            sort_by: 'started_at',
            sort_order: 'desc',
          },
          summary: {
            events_count: 1,
            total_linked_posts: 3,
            total_comments: 310,
            avg_involvement: 0.57,
            draft_reports: 1,
            ready_reports: 0,
            failed_reports: 0,
          },
          items: [
            {
              event_id: 81,
              title: 'Election coverage spike',
              status: 'active',
              started_at: '2026-03-12T06:30:00Z',
              ended_at: null,
              confidence: 0.88,
              comments_count: 310,
              involvement: 0.57,
              posts_count: 3,
              post_ids: [4012, 3975, 3980],
              root_post_id: 4012,
              channels: [{ channel_id: 77, channel_username: 'signal_watch' }],
              report_status: 'draft',
              graph_ready: true,
            },
          ],
          meta: {
            sort: { by: 'started_at', order: 'desc' },
            supported_sorts: ['started_at', 'comments_count', 'involvement', 'posts_count'],
          },
        };
      }

      throw new Error(`Unhandled GET path in event detail back navigation test: ${path}`);
    });

    renderEventDetail();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Election coverage spike/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^Back$/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Events workspace/i })).toBeInTheDocument();
    });
  });
});
