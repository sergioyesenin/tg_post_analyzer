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

const ru = (value: string) => JSON.parse('"' + value + '"') as string;

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
      expect(screen.getByText(ru('\u041c\u0430\u0440\u0448\u0440\u0443\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d'))).toBeInTheDocument();
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
      expect(screen.getByText(ru('\u041e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u0434\u043b\u044f \u043f\u043e\u0438\u0441\u043a\u0430 \u043f\u043e\u0441\u0442\u043e\u0432 \u043f\u043e \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u043c \u0441\u043b\u043e\u0432\u0430\u043c, \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u044f \u0433\u0440\u0430\u0444\u0430 \u0438 \u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0439 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438 \u043e\u0442\u0447\u0435\u0442\u0430. \u041e\u043d \u043d\u0435 \u0432\u0445\u043e\u0434\u0438\u0442 \u0432 \u043e\u0441\u043d\u043e\u0432\u043d\u044b\u0435 \u0440\u0435\u0436\u0438\u043c\u044b \u0434\u0430\u0448\u0431\u043e\u0440\u0434\u0430.'))).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441 \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u0441\u043b\u043e\u0432')), 'policy shift');
    await user.click(screen.getByLabelText(ru('\u041a\u0430\u043d\u0430\u043b Signal Watch (@signal_watch)')));
    await user.click(screen.getByRole('button', { name: ru('\u041d\u0430\u0439\u0442\u0438 \u043f\u043e\u0441\u0442\u044b') }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/api/keyword/search/posts',
        expect.objectContaining({ query: 'policy shift' }),
      );
    });

    expect(screen.getByText(/\u041d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0435 \u043f\u043e\u0441\u0442\u044b \u0434\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0430/u)).toBeInTheDocument();
    expect(screen.getByText(/Policy shift discussion spikes/i)).toBeInTheDocument();
    expect(screen.getByLabelText(ru('\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u043f\u043e\u0441\u0442 4012'))).toBeInTheDocument();
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

    await user.click(screen.getByLabelText(ru('\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u043f\u043e\u0441\u0442 4012')));
    await user.click(screen.getByRole('button', { name: ru('\u041f\u043e\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0433\u0440\u0430\u0444') }));

    await waitFor(() => {
      expect(screen.getByText(ru('2 \u0443\u0437\u043b\u043e\u0432 \u0438 1 \u0440\u0435\u0431\u0435\u0440'))).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(ru('\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u0430 \u043f\u043e \u0433\u0440\u0430\u0444\u0443')), 'Policy graph report');
    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442\u0447\u0435\u0442') }));

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
      expect(screen.getByText(ru('\u041e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u0434\u043b\u044f \u043f\u043e\u0438\u0441\u043a\u0430 \u043f\u043e\u0441\u0442\u043e\u0432 \u043f\u043e \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u043c \u0441\u043b\u043e\u0432\u0430\u043c, \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u044f \u0433\u0440\u0430\u0444\u0430 \u0438 \u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0439 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438 \u043e\u0442\u0447\u0435\u0442\u0430. \u041e\u043d \u043d\u0435 \u0432\u0445\u043e\u0434\u0438\u0442 \u0432 \u043e\u0441\u043d\u043e\u0432\u043d\u044b\u0435 \u0440\u0435\u0436\u0438\u043c\u044b \u0434\u0430\u0448\u0431\u043e\u0440\u0434\u0430.'))).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(ru('\u0417\u0430\u043f\u0440\u043e\u0441 \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u0441\u043b\u043e\u0432')), 'zz');
    await user.click(screen.getByRole('button', { name: ru('\u041d\u0430\u0439\u0442\u0438 \u043f\u043e\u0441\u0442\u044b') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u041f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e'))).toBeInTheDocument();
    });

    cleanup();

    vi.restoreAllMocks();
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError('Failed', 500));

    renderKeywordGraph('/keyword-graph?query=policy');

    await waitFor(() => {
      expect(screen.getByText(ru('\u041f\u043e\u0438\u0441\u043a \u043f\u043e \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u043c \u0441\u043b\u043e\u0432\u0430\u043c \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0441\u044f \u043e\u0448\u0438\u0431\u043a\u043e\u0439'))).toBeInTheDocument();
    });
  });

  it('renders feature-unavailable state when backend returns 404 rollout or flag denial', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue(createChannelsResponse());
    vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiError('Not found', 404));

    renderKeywordGraph('/keyword-graph?query=policy');

    await waitFor(() => {
      expect(screen.getByText(ru('\u0413\u0440\u0430\u0444 \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u0441\u043b\u043e\u0432 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0443\u0447\u0435\u0442\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u0438 \u0438\u043b\u0438 \u043e\u043a\u0440\u0443\u0436\u0435\u043d\u0438\u044f. Backend feature flag \u0438\u043b\u0438 rollout gate \u0437\u0430\u043f\u0440\u0435\u0442\u0438\u043b \u0437\u0430\u043f\u0440\u043e\u0441.'))).toBeInTheDocument();
    });
  });
});


