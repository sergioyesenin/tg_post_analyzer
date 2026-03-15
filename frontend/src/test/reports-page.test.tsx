import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient } from '@shared/api/client';
import {
  createAcceptedJobResponse,
  createEventReportsListResponse,
  createJobResultResponse,
  createJobStatusResponse,
  createPostReportsListResponse,
  createProcessReportsListResponse,
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

function renderReports(initialEntry = '/reports/posts', roles: string[] = ['analyst']) {
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

describe('Reports page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders reports list tables for posts, events, and processes', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        return createPostReportsListResponse();
      }

      if (path.startsWith('/api/reports/events/list')) {
        return createEventReportsListResponse();
      }

      if (path.startsWith('/api/reports/processes/list')) {
        return createProcessReportsListResponse();
      }

      throw new Error(`Unhandled GET path in reports rendering test: ${path}`);
    });

    const user = userEvent.setup();
    renderReports('/reports/posts');

    await waitFor(() => {
      expect(screen.getByText(ru('\u041f\u043e\u0441\u0442 #4012'), { exact: false })).toBeInTheDocument();
    });

    expect(screen.getAllByRole('link', { name: ru('\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0441\u0442') }).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('link', { name: ru('\u0421\u043e\u0431\u044b\u0442\u0438\u044f') }));

    await waitFor(() => {
      expect(screen.getByText(/Election coverage spike/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('link', { name: ru('\u041f\u0440\u043e\u0446\u0435\u0441\u0441\u044b') }));

    await waitFor(() => {
      expect(screen.getByText(/Narrative escalation chain/i)).toBeInTheDocument();
    });
  });

  it('shows export actions to viewer while hiding batch generation controls', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        return createPostReportsListResponse();
      }

      throw new Error(`Unhandled GET path in reports role test: ${path}`);
    });

    renderReports('/reports/posts?channel_ids=77&limit=25', ['viewer']);

    await waitFor(() => {
      expect(screen.getByText(/\u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0447\u0442\u0435\u043d\u0438\u044f/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: ru('\u042d\u043a\u0441\u043f\u043e\u0440\u0442 CSV') })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/reports/posts/export?channel_ids=77&limit=25&offset=0&format=csv'),
    );
    expect(screen.getByRole('link', { name: ru('\u042d\u043a\u0441\u043f\u043e\u0440\u0442 JSON') })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u043e \u0444\u0438\u043b\u044c\u0442\u0440\u0443') })).not.toBeInTheDocument();
  });

  it('runs batch report generation flow for post reports and refreshes the list', async () => {
    const user = userEvent.setup();
    let postsVersion = 0;

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/posts/list')) {
        postsVersion += 1;
        return createPostReportsListResponse(
          postsVersion > 1
            ? [
                {
                  ...createPostReportsListResponse()[0],
                  status: 'draft',
                },
              ]
            : createPostReportsListResponse(),
        );
      }

      if (path === '/api/jobs/501') {
        return createJobStatusResponse({ type: 'build_post_report_batch', status: 'done' });
      }

      if (path === '/api/jobs/501/result') {
        return createJobResultResponse({ status: 'done', report_id: 601, post_id: 4012 });
      }

      throw new Error(`Unhandled GET path in reports batch test: ${path}`);
    });

    vi.spyOn(apiClient, 'post').mockResolvedValue(
      createAcceptedJobResponse({ job_id: 501, job_type: 'build_post_report_batch' }),
    );

    renderReports('/reports/posts?channel_ids=77&categories=media&min_comments=5&limit=25');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u043e \u0444\u0438\u043b\u044c\u0442\u0440\u0443') })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: ru('\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u043e \u0444\u0438\u043b\u044c\u0442\u0440\u0443') }));

    await waitFor(() => {
      expect(screen.getByText(ru('\u041f\u0430\u043a\u0435\u0442\u043d\u043e\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u043e\u0432'))).toBeInTheDocument();
      expect(screen.getByText(/report_id: 601/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText(ru('\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a')).length).toBeGreaterThan(0);
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/reports/posts/generate-by-filter?channel_ids=77&categories=media&min_comments=5&limit=25&offset=0',
    );
  });

  it('renders empty and error states for reports catalogs', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/events/list')) {
        return [];
      }

      throw new Error(`Unhandled GET path in reports empty test: ${path}`);
    });

    renderReports('/reports/events');

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435\u0442 \u043e\u0442\u0447\u0435\u0442\u043e\u0432 \u043f\u043e \u0441\u043e\u0431\u044b\u0442\u0438\u044f\u043c \u0434\u043b\u044f \u0442\u0435\u043a\u0443\u0449\u0438\u0445 \u0444\u0438\u043b\u044c\u0442\u0440\u043e\u0432'))).toBeInTheDocument();
    });

    vi.restoreAllMocks();

    vi.spyOn(apiClient, 'get').mockImplementation(async (path: string) => {
      if (path.startsWith('/api/reports/processes/list')) {
        throw new ApiError('Failed', 500);
      }

      throw new Error(`Unhandled GET path in reports error test: ${path}`);
    });

    renderReports('/reports/processes');

    await waitFor(() => {
      expect(screen.getByText(ru('\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u043a\u0430\u0442\u0430\u043b\u043e\u0433 \u043e\u0442\u0447\u0435\u0442\u043e\u0432'))).toBeInTheDocument();
    });
  });
});
