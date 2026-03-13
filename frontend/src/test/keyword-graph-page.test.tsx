import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import { createChannelsResponse } from '@test/dashboard-fixtures';
import {
  createKeywordGraphBuildResponse,
  createKeywordGraphReportResponse,
  createKeywordSearchResponse,
} from '@test/dashboard-fixtures';
import { createMemoryTokenStorage, renderAuthHarness } from '@test/auth-harness';

function createAuthenticatedUser(roles: string[]) {
  return {
    id: 31,
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

function renderKeywordGraph(initialEntry: string, roles: string[] = ['analyst']) {
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

describe('Keyword graph page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('enforces RBAC for keyword graph route', async () => {
    renderKeywordGraph('/keyword-graph', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/Route is restricted/i)).toBeInTheDocument();
    });
  });

  it('runs keyword search and renders analytical results', async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new Error(`Unhandled GET path in keyword search test: ${path}`);
    });
    const postSpy = vi.spyOn(apiClient, 'post').mockImplementation(async (path: string, body?: unknown) => {
      if (path === '/api/keyword/search/posts') {
        expect(body).toEqual({
          query: 'policy shift',
          limit: 50,
          date_from: null,
          date_to: null,
          channel_ids: [1],
        });
        return createKeywordSearchResponse();
      }

      throw new Error(`Unhandled POST path in keyword search test: ${path}`);
    });

    renderKeywordGraph('/keyword-graph');

    await waitFor(() => {
      expect(screen.getByText(/Separate analytical tool for keyword-driven post search/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Keyword query/i), 'policy shift');
    await user.click(screen.getByLabelText(/Channel Signal Watch \(@signal_watch\)/i));
    await user.click(screen.getByRole('button', { name: /Search posts/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/api/keyword/search/posts',
        expect.objectContaining({ query: 'policy shift' }),
      );
    });

    expect(screen.getByText(/Matched posts for the analytical query/i)).toBeInTheDocument();
    expect(screen.getByText(/Policy shift discussion spikes/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Select post 4012/i)).toBeInTheDocument();
  });

  it('builds graph and generates a report from selected posts', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new Error(`Unhandled GET path in keyword build/report test: ${path}`);
    });
    vi.spyOn(apiClient, 'post').mockImplementation(async (path: string, body?: unknown) => {
      if (path === '/api/keyword/search/posts') {
        return createKeywordSearchResponse();
      }

      if (path === '/api/keyword/graph/build') {
        expect(body).toEqual({
          post_ids: [4012],
          exclude_post_ids: [],
          graph_mode: 'transient',
          include_neighbors: true,
          neighbor_depth: 1,
        });
        return createKeywordGraphBuildResponse();
      }

      if (path === '/api/keyword/graph/report') {
        expect(body).toEqual({
          title: 'Policy graph report',
          post_ids: [4012],
          exclude_post_ids: [],
          graph_mode: 'transient',
          include_neighbors: true,
          neighbor_depth: 1,
        });
        return createKeywordGraphReportResponse({ title: 'Policy graph report' });
      }

      throw new Error(`Unhandled POST path in keyword build/report test: ${path}`);
    });

    renderKeywordGraph('/keyword-graph?query=policy%20shift');

    await waitFor(() => {
      expect(screen.getByText(/Policy shift discussion spikes/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/Select post 4012/i));
    await user.click(screen.getByRole('button', { name: /Build graph/i }));

    await waitFor(() => {
      expect(screen.getByText(/2 nodes and 1 edges/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Graph report title/i), 'Policy graph report');
    await user.click(screen.getByRole('button', { name: /Generate report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Analytical report content for the keyword graph seed set/i)).toBeInTheDocument();
    });
  });

  it('renders empty search state and inline error state', async () => {
    const user = userEvent.setup();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path === '/api/channels/') {
        return createChannelsResponse();
      }

      throw new Error(`Unhandled GET path in keyword empty state test: ${path}`);
    });
    vi.spyOn(apiClient, 'post').mockImplementation(async (path: string) => {
      if (path === '/api/keyword/search/posts') {
        return createKeywordSearchResponse({ total: 0, items: [] });
      }

      throw new Error(`Unhandled POST path in keyword empty state test: ${path}`);
    });

    renderKeywordGraph('/keyword-graph');

    await waitFor(() => {
      expect(screen.getByText(/Separate analytical tool for keyword-driven post search/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Keyword query/i), 'zz');
    await user.click(screen.getByRole('button', { name: /Search posts/i }));

    await waitFor(() => {
      expect(screen.getByText(/No posts matched the query/i)).toBeInTheDocument();
    });

    cleanup();

    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError('Failed', 500));

    renderKeywordGraph('/keyword-graph?query=policy');

    await waitFor(() => {
      expect(screen.getByText(/Keyword search failed/i)).toBeInTheDocument();
    });
  });

  it('renders feature-unavailable state when backend returns 404 rollout or flag denial', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(createChannelsResponse());
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError('Not found', 404));

    renderKeywordGraph('/keyword-graph?query=policy');

    await waitFor(() => {
      expect(screen.getByText(/Keyword graph is unavailable/i)).toBeInTheDocument();
    });
  });
});
